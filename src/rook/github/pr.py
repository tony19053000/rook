"""SHIP for GitHub repos (ROOK-031, 02 §4): commit the verified fix to `rook/fix-<cx>`, push that branch and
open a pull request whose body is Rook's evidence.

Rules (03 §6): never the default branch (the branch is always `rook/fix-<cx>`, and a push is refused if that
ever equals the repo's default branch), never a force push. The installation token is asked for at SHIP time
(a run can outlive a token), goes to git only through the child env (`workspace.git_auth_env`) and to the
GitHub API only as a header, and is registered with the redaction filter.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from rook.core.events import redact_text, register_secret
from rook.core.workspace import (
    GITHUB_URL,
    ShipRequest,
    ShipResult,
    commit_fix_branch,
    git,
    git_auth_env,
)
from rook.github.app import GitHubApi, GitHubError, valid_repo

TokenSource = Callable[[], Awaitable[str]]
MAX_BODY = 60_000
FOOTER = ("\n\n---\n_Opened by [Rook](https://github.com/tony19053000/rook). The counterexample was found, shrunk "
          "and replayed by Rook's engine, and the fix was verified by execution (replay, the project's tests and a "
          "fresh search) before this PR was opened. Rook never pushes to the default branch._\n")


def pr_body(request: ShipRequest, files: list[str]) -> str:
    """The PR description: the evidence lines from the session, the files changed and a footer (redacted)."""
    evidence = "\n".join(f"- {line}" for line in request.body.splitlines() if line.strip())
    changed = "\n".join(f"- `{f}`" for f in files)
    body = (f"## {request.title}\n\n### Evidence\n{evidence}\n\n### Files\n{changed}\n\nReplay it locally: "
            f"`rook replay {request.cx_id} --base-url http://127.0.0.1:<port>`")
    return redact_text(body)[:MAX_BODY] + FOOTER


class GitHubShipper:
    """Push the fix branch and open a PR on `repo` (`owner/name`), based on `base` (default: the default branch)."""

    def __init__(self, repo: str, token: TokenSource, *, base: str | None = None,
                 api_url: str = "https://api.github.com", github_url: str = GITHUB_URL,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        if not valid_repo(repo):
            raise ValueError(f"a GitHub repo must look like 'owner/name', not {repo!r}")
        self.repo = repo
        self.base = base
        self._token = token
        self.api = GitHubApi(api_url, transport)
        self.github_url = github_url.rstrip("/")

    async def ship(self, workspace: Path, request: ShipRequest) -> ShipResult:
        committed = await asyncio.to_thread(commit_fix_branch, workspace, request)
        token = await self._token()
        register_secret(token)
        info = await self.api.call("GET", f"/repos/{self.repo}", token)
        default = info.get("default_branch") if isinstance(info, dict) else None
        if not isinstance(default, str) or not default:
            raise GitHubError("GitHub sent an unexpected answer for the repo")
        if committed.branch in (default, self.base):
            raise GitHubError(f"refusing to push to {committed.branch!r}: it is the base branch")
        await asyncio.to_thread(self._push, workspace, committed.branch, token)
        pr = await self.api.call("POST", f"/repos/{self.repo}/pulls", token, expect=(201,), json={
            "title": request.title[:250], "head": committed.branch, "base": self.base or default,
            "body": pr_body(request, committed.files), "maintainer_can_modify": True})
        if not isinstance(pr, dict) or not isinstance(pr.get("html_url"), str) or not isinstance(pr.get("number"), int):
            raise GitHubError("GitHub sent an unexpected answer for the pull request")
        return ShipResult(branch=committed.branch, commit=committed.commit, files=committed.files, pushed=True,
                          pr_url=pr["html_url"], pr_number=pr["number"])

    def _push(self, workspace: Path, branch: str, token: str) -> None:
        """A plain (never forced) push of the new branch, to the repo's URL (not the workspace's `origin`)."""
        url = f"{self.github_url}/{self.repo}.git"
        git(workspace, "push", "-q", "--no-verify", url, f"refs/heads/{branch}:refs/heads/{branch}",
            env=git_auth_env(token, self.github_url))
