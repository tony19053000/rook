"""PREPARE never lets a symlink lead out of the workspace (Bob runs on the host with it as cwd), and a
cancelled PREPARE leaves no git process and no half-made workspace behind."""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest
from session_helpers import minishop_source

from rook.core.workspace import (
    PrepareCancelled,
    RepoSpec,
    _remove_escaping_links,
    git,
    prepare_workspace,
)

SECRET = "TOP-SECRET-outside-the-repo"


def outside(tmp_path: Path) -> tuple[Path, Path]:
    """A secret file and a secret folder next to (not inside) the repo."""
    secret_dir = tmp_path / "home" / ".ssh"
    secret_dir.mkdir(parents=True)
    (secret_dir / "id_rsa").write_text(SECRET)
    secret = tmp_path / "home" / ".bob-key.env"
    secret.write_text(SECRET)
    return secret, secret_dir


def prepare(src: Path, tmp_path: Path, run_id: str = "r_abcdefghijkl") -> tuple[Path, tuple[str, ...]]:
    ws = prepare_workspace(RepoSpec(kind="local", ref=str(src)), run_id, root=tmp_path / "wss")
    return ws.path, ws.skipped


def assert_nothing_outside_is_readable(ws: Path) -> None:
    """Every path in the workspace resolves inside it, and no file read through it holds the secret."""
    root = os.path.realpath(ws)
    for here, dirs, files in os.walk(ws):  # links are listed but not followed
        for name in [*dirs, *files]:
            path = os.path.join(here, name)
            real = os.path.realpath(path)
            assert real == root or real.startswith(root + os.sep), f"{path} leads to {real}"
            if os.path.isfile(path):  # follows the link, if it is one
                assert SECRET not in Path(path).read_text(errors="replace"), path


def links(ws: Path) -> dict[str, str]:
    return {p.relative_to(ws).as_posix(): os.readlink(p) for p in ws.rglob("*") if p.is_symlink()}


