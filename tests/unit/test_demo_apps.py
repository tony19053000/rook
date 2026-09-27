"""ROOK-039: the three demo apps (shop-app, billing-service, wallet-api) on the hosted path, in replay mode.

Each app runs exactly as the hosted server runs it: its deploy/demos/allowlist.yaml entry (pointed at a local
build of the pinned SHA), a ProcessSandbox subprocess started from the run's workspace copy, and the entry's
allowlisted `test` command. A guest approves the app's main rule; every Bob call replays a committed recording
(`tests/fixtures/recordings/hosted_<app>/`), so a run finds the planted bug, shrinks it, diagnoses it, fixes it
and verifies the fix for 0 coins.

The apps are not in this repo. Build them once (network, about a minute; needs node, npm, go and uv):

    deploy/demos/build-demos.sh deploy/demos/repos.txt ~/.cache/rook/demos

(or set ROOK_DEMOS_DIR to such a folder). Without a build, or without node / go, the app's tests are skipped.

To record the calls that miss (costs Bobcoins, run by hand, one app at a time):

    source ~/.bob-key.env
    export PATH=~/.nvm/versions/node/v24.21.0/bin:$PATH
    ROOK_RECORD_DIR=tests/fixtures/recordings/hosted_<app> ROOK_DEMO=<app> \\
        uv run pytest -m bob -s tests/unit/test_demo_apps.py

A recording pass with a live Surgeon cannot verify (02 section 8); run it again until nothing misses. Then
replace local paths in the new files (`/tmp/pytest-of-<user>/...` becomes `/workspace`).
"""

import os
import re
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from session_helpers import answer_questions, history
from test_session_recorded import RECORDINGS, HybridClient

from rook.core.events import EVENT_TYPES, EventBus, clear_secrets
from rook.core.session import Session, SessionOptions
from rook.core.workspace import COPY_IGNORE, RepoSpec
from rook.sandbox.allowlist import Allowlist, AllowlistEntry
from rook.sandbox.process import ProcessSandbox
from rook.server.config import load_demo_repos
from rook.server.routes.runs import REPLAY_SEARCH

ROOT = Path(__file__).parents[2]
DEMOS = ROOT / "deploy" / "demos"
IMAGE_DEMOS = "/opt/rook/demos"  # app_dir's parent in the hosted image
DEMOS_DIR = Path(os.environ.get("ROOK_DEMOS_DIR", "~/.cache/rook/demos")).expanduser()
BUDGET = float(os.environ.get("ROOK_RECORD_BUDGET", "1.0"))  # a recording pass's cap (coins); replay: 0
REPLAY_SECONDS = 60.0  # ROOK-039: each bug in under a minute


@dataclass(frozen=True)
class Demo:
    name: str
    repo: str
    language: str
    toolchain: str  # the binary the app needs on this machine


DEMO_APPS = {
    "shop-app": Demo("shop-app", "tony19053000/shop-app", "JavaScript", "node"),
    "billing-service": Demo("billing-service", "tony19053000/billing-service", "Python", "python"),
    "wallet-api": Demo("wallet-api", "tony19053000/wallet-api", "Go", "go"),
}


# The rule each app's committed recordings approve (the guest's pick when they were made).
RECORDED_RULE = {"shop-app": "refunded_total_le_order_total", "wallet-api": "wallet_balance_non_negative"}
VERIFIED = {"shop-app"}  # apps whose recorded hosted replay ends "Fixed and verified"


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


# --- the deployed config (always runs) ---


def raw_entries() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load((DEMOS / "allowlist.yaml").read_text())
    return {e["repo"]: e for e in raw["entries"]}


def manifest() -> list[list[str]]:
    lines = (DEMOS / "repos.txt").read_text().splitlines()
    return [ln.split() for ln in lines if ln.strip() and not ln.startswith("#")]


def test_every_demo_app_is_pinned_and_allowlisted_and_offered_only_once_verified() -> None:
    allowlist = Allowlist.from_yaml(DEMOS / "allowlist.yaml")
    catalog = {d.ref for d in load_demo_repos(DEMOS / "demos.yaml")}
    pinned = {ref: (sha, url, recipe) for ref, sha, url, recipe in manifest()}
    assert set(pinned) == {d.repo for d in DEMO_APPS.values()}
    for demo in DEMO_APPS.values():
        sha, url, recipe = pinned[demo.repo]
        assert url == f"https://github.com/{demo.repo}.git"
        assert recipe == {"JavaScript": "npm", "Python": "uv", "Go": "go"}[demo.language]
        entry = allowlist.get(demo.repo, sha)
        assert entry.app_dir == Path(IMAGE_DEMOS) / demo.name
        assert entry.health_path == "/health" and entry.port_env == "PORT"
        assert entry.command_timeout <= 600
        # Only an app whose recorded hosted replay ends "Fixed and verified" is offered (the server runs only
        # catalog repos, so an allowlist entry alone starts nothing).
        assert (demo.repo in catalog) == (demo.name in VERIFIED)
    assert "rook-demo/minishop" in catalog


