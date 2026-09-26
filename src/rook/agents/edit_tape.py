"""Record and replay the workspace edits of an edit-capable Bob call (the Surgeon).

A recording (`agents/recorder.py`) holds only Bob's NDJSON stream, so replaying a Surgeon call would
not change any file. The edit tape closes that gap: in record mode, the files the call changed are
saved next to its stream as `<key>.edits.json` (`{"format": 1, "files": {path: text | null},
"withheld": {path: kind}}`, null = deleted); in replay mode they are written back into the workspace
before the path guard runs, so a replayed run goes through the same guard, review and verification as
the live one. The tape is written only after the path guard: `files` holds the changes it allowed,
and `withheld` only the paths of the changes it rejected (their content is never taped; replay writes
PLACEHOLDER there, or deletes the path, so the replayed guard rejects the round again).

Only regular text files are taped. Paths are checked (relative, normalised, no symlink on the way:
every folder is opened relative to its parent with O_NOFOLLOW) before anything is written. The text is
taped verbatim, because heuristic redaction would change code (e.g. "bearer token" in a message) and the
replay would then differ from the live run; a file holding a registered secret value is never taped.
"""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from rook.core.events import has_known_secret

FORMAT = 1
MAX_FILE_BYTES = 1_000_000
PLACEHOLDER = "[a change the path guard rejected; its content was not taped]\n"
TapeMode = Literal["record", "replay"]


class EditTapeError(ValueError):
    pass


def tape_mode(client: Any) -> TapeMode | None:
    """`record`/`replay` for a BobClient that records or replays; None otherwise (live or a fake)."""
    if getattr(client, "mode", None) == "replay":
        return "replay"
    if getattr(client, "record", False):
        return "record"
    return None


def tape_path(client: Any, key: str) -> Path:
    return Path(client.recorder.dir) / f"{key}.edits.json"


def _parts(rel: str) -> list[str]:
    path = PurePosixPath(rel)
    if not rel or path.is_absolute() or "\\" in rel or "\x00" in rel or str(path) != rel:
        raise EditTapeError(f"refused taped path {rel!r}")
    if any(p in ("", ".", "..") for p in path.parts):
        raise EditTapeError(f"refused taped path {rel!r}")
    return list(path.parts)


def save(path: Path, root: Path, allowed: dict[str, str], withheld: dict[str, str] | None = None) -> Path:
    """Tape a Surgeon call. `allowed` (path -> "added"|"modified"|"deleted") must hold ONLY the changes
    the path guard approved: their current content under `root` is taped verbatim. `withheld` is the
    guard-rejected changes: only their path and kind are taped, never their content."""
    files: dict[str, str | None] = {}
    for rel, kind in sorted(allowed.items()):
        target = root / rel
        if kind == "deleted":
            files[rel] = None
        elif target.is_file() and not target.is_symlink() and target.stat().st_size <= MAX_FILE_BYTES:
            text = target.read_bytes().decode("utf-8", errors="replace")
            if has_known_secret(text):
                raise EditTapeError(f"refusing to tape {rel}: it contains a registered secret value")
            files[rel] = text
    data: dict[str, Any] = {"format": FORMAT, "files": files}
    if withheld:
        data["withheld"] = dict(sorted(withheld.items()))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def load(path: Path) -> dict[str, str | None]:
    """The edits to replay (path -> text, None = delete), or {} when the call made no edits (no tape).
    Withheld (guard-rejected) paths come back as PLACEHOLDER text, or None if they were deleted."""
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    files, withheld = data.get("files"), data.get("withheld", {})
    if data.get("format") != FORMAT or not isinstance(files, dict) or not isinstance(withheld, dict):
        raise EditTapeError(f"unsupported edit tape {path.name}")
    if not all(isinstance(k, str) and (v is None or isinstance(v, str)) for k, v in files.items()) or \
            not all(isinstance(k, str) and v in ("added", "modified", "deleted") for k, v in withheld.items()):
        raise EditTapeError(f"malformed edit tape {path.name}")
    return {**{rel: None if kind == "deleted" else PLACEHOLDER for rel, kind in withheld.items()}, **files}


def apply(root: Path, files: dict[str, str | None]) -> None:
    """Write the taped files into `root` without following any symlink."""
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    for rel, text in sorted(files.items()):
        parts = _parts(rel)
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            for part in parts[:-1]:
                if text is not None:
                    try:
                        os.mkdir(part, 0o755, dir_fd=fd)
                    except FileExistsError:
                        pass
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | nofollow, dir_fd=fd)
                except OSError as exc:
                    raise EditTapeError(f"taped path {rel!r} is not below plain folders: {exc}") from exc
                os.close(fd)
                fd = child
            if text is None:
                try:
                    os.unlink(parts[-1], dir_fd=fd)
                except FileNotFoundError:
                    pass
                continue
            file_fd = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_TRUNC | nofollow, 0o644, dir_fd=fd)
        finally:
            os.close(fd)
        with os.fdopen(file_fd, "w", encoding="utf-8") as fh:
            fh.write(text)