def test_an_absolute_link_outside_the_repo_is_left_out(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    secret, _ = outside(tmp_path)
    src = minishop_source(tmp_path)
    (src / "passwd").symlink_to("/etc/passwd")
    (src / "key.env").symlink_to(secret)
    with caplog.at_level(logging.WARNING, logger="rook.core.workspace"):
        ws, skipped = prepare(src, tmp_path)
    assert set(skipped) == {"passwd", "key.env"}
    assert not os.path.lexists(ws / "passwd") and not os.path.lexists(ws / "key.env")
    assert sum("left out" in r.getMessage() for r in caplog.records) == 2  # one warning per link
    assert (ws / "app.py").is_file()
    assert_nothing_outside_is_readable(ws)


def test_a_dotdot_link_outside_the_repo_is_left_out(tmp_path: Path) -> None:
    outside(tmp_path)
    src = minishop_source(tmp_path)
    (src / "sub").mkdir()
    (src / "sub" / "key.env").symlink_to("../../home/.bob-key.env")
    (src / "up").symlink_to("..", target_is_directory=True)  # the folder that holds the repo
    ws, skipped = prepare(src, tmp_path)
    assert set(skipped) == {"sub/key.env", "up"}
    assert (ws / "sub").is_dir() and links(ws) == {}
    assert_nothing_outside_is_readable(ws)


def test_a_chain_of_links_that_ends_outside_is_left_out(tmp_path: Path) -> None:
    secret, _ = outside(tmp_path)
    src = minishop_source(tmp_path)
    (src / "last").symlink_to(secret)
    (src / "middle").symlink_to("last")
    (src / "first").symlink_to(src / "middle")  # link -> link -> link -> outside
    ws, skipped = prepare(src, tmp_path)
    assert set(skipped) == {"first", "middle", "last"}
    assert links(ws) == {}
    assert_nothing_outside_is_readable(ws)


def test_a_directory_link_outside_the_repo_is_left_out(tmp_path: Path) -> None:
    _, secret_dir = outside(tmp_path)
    src = minishop_source(tmp_path)
    (src / "ssh").symlink_to(secret_dir, target_is_directory=True)
    (src / "etc").symlink_to("/etc", target_is_directory=True)
    ws, skipped = prepare(src, tmp_path)
    assert set(skipped) == {"ssh", "etc"}
    assert not os.path.lexists(ws / "ssh") and not os.path.lexists(ws / "etc")
    assert_nothing_outside_is_readable(ws)


def test_dangling_and_looping_links_are_left_out(tmp_path: Path) -> None:
    src = minishop_source(tmp_path)
    (src / "gone").symlink_to("missing.py")  # dangling, inside
    (src / "later").symlink_to(tmp_path / "not-yet")  # dangling, outside: could be created later
    (src / "loop_a").symlink_to("loop_b")
    (src / "loop_b").symlink_to("loop_a")
    ws, skipped = prepare(src, tmp_path)
    assert set(skipped) == {"gone", "later", "loop_a", "loop_b"}
    (tmp_path / "not-yet").write_text(SECRET)
    assert links(ws) == {}
    assert_nothing_outside_is_readable(ws)


def test_links_that_stay_inside_become_relative_links_inside_the_workspace(tmp_path: Path) -> None:
    src = minishop_source(tmp_path)
    (src / "pkg").mkdir()
    (src / "pkg" / "mod.py").write_text("X = 1\n")
    (src / "abs.py").symlink_to(src / "pkg" / "mod.py")  # absolute, but inside the repo
    (src / "pkg" / "rel.py").symlink_to("mod.py")
    (src / "pkgdir").symlink_to("pkg", target_is_directory=True)
    (src / "chain.py").symlink_to("abs.py")  # link -> link -> file, all inside
    (src / "pkg" / "root").symlink_to("..", target_is_directory=True)  # the repo root itself
    ws, skipped = prepare(src, tmp_path)
    assert skipped == ()
    assert links(ws) == {"abs.py": "pkg/mod.py", "pkg/rel.py": "mod.py", "pkgdir": "pkg",
                         "chain.py": "pkg/mod.py", "pkg/root": ".."}
    assert (ws / "abs.py").read_text() == "X = 1\n" and (ws / "pkgdir" / "mod.py").read_text() == "X = 1\n"
    (src / "pkg" / "mod.py").write_text("changed in the user's folder\n")  # the links do not reach it
    assert (ws / "chain.py").read_text() == "X = 1\n"
    assert_nothing_outside_is_readable(ws)


def test_special_files_are_left_out_without_blocking(tmp_path: Path) -> None:
    src = minishop_source(tmp_path)
    os.mkfifo(src / "pipe")  # copying a FIFO's content would block forever
    ws, skipped = prepare(src, tmp_path)
    assert skipped == ("pipe",) and not os.path.lexists(ws / "pipe")


def test_a_github_clone_has_no_links_and_the_scan_removes_escaping_ones(tmp_path: Path) -> None:
    outside(tmp_path)
    src = minishop_source(tmp_path)
    (src / "passwd").symlink_to("/etc/passwd")
    (src / "key.env").symlink_to("../home/.bob-key.env")
    (src / "inner.py").symlink_to("app.py")
    git(src, "init", "-q")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "upstream with links")
    origin = tmp_path / "server" / "acme" / "shop.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(src), str(origin)], check=True, capture_output=True)
    ws = prepare_workspace(RepoSpec(kind="github", ref="acme/shop"), "r_abcdefghijkl", root=tmp_path / "w",
                           github_url=f"file://{tmp_path / 'server'}").path
    assert links(ws) == {}  # checked out as plain files holding the link text
    assert (ws / "passwd").read_text() == "/etc/passwd" and (ws / "inner.py").read_text() == "app.py"
    assert git(ws, "config", "core.symlinks") == "false"  # kept for any later checkout
    assert git(ws, "status", "--porcelain") == ""
    assert_nothing_outside_is_readable(ws)
    # The safety net after a clone: any escaping, dangling or looping link is removed, inner ones stay.
    (ws / "d").mkdir()
    (ws / "d" / "abs").symlink_to("/etc/passwd")
    (ws / "d" / "up").symlink_to("../../..", target_is_directory=True)
    (ws / "d" / "gone").symlink_to("nothing")
    (ws / "d" / "ok").symlink_to("../app.py")
    assert sorted(_remove_escaping_links(ws)) == ["d/abs", "d/gone", "d/up"]
    assert links(ws) == {"d/ok": "../app.py"}
    assert_nothing_outside_is_readable(ws)


# --- cancel ---


def test_a_cancel_before_prepare_leaves_no_workspace(tmp_path: Path) -> None:
    stop = threading.Event()
    stop.set()
    with pytest.raises(PrepareCancelled):
        prepare_workspace(RepoSpec(kind="local", ref=str(minishop_source(tmp_path))), "r_abcdefghijkl",
                          root=tmp_path / "wss", cancel=stop)
    assert list((tmp_path / "wss").iterdir()) == []


def test_a_cancel_kills_a_running_git_and_its_children(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    pids = tmp_path / "pids"
    fake = bin_dir / "git"  # a git that starts a helper and hangs, like a slow clone
    fake.write_text(f"#!/bin/sh\nsleep 60 &\necho $$ $! > {pids}\nwait\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    started = time.monotonic()
    with pytest.raises(PrepareCancelled):
        git(tmp_path, "clone", cancel=stop)
    assert time.monotonic() - started < 5
    for pid in map(int, pids.read_text().split()):
        deadline = time.monotonic() + 5
        while Path(f"/proc/{pid}").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not Path(f"/proc/{pid}").exists(), "git or its helper outlived the cancel"