def test_demo_apps_bind_loopback_and_keep_data_in_the_run_temp_dir() -> None:
    entries = raw_entries()
    shop, billing, wallet = (entries[DEMO_APPS[n].repo] for n in DEMO_APPS)
    assert shop["env"]["HOST"] == "127.0.0.1" and wallet["env"]["HOST"] == "127.0.0.1"
    assert "127.0.0.1" in billing["start"]
    assert billing["db_env"] == wallet["db_env"] == "DATABASE_PATH"  # a fresh SQLite file per run
    # Go: the image's module and build caches, no toolchain or module download at run time.
    assert wallet["env"]["GOTOOLCHAIN"] == "local" and wallet["env"]["GOPROXY"] == "off"
    assert wallet["env"]["GOMODCACHE"].startswith(IMAGE_DEMOS) and wallet["env"]["GOCACHE"].startswith(IMAGE_DEMOS)
    # The test commands come from app_dir (the workspace copy has no node_modules / .venv) and take one path.
    assert shop["commands"]["test"][1] == f"{IMAGE_DEMOS}/shop-app/node_modules/vitest/vitest.mjs"
    assert billing["commands"]["test"][0] == f"{IMAGE_DEMOS}/billing-service/.venv/bin/python"
    assert "commands" not in wallet  # `go test` takes no file path: Rook's HTTP fallback test is used
    assert {"node_modules", ".venv"} <= set(COPY_IGNORE)


def test_build_demos_puts_go_caches_next_to_the_apps() -> None:
    text = (DEMOS / "build-demos.sh").read_text()
    assert 'GOMODCACHE="$dest/.go/mod" GOCACHE="$dest/.go/cache" go build ./...' in text


# --- the apps on this machine ---


def _go_binary(app_dir: Path, env: dict[str, str]) -> str | None:
    """The Go toolchain the app wants (go.mod may need a newer one than the go on PATH)."""
    go = shutil.which("go")
    if go is None:
        return None
    proc = subprocess.run([go, "env", "GOROOT"], cwd=app_dir, env={**os.environ, **env}, capture_output=True,
                          text=True, check=False, timeout=120)
    root = proc.stdout.strip()
    return str(Path(root) / "bin" / "go") if proc.returncode == 0 and root else None


def local_entry(name: str) -> AllowlistEntry:
    """The deployed allowlist entry with the image's paths mapped to this machine (skips if not built)."""
    demo = DEMO_APPS[name]
    app_dir = DEMOS_DIR / name
    if not app_dir.is_dir():
        pytest.skip(f"{name} is not built: deploy/demos/build-demos.sh deploy/demos/repos.txt {DEMOS_DIR}")
    raw = raw_entries()[demo.repo]

    def local(value: str) -> str:
        return value.replace(IMAGE_DEMOS, str(DEMOS_DIR))

    env = {k: local(v) for k, v in raw.get("env", {}).items()}
    tools = {"/usr/local/bin/node": shutil.which("node")}
    if demo.toolchain == "go":
        tools["/usr/local/go/bin/go"] = _go_binary(app_dir, {k: v for k, v in env.items() if k != "GOTOOLCHAIN"})
    for image_path, found in tools.items():
        uses = image_path in raw["start"] or any(image_path in c for c in raw.get("commands", {}).values())
        if uses and found is None:
            pytest.skip(f"{name} needs {Path(image_path).name} on this machine")

    def argv(values: list[str]) -> list[str]:
        return [tools.get(v) or local(v) for v in values]

    return AllowlistEntry(**{**raw, "app_dir": app_dir, "start": argv(raw["start"]), "env": env,
                             "commands": {k: argv(v) for k, v in raw.get("commands", {}).items()}})


def workspace_copy(app_dir: Path, dest: Path) -> Path:
    shutil.copytree(app_dir, dest, ignore=shutil.ignore_patterns(*COPY_IGNORE))
    return dest


