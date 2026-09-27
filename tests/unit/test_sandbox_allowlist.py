"""ROOK-013: the demo allowlist and ProcessSandbox's checks that run before any process starts."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from rook.sandbox import (
    DEFAULT_ALLOWLIST,
    Allowlist,
    AllowlistEntry,
    NotAllowlistedError,
    ProcessSandbox,
    SandboxError,
    free_port,
)

SHA = "a" * 40
OTHER_SHA = "b" * 40


def _entry(**kwargs) -> AllowlistEntry:
    data = {
        "repo": "rook-demo/shop",
        "commit": SHA,
        "app_dir": Path("/srv/shop"),
        "start": ["{python}", "app.py"],
    }
    return AllowlistEntry.model_validate({**data, **kwargs})


def test_lookup_is_by_repo_and_commit_case_insensitive() -> None:
    allow = Allowlist([_entry()])
    assert allow.get("Rook-Demo/Shop", SHA.upper()).repo == "rook-demo/shop"
    assert ("rook-demo/shop", SHA) in allow and len(allow) == 1


def test_unknown_repo_or_other_commit_is_refused() -> None:
    allow = Allowlist([_entry()])
    with pytest.raises(NotAllowlistedError, match="run arbitrary repos with the CLI"):
        allow.get("someone/else", SHA)
    with pytest.raises(NotAllowlistedError):
        allow.get("rook-demo/shop", OTHER_SHA)


def test_process_sandbox_refuses_non_allowlisted_repo() -> None:
    with pytest.raises(NotAllowlistedError):
        ProcessSandbox("evil/repo", SHA, allowlist=Allowlist([_entry()]))
    # The default (hosted) allowlist has nothing yet, so nothing runs by default.
    with pytest.raises(NotAllowlistedError):
        ProcessSandbox("rook-demo/shop", SHA)
    assert len(DEFAULT_ALLOWLIST) == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"repo": "no-slash"},
        {"repo": "a/b; rm -rf /"},
        {"commit": "abc123"},  # short SHAs are not pinned
        {"start": []},
        {"start": ["{python}", "{cmd}"]},
        {"health_path": "health"},
        {"health_path": "//evil.test/health"},
        {"env": {"lower-case": "x"}},
        {"port_env": "DB", "db_env": "DB"},
        {"commands": {"test": ["{shell}"]}},
        {"command_timeout": 0},
        {"unknown": 1},
    ],
)
def test_invalid_entries_are_rejected(bad: dict) -> None:
    with pytest.raises(ValidationError):
        _entry(**bad)


def test_duplicate_entries_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        Allowlist([_entry(), _entry()])


def test_from_yaml_resolves_relative_app_dir(tmp_path: Path) -> None:
    (tmp_path / "allowlist.yaml").write_text(
        f"entries:\n  - repo: rook-demo/shop\n    commit: '{SHA}'\n    app_dir: apps/shop\n"
        "    start: ['{python}', '-m', 'uvicorn', 'app:app', '--port', '{port}']\n    db_env: DATABASE_PATH\n"
    )
    entry = Allowlist.from_yaml(tmp_path / "allowlist.yaml").get("rook-demo/shop", SHA)
    assert entry.app_dir == (tmp_path / "apps" / "shop").resolve()
    assert entry.db_env == "DATABASE_PATH" and entry.port_env == "PORT"


@pytest.mark.parametrize("name", ["PATH", "HOME", "PORT", "DATABASE_PATH", "OTHER_VALUE"])
def test_caller_env_must_be_settable_by_the_entry(name: str) -> None:
    allow = Allowlist([_entry(db_env="DATABASE_PATH", settable_env={"SETUP_VALUE"})])
    with pytest.raises(ValueError, match="may only set"):
        ProcessSandbox("rook-demo/shop", SHA, allowlist=allow, env={name: "x"})
    sandbox = ProcessSandbox("rook-demo/shop", SHA, allowlist=allow, env={"SETUP_VALUE": "ok"})
    assert sandbox._child_env(Path("/tmp/x"), 1234)["SETUP_VALUE"] == "ok"


DANGEROUS = [
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "PYTHONPATH",
    "PYTHONSTARTUP",
    "PYTHONHOME",
    "NODE_OPTIONS",
    "BASH_ENV",
    "ENV",
    "PATH",
    "HOME",
    "PERL5OPT",
    "HTTP_PROXY",
    "OPENSSL_CONF",
    "OPENSSL_ENGINES",
    "GLIBC_TUNABLES",
    "MALLOC_CHECK_",
    "MALLOC_ARENA_MAX",
]


@pytest.mark.parametrize("name", DANGEROUS)
def test_dangerous_env_is_refused_in_the_entry(name: str) -> None:
    with pytest.raises(ValidationError, match="may not be set"):
        _entry(env={name: "/tmp/evil"})
    with pytest.raises(ValidationError, match="may not be set"):
        _entry(settable_env={name})


@pytest.mark.parametrize("field", ["port_env", "db_env"])
def test_port_and_db_env_cannot_be_dangerous(field: str) -> None:
    with pytest.raises(ValidationError, match="may not be set"):
        _entry(**{field: "PYTHONPATH"})


@pytest.mark.parametrize("name", DANGEROUS)
def test_dangerous_caller_env_is_refused_even_if_the_entry_lists_it(name: str) -> None:
    # Bypass validation to simulate a bad entry: the caller-side check must still refuse it.
    entry = _entry().model_copy(update={"settable_env": frozenset({name})})
    with pytest.raises(ValueError, match="may not be set"):
        ProcessSandbox("rook-demo/shop", SHA, allowlist=Allowlist([entry]), env={name: "/tmp/evil"})


def test_reviewer_repro_ld_preload_and_pythonpath_never_reach_the_child() -> None:
    allow = Allowlist([_entry()])
    with pytest.raises(ValueError):
        ProcessSandbox("rook-demo/shop", SHA, allowlist=allow, env={"LD_PRELOAD": "/tmp/evil.so"})
    with pytest.raises(ValueError):
        ProcessSandbox("rook-demo/shop", SHA, allowlist=allow, env={"PYTHONPATH": "/tmp/evilmod"})


@pytest.mark.parametrize("name", ["A=B", "A\x00", "A\nB", "lower", "1ABC", "SETUP_VALUE\n", ""])
def test_malformed_env_names_are_refused(name: str) -> None:
    with pytest.raises(ValidationError):
        _entry(env={name: "x"})
    with pytest.raises(ValidationError):
        _entry(settable_env={name})


def test_nul_in_env_values_is_refused() -> None:
    with pytest.raises(ValidationError, match="NUL"):
        _entry(env={"APP_MODE": "a\x00b"})
    allow = Allowlist([_entry(settable_env={"SETUP_VALUE"})])
    with pytest.raises(ValueError, match="NUL"):
        ProcessSandbox("rook-demo/shop", SHA, allowlist=allow, env={"SETUP_VALUE": "a\x00b"})


def test_trailing_newline_in_repo_or_commit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _entry(repo="rook-demo/shop\n")
    with pytest.raises(ValidationError):
        _entry(commit=SHA + "\n")
    with pytest.raises(NotAllowlistedError):
        Allowlist([_entry()]).get("rook-demo/shop", SHA + "\nx")
    with pytest.raises(NotAllowlistedError):
        Allowlist([_entry()]).get("rook-demo/shop", SHA + "\n")


def test_exec_refuses_commands_not_in_the_entry() -> None:
    allow = Allowlist([_entry(commands={"test": ["{python}", "-c", "print('ok')"]})])
    sandbox = ProcessSandbox("rook-demo/shop", SHA, allowlist=allow)
    with pytest.raises(SandboxError, match="not allowlisted"):
        sandbox.exec(["sh", "-c", "echo hi"])
    with pytest.raises(SandboxError, match="not allowlisted"):
        sandbox.exec([sys.executable, "-c", "print('other')"])


def test_base_url_before_start_is_an_error() -> None:
    sandbox = ProcessSandbox("rook-demo/shop", SHA, allowlist=Allowlist([_entry()]))
    with pytest.raises(SandboxError, match="not started"):
        _ = sandbox.base_url
    sandbox.stop()  # stopping a never-started sandbox is a no-op


def test_free_port_returns_a_bindable_port() -> None:
    port = free_port()
    assert 1024 <= port <= 65535
