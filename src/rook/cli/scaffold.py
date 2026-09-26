"""`rook init`: prepare a repo for Rook: the `rook/` folder and a GitHub workflow that runs `rook run --ci`.

Existing files are never overwritten (unless `--force`), and nothing outside the repo folder is written.
The workflow reads `BOB_API_KEY` from the repo's GitHub secrets; no secret is ever written to a file.
"""

from __future__ import annotations

from pathlib import Path

WORKFLOW_PATH = Path(".github") / "workflows" / "rook.yml"
README_PATH = Path("rook") / "README.md"

WORKFLOW = """\
# Rook: search each pull request for the smallest sequence of actions that breaks a business rule.
# Needs the BOB_API_KEY repository secret. rook-report.md is kept as a build artifact.
name: rook
on:
  pull_request:
permissions:
  contents: read
jobs:
  rook:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uv tool install rook-cli
      - run: rook run . --ci --auto
        env:
          BOB_API_KEY: ${{ secrets.BOB_API_KEY }}
      - if: always()
        uses: actions/upload-artifact@v4
        with:
          name: rook-report
          path: rook-report.*
"""

README = """\
# rook/

Rook keeps its files here:

- `rook.yaml`: the model of your app (actors, actions, state and the business rules you approved)
- `counterexamples/cx_NNN.json`: each broken rule, as the minimal steps that break it

Replay one against your running app: `rook replay cx_001 --base-url http://127.0.0.1:8000`.
"""


def init_repo(root: Path, *, force: bool = False) -> list[tuple[Path, str]]:
    """Write the starter files; returns (path, "created" | "kept" | "replaced") for each."""
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"{root} is not a folder")
    out = []
    (root / "rook" / "counterexamples").mkdir(parents=True, exist_ok=True)
    for rel, text in ((README_PATH, README), (WORKFLOW_PATH, WORKFLOW)):
        path = root / rel
        if path.is_symlink():
            out.append((rel, "kept"))  # never write through a link
            continue
        existed = path.exists()
        if existed and not force:
            out.append((rel, "kept"))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        out.append((rel, "replaced" if existed else "created"))
    return out
