"""ROOK-032: the GitHub Action (`action.yml`) and its PR comment step (`rook-pr-comment`).

AC: a workflow example in the README; a dry run on a fixture PR event prints the exact comment request.
No network: the live path is driven through an httpx MockTransport.
"""

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from rook.core.events import clear_secrets
from rook.github import pr_comment as pc

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "tests" / "fixtures" / "github_action"
EVENT = FIX / "pull_request.json"
REPORT = FIX / "rook-report.md"
TOKEN = "ghs_FAKEfixtureTOKEN0000000000000000000"
OTHER_SECRET = "plain-secret-without-a-known-prefix-42"
SHA = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


def env(**extra: str) -> dict[str, str]:
    return {"GITHUB_TOKEN": TOKEN, "GITHUB_API_URL": "https://api.github.com", **extra}


def dry_run(capsys: pytest.CaptureFixture[str], *args: str, environ: dict[str, str] | None = None) -> Any:
    code = pc.main(["--dry-run", "--event-name", "pull_request", *args], environ or env())
    out = capsys.readouterr().out
    assert code == 0
    return json.loads(out), out


# --- the dry run (AC) -----------------------------------------------------------------------------------


def test_dry_run_on_the_fixture_pr_creates_one_comment(capsys: pytest.CaptureFixture[str]) -> None:
    requests, _ = dry_run(capsys, "--event", str(EVENT), "--report", str(REPORT))
    listing, write = requests
    assert listing["method"] == "GET" and listing["json"] is None
    assert listing["url"] == ("https://api.github.com/repos/tony19053000/minishop-demo/issues/7/comments"
                              "?per_page=100&page=1")
    assert write["method"] == "POST"
    assert write["url"] == "https://api.github.com/repos/tony19053000/minishop-demo/issues/7/comments"
    assert write["json"] == {"body": f"{pc.MARKER}\n{REPORT.read_text(encoding='utf-8')}"}
    assert write["headers"]["Authorization"] == "Bearer [REDACTED]"
    assert write["headers"]["X-GitHub-Api-Version"] == pc.API_VERSION


def test_dry_run_updates_the_existing_rook_comment(capsys: pytest.CaptureFixture[str]) -> None:
    requests, _ = dry_run(capsys, "--event", str(EVENT), "--report", str(REPORT),
                          "--existing", str(FIX / "comments_with_rook.json"))
    write = requests[1]
    # 101 is a person quoting the marker, 102 a bot without it: only the bot's marked comment (103) is ours.
    assert write["method"] == "PATCH"
    assert write["url"] == "https://api.github.com/repos/tony19053000/minishop-demo/issues/comments/103"
    assert write["json"]["body"].startswith(pc.MARKER)


def test_dry_run_creates_when_no_rook_comment_exists(capsys: pytest.CaptureFixture[str]) -> None:
    requests, _ = dry_run(capsys, "--event", str(EVENT), "--report", str(REPORT),
                          "--existing", str(FIX / "comments_without_rook.json"))
    assert requests[1]["method"] == "POST"


def test_event_path_comes_from_the_environment(capsys: pytest.CaptureFixture[str]) -> None:
    requests, _ = dry_run(capsys, "--report", str(REPORT), environ=env(GITHUB_EVENT_PATH=str(EVENT)))
    assert requests[1]["url"].endswith("/issues/7/comments")


