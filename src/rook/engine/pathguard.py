"""The diff path guard (03_SECURITY_ACCESS.md section 4): what a Surgeon call may change, decided by code.

The Surgeon's mode already limits its edit tool to a per-call `fileRegex` (agents/registry.py). This
guard is the second, deterministic check, and it does not trust the first:

1. `snapshot()` records every entry of the workspace (walked without following symlinks) right before
   the call: its kind, mode and stat signature, and for regular files a sha256 and a backup copy
   (kept in a private temp dir, outside the workspace).
2. `enforce(snapshot, allowed)` compares the workspace with it right after the call. Every added,
   modified or deleted path that is not exactly one of the allowed paths is REVERTED (an added entry
   is removed, a modified or deleted one is restored from the backup), and the change is reported
   with a reason. A symlink anywhere, a change to an allowed path that is not a plain file edit (a
   delete, a directory, a symlink), a change under `.git/`, `.bob/` or `rook/`, and a lookalike of an
   allowed path (same name after NFKC normalisation and case folding) are always violations.
3. The workspace is then compared with the snapshot again: anything still different outside the
   allowed paths raises `PathGuardError` (the workspace could not be restored; the run must stop).

Allowed paths match byte for byte only. NFKC + casefold is used to *catch* tricks (".GIT", a
full-width "ｒook", a lookalike of `app.py`), never to widen what is allowed.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import shutil
import stat
import tempfile
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

from rook.agents.registry import surgeon_edit_regex

Kind = Literal["file", "dir", "link", "other"]
ChangeKind = Literal["added", "modified", "deleted"]

# Top-level folders the Surgeon may never change: git internals, Bob's modes, Rook's own output.
PROTECTED_TOP = frozenset({".git", ".bob", "rook", ".rook", ".rook-sandbox"})
# Folders whose files are only stat-checked (no backup): huge and never part of a fix. A change there
# cannot be restored and raises PathGuardError.
NO_BACKUP_DIRS = frozenset({"node_modules", ".venv", "venv", ".tox", ".next", ".mypy_cache", ".ruff_cache"})
FILE_BACKUP_MAX = 5 * 1024 * 1024
TOTAL_BACKUP_MAX = 512 * 1024 * 1024
DIFF_MAX_CHARS = 40_000
_CHUNK = 1024 * 1024


class PathGuardError(RuntimeError):
    """The workspace could not be restored to its pre-call state outside the allowed paths."""


def fold(path: str) -> str:
    """The comparison form used to catch lookalikes: NFKC-normalised and case-folded."""
    return unicodedata.normalize("NFKC", path).casefold()


def _protected(path: str) -> bool:
    top = fold(path).split("/", 1)[0].rstrip(". ")
    return top in PROTECTED_TOP


def check_allowed_paths(workspace: Path, paths: Iterable[str]) -> list[str]:
    """Validate the paths a Surgeon call may change and return them sorted.

    Each must pass the mode regex's own check (relative, normalised, no `.git`/`.bob`, no control
    chars), be NFKC-normalised already, lie outside the protected folders, and no existing component
    of it may be a symlink or a non-directory parent (so an edit can never be redirected elsewhere).
    """
    out = sorted(set(paths))
    surgeon_edit_regex(out)  # raises ValueError on any unsafe path
    root = workspace.resolve()
    for path in out:
        if unicodedata.normalize("NFKC", path) != path:
            raise ValueError(f"surgeon path is not NFKC-normalised: {path!r}")
        if _protected(path):
            raise ValueError(f"surgeon may never edit {path.split('/', 1)[0]}/: {path!r}")
        current = root
        parts = PurePosixPath(path).parts
        for index, part in enumerate(parts):
            current = current / part
            try:
                mode = os.lstat(current).st_mode
            except FileNotFoundError:
                break  # the rest does not exist yet (a new test file)
            if stat.S_ISLNK(mode):
                raise ValueError(f"surgeon path goes through a symlink: {path!r}")
            last = index == len(parts) - 1
            if not last and not stat.S_ISDIR(mode):
                raise ValueError(f"surgeon path has a non-directory parent: {path!r}")
            if last and not stat.S_ISREG(mode):
                raise ValueError(f"surgeon path is not a regular file: {path!r}")
    folded = [fold(p) for p in out]
    if len(set(folded)) != len(folded):
        raise ValueError(f"surgeon paths differ only by case or Unicode form: {out!r}")
    return out


@dataclass(frozen=True)
class Entry:
    kind: Kind
    mode: int
    size: int
    mtime_ns: int
    ino: int
    digest: str | None = None  # sha256 of a regular file that has a backup
    target: str | None = None  # a symlink's target


@dataclass
class Snapshot:
    root: Path
    entries: dict[str, Entry]
    store: Path  # content-addressed backups: <store>/<sha256>

    def backup(self, digest: str) -> Path:
        return self.store / digest

    def close(self) -> None:
        shutil.rmtree(self.store, ignore_errors=True)


@dataclass(frozen=True)
class Change:
    path: str
    kind: ChangeKind
    allowed: bool
    reason: str  # why it is not allowed ("" when allowed)


@dataclass
class GuardReport:
    changes: list[Change] = field(default_factory=list)
    reverted: list[str] = field(default_factory=list)

    @property
    def violations(self) -> list[Change]:
        return [c for c in self.changes if not c.allowed]

    @property
    def allowed(self) -> list[Change]:
        return [c for c in self.changes if c.allowed]

    @property
    def ok(self) -> bool:
        return not self.violations

    def reason(self) -> str:
        return "; ".join(f"{c.path} ({c.kind}): {c.reason}" for c in self.violations)


def _entry(path: Path, st: os.stat_result) -> Entry:
    mode = st.st_mode
    if stat.S_ISLNK(mode):
        return Entry("link", mode, st.st_size, st.st_mtime_ns, st.st_ino, target=os.readlink(path))
    kind: Kind = "file" if stat.S_ISREG(mode) else "dir" if stat.S_ISDIR(mode) else "other"
    return Entry(kind, mode, st.st_size if kind == "file" else 0, st.st_mtime_ns if kind == "file" else 0,
                 st.st_ino)


def _hash(path: Path, copy_to: Path | None) -> str:
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as src:
        chunks = []
        while chunk := src.read(_CHUNK):
            digest.update(chunk)
            if copy_to is not None:
                chunks.append(chunk)
    name = digest.hexdigest()
    if copy_to is not None:
        target = copy_to / name
        if not target.exists():
            tmp = copy_to / f".{name}.tmp"
            tmp.write_bytes(b"".join(chunks))
            os.replace(tmp, target)
    return name


def _walk(root: Path) -> Iterable[tuple[str, Path, os.stat_result, bool]]:
    """(relative path, path, lstat, backed_up_area) for every entry below root; never follows links."""
    stack: list[tuple[Path, str, bool]] = [(root, "", True)]
    while stack:
        directory, prefix, backup = stack.pop()
        with os.scandir(directory) as it:
            items = sorted(it, key=lambda e: e.name)
        for item in items:
            rel = f"{prefix}{item.name}"
            st = item.stat(follow_symlinks=False)
            area = backup and item.name not in NO_BACKUP_DIRS
            yield rel, Path(item.path), st, area
            if stat.S_ISDIR(st.st_mode):
                stack.append((Path(item.path), rel + "/", area))


class PathGuard:
    def __init__(self, workspace: str | os.PathLike[str]) -> None:
        self.root = Path(workspace).resolve()
        if not self.root.is_dir():
            raise ValueError(f"workspace is not a folder: {workspace}")

    # --- snapshots ---

    def snapshot(self) -> Snapshot:
        store = Path(tempfile.mkdtemp(prefix="rook-guard-"))
        entries: dict[str, Entry] = {}
        total = 0
        try:
            for rel, path, st, area in _walk(self.root):
                entry = _entry(path, st)
                if entry.kind == "file":
                    backup = area and st.st_size <= FILE_BACKUP_MAX and total + st.st_size <= TOTAL_BACKUP_MAX
                    if backup:
                        total += st.st_size
                        entry = Entry("file", entry.mode, entry.size, entry.mtime_ns, entry.ino,
                                      digest=_hash(path, store))
                entries[rel] = entry
        except BaseException:
            shutil.rmtree(store, ignore_errors=True)
            raise
        return Snapshot(self.root, entries, store)

    def _current(self) -> dict[str, tuple[Path, os.stat_result]]:
        return {rel: (path, st) for rel, path, st, _ in _walk(self.root)}

    def changes(self, snap: Snapshot) -> list[tuple[str, ChangeKind]]:
        """Every path added, modified or deleted since `snap`, sorted."""
        now = self._current()
        out: list[tuple[str, ChangeKind]] = []
        for rel, (path, st) in now.items():
            before = snap.entries.get(rel)
            if before is None:
                out.append((rel, "added"))
            elif self._differs(before, path, st):
                out.append((rel, "modified"))
        out += [(rel, "deleted") for rel in snap.entries if rel not in now]
        return sorted(out)

    @staticmethod
    def _differs(before: Entry, path: Path, st: os.stat_result) -> bool:
        after = _entry(path, st)
        if after.kind != before.kind or stat.S_IMODE(after.mode) != stat.S_IMODE(before.mode):
            return True
        if after.kind == "link":
            return after.target != before.target
        if after.kind != "file":
            return False
        if (after.size, after.mtime_ns, after.ino) == (before.size, before.mtime_ns, before.ino):
            return False
        if before.digest is None:
            return True
        return after.size != before.size or _hash(path, None) != before.digest

    # --- the check ---

    def classify(self, snap: Snapshot, allowed: Iterable[str]) -> list[Change]:
        allowed_set = set(allowed)
        folded = {fold(a): a for a in allowed_set}
        out: list[Change] = []
        for rel, kind in self.changes(snap):
            path = self.root / rel
            reason = ""
            if os.path.islink(path) and kind != "deleted":
                reason = "symlinks may not be created or changed"
            elif rel in allowed_set:
                if kind == "deleted":
                    reason = "an allowed file may be edited, not deleted"
                elif not stat.S_ISREG(os.lstat(path).st_mode):
                    reason = "an allowed path must stay a regular file"
            elif _protected(rel):
                reason = f"{rel.split('/', 1)[0]}/ may never be changed by the Surgeon"
            elif fold(rel) in folded:
                reason = f"looks like the allowed path {folded[fold(rel)]!r} but is a different path"
            elif any(a.startswith(rel + "/") for a in allowed_set) and kind == "added":
                continue  # a new parent folder of an allowed new file (e.g. tests/)
            else:
                reason = "not in the allowed paths"
            out.append(Change(rel, kind, not reason, reason))
        return out

    def enforce(self, snap: Snapshot, allowed: Iterable[str]) -> GuardReport:
        """Revert every change outside `allowed` and report all changes. Raises PathGuardError if the
        workspace cannot be brought back to `snap` outside the allowed paths."""
        allowed_list = list(allowed)
        changes = self.classify(snap, allowed_list)
        bad = [c.path for c in changes if not c.allowed]
        self.restore(snap, bad)
        kept = {c.path for c in changes if c.allowed}
        parents = {p for a in kept for p in _parents(a)}
        left = [rel for rel, _ in self.changes(snap) if rel not in kept and rel not in parents]
        if left:
            raise PathGuardError(f"could not restore: {', '.join(left[:10])}")
        return GuardReport(changes=changes, reverted=bad)

    # --- restoring ---

    def restore(self, snap: Snapshot, paths: Iterable[str] | None = None) -> list[str]:
        """Bring `paths` (default: every changed path) back to their state in `snap`."""
        wanted = [rel for rel, _ in self.changes(snap)] if paths is None else list(paths)
        for rel in wanted:
            before = snap.entries.get(rel)
            if before is not None and before.kind not in ("dir", "link") and before.digest is None:
                raise PathGuardError(f"cannot restore {rel}: no backup was kept")
        # Remove what should not be there (deepest first), then restore what should (shallowest first).
        for rel in sorted(wanted, key=lambda r: r.count("/"), reverse=True):
            before = snap.entries.get(rel)
            path = self.root / rel
            if not os.path.lexists(path):
                continue
            st = os.lstat(path)
            if before is not None and before.kind == "dir" and stat.S_ISDIR(st.st_mode):
                os.chmod(path, stat.S_IMODE(before.mode))  # a folder that only changed its mode
            elif before is None or self._differs(before, path, st):
                self._remove(path)
        for rel in sorted(wanted, key=lambda r: r.count("/")):
            before = snap.entries.get(rel)
            if before is not None and not os.path.lexists(self.root / rel):
                self._recreate(snap, rel, before)
        return wanted

    def _remove(self, path: Path) -> None:
        if not path.is_symlink() and path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    def _ensure_parents(self, rel: str) -> Path:
        current = self.root
        for part in PurePosixPath(rel).parts[:-1]:
            current = current / part
            if os.path.islink(current) or (os.path.lexists(current) and not current.is_dir()):
                raise PathGuardError(f"cannot restore {rel}: {current.relative_to(self.root)} is not a folder")
            if not os.path.lexists(current):
                os.mkdir(current)
        return current

    def _recreate(self, snap: Snapshot, rel: str, before: Entry) -> None:
        parent = self._ensure_parents(rel)
        path = parent / PurePosixPath(rel).name
        if before.kind == "dir":
            os.mkdir(path)
            os.chmod(path, stat.S_IMODE(before.mode))
        elif before.kind == "link":
            assert before.target is not None
            os.symlink(before.target, path)
        elif before.kind == "file" and before.digest is not None:
            tmp = parent / f".rook-restore-{os.getpid()}.tmp"
            shutil.copyfile(snap.backup(before.digest), tmp)
            os.chmod(tmp, stat.S_IMODE(before.mode))
            os.replace(tmp, path)
        else:
            raise PathGuardError(f"cannot restore {rel}: it was a special file or had no backup")

    # --- the diff shown to the Fix Reviewer ---

    def diff(self, snap: Snapshot, paths: Iterable[str], limit: int = DIFF_MAX_CHARS) -> str:
        parts: list[str] = []
        for rel in sorted(paths):
            before = snap.entries.get(rel)
            old = _read_text(snap.backup(before.digest)) if before and before.digest else []
            path = self.root / rel
            new = _read_text(path) if os.path.lexists(path) and not os.path.islink(path) else []
            parts.extend(difflib.unified_diff(
                old, new, fromfile=f"a/{rel}" if before else "/dev/null", tofile=f"b/{rel}"))
        text = "".join(line if line.endswith("\n") else line + "\n" for line in parts)
        if len(text) > limit:
            text = text[:limit] + f"\n[diff truncated by Rook at {limit} characters]\n"
        return text


def _parents(rel: str) -> list[str]:
    parts = PurePosixPath(rel).parts
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def _read_text(path: Path) -> list[str]:
    return path.read_bytes().decode("utf-8", errors="replace").splitlines(keepends=True)
