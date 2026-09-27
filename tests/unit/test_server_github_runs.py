"""ROOK-041: hosted runs of a signed-in user's own GitHub repos.

Admission (guest 401, not configured 503, not linked / not your repo 403, busy / daily limit / coin cap 429),
`/me.can_run_github`, the session factory (live Bob, DockerSandbox on the access network, GitHubShipper with a
fresh token), the token never reaching events or logs, the Docker probe (same-path workspace mount, sandbox
network) and DockerSandbox / compose in access-network mode. GitHub is an httpx MockTransport; no real Bob,
Docker or network.
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from server_helpers import (
    ALICE,
    BOB,
    NEW_RUN,
    Factory,
    client_for,
    guest_headers,
    make_app,
    state_of,
    wait_for,
)
from test_github_app import FakeGitHub, callback, settings_for, start_install

from rook.agents.bob import BobClient
from rook.agents.schemas import SandboxPlan
from rook.core.events import REDACTED, EventBus, clear_secrets, now_ts, redact_text
from rook.core.session import Session, SessionOptions
from rook.core.workspace import RepoSpec, git, prepare_workspace
from rook.github.pr import GitHubShipper
from rook.sandbox import docker as docker_mod
from rook.sandbox.allowlist import DEFAULT_ALLOWLIST
from rook.sandbox.base import SandboxError
from rook.sandbox.compose import Hardening, render
from rook.sandbox.docker import DockerSandbox
from rook.server.config import ServerSettings
from rook.server.github_runs import BUSY, DockerProbe, same_path_mount
from rook.server.runs import GitHubAccess, RunSpec, default_session_factory
from rook.store.repo import RunRecord, Store

API = "/api/v1"
REPO = {"kind": "github", "ref": "alice/shop"}
GH_RUN = {"repo": REPO, "request": "find a refund bug", "options": {"auto": False}}


@pytest.fixture(autouse=True)
def _forget_secrets() -> Any:
    yield
    clear_secrets()


def gh_run_app(tmp_path: Path, fake: FakeGitHub, factory: Any = None, *, docker: bool = True,
               **extra: Any) -> Any:
    values = {**settings_for(), "bob_key_set": True, **extra}
    return make_app(tmp_path, factory, github_transport=httpx.MockTransport(fake), docker_ready=lambda: docker,
                    **values)


async def link(client: httpx.AsyncClient, fake: FakeGitHub, headers: dict[str, str], installation: int,
               repos: list[str]) -> None:
    state = await start_install(client, headers)
    fake.install(installation)
    fake.repos[installation] = [{"full_name": r, "private": True, "language": "Python"} for r in repos]
    assert (await callback(client, headers, installation, state)).status_code == 200


# --- admission ---


async def test_a_guest_gets_401_and_a_demo_still_runs(tmp_path: Path) -> None:
    fake = FakeGitHub()
    factory = Factory()
    app = gh_run_app(tmp_path, fake, factory)
    _, guest = guest_headers(app)
    async with client_for(app) as client:
        refused = await client.post(f"{API}/runs", json=GH_RUN, headers=guest)
        demo = await client.post(f"{API}/runs", json=NEW_RUN, headers=guest)
        for session in factory.sessions.values():
            session.cancel()
    assert refused.status_code == 401 and "Sign in" in refused.json()["detail"]
    assert demo.status_code == 200


@pytest.mark.parametrize("extra, docker", [
    ({"bob_key_set": False}, True),  # no BOB_API_KEY: GitHub runs need live Bob
    ({"github_runs_max": 0}, True),  # turned off
    ({}, False),  # no usable Docker
])
async def test_not_configured_is_503_and_me_says_so(tmp_path: Path, extra: dict[str, Any], docker: bool) -> None:
    fake = FakeGitHub()
    app = gh_run_app(tmp_path, fake, docker=docker, **extra)
    async with client_for(app) as client:
        await link(client, fake, ALICE, 11, ["alice/shop"])
        response = await client.post(f"{API}/runs", json=GH_RUN, headers=ALICE)
        me = (await client.get(f"{API}/me", headers=ALICE)).json()
    assert response.status_code == 503 and "not available on this server" in response.json()["detail"]
    assert me["github_connected"] is True and me["can_run_github"] is False


async def test_no_github_app_is_503(tmp_path: Path) -> None:
    app = make_app(tmp_path, bob_key_set=True)
    async with client_for(app) as client:
        response = await client.post(f"{API}/runs", json=GH_RUN, headers=ALICE)
    assert response.status_code == 503


async def test_not_linked_is_403_and_me_is_false(tmp_path: Path) -> None:
    fake = FakeGitHub()
    app = gh_run_app(tmp_path, fake)
    async with client_for(app) as client:
        response = await client.post(f"{API}/runs", json=GH_RUN, headers=ALICE)
        me = (await client.get(f"{API}/me", headers=ALICE)).json()
    assert response.status_code == 403 and "Connect GitHub first" in response.json()["detail"]
    assert me["can_run_github"] is False


async def test_a_repo_outside_the_callers_installation_is_403(tmp_path: Path) -> None:
    fake = FakeGitHub()
    factory = Factory()
    app = gh_run_app(tmp_path, fake, factory)
    async with client_for(app) as client:
        await link(client, fake, ALICE, 11, ["alice/shop"])
        other = await client.post(f"{API}/runs", json={**GH_RUN, "repo": {"kind": "github", "ref": "bob/secret"}},
                                  headers=ALICE)
        # Bob is linked to his own installation; Alice's repo is not in it
        await link(client, fake, BOB, 12, ["bob/secret"])
        fake.repos = {12: [{"full_name": "bob/secret"}]}  # the fake lists the first installation's repos
        state_of(app).github._repos.clear()  # type: ignore[attr-defined]
        cross = await client.post(f"{API}/runs", json=GH_RUN, headers=BOB)
    assert other.status_code == 403 and "not shared" in other.json()["detail"]
    assert cross.status_code == 403
    assert factory.sessions == {}
    assert "bob/secret" not in other.text


async def test_a_linked_user_starts_a_run_on_their_repo(tmp_path: Path) -> None:
    fake = FakeGitHub()
    factory = Factory()
    app = gh_run_app(tmp_path, fake, factory)
    async with client_for(app) as client:
        await link(client, fake, ALICE, 11, ["alice/Shop"])
        me = (await client.get(f"{API}/me", headers=ALICE)).json()
        response = await client.post(f"{API}/runs", json=GH_RUN, headers=ALICE)  # "alice/shop": any case
        assert response.status_code == 200, response.text
        spec = factory.sessions[response.json()["run_id"]].spec
        fresh = await spec.github.token_source()
        for session in factory.sessions.values():
            session.cancel()
    assert me["can_run_github"] is True
    assert spec.repo == RepoSpec(kind="github", ref="alice/Shop")  # GitHub's name, never the request's
    assert spec.github.clone_token.startswith("ghs_minted")
    assert fresh.startswith("ghs_minted")
    assert spec.options.budget == 1.5 and not spec.options.hosted and spec.options.auto is False
    assert spec.github.clone_token not in repr(spec)
    minted = [r for r in fake.requests if r.url.path.endswith("/access_tokens") and r.content]
    assert json.loads(minted[-1].content)["repositories"] == ["Shop"]  # scoped to the one repo


async def test_one_github_run_at_a_time_server_wide(tmp_path: Path) -> None:
    fake = FakeGitHub()
    factory = Factory()
    app = gh_run_app(tmp_path, fake, factory, max_concurrent_runs=5)
    async with client_for(app) as client:
        await link(client, fake, ALICE, 11, ["alice/shop"])
        first = await client.post(f"{API}/runs", json=GH_RUN, headers=ALICE)
        second = await client.post(f"{API}/runs", json=GH_RUN, headers=ALICE)
        demo = await client.post(f"{API}/runs", json=NEW_RUN, headers=ALICE)  # demos are not affected
        for session in factory.sessions.values():
            session.cancel()
        await wait_for(lambda: not state_of(app).runs.live_ids())
        third = await client.post(f"{API}/runs", json=GH_RUN, headers=ALICE)
        for session in factory.sessions.values():
            session.cancel()
    assert first.status_code == 200 and demo.status_code == 200 and third.status_code == 200
    assert second.status_code == 429 and second.json()["detail"] == BUSY
    assert not second.json()["detail"].startswith("Demo limit")  # the web maps that to the guest card
    assert second.headers["Retry-After"] == "60"


async def test_runs_per_user_per_day_and_refusals_do_not_count(tmp_path: Path) -> None:
    fake = FakeGitHub()
    factory = Factory()
    app = gh_run_app(tmp_path, fake, factory, user_runs_per_day=2)
    async with client_for(app) as client:
        await link(client, fake, ALICE, 11, ["alice/shop"])
        refused = await client.post(f"{API}/runs", json={**GH_RUN, "repo": {"kind": "github", "ref": "x/y"}},
                                    headers=ALICE)
        codes = []
        for _ in range(3):
            response = await client.post(f"{API}/runs", json=GH_RUN, headers=ALICE)
            codes.append(response.status_code)
            for session in factory.sessions.values():
                session.cancel()
            await wait_for(lambda: not state_of(app).runs.live_ids())
    assert refused.status_code == 403
    assert codes == [200, 200, 429]
    assert response.json()["detail"] == "You've used today's 2 runs on your GitHub repos; try again tomorrow"


async def test_the_daily_coin_cap_applies_even_on_a_replay_server(tmp_path: Path) -> None:
    fake = FakeGitHub()
    factory = Factory()
    app = gh_run_app(tmp_path, fake, factory, daily_coin_cap=1.0)
    async with client_for(app) as client:
        await link(client, fake, ALICE, 11, ["alice/shop"])
        store = state_of(app).store
        store.insert_run(RunRecord(id="r_aaaaaaaaaaaa", user_id="u_x", repo_kind="github", repo_ref="a/b",
                                   status="done", created_at=now_ts(), coins=1.0))
        response = await client.post(f"{API}/runs", json=GH_RUN, headers=ALICE)
        demo = await client.post(f"{API}/runs", json=NEW_RUN, headers=ALICE)  # replay demos are free
        for session in factory.sessions.values():
            session.cancel()
    assert response.status_code == 429 and "budget" in response.json()["detail"]
    assert demo.status_code == 200


# --- the session factory ---


def _settings(tmp_path: Path, **extra: Any) -> ServerSettings:
    return ServerSettings.model_validate({"db_path": tmp_path / "s.db", "workspaces_root": tmp_path / "ws",
                                          "guest_secret": "s" * 40, "bob_mode": "replay",
                                          "sandbox_network": "rook-sandbox", **extra})


def _spec(tmp_path: Path, token: str = "ghs_CloneT0kenForTests") -> RunSpec:
    store = Store(tmp_path / "runs.db")

    async def fresh() -> str:
        return "ghs_ShipT0kenForTests"

    return RunSpec("r_abcdefghijkl", RepoSpec(kind="github", ref="alice/shop"), "", SessionOptions(budget=1.5),
                   "u_alice", EventBus(store), store, GitHubAccess(clone_token=token, token_source=fresh))


def test_the_factory_makes_a_live_docker_github_session(tmp_path: Path) -> None:
    settings = _settings(tmp_path, sandbox_memory="768m", sandbox_cpus=0.5)
    session = default_session_factory(settings, DEFAULT_ALLOWLIST)(_spec(tmp_path))
    assert isinstance(session, Session)
    client = session._client_factory(session.bus, session.run_id, tmp_path)
    assert isinstance(client, BobClient) and client.mode == "live"  # a demo on this server would replay
    assert isinstance(session.shipper, GitHubShipper) and session.shipper.repo == "alice/shop"
    assert session.shipper.base is None  # the PR goes to the default branch, from rook/fix-<cx>
    assert session._token == "ghs_CloneT0kenForTests" and session.options.budget == 1.5
    assert session._launcher_factory is not None and not session._run_workspace


def test_the_factory_launcher_is_a_docker_sandbox_on_the_access_network(tmp_path: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    made: list[DockerSandbox] = []

    def fake_start(self: DockerSandbox, plan: SandboxPlan | None = None) -> str:
        made.append(self)
        return "http://x"

    monkeypatch.setattr(DockerSandbox, "start", fake_start)
    settings = _settings(tmp_path, sandbox_memory="768m", sandbox_cpus=0.5)
    session = default_session_factory(settings, DEFAULT_ALLOWLIST)(_spec(tmp_path))
    ws = tmp_path / "ws1"
    ws.mkdir()
    workspace = type("W", (), {"path": ws})()
    launch = session._launcher_factory(workspace, "r_abcdefghijkl")  # type: ignore[misc, arg-type]
    summary: Any = type("Summary", (), {"language": "python"})()
    launch(SandboxPlan.model_validate({"mode": "command", "start": "python app.py", "port": 8000}), {}, summary)
    assert made[0].access_network == "rook-sandbox"
    assert made[0].limits.memory == "768m" and made[0].limits.cpus == 0.5


def test_a_github_spec_without_its_token_is_refused(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    spec = RunSpec(spec.run_id, spec.repo, "", spec.options, spec.user_id, spec.bus, spec.store, None)
    with pytest.raises(ValueError):
        default_session_factory(_settings(tmp_path), DEFAULT_ALLOWLIST)(spec)


async def test_the_clone_token_never_reaches_events_or_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                            caplog: pytest.LogCaptureFixture) -> None:
    """A real Session from the server factory, cloning over a local `file://` "GitHub" that refuses: the
    token goes to git only through the env, and nothing stored or logged holds it."""
    token = "ghs_" + "SecretCl0neT0kenXYZ"
    settings = _settings(tmp_path)
    spec = _spec(tmp_path, token)
    session = default_session_factory(settings, DEFAULT_ALLOWLIST)(spec)
    assert isinstance(session, Session)
    session._github_url = f"file://{tmp_path / 'nowhere'}"  # the clone fails fast, offline
    seen_env: list[dict[str, str]] = []
    real_popen = subprocess.Popen

    def spy(argv: list[str], **kwargs: Any) -> Any:
        assert token not in " ".join(argv)
        seen_env.append(dict(kwargs.get("env") or {}))
        return real_popen(argv, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", spy)
    with caplog.at_level(logging.DEBUG):
        result = await session.run()
    assert result.status == "failed"
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    assert any(basic in env.get("GIT_CONFIG_VALUE_0", "") for env in seen_env)  # the env, never argv
    events = spec.store.events_after(spec.run_id, 0)
    assert events and all(token not in e.model_dump_json() and basic not in e.model_dump_json() for e in events)
    assert token not in caplog.text
    assert redact_text(f"x {token} y") == f"x {REDACTED} y"


# --- the Docker probe ---


class FakeDocker:
    def __init__(self, *, daemon: bool = True, inspect: dict[str, Any] | None = None) -> None:
        self.daemon = daemon
        self.inspect = inspect
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> tuple[int, str]:
        self.calls.append(args)
        if args[0] == "version":
            return (0, "29.0\n") if self.daemon else (1, "")
        if args[0] == "inspect":
            return (0, json.dumps(self.inspect)) if self.inspect is not None else (1, "")
        return 1, ""


def probe(tmp_path: Path, fake: FakeDocker, *, in_container: bool, network: str | None = "rook-sandbox",
          root: Path | None = None) -> DockerProbe:
    return DockerProbe(root or tmp_path / "ws", network, run=fake, in_container=lambda: in_container,
                       container_id=lambda: "abc123")


@pytest.fixture
def docker_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rook.server.github_runs.shutil.which", lambda name, path=None: "/usr/bin/docker")


def test_probe_on_a_host_needs_only_a_daemon(tmp_path: Path, docker_cli: None) -> None:
    assert probe(tmp_path, FakeDocker(), in_container=False, network=None).problem() is None
    assert "daemon" in (probe(tmp_path, FakeDocker(daemon=False), in_container=False).problem() or "")


def test_probe_without_a_docker_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("rook.server.github_runs.shutil.which", lambda name, path=None: None)
    assert probe(tmp_path, FakeDocker(), in_container=False).problem() == "no docker CLI"


def _inspect(source: str, target: str, networks: tuple[str, ...] = ("rook_default", "rook-sandbox")) -> dict[str, Any]:
    return {"mounts": [{"Type": "volume", "Source": "/var/lib/docker/volumes/x", "Destination": "/data"},
                       {"Type": "bind", "Source": source, "Destination": target}],
            "networks": {n: {} for n in networks}}


def test_probe_in_a_container_needs_a_same_path_workspace_mount_and_the_network(tmp_path: Path,
                                                                                docker_cli: None) -> None:
    root = tmp_path / "srv" / "workspaces"
    same = str(tmp_path / "srv")
    assert probe(tmp_path, FakeDocker(inspect=_inspect(same, same)), in_container=True, root=root).problem() is None
    # the #1 trap: the host path differs from the container path (the daemon would bind the wrong folder)
    moved = probe(tmp_path, FakeDocker(inspect=_inspect("/var/lib/rook/ws", same)), in_container=True, root=root)
    assert "same path" in (moved.problem() or "")
    # workspaces on a named volume only (the old /data layout)
    volume_only = {"mounts": [{"Type": "volume", "Source": "/v", "Destination": str(root)}],
                   "networks": {"rook-sandbox": {}}}
    assert "same path" in (probe(tmp_path, FakeDocker(inspect=volume_only), in_container=True,
                                 root=root).problem() or "")
    off_net = FakeDocker(inspect=_inspect(same, same, networks=("rook_default",)))
    assert "network" in (probe(tmp_path, off_net, in_container=True, root=root).problem() or "")
    assert "ROOK_SANDBOX_NETWORK" in (probe(tmp_path, FakeDocker(), in_container=True, network=None,
                                            root=root).problem() or "")
    assert "inspect" in (probe(tmp_path, FakeDocker(inspect=None), in_container=True, root=root).problem() or "")


def test_probe_results_are_cached(tmp_path: Path, docker_cli: None) -> None:
    fake = FakeDocker()
    now = [0.0]
    check = DockerProbe(tmp_path, None, run=fake, in_container=lambda: False, clock=lambda: now[0])
    assert check() and check()
    assert len(fake.calls) == 1
    now[0] = 61.0
    fake.daemon = False
    assert not check()


def test_same_path_mount_is_strict(tmp_path: Path) -> None:
    mounts = [{"Type": "bind", "Source": "/srv/rook", "Destination": "/srv/rook"}]
    assert same_path_mount(mounts, Path("/srv/rook/workspaces"))
    assert not same_path_mount(mounts, Path("/srv/rookie/workspaces"))
    assert not same_path_mount("nope", Path("/srv/rook"))


# --- settings ---


def test_settings_read_the_limits_and_only_whether_the_bob_key_is_set() -> None:
    settings = ServerSettings.from_env({"BOB_API_KEY": "bob_prod_secretvalue", "ROOK_GITHUB_RUNS_MAX": "2",
                                        "ROOK_USER_RUNS_PER_DAY": "3", "ROOK_USER_RUN_BUDGET": "0.8",
                                        "ROOK_SANDBOX_NETWORK": "rook-sandbox", "ROOK_SANDBOX_MEMORY": "1500m",
                                        "ROOK_SANDBOX_CPUS": "1.5"})
    assert settings.bob_key_set and settings.github_runs_max == 2 and settings.user_runs_per_day == 3
    assert settings.user_run_budget == 0.8 and settings.sandbox_network == "rook-sandbox"
    assert (settings.sandbox_memory, settings.sandbox_cpus) == ("1500m", 1.5)
    assert "bob_prod_secretvalue" not in repr(settings) and "bob_prod_secretvalue" not in settings.model_dump_json()
    defaults = ServerSettings.from_env({})
    assert not defaults.bob_key_set and defaults.github_runs_max == 1 and defaults.user_run_budget == 1.5
    with pytest.raises(ValueError):
        ServerSettings.from_env({"ROOK_SANDBOX_NETWORK": "bad net; rm"})


# --- DockerSandbox and compose in access-network mode ---


class RecordingDocker:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: Any, *, timeout: float = 0) -> subprocess.CompletedProcess[str]:
        args = list(args)
        self.calls.append(args)
        out = ""
        if args[:2] == ["inspect", "-f"]:
            out = "true\n"
        elif args[0] == "run":
            out = "cid123\n"
        return subprocess.CompletedProcess(["docker", *args], 0, out, "")


def test_access_network_mode_publishes_nothing_and_rebuilds_on_restart(tmp_path: Path,
                                                                       monkeypatch: pytest.MonkeyPatch) -> None:
    fake = RecordingDocker()
    monkeypatch.setattr(docker_mod.reaper, "docker", fake)
    monkeypatch.setattr(docker_mod.reaper, "sweep", lambda name: None)
    monkeypatch.setattr(DockerSandbox, "_start_watchdog", lambda self: None)
    monkeypatch.setattr(DockerSandbox, "_wait_healthy", lambda self, plan: None)
    (tmp_path / "app.py").write_text("print('hi')\n")
    sandbox = DockerSandbox(tmp_path, run_id="r_abcdefghijkl", access_network="rook-sandbox")
    plan = SandboxPlan.model_validate({"mode": "command", "start": "python app.py", "port": 8000})
    url = sandbox.start(plan)
    assert sandbox.name is not None
    assert url == f"http://{sandbox.name}-proxy:8080"
    proxy_run = next(c for c in fake.calls if c[0] == "run" and "--publish" not in c and c[c.index("--name") + 1]
                     .endswith("-proxy"))
    assert proxy_run[proxy_run.index("--network") + 1] == "rook-sandbox"
    assert not any("--publish" in c for c in fake.calls)
    assert not any(c[:2] == ["network", "create"] and c[-1].endswith("-pub") for c in fake.calls)
    assert not any(c[0] == "port" for c in fake.calls)
    builds = sum(1 for c in fake.calls if c[0] == "build")
    assert sandbox.restart() == url
    assert sum(1 for c in fake.calls if c[0] == "build") == builds + 1  # the patched code is rebuilt
    sandbox.stop()
    with pytest.raises(SandboxError):
        DockerSandbox(tmp_path, access_network="bad name; x")


def test_compose_in_access_network_mode_joins_the_external_network(tmp_path: Path) -> None:
    (tmp_path / "compose.yaml").write_text(yaml.safe_dump({"services": {"web": {"build": ".",
                                                                                "ports": ["8000:8000"]}}}))
    doc, app = render(tmp_path / "compose.yaml", tmp_path, service=None, port=8000, host_port=None, env={},
                      hardening=Hardening(labels={"rook.run": "rook-x"}), access_network="rook-sandbox",
                      access_alias="rook-x-proxy")
    proxy = doc["services"]["rook-proxy"]
    assert "ports" not in proxy and app == "web"
    assert proxy["networks"]["rook-publish"] == {"aliases": ["rook-x-proxy"]}
    assert doc["networks"]["rook-publish"] == {"external": True, "name": "rook-sandbox"}
    assert doc["networks"]["default"]["internal"] is True
    assert "ports" not in doc["services"]["web"]


# --- the clone drops the repo's own Bob config ---


def test_a_cloned_repos_own_bob_folder_is_removed(tmp_path: Path) -> None:
    src = tmp_path / "src"
    (src / ".bob").mkdir(parents=True)
    (src / ".bob" / "settings.json").write_text('{"mcpServers": {"x": {"command": "sh"}}}')
    (src / "app.py").write_text("x = 1\n")
    git(src, "init", "-q")
    git(src, "add", "-A")
    git(src, "commit", "-q", "-m", "upstream")
    origin = tmp_path / "server" / "acme" / "shop.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(src), str(origin)], check=True, capture_output=True)
    ws = prepare_workspace(RepoSpec(kind="github", ref="acme/shop"), "r_abcdefghijkl", root=tmp_path / "w",
                           github_url=f"file://{tmp_path / 'server'}")
    assert not (ws.path / ".bob").exists() and (ws.path / "app.py").is_file()
    assert ".bob" in ws.skipped
