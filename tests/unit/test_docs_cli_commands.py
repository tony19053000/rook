"""ROOK-055: every `rook …` command the docs quote exists in the real CLI.

The site's docs copy lives in `web/content/docs*.ts`; the web tests have no Python and these tests have no
Node, so this file reads the copy as text. The convention it relies on (and enforces): a command is always
written in a code block (a quoted string that starts with `rook `) or between backticks. Any other
"rook <word>" in the copy fails the test, so a command cannot hide in prose.

Each quoted command is parsed by the Typer app's own parser (`make_context`), so an unknown subcommand, an
unknown flag, a missing required option or a bad value fails exactly as it would in a terminal. A bare
`rook <subcommand>` is a mention of the command and only has to exist. The README's commands are checked the
same way, and the counterexample fields the docs list are compared with the pydantic model.
"""

from __future__ import annotations

import re
import shlex
import tomllib
from pathlib import Path

import pytest
import typer

from rook.cli.main import app
from rook.export.counterexample import Counterexample

ROOT = Path(__file__).resolve().parents[2]
CONTENT = ROOT / "web" / "content"
DOC_FILES = sorted(CONTENT.glob("docs*.ts"))
CLI = typer.main.get_command(app)

# "rook" as a command word: not part of a path, a URL, a package name or an identifier.
_ROOK = re.compile(r"(?<![\w./@-])rook (?=[a-z\[<.~-])")
# What may come right before a quoted command: the opening of a code span or a string, a shell prompt, a
# workflow `run:` key, or `uvx --from git+${REPO_URL}` as the install guide writes it (the same entry point).
_OPENERS = ("`", '"', "$ ", "run: ", "--from git+${REPO_URL} ")
# A command ends where its code span, string or line ends, or at a shell comment.
_END = re.compile(r'[`"\\\n]| +#')


def quoted_commands(text: str) -> list[tuple[str, bool]]:
    """Every `rook …` in `text` as (command, in_code): the command's words after "rook"."""
    found = []
    for match in _ROOK.finditer(text):
        rest = text[match.end():]
        end = _END.search(rest)
        command = rest[: end.start() if end else len(rest)].strip()
        found.append((command, text[: match.start()].endswith(_OPENERS)))
    return found


def docs_commands() -> list[tuple[str, str]]:
    return [(path.name, cmd) for path in DOC_FILES for cmd, _ in quoted_commands(path.read_text(encoding="utf-8"))]


def readme_commands() -> list[str]:
    """The `rook …` lines of the README's bash blocks, plus its inline code spans."""
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lines = [line for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL) for line in block.splitlines()]
    spans = re.findall(r"`(rook [^`]*)`", text)
    return [cmd for source in (*lines, *spans) if source.startswith("rook ") for cmd, _ in quoted_commands(source)]


def check_command(command: str) -> None:
    """Raise if `rook <command>` would not parse in the real CLI."""
    words = shlex.split(command)
    assert words, "an empty command"
    name, args = words[0], words[1:]
    if name.startswith("-"):
        assert name in {opt for p in CLI.params for opt in p.opts} | {"--help"}, f"rook has no option {name}"
        return
    sub = CLI.commands.get(name)
    assert sub is not None, f"rook has no command {name!r} (it has: {', '.join(sorted(CLI.commands))})"
    if not args or args == ["--help"]:
        return  # a mention of the command, or its help
    for arg in args:
        if arg.startswith("--"):
            assert arg in {opt for p in sub.params for opt in p.opts}, f"rook {name} has no option {arg}"
    try:
        sub.make_context(name, list(args)).close()
    except Exception as exc:  # the parser's usage errors (their class moved between typer versions)
        raise AssertionError(f"`rook {command}` does not parse: {getattr(exc, 'message', exc)}") from exc


def test_the_docs_content_files_are_found() -> None:
    names = {p.name for p in DOC_FILES}
    assert {"docs.ts", "docsGettingStarted.ts", "docsInstall.ts", "docsRules.ts", "docsCounterexamples.ts",
            "docsGithubAction.ts", "docsData.ts"} <= names