def link_node_modules(workspaces_root: Path, entry: AllowlistEntry) -> None:
    """What the image's `/node_modules` link does: Node finds app_dir's modules from a workspace copy."""
    if (entry.app_dir / "node_modules").is_dir():
        workspaces_root.mkdir(parents=True, exist_ok=True)
        (workspaces_root / "node_modules").symlink_to(entry.app_dir / "node_modules")


@pytest.mark.parametrize("name", list(DEMO_APPS))
def test_each_demo_app_starts_from_a_workspace_copy(tmp_path: Path, name: str) -> None:
    entry = local_entry(name)
    root = tmp_path / "workspaces"
    link_node_modules(root, entry)
    ws = workspace_copy(entry.app_dir, root / "r_abcd")
    sandbox = ProcessSandbox(entry.repo, entry.commit, allowlist=Allowlist([entry]), workspace=ws)
    try:
        base = sandbox.start()
        assert httpx.get(base + "/health", timeout=5).status_code == 200
        assert sandbox.run_dir == ws
    finally:
        sandbox.stop()


# --- a hosted guest run ---


class CappedClient(HybridClient):
    """Replays what is recorded; records a missing call only while under BUDGET coins."""

    async def call(self, agent_id: str, slug: str, prompt: str, workspace: Any, output_model: Any,
                   max_turns: int = 8, max_cost: float | None = None) -> Any:
        if self.live is not None and self.live_cost >= BUDGET:
            raise RuntimeError(f"recording budget of {BUDGET} coins spent")
        return await super().call(agent_id, slug, prompt, workspace, output_model, max_turns, max_cost)


def recordings(name: str) -> Path:
    return RECORDINGS / f"hosted_{name}"


def pick(rules: list[dict[str, Any]], patterns: str) -> list[str]:
    """Recording only (ROOK_PICK_RULE): the first accepted rule matching the first pattern that matches any
    (comma-separated regexes over id, text and check), for a new recording whose rule ids are not known yet."""
    for pattern in patterns.split(","):
        for r in rules:
            if r["accepted"] and re.search(pattern, f"{r['id']} {r['text']} {r['check']}", re.IGNORECASE):
                return [r["id"]]
    return []


def guest(name: str) -> Callable[[dict[str, Any]], Any]:
    patterns = os.environ.get("ROOK_PICK_RULE", "")
    rule = "" if patterns else RECORDED_RULE.get(name, "")

    def answer(data: dict[str, Any]) -> Any:
        if data["kind"] == "approve_rules":
            rules = data["payload"]["rules"]
            print("proposed rules:\n" + "\n".join(f"  {r['id']} accepted={r['accepted']}: {r['check']}"
                                                   for r in rules))
            if patterns:
                return pick(rules, patterns) or "none"
            return [rule] if any(r["id"] == rule and r["accepted"] for r in rules) else "none"
        if data["kind"] == "menu":  # a failed agent: end with a report, like the smoke tests
            return "report"
        return "yes"

    return answer


async def hosted_run(tmp_path: Path, name: str, record_dir: Path | None = None,
                     **search: Any) -> tuple[Session, CappedClient, float]:
    entry = local_entry(name)
    replays = tmp_path / "recordings"
    replays.mkdir()
    for path in sorted(recordings(name).glob("*")):
        shutil.copy2(path, replays / path.name)
    clients: list[CappedClient] = []

    def client(bus: EventBus, run_id: str, ws: Path) -> CappedClient:
        clients.append(CappedClient(bus, run_id, replays, record_dir))
        return clients[0]

    root = tmp_path / "workspaces"
    link_node_modules(root, entry)
    # The replay server's options (routes/runs.py).
    options = SessionOptions(auto=False, hosted=True, **{**REPLAY_SEARCH, **search})
    session = Session(RepoSpec(kind="demo", ref=entry.repo, commit=entry.commit), "find and fix a bug", options,
                      workspaces_root=root, client_factory=client, allowlist=Allowlist([entry]),
                      run_workspace=True)
    asked = answer_questions(session, guest(name))
    started = time.monotonic()
    result = await session.run()
    elapsed = time.monotonic() - started
    await asked
    print(f"\n[{name}] {result.status} in {elapsed:.1f}s: {result.summary}\nmissing recordings: "
          f"{clients[0].missing}")
    for e in history(session):
        if e.type in ("counterexample.saved", "diagnosis.ready", "verify.done", "verify.step", "fix.ready", "run.log", "test.finished"):
            print(f"  {e.type}: {str(e.data)[:400]}")
    return session, clients[0], elapsed


