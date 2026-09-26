"""ROOK-021: the diff path guard reverts every change outside the allowed paths (03 section 4)."""

import os
import re
from pathlib import Path

import pytest

from rook.agents.registry import surgeon_edit_regex
from rook.engine.pathguard import (
    NO_BACKUP_DIRS,
    PathGuard,
    PathGuardError,
    Snapshot,
    check_allowed_paths,
    fold,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    _write(root / "app.py", "def refund():\n    return 0\n")
    _write(root / "other.py", "X = 1\n")
    _write(root / "pkg" / "mod.py", "Y = 2\n")
    _write(root / ".git" / "config", "[core]\n")
    _write(root / ".git" / "hooks" / "pre-commit.sample", "#!/bin/sh\n")
    _write(root / "rook" / "rook.yaml", "version: 1\n")
    _write(root / ".bob" / "custom_modes.yaml", "customModes: []\n")
    (root / "empty").mkdir()
    return root


def tree(root: Path) -> dict[str, str | None]:
    """Every entry below root: file text, 'link -> target' or None for folders."""
    out: dict[str, str | None] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                out[rel] = f"link -> {os.readlink(path)}"
            elif path.is_dir():
                out[rel] = None
            else:
                out[rel] = path.read_text(errors="replace")
    return out


def guarded(ws: Path) -> tuple[PathGuard, Snapshot, dict[str, str | None]]:
    guard = PathGuard(ws)
    return guard, guard.snapshot(), tree(ws)


def test_an_allowed_edit_is_kept_and_nothing_is_reported(ws: Path) -> None:
    guard, snap, _ = guarded(ws)
    (ws / "app.py").write_text("def refund():\n    return 1\n")
    report = guard.enforce(snap, ["app.py"])
    assert report.ok and [c.path for c in report.allowed] == ["app.py"] and report.reverted == []
    assert (ws / "app.py").read_text().endswith("return 1\n")
    diff = guard.diff(snap, ["app.py"])
    assert "--- a/app.py" in diff and "-    return 0" in diff and "+    return 1" in diff
    snap.close()


def test_an_edit_outside_the_allowlist_is_reverted(ws: Path) -> None:
    guard, snap, before = guarded(ws)
    (ws / "app.py").write_text("patched\n")
    (ws / "other.py").write_text("X = 2  # sneaky\n")
    report = guard.enforce(snap, ["app.py"])
    assert not report.ok
    (bad,) = report.violations
    assert (bad.path, bad.kind, bad.reason) == ("other.py", "modified", "not in the allowed paths")
    assert report.reverted == ["other.py"]
    assert tree(ws) == {**before, "app.py": "patched\n"}  # only the allowed edit survives


def test_a_new_file_outside_is_removed_and_a_deleted_one_restored(ws: Path) -> None:
    guard, snap, before = guarded(ws)
    _write(ws / "evil" / "deep" / "x.py", "boom\n")
    (ws / "pkg" / "mod.py").unlink()
    (ws / "empty").rmdir()
    report = guard.enforce(snap, ["app.py"])
    kinds = {c.path: c.kind for c in report.violations}
    assert kinds == {"evil": "added", "evil/deep": "added", "evil/deep/x.py": "added",
                     "pkg/mod.py": "deleted", "empty": "deleted"}
    assert tree(ws) == before


def test_a_symlink_created_by_bob_is_removed_even_at_an_allowed_path(ws: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.txt"
    outside.write_text("secret\n")
    guard, snap, before = guarded(ws)
    (ws / "leak.py").symlink_to(outside)
    (ws / "linkdir").symlink_to(tmp_path, target_is_directory=True)
    (ws / "app.py").unlink()
    (ws / "app.py").symlink_to(outside)
    report = guard.enforce(snap, ["app.py"])
    reasons = {c.path: c.reason for c in report.violations}
    assert set(reasons) == {"leak.py", "linkdir", "app.py"}
    assert all("symlink" in r for r in reasons.values())
    assert tree(ws) == before and outside.read_text() == "secret\n"


def test_changes_under_git_bob_and_rook_are_reverted(ws: Path) -> None:
    guard, snap, before = guarded(ws)
    (ws / ".git" / "config").write_text("[core]\n\thooksPath = /tmp/x\n")
    _write(ws / ".git" / "hooks" / "post-checkout", "#!/bin/sh\nrm -rf /\n")
    (ws / ".bob" / "custom_modes.yaml").write_text("customModes: [evil]\n")
    _write(ws / "rook" / "tests" / "test_rook_cx_001.py", "def test(): pass\n")
    (ws / "rook" / "rook.yaml").unlink()
    report = guard.enforce(snap, ["app.py"])
    assert report.violations and all("may never be changed" in c.reason for c in report.violations)
    assert tree(ws) == before


@pytest.mark.parametrize("trick", ["App.py", "APP.PY", "\uff41pp.py", "app.\uff50\uff59"])
def test_case_and_unicode_lookalikes_of_an_allowed_path_are_reverted(ws: Path, trick: str) -> None:
    guard, snap, before = guarded(ws)
    try:
        (ws / trick).write_text("shadow\n")
    except OSError:
        pytest.skip("the filesystem refuses this name")
    if fold(trick) != fold("app.py"):
        pytest.skip("not a lookalike under NFKC + casefold")
    if (ws / "app.py").read_text() == "shadow\n":
        pytest.skip("case-insensitive filesystem: the same file")
    report = guard.enforce(snap, ["app.py"])
    (bad,) = report.violations
    assert bad.path == trick and "looks like the allowed path 'app.py'" in bad.reason
    assert tree(ws) == before


@pytest.mark.parametrize("name", [".GIT/config", ".Git/hooks/x", "ＲＯＯＫ/x.py", "Rook/tests/t.py", ".bob./x"])
def test_folded_spellings_of_protected_folders_are_protected(ws: Path, name: str) -> None:
    guard, snap, before = guarded(ws)
    try:
        _write(ws / name, "x\n")
    except OSError:
        pytest.skip("the filesystem refuses this name")
    report = guard.enforce(snap, ["app.py"])
    assert report.violations and all("may never be changed" in c.reason for c in report.violations)
    assert tree(ws) == before


def test_a_new_allowed_file_may_create_its_folder(ws: Path) -> None:
    guard, snap, _ = guarded(ws)
    _write(ws / "tests" / "test_rook_cx_001.py", "def test_x():\n    assert False\n")
    report = guard.enforce(snap, ["tests/test_rook_cx_001.py"])
    assert report.ok and [c.path for c in report.allowed] == ["tests/test_rook_cx_001.py"]
    assert "+++ b/tests/test_rook_cx_001.py" in guard.diff(snap, ["tests/test_rook_cx_001.py"])
    guard.restore(snap)  # a rejected round removes it and its folder
    assert not (ws / "tests").exists()


def test_deleting_an_allowed_file_is_a_violation(ws: Path) -> None:
    guard, snap, before = guarded(ws)
    (ws / "app.py").unlink()
    report = guard.enforce(snap, ["app.py"])
    assert [c.reason for c in report.violations] == ["an allowed file may be edited, not deleted"]
    assert tree(ws) == before


def test_restore_brings_back_everything_including_modes(ws: Path) -> None:
    guard, snap, before = guarded(ws)
    mode = (ws / "other.py").stat().st_mode & 0o777
    os.chmod(ws / "other.py", 0o700)
    (ws / "app.py").write_text("x\n")
    (ws / "pkg" / "mod.py").unlink()
    (ws / "pkg").rmdir()
    _write(ws / "new.py", "n\n")
    guard.restore(snap)
    assert tree(ws) == before and guard.changes(snap) == []
    assert (ws / "other.py").stat().st_mode & 0o777 == mode


def test_same_content_rewritten_is_not_a_change(ws: Path) -> None:
    guard, snap, _ = guarded(ws)
    (ws / "other.py").write_text("X = 1\n")
    assert guard.changes(snap) == []


def test_a_change_without_a_backup_cannot_be_restored(ws: Path) -> None:
    heavy = min(NO_BACKUP_DIRS)
    _write(ws / heavy / "lib.js", "a\n")
    guard, snap, _ = guarded(ws)
    (ws / heavy / "lib.js").write_text("tampered\n")
    with pytest.raises(PathGuardError, match="no backup"):
        guard.enforce(snap, ["app.py"])


def test_snapshot_backups_live_outside_the_workspace(ws: Path) -> None:
    _, snap, _ = guarded(ws)
    assert not snap.store.is_relative_to(ws) and any(snap.store.iterdir())
    snap.close()
    assert not snap.store.exists()


# --- the allowlist and the mode's fileRegex ---


def test_allowed_paths_are_checked(ws: Path, tmp_path: Path) -> None:
    assert check_allowed_paths(ws, ["app.py", "tests/test_rook_cx_001.py"]) == [
        "app.py", "tests/test_rook_cx_001.py"]
    (ws / "link.py").symlink_to(tmp_path / "outside.py")
    (ws / "linkdir").symlink_to(tmp_path, target_is_directory=True)
    for bad in ["link.py", "linkdir/x.py", "../x.py", "/etc/passwd", "rook/tests/t.py", "Rook/t.py",
                "ｒook/t.py", ".git/config", ".GIT/config", "ａpp.py", "pkg", "app.py/x.py", "./app.py",
                "a\\b.py", "app\x00.py", ""]:
        with pytest.raises(ValueError):
            check_allowed_paths(ws, [bad])
    with pytest.raises(ValueError, match="differ only by case"):
        check_allowed_paths(ws, ["app.py", "App.py"])


def test_the_file_regex_is_escaped_and_anchored() -> None:
    allowed = ["app.py", "tests/test_rook_cx_001.py", "src/a+b(1).py"]
    regex = re.compile(surgeon_edit_regex(allowed))
    for path in allowed:
        assert regex.search(path)
    for path in ["appXpy", "app.py.bak", "xapp.py", "sub/app.py", "tests/test_rook_cx_001.pyc",
                 "src/aab(1).py", "src/a+b1.py", ".git/config", "tests/test_rook_cx_0012.py"]:
        assert not regex.search(path), path
    assert regex.pattern.startswith("^(?:") and regex.pattern.endswith(")$")


def test_the_file_regex_also_matches_the_absolute_path_in_the_workspace_only() -> None:
    ws = "/home/u/.rook/workspaces/r_1 (copy)+x"
    regex = re.compile(surgeon_edit_regex(["app.py", "tests/t.py"], ws))
    for path in ["app.py", "tests/t.py", f"{ws}/app.py", f"{ws}/tests/t.py"]:
        assert regex.search(path), path
    for path in [f"{ws}/other.py", f"{ws}/sub/app.py", "/elsewhere/app.py", f"{ws}x/app.py", f"/x{ws}/app.py",
                 f"{ws}/app.py.bak", f"{ws}//app.py", "/home/u/.rook/workspaces/r_1 (copy)xx/app.py"]:
        assert not regex.search(path), path
    for bad in ["relative/ws", "/ws\n", "C:\\ws"]:
        with pytest.raises(ValueError):
            surgeon_edit_regex(["app.py"], bad)
