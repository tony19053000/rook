"""Post `rook-report.md` as one pull-request comment (the GitHub Action, ROOK-032).

The comment carries a hidden marker, so a second run updates the Rook comment instead of adding another.
Only comments written by a bot are updated, so a person who pastes the marker cannot redirect the edit.

Security (03_SECURITY_ACCESS.md §2): the token is read from `GITHUB_TOKEN` (never argv), is registered with
the redaction filter, and is never printed: `--dry-run` shows the requests with the Authorization header
redacted. Requests go only to `GITHUB_API_URL` (https), with the repo and PR number taken from the event
file and validated. A comment that cannot be posted is a warning, not a failure: the job's result is
Rook's exit code (a fork PR's token is read-only, for example).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from rook.core.events import REDACTED, redact_text, register_secret

MARKER = "<!-- rook-report -->"
MAX_COMMENT = 65_536  # GitHub's limit on a comment body, in characters
TRUNCATED_NOTE = "\n\n_The report was truncated to fit a GitHub comment; the full report is in the job summary._\n"
MISSING_REPORT = ("## Rook: ! No report\n\nRook did not write `rook-report.md` (the run failed before it "
                  "could). See the job log.\n")
PR_EVENTS = frozenset({"pull_request", "pull_request_target"})
DEFAULT_API = "https://api.github.com"
API_VERSION = "2022-11-28"
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_FENCE = re.compile(r"^~~~", re.MULTILINE)


class SkipComment(Exception):
    """Nothing to comment on (not a pull-request event)."""


@dataclass(frozen=True)
class PullRequest:
    repo: str  # owner/name
    number: int


@dataclass(frozen=True)
class ApiRequest:
    method: str
    url: str
    json: dict[str, Any] | None = None


def pull_request(event_name: str, event: Any) -> PullRequest:
    """The PR a `pull_request` / `pull_request_target` event is about; SkipComment for any other event."""
    if event_name not in PR_EVENTS:
        raise SkipComment(f"not a pull request event ({event_name or 'unknown'})")
    pr = event.get("pull_request") if isinstance(event, dict) else None
    repo = (event.get("repository") or {}).get("full_name") if isinstance(event, dict) else None
    number = pr.get("number") if isinstance(pr, dict) else None
    if not isinstance(repo, str) or not _REPO.fullmatch(repo) or ".." in repo:
        raise ValueError("the event has no valid repository.full_name")
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise ValueError("the event has no valid pull_request.number")
    return PullRequest(repo, number)


def comment_body(report_md: str | None, limit: int = MAX_COMMENT) -> str:
    """The marker plus the report, cut to `limit` characters (closing a code block the cut left open)."""
    text = f"{MARKER}\n{report_md if report_md is not None else MISSING_REPORT}"
    if len(text) <= limit:
        return text
    room = limit - len(TRUNCATED_NOTE) - len("\n~~~")
    cut = text[:room]
    if (newline := cut.rfind("\n")) > room - 2_000:
        cut = cut[:newline]  # end on a whole line
    if len(_FENCE.findall(cut)) % 2:
        cut += "\n~~~"
    return cut + TRUNCATED_NOTE


def find_rook_comment(comments: Sequence[Any]) -> int | None:
    """The id of the existing Rook comment: a bot's comment that starts with the marker."""
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        user = comment.get("user")
        user = user if isinstance(user, dict) else {}
        body, comment_id = comment.get("body"), comment.get("id")
        if (user.get("type") == "Bot" and isinstance(body, str) and body.startswith(MARKER)
                and isinstance(comment_id, int)):
            return comment_id
    return None


def api_base(url: str | None) -> str:
    base = (url or DEFAULT_API).rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("GITHUB_API_URL must be an https URL without credentials")
    return base


def list_request(api: str, pr: PullRequest, page: int = 1) -> ApiRequest:
    return ApiRequest("GET", f"{api}/repos/{pr.repo}/issues/{pr.number}/comments?per_page=100&page={page}")


