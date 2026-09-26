"""Set one secret in the host's root-only env file (runs ON the EC2 host, as root, via deploy/aws/scripts/set-secret.sh).

    <value on stdin> | sudo python3 set_env.py NAME [--file /etc/rook/rook.env]

The value comes only from stdin, never from argv, and is never printed. The file is rewritten atomically with mode
600, keeping every other entry. Values are written in the docker compose env_file syntax:
- a single-line value in single quotes (taken literally: no `$` interpolation, no escapes);
- a multi-line PEM (GITHUB_APP_PRIVATE_KEY only) in double quotes with `\\n` escapes, which compose turns back into
  real newlines, so the server process sees the PEM exactly as in the .pem file.
Python 3 standard library only (the host has no project venv).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

ALLOWED = (
    "BOB_API_KEY",
    "ROOK_GUEST_SECRET",
    "SUPABASE_JWT_SECRET",
    "SUPABASE_URL",
    "GITHUB_APP_ID",
    "GITHUB_APP_PRIVATE_KEY",
    "GITHUB_WEBHOOK_SECRET",
)
PEM_NAME = "GITHUB_APP_PRIVATE_KEY"
DEFAULT_FILE = Path("/etc/rook/rook.env")
_PEM = re.compile(r"-----BEGIN [A-Z ]+-----\n[A-Za-z0-9+/=\n]+\n-----END [A-Z ]+-----")
_MIN_LENGTH = {"ROOK_GUEST_SECRET": 32}


class SecretError(ValueError):
    """A bad name or value. The message never contains the value."""


def encode(name: str, raw: str) -> str:
    """The env-file line for `name`, or SecretError."""
    if name not in ALLOWED:
        raise SecretError(f"{name!r} is not a settable secret (allowed: {', '.join(ALLOWED)})")
    value = raw.replace("\r\n", "\n").rstrip("\n")
    if not value.strip():
        raise SecretError(f"{name}: empty value")
    if "\x00" in value or "\r" in value:
        raise SecretError(f"{name}: the value has a NUL or CR character")
    if name == PEM_NAME:
        value = value.strip()
        if not _PEM.fullmatch(value):
            raise SecretError(f"{name}: not a PEM private key (pipe the .pem file in unchanged)")
        return f'{name}="{value.replace(chr(10), chr(92) + "n")}\\n"'
    if "\n" in value:
        raise SecretError(f"{name}: the value must be one line")
    if "'" in value:
        raise SecretError(f"{name}: the value may not contain a single quote")
    if len(value) < _MIN_LENGTH.get(name, 1):
        raise SecretError(f"{name}: the value must be at least {_MIN_LENGTH[name]} characters")
    return f"{name}='{value}'"


def write(path: Path, name: str, line: str) -> None:
    """Replace (or add) `name` in `path`, atomically, mode 600."""
    kept: list[str] = []
    if path.exists():
        kept = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith(f"{name}=")]
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".rook.env.")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join([*kept, line]) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    os.chmod(path, 0o600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set one secret from stdin in the rook env file.")
    parser.add_argument("name")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    args = parser.parse_args(argv)
    try:
        line = encode(args.name, sys.stdin.read())
    except (SecretError, UnicodeDecodeError) as exc:
        msg = str(exc) if isinstance(exc, SecretError) else f"{args.name}: the value is not UTF-8"
        print(f"error: {msg}", file=sys.stderr)
        return 2
    write(args.file, args.name, line)
    print(f"{args.name} set in {args.file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
