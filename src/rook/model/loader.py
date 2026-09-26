"""Load and validate `rook.yaml` (always `yaml.safe_load`)."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from rook.model.schema import ReferenceIssues, RookModel


class ModelError(ValueError):
    """A rook.yaml file could not be parsed or failed validation. `errors` holds one line per problem."""

    def __init__(self, source: str, errors: list[str]) -> None:
        self.source = source
        self.errors = errors
        super().__init__(f"invalid rook model ({source}):\n" + "\n".join(f"  - {e}" for e in errors))


def _format(err: Any) -> list[str]:
    cause = err.get("ctx", {}).get("error")
    if isinstance(cause, ReferenceIssues):
        return [f"{'.'.join(map(str, loc))}: {msg}" for loc, msg in cause.issues]
    loc = ".".join(str(part) for part in err["loc"]) or "<root>"
    return [f"{loc}: {err['msg'].removeprefix('Value error, ')}"]


def load_model_str(text: str, source: str = "<string>") -> RookModel:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ModelError(source, [f"YAML syntax error: {exc}"]) from exc
    if not isinstance(data, dict):
        raise ModelError(source, ["<root>: expected a mapping at the top level"])
    try:
        return RookModel.model_validate(data)
    except ValidationError as exc:
        raise ModelError(
            source, [line for e in exc.errors(include_url=False) for line in _format(e)]
        ) from exc


def load_model(path: str | Path) -> RookModel:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ModelError(str(path), [f"cannot read file: {exc}"]) from exc
    return load_model_str(text, source=str(path))