def upsert_request(api: str, pr: PullRequest, body: str, existing: int | None) -> ApiRequest:
    """Create the comment, or update the one Rook wrote before."""
    if existing is None:
        return ApiRequest("POST", f"{api}/repos/{pr.repo}/issues/{pr.number}/comments", {"body": body})
    return ApiRequest("PATCH", f"{api}/repos/{pr.repo}/issues/comments/{existing}", {"body": body})


def headers(token: str) -> dict[str, str]:
    return {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": API_VERSION,
            "Authorization": f"Bearer {token}", "User-Agent": "rook-action"}


def fetch_comments(send: Callable[[ApiRequest], httpx.Response], api: str, pr: PullRequest,
                   max_pages: int = 10) -> list[Any]:
    comments: list[Any] = []
    for page in range(1, max_pages + 1):
        response = send(list_request(api, pr, page))
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            break
        comments += batch
        if len(batch) < 100:
            break
    return comments


def read_report(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, IsADirectoryError, UnicodeDecodeError):
        return None


def dry_run_text(requests: Sequence[ApiRequest], token: str) -> str:
    """The exact requests as JSON, with the Authorization header redacted."""
    shown = {k: (f"Bearer {REDACTED}" if k == "Authorization" else v) for k, v in headers(token).items()}
    out = [{**asdict(r), "headers": shown} for r in requests]
    return redact_text(json.dumps(out, indent=2, ensure_ascii=False))


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="rook-pr-comment", description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, default=Path("rook-report.md"), help="The report to post.")
    parser.add_argument("--event", type=Path, help="The event JSON (default: $GITHUB_EVENT_PATH).")
    parser.add_argument("--event-name", help="The event name (default: $GITHUB_EVENT_NAME).")
    parser.add_argument("--dry-run", action="store_true", help="Print the requests instead of sending them.")
    parser.add_argument("--existing", type=Path,
                        help="With --dry-run: a JSON list of the PR's comments (default: none).")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None, environ: dict[str, str] | None = None) -> int:
    args = _parse(argv)
    env = dict(os.environ) if environ is None else environ
    token = env.get("GITHUB_TOKEN", "")
    register_secret(token)
    try:
        event_path = args.event or (Path(env["GITHUB_EVENT_PATH"]) if env.get("GITHUB_EVENT_PATH") else None)
        if event_path is None:
            raise ValueError("no event file (--event or GITHUB_EVENT_PATH)")
        event = json.loads(event_path.read_text(encoding="utf-8"))
        pr = pull_request(args.event_name or env.get("GITHUB_EVENT_NAME", ""), event)
        api = api_base(env.get("GITHUB_API_URL"))
    except SkipComment as exc:
        print(f"rook-pr-comment: skipped: {exc}")
        return 0
    except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
        print(redact_text(f"::warning::rook-pr-comment: {exc}"))
        return 0
    report = read_report(args.report)
    body = comment_body(redact_text(report) if report is not None else None)  # the bus redacted it too
    if args.dry_run:
        existing = json.loads(args.existing.read_text(encoding="utf-8")) if args.existing else []
        comment_id = find_rook_comment(existing if isinstance(existing, list) else [])
        print(dry_run_text([list_request(api, pr), upsert_request(api, pr, body, comment_id)], token))
        return 0
    if not token:
        print("::warning::rook-pr-comment: GITHUB_TOKEN is not set; no comment posted")
        return 0
    return _send(api, pr, body, token)


def _send(api: str, pr: PullRequest, body: str, token: str,
          transport: httpx.BaseTransport | None = None) -> int:
    with httpx.Client(headers=headers(token), timeout=30.0, follow_redirects=False,
                      transport=transport) as client:
        def send(req: ApiRequest) -> httpx.Response:
            return client.request(req.method, req.url, json=req.json)

        try:
            comment_id = find_rook_comment(fetch_comments(send, api, pr))
            response = send(upsert_request(api, pr, body, comment_id))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            print(redact_text(f"::warning::rook-pr-comment: could not post the comment: {exc}"))
            return 0
    print(f"rook-pr-comment: {'updated' if comment_id else 'created'} the Rook comment on #{pr.number}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
