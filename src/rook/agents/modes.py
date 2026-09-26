"""Writes `<workspace>/.bob/custom_modes.yaml` from the registry (docs/02_ARCHITECTURE.md §5.2).

`bob run --mode <slug>` pre-approves every tool its mode's groups allow, so these groups are the real
permission boundary. `.bob/` is added to the workspace's `.git/info/exclude` so it never reaches a PR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from rook.agents.prompts import json_contract
from rook.agents.registry import AGENTS, groups_for

EXCLUDE_LINE = ".bob/"


def modes_document(surgeon_paths: list[str] | None = None) -> dict[str, Any]:
    modes = []
    for spec in AGENTS.values():
        modes.append({
            "slug": spec.slug,
            "name": f"Rook {spec.name}",
            "description": f"Rook {spec.name}: {spec.verb.lower()}",
            "roleDefinition": spec.role_definition,
            "whenToUse": spec.when_to_use,
            "customInstructions": f"{spec.instructions}\n\n{json_contract(spec.id)}",
            "groups": groups_for(spec.id, surgeon_paths),
        })
    return {"customModes": modes}


def write_modes(workspace: str | Path, surgeon_paths: list[str] | None = None) -> Path:
    """Write the modes file (the Surgeon may edit only `surgeon_paths`, if given) and git-exclude `.bob/`."""
    ws = Path(workspace)
    path = ws / ".bob" / "custom_modes.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(modes_document(surgeon_paths), sort_keys=False, allow_unicode=True, width=100)
    path.write_text(text, encoding="utf-8")
    _exclude_bob(ws)
    return path


def _git_dir(ws: Path) -> Path | None:
    """The directory holding info/exclude: `.git`, or a worktree's common dir (`.git` is then a file)."""
    dot_git = ws / ".git"
    if dot_git.is_dir():
        return dot_git
    if not dot_git.is_file():
        return None
    first = dot_git.read_text(encoding="utf-8").strip()
    if not first.startswith("gitdir:"):
        return None
    git_dir = (ws / first.removeprefix("gitdir:").strip()).resolve()
    common = git_dir / "commondir"
    if common.is_file():
        git_dir = (git_dir / common.read_text(encoding="utf-8").strip()).resolve()
    return git_dir if git_dir.is_dir() else None


def _exclude_bob(ws: Path) -> None:
    git_dir = _git_dir(ws)
    if git_dir is None:
        return
    exclude = git_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    if EXCLUDE_LINE in (line.strip() for line in current.splitlines()):
        return
    prefix = "" if not current or current.endswith("\n") else "\n"
    with exclude.open("a", encoding="utf-8") as fh:
        fh.write(f"{prefix}{EXCLUDE_LINE}\n")