def checked_events(session: Session) -> list[Any]:
    events = history(session)
    for e in events:
        EVENT_TYPES[e.type].model_validate(e.data)
    return events


def replayed_for_free(session: Session, client: CappedClient) -> None:
    assert client.missing == [], f"no recording for: {client.missing}"
    finished = [e.data for e in history(session) if e.type == "agent.finished"]
    assert finished and all(f["recorded"] for f in finished)
    assert session.state.coins_spent == 0.0 and client.replayer.total_cost == 0.0


async def test_a_hosted_shop_app_replay_run_finds_fixes_and_verifies_the_refund_bug(tmp_path: Path) -> None:
    """shop-app's recorded guest run (the featured rule: refunds never add up to more than the order total): the
    search breaks it (an order is cancelled, which refunds it in full, then an admin refunds it again), the run
    shrinks and replays it, diagnoses the refund guard in src/routes/orders.js, fixes it, and VERIFY passes all
    four checks (replay, the project's vitest suite, the Surgeon's native regression test, a fresh search).
    Every Bob call replays a recording: 0 coins, well under a minute."""
    if not any(recordings("shop-app").glob("*.ndjson")):
        pytest.skip("no recordings for shop-app")
    session, client, elapsed = await hosted_run(tmp_path, "shop-app")
    replayed_for_free(session, client)
    result = session.result
    assert result is not None and result.status == "done" and result.verified, result
    assert result.summary.startswith("Fixed and verified cx_001")
    events = checked_events(session)
    types = [e.type for e in events]
    order = ["violation.found", "counterexample.saved", "diagnosis.ready", "fix.ready", "verify.done",
             "fix.committed", "run.finished"]
    positions = [types.index(t) for t in order]
    assert positions == sorted(positions), order
    saved = next(e.data for e in events if e.type == "counterexample.saved")
    assert saved["rule_id"] == RECORDED_RULE["shop-app"]
    assert [s["action"] for s in saved["steps"]][-1] == "refund_order"
    (diagnosis,) = [e.data for e in events if e.type == "diagnosis.ready"]
    assert diagnosis["file"] == "src/routes/orders.js" and diagnosis["line"] == 264 and diagnosis["reviewed"]
    steps = {e.data["check"]: e.data["status"] for e in events
             if e.type == "verify.step" and e.data["status"] != "running"}
    assert steps == dict.fromkeys(["replay", "project_tests", "regression_test", "fresh_search"], "passed")
    assert elapsed < REPLAY_SECONDS, f"shop-app replay took {elapsed:.0f}s"


def test_shop_app_is_offered_with_its_recorded_rule() -> None:
    (demo,) = [d for d in load_demo_repos(DEMOS / "demos.yaml") if d.name == "shop-app"]
    assert demo.ref == DEMO_APPS["shop-app"].repo and demo.language == "JavaScript"
    assert demo.featured_rule == RECORDED_RULE["shop-app"]
    assert demo.commit == next(sha for ref, sha, _, _ in manifest() if ref == demo.ref)


@pytest.mark.parametrize("name", list(DEMO_APPS))
def test_demo_recordings_hold_no_local_paths_or_secrets(name: str) -> None:
    for path in sorted(recordings(name).glob("*")):
        text = path.read_text(encoding="utf-8")
        assert "pytest-of-" not in text and "/home/" not in text and "/tmp/" not in text, path.name
        assert "bob_prod_" not in text and "eyJ" not in text, path.name
        key = os.environ.get("BOB_API_KEY")
        assert not key or key not in text


@pytest.mark.bob
async def test_record_the_missing_calls_of_a_hosted_demo_run(tmp_path: Path) -> None:
    """Replays what is recorded and records only the calls that miss. Costs Bobcoins."""
    if not os.environ.get("BOB_API_KEY"):
        pytest.skip("BOB_API_KEY is not set (source ~/.bob-key.env)")
    name = os.environ.get("ROOK_DEMO", "")
    if name not in DEMO_APPS:
        pytest.skip(f"set ROOK_DEMO to one of {sorted(DEMO_APPS)}")
    record_dir = os.environ.get("ROOK_RECORD_DIR")
    target = Path(record_dir).resolve() if record_dir else tmp_path / "rec"
    target.mkdir(parents=True, exist_ok=True)
    _, client, elapsed = await hosted_run(tmp_path, name, target)
    print(f"recorded calls: {client.missing}; coins used: {client.live_cost:.4f}; {elapsed:.0f}s")
