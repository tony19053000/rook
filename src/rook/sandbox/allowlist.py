"""Demo repos the hosted server may run (03 section 3), pinned by repo name and commit SHA.

Nothing else is ever executed by `ProcessSandbox`: the start command, env and extra commands all come
from here, never from a SandboxPlan (which Bob writes) or from the user.

Argv entries may use two placeholders, replaced as whole tokens or inside a token:
`{python}` (this interpreter) and `{port}` (the port picked for the run).
"""

import re
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Always used with fullmatch: `$` would also accept a trailing newline.
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_SHA = re.compile(r"[0-9a-f]{40}")
_ENV_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
_PLACEHOLDERS = ("{python}", "{port}")

# Env vars that change how the loader, an interpreter or a shell behaves (code injection), or that the
# sandbox sets itself. Nobody may set them through an allowlist entry or a caller-supplied value.
_DENIED_ENV_PREFIXES = ("LD_", "DYLD_", "PYTHON", "NODE_", "NPM_CONFIG_", "BASH_FUNC_", "GIT_", "UV_", "PIP_")
_DENIED_ENV_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "TMPDIR",
        "LANG",
        "SHELL",
        "ENV",
        "BASH_ENV",
        "IFS",
        "CDPATH",
        "PS4",
        "PERL5LIB",
        "PERL5OPT",
        "PERLLIB",
        "RUBYLIB",
        "RUBYOPT",
        "GEM_HOME",
        "GEM_PATH",
        "GOPATH",
        "CLASSPATH",
        "JAVA_TOOL_OPTIONS",
        "_JAVA_OPTIONS",
        "JDK_JAVA_OPTIONS",
        "LIBPATH",
        "MANPATH",
        "GCONV_PATH",
        "LOCPATH",
        "NLSPATH",
        "HOSTALIASES",
        "RESOLV_HOST_CONF",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    }
)


def check_env_name(name: str) -> str:
    """A plain upper-case identifier that is not on the denylist, else ValueError."""
    if not isinstance(name, str) or not _ENV_NAME.fullmatch(name):
        raise ValueError(f"invalid env var name {name!r}")
    upper = name.upper()
    if upper in _DENIED_ENV_NAMES or upper.startswith(_DENIED_ENV_PREFIXES):
        raise ValueError(f"env var {name!r} may not be set for a sandboxed app")
    return name


def check_env_value(name: str, value: str) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError(f"env var {name!r} must be a string without NUL bytes")
    return value


REFUSED_MESSAGE = "is not an allowlisted demo repo; run arbitrary repos with the CLI"


class NotAllowlistedError(PermissionError):
    """The repo (or this commit of it) is not on the allowlist."""


def _check_argv(argv: Sequence[str]) -> list[str]:
    if not argv or not all(argv):
        raise ValueError("a command must be a non-empty list of non-empty strings")
    for token in argv:
        if "\x00" in token:
            raise ValueError("a command may not contain NUL bytes")
        leftover = token
        for ph in _PLACEHOLDERS:
            leftover = leftover.replace(ph, "")
        if "{" in leftover or "}" in leftover:
            raise ValueError(f"unknown placeholder in {token!r} (allowed: {', '.join(_PLACEHOLDERS)})")
    return list(argv)


class AllowlistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    repo: str  # "owner/name"
    commit: str  # full 40-hex SHA
    app_dir: Path  # where the repo is pre-installed (in the hosted image)
    start: list[str]  # argv
    port_env: str | None = "PORT"  # env var that receives the port
    db_env: str | None = None  # env var that receives a fresh temp DB file path per run
    health_path: str = "/health"
    health_timeout: float = Field(default=60.0, gt=0)
    env: dict[str, str] = Field(default_factory=dict)  # fixed, non-secret values
    settable_env: frozenset[str] = frozenset()  # the only names a caller may pass (e.g. setup answers)
    commands: dict[str, list[str]] = Field(default_factory=dict)  # e.g. {"test": [...]}, for exec()

    @field_validator("repo")
    @classmethod
    def _repo(cls, v: str) -> str:
        if not _REPO.fullmatch(v):
            raise ValueError(f"repo must look like 'owner/name', not {v!r}")
        return v.lower()

    @field_validator("commit")
    @classmethod
    def _commit(cls, v: str) -> str:
        v = v.lower()
        if not _SHA.fullmatch(v):
            raise ValueError("commit must be a full 40-character SHA")
        return v

    @field_validator("start")
    @classmethod
    def _start(cls, v: list[str]) -> list[str]:
        return _check_argv(v)

    @field_validator("commands")
    @classmethod
    def _commands(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        return {name: _check_argv(argv) for name, argv in v.items()}

    @model_validator(mode="after")
    def _checks(self) -> Self:
        if not self.health_path.startswith("/") or self.health_path.startswith("//"):
            raise ValueError(f"health_path must start with a single '/': {self.health_path!r}")
        for name in (self.port_env, self.db_env, *self.env, *self.settable_env):
            if name is not None:
                check_env_name(name)
        for name, value in self.env.items():
            check_env_value(name, value)
        if self.port_env is not None and self.port_env == self.db_env:
            raise ValueError("port_env and db_env must differ")
        if self.settable_env & {self.port_env, self.db_env}:
            raise ValueError("settable_env may not include port_env or db_env")
        return self


class Allowlist:
    def __init__(self, entries: Iterable[AllowlistEntry] = ()) -> None:
        self._entries: dict[tuple[str, str], AllowlistEntry] = {}
        for entry in entries:
            key = (entry.repo, entry.commit)
            if key in self._entries:
                raise ValueError(f"duplicate allowlist entry {entry.repo}@{entry.commit}")
            self._entries[key] = entry

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        """Load `{entries: [AllowlistEntry, ...]}`. Relative `app_dir`s are relative to the file."""
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        entries = []
        for raw in data.get("entries") or []:
            entry = AllowlistEntry.model_validate(raw)
            if not entry.app_dir.is_absolute():
                entry = entry.model_copy(update={"app_dir": (path.parent / entry.app_dir).resolve()})
            entries.append(entry)
        return cls(entries)

    def get(self, repo: str, commit: str) -> AllowlistEntry:
        entry = self._entries.get((repo.lower(), commit.lower()))
        if entry is None:
            raise NotAllowlistedError(f"{repo}@{commit} {REFUSED_MESSAGE}")
        return entry

    def __contains__(self, key: tuple[str, str]) -> bool:
        repo, commit = key
        return (repo.lower(), commit.lower()) in self._entries

    def __len__(self) -> int:
        return len(self._entries)


# The demo apps and their pinned SHAs are added with the hosted image (ROOK-037 / ROOK-039).
DEFAULT_ALLOWLIST = Allowlist()