def test_no_secret_in_the_dry_run_output(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    report = tmp_path / "rook-report.md"
    report.write_text(f"## Rook\n\nleaked {OTHER_SECRET} and {TOKEN}\n", encoding="utf-8")
    environ = env(GITHUB_TOKEN=OTHER_SECRET, BOB_API_KEY="bob_prod_fixturekey123")
    _, out = dry_run(capsys, "--event", str(EVENT), "--report", str(report), environ=environ)
    assert OTHER_SECRET not in out and TOKEN not in out and "bob_prod_" not in out
    assert "[REDACTED]" in out


def test_missing_report_posts_a_short_note(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    requests, _ = dry_run(capsys, "--event", str(EVENT), "--report", str(tmp_path / "nope.md"))
    assert requests[1]["json"]["body"] == f"{pc.MARKER}\n{pc.MISSING_REPORT}"


@pytest.mark.parametrize("name,event", [("push", "push.json"), ("workflow_dispatch", "pull_request.json"),
                                         ("", "pull_request.json")])
def test_non_pr_events_skip_cleanly(capsys: pytest.CaptureFixture[str], name: str, event: str) -> None:
    code = pc.main(["--dry-run", "--event-name", name, "--event", str(FIX / event), "--report", str(REPORT)],
                   env())
    out = capsys.readouterr().out
    assert code == 0 and out.startswith("rook-pr-comment: skipped: not a pull request event")
    assert "https://" not in out


def test_pull_request_target_is_a_pr_event() -> None:
    assert pc.pull_request("pull_request_target", json.loads(EVENT.read_text())) == pc.PullRequest(
        "tony19053000/minishop-demo", 7)


@pytest.mark.parametrize("event", [
    {"pull_request": {"number": 7}, "repository": {"full_name": "a/b/../c"}},
    {"pull_request": {"number": 7}, "repository": {"full_name": "owner/name?x=1"}},
    {"pull_request": {"number": "7"}, "repository": {"full_name": "owner/name"}},
    {"pull_request": {"number": True}, "repository": {"full_name": "owner/name"}},
    {"repository": {"full_name": "owner/name"}},
    [],
])
def test_bad_events_are_refused(event: Any) -> None:
    with pytest.raises(ValueError):
        pc.pull_request("pull_request", event)


def test_a_bad_event_file_warns_and_does_not_fail(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    bad = tmp_path / "event.json"
    bad.write_text("{not json", encoding="utf-8")
    assert pc.main(["--dry-run", "--event-name", "pull_request", "--event", str(bad)], env()) == 0
    assert capsys.readouterr().out.startswith("::warning::")


@pytest.mark.parametrize("url", ["http://api.github.com", "https://user:pw@api.github.com", "file:///etc"])
def test_only_https_api_urls(url: str) -> None:
    with pytest.raises(ValueError):
        pc.api_base(url)


def test_default_api_url() -> None:
    assert pc.api_base(None) == "https://api.github.com"
    assert pc.api_base("https://ghe.example.com/api/v3/") == "https://ghe.example.com/api/v3"


# --- truncation -----------------------------------------------------------------------------------------


def test_short_reports_are_not_truncated() -> None:
    text = REPORT.read_text(encoding="utf-8")
    assert pc.comment_body(text) == f"{pc.MARKER}\n{text}"


def test_long_reports_fit_githubs_limit() -> None:
    report = "## Rook\n\n" + "\n".join(f"{i}. `step {i}`" for i in range(20_000))
    body = pc.comment_body(report)
    assert len(body) <= pc.MAX_COMMENT == 65_536
    assert body.startswith(pc.MARKER) and body.endswith(pc.TRUNCATED_NOTE)
    kept = body[: -len(pc.TRUNCATED_NOTE)]
    assert re.fullmatch(r"\d+\. `step \d+`", kept.splitlines()[-1])  # cut on a whole line


def test_truncation_closes_an_open_code_block() -> None:
    report = "## Rook\n\nObserved:\n\n~~~\n" + "x" * 80_000 + "\n~~~\n"
    body = pc.comment_body(report)
    assert len(body) <= pc.MAX_COMMENT
    assert len(re.findall(r"^~~~", body, re.MULTILINE)) == 2


def test_a_single_huge_line_still_fits() -> None:
    body = pc.comment_body("y" * 200_000, limit=1_000)
    assert len(body) <= 1_000 and body.startswith(pc.MARKER)


# --- sending (mocked GitHub) ----------------------------------------------------------------------------


def mock_github(existing_pages: list[list[dict[str, Any]]], write_status: int = 201) -> tuple[
        httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            page = int(request.url.params["page"])
            return httpx.Response(200, json=existing_pages[page - 1] if page <= len(existing_pages) else [])
        return httpx.Response(write_status, json={"id": 999})

    return httpx.MockTransport(handle), seen


def bot(comment_id: int, body: str) -> dict[str, Any]:
    return {"id": comment_id, "user": {"type": "Bot"}, "body": body}


PR = pc.PullRequest("tony19053000/minishop-demo", 7)
API = "https://api.github.com"


def test_send_pages_through_comments_and_updates_ours(capsys: pytest.CaptureFixture[str]) -> None:
    first = [bot(i, "other") for i in range(100)]
    transport, seen = mock_github([first, [bot(555, f"{pc.MARKER}\nold")]])
    assert pc._send(API, PR, "new body", TOKEN, transport) == 0
    assert [(r.method, r.url.path) for r in seen] == [
        ("GET", "/repos/tony19053000/minishop-demo/issues/7/comments"),
        ("GET", "/repos/tony19053000/minishop-demo/issues/7/comments"),
        ("PATCH", "/repos/tony19053000/minishop-demo/issues/comments/555")]
    assert json.loads(seen[-1].content) == {"body": "new body"}
    assert seen[-1].headers["Authorization"] == f"Bearer {TOKEN}"
    out = capsys.readouterr().out
    assert "updated the Rook comment on #7" in out and TOKEN not in out


def test_send_creates_when_none(capsys: pytest.CaptureFixture[str]) -> None:
    transport, seen = mock_github([[]])
    assert pc._send(API, PR, "body", TOKEN, transport) == 0
    assert seen[-1].method == "POST" and seen[-1].url.path.endswith("/issues/7/comments")
    assert "created" in capsys.readouterr().out


def test_a_refused_comment_warns_without_failing_the_job(capsys: pytest.CaptureFixture[str]) -> None:
    transport, _ = mock_github([[]], write_status=403)  # e.g. a fork PR's read-only token
    assert pc._send(API, PR, "body", TOKEN, transport) == 0
    out = capsys.readouterr().out
    assert out.startswith("::warning::rook-pr-comment: could not post the comment") and TOKEN not in out


def test_no_token_warns_and_sends_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    code = pc.main(["--event-name", "pull_request", "--event", str(EVENT), "--report", str(REPORT)],
                   {"GITHUB_API_URL": API})
    assert code == 0 and "GITHUB_TOKEN is not set" in capsys.readouterr().out


# --- action.yml and the README example -------------------------------------------------------------------


def action() -> dict[str, Any]:
    data = yaml.safe_load((ROOT / "action.yml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_action_is_a_composite_that_runs_rook_ci_auto_and_comments() -> None:
    data = action()
    assert data["runs"]["using"] == "composite"
    scripts = "\n".join(s.get("run", "") for s in data["runs"]["steps"])
    assert "run --ci" in scripts and "args+=(--auto)" in scripts and "rook-pr-comment" in scripts
    assert data["inputs"]["bob-mode"]["default"] == "replay"
    assert data["inputs"]["auto"]["default"] == "true"
    names = [s.get("name") for s in data["runs"]["steps"]]
    # The comment is posted before the job fails on a broken rule.
    assert names.index("Comment on the pull request") < names.index("Fail when a rule is broken")


def test_action_pins_third_party_actions_by_sha() -> None:
    uses = [s["uses"] for s in action()["runs"]["steps"] if "uses" in s]
    assert uses and all(SHA.match(u) for u in uses), uses


def test_action_never_interpolates_into_scripts() -> None:
    for step in action()["runs"]["steps"]:
        assert "${{" not in step.get("run", ""), step.get("name")
        assert all("github.event" not in str(v) for v in (step.get("env") or {}).values())


def test_action_gives_the_bob_key_only_where_needed() -> None:
    steps = action()["runs"]["steps"]
    with_key = [s.get("id") for s in steps if "BOB_API_KEY" in (s.get("env") or {})]
    assert with_key == ["mode", "rook"]
    mode = next(s for s in steps if s.get("id") == "mode")
    assert "::add-mask::" in mode["run"]
    rook = next(s for s in steps if s.get("id") == "rook")
    assert "steps.mode.outputs.mode == 'live'" in rook["env"]["BOB_API_KEY"]
    installs = [s for s in steps if s.get("name") == "Install Bob Shell"]
    assert installs and installs[0]["if"] == "steps.mode.outputs.mode == 'live'"


def readme_workflow() -> dict[Any, Any]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    section = text.split("## GitHub Action", 1)[1]
    block = re.search(r"```yaml\n(.*?)```", section, re.DOTALL)
    assert block, "README has no workflow example"
    data = yaml.safe_load(block.group(1))
    assert isinstance(data, dict)
    return data


def test_readme_has_a_safe_workflow_example() -> None:
    wf = readme_workflow()
    triggers = wf[True] if True in wf else wf["on"]  # YAML 1.1 reads a bare `on` key as True
    assert "pull_request" in triggers and "pull_request_target" not in triggers
    assert wf["permissions"] == {"contents": "read", "pull-requests": "write"}
    steps = wf["jobs"]["rook"]["steps"]
    third_party = [s["uses"] for s in steps if not s["uses"].startswith("tony19053000/rook@")]
    assert third_party and all(SHA.match(u) for u in third_party)
    rook = next(s for s in steps if s["uses"].startswith("tony19053000/rook@"))
    assert rook["with"]["bob-api-key"] == "${{ secrets.BOB_API_KEY }}"
    assert "pull_request_target" in (ROOT / "README.md").read_text(encoding="utf-8").split("## GitHub Action")[1]


def test_the_posted_body_is_redacted_like_the_dry_run(capsys: pytest.CaptureFixture[str], tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    report = tmp_path / "rook-report.md"
    report.write_text(f"## Rook\n\n{TOKEN}\n", encoding="utf-8")
    sent: list[str] = []

    def fake_send(api: str, pr: pc.PullRequest, body: str, token: str) -> int:
        sent.append(body)
        return 0

    monkeypatch.setattr(pc, "_send", fake_send)
    assert pc.main(["--event-name", "pull_request", "--event", str(EVENT), "--report", str(report)], env()) == 0
    assert sent == [f"{pc.MARKER}\n## Rook\n\n[REDACTED]\n"]