def test_every_command_in_the_docs_is_written_as_code() -> None:
    """Outside a code block or a code span, "rook <word>" would not be checked as a command: refuse it."""
    for path in DOC_FILES:
        for command, in_code in quoted_commands(path.read_text(encoding="utf-8")):
            assert in_code, f"{path.name}: write `rook {command}` in backticks or in a code block"


def test_the_docs_quote_enough_commands_to_mean_something() -> None:
    commands = docs_commands()
    assert len(commands) >= 40
    used = {cmd.split()[0] for _, cmd in commands}
    assert set(CLI.commands) <= used, f"no guide shows: {sorted(set(CLI.commands) - used)}"
    flags = {word for _, cmd in commands for word in cmd.split() if word.startswith("--")}
    assert {"--ci", "--auto", "--setup", "--budget", "--sequences", "--seconds", "--base-url", "--times",
            "--repo", "--model", "--force", "--version", "--help"} <= flags


@pytest.mark.parametrize(("source", "command"), docs_commands(), ids=[f"{s}: rook {c}" for s, c in docs_commands()])
def test_every_command_quoted_in_the_docs_parses_in_the_real_cli(source: str, command: str) -> None:
    try:
        check_command(command)
    except AssertionError as exc:
        raise AssertionError(f"{source}: {exc}") from exc


def test_every_command_in_the_readme_parses_in_the_real_cli() -> None:
    commands = readme_commands()
    assert len(commands) >= 8
    for command in commands:
        check_command(command)


@pytest.mark.parametrize("bad", [
    "scan ./my-app",                                   # no such command
    "run ./my-app --fast",                             # no such flag
    "run --ci --autofix",                              # a flag that only starts like a real one
    "replay cx_001",                                   # --base-url is required
    "replay --base-url http://127.0.0.1:8000",         # the counterexample is required
    "replay cx_001 --base-url http://127.0.0.1:8000 --times 0",    # out of range
    "verify cx_001 --base-url http://127.0.0.1:8000 --times 3",    # --times belongs to replay
    "run ./a ./b",                                     # one repo only
    "explain cx_001 --base-url http://127.0.0.1:8000",  # explain takes no app
    "--verbose",                                       # no such top-level option
])
def test_the_check_rejects_commands_that_do_not_exist(bad: str) -> None:
    with pytest.raises(AssertionError):
        check_command(bad)


def test_the_check_finds_commands_wherever_the_copy_puts_them() -> None:
    sample = ('text: "Run `rook run ./my-app --ci` and then `rook login`.", code: lines("rook", "rook init --force"),\n'
              '"      - run: rook run . --ci --auto", "$ rook --version", "uses: tony19053000/rook@<sha>",\n'
              '"rook/rook.yaml", "rook-report.md", "the rook CLI", "a prose rook run here"')
    assert quoted_commands(sample) == [
        ("run ./my-app --ci", True), ("login", True), ("init --force", True), ("run . --ci --auto", True),
        ("--version", True), ("run here", False)]


def test_the_counterexample_fields_in_the_docs_are_the_models() -> None:
    text = (CONTENT / "docsCounterexamples.ts").read_text(encoding="utf-8")
    block = text.split("export const cxFields = [", 1)[1].split("] as const;", 1)[0]
    assert re.findall(r'\{\s*term: "(\w+)"', block) == list(Counterexample.model_fields)


def test_the_docs_name_the_package_and_python_version_of_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    text = (CONTENT / "docsInstall.ts").read_text(encoding="utf-8")
    assert f'export const PACKAGE_NAME = "{project["name"]}";' in text
    minimum = project["requires-python"].removeprefix(">=")
    assert f'export const PYTHON_MINIMUM = "{minimum}";' in text
    assert set(project["scripts"]) == {"rook", "rook-pr-comment"}
