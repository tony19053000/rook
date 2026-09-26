"""Slash commands (04_FRONTEND_SPEC.md §2.4): the registry, parsing and Tab completion."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SlashCommand:
    name: str
    args: str
    help: str
    arg_required: bool = False
    choices: tuple[str, ...] = ()


COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("run", "[repo]", "search a repo for broken rules"),
    SlashCommand("repo", "", "switch repo"),
    SlashCommand("rules", "", "view or edit the rules"),
    SlashCommand("replay", "<cx>", "replay a counterexample", arg_required=True),
    SlashCommand("explain", "<cx>", "ask Bob why it broke", arg_required=True),
    SlashCommand("verify", "<cx>", "prove a fix works", arg_required=True),
    SlashCommand("dashboard", "", "open the web view of this run"),
    SlashCommand("login", "", "sign in or switch account"),
    SlashCommand("github", "", "connect GitHub"),
    SlashCommand("logout", "", "sign out"),
    SlashCommand("auto", "on|off", "auto-approve questions", arg_required=True, choices=("on", "off")),
    SlashCommand("help", "", "show commands and shortcuts"),
)
BY_NAME: dict[str, SlashCommand] = {c.name: c for c in COMMANDS}

SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("Enter", "send, or answer the current question"),
    ("↑/↓", "move in menus, or input history"),
    ("Esc", "cancel the question, or interrupt the run"),
    ("Ctrl+C twice", "quit"),
    ("?", "show shortcuts (in an empty input)"),
    ("Tab", "complete a slash command"),
)


@dataclass(frozen=True)
class Parsed:
    name: str
    arg: str


def parse(text: str) -> Parsed | None:
    """Split `/name rest` into its parts; None when `text` isn't a slash command."""
    text = text.strip()
    if not text.startswith("/") or len(text) == 1:
        return None
    name, _, arg = text[1:].partition(" ")
    return Parsed(name.lower(), arg.strip())


def validate(parsed: Parsed) -> str | None:
    """An error message for an unknown command or bad arguments, else None."""
    command = BY_NAME.get(parsed.name)
    if command is None:
        return f"Unknown command /{parsed.name}. Type /help to see the commands."
    if command.arg_required and not parsed.arg:
        return f"Usage: /{command.name} {command.args}"
    if command.choices and parsed.arg not in command.choices:
        return f"Usage: /{command.name} {command.args}"
    return None


@dataclass(frozen=True)
class Completion:
    value: str
    candidates: tuple[str, ...]


def complete(text: str) -> Completion:
    """Complete a partial `/name`. One match gets a trailing space; several extend to their common prefix."""
    if not text.startswith("/") or " " in text:
        return Completion(text, ())
    prefix = text[1:].lower()
    matches = tuple(c.name for c in COMMANDS if c.name.startswith(prefix))
    if not matches:
        return Completion(text, ())
    if len(matches) == 1:
        return Completion(f"/{matches[0]} ", matches)
    return Completion("/" + os.path.commonprefix(list(matches)), matches)


def help_lines() -> list[str]:
    width = max(len(f"/{c.name} {c.args}".rstrip()) for c in COMMANDS)
    return [f"{f'/{c.name} {c.args}'.rstrip():<{width}}  {c.help}" for c in COMMANDS]


def shortcut_lines() -> list[str]:
    width = max(len(k) for k, _ in SHORTCUTS)
    return [f"{key:<{width}}  {text}" for key, text in SHORTCUTS]
