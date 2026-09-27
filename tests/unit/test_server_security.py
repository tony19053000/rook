"""ROOK-029 security (03 §6-§8): CORS, body size, rate limits, guest cookie and quotas, the queue, the daily
coin cap, secrets never in responses, and restart recovery."""

from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError
from server_helpers import (
    ALICE,
    DEMO,
    NEW_RUN,
    Factory,
    client_for,
    create_run,
    guest_headers,
    make_app,
    second_client,
    state_of,
    wait_for,
)

from rook.core.events import clear_secrets, now_ts, register_secret
from rook.server.auth import GUEST_COOKIE, GuestCookies
from rook.server.config import ServerSettings
from rook.server.limits import PROXY_SECRET_HEADER, RateLimiter, client_ip
from rook.store.repo import RunRecord, Store

API = "/api/v1"
WEB = "https://rook.example.app"


# --- CORS: only the configured web origin, with credentials; never `*` ---


async def test_cors_allows_the_web_origin_with_credentials(tmp_path: Path) -> None:
    async with client_for(make_app(tmp_path)) as client:
        simple = await client.get(f"{API}/health", headers={"Origin": WEB})
        preflight = await client.options(f"{API}/runs", headers={
            "Origin": WEB, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type"})
    assert simple.headers["access-control-allow-origin"] == WEB
    assert simple.headers["access-control-allow-credentials"] == "true"
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == WEB
    allowed = preflight.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed and "content-type" in allowed


async def test_cors_rejects_other_origins(tmp_path: Path) -> None:
    async with client_for(make_app(tmp_path)) as client:
        simple = await client.get(f"{API}/health", headers={"Origin": "https://evil.example"})
        preflight = await client.options(f"{API}/runs", headers={
            "Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization"})
        odd_header = await client.options(f"{API}/runs", headers={
            "Origin": WEB, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-evil"})
    assert "access-control-allow-origin" not in simple.headers
    assert preflight.status_code == 400 and "access-control-allow-origin" not in preflight.headers
    assert odd_header.status_code == 400


@pytest.mark.parametrize("origin", ["*", "https://ok.app/path", "null", "rook.app"])
def test_settings_refuse_a_wildcard_or_malformed_origin(origin: str) -> None:
    with pytest.raises(ValidationError):
        ServerSettings(web_origins=[origin])


def test_settings_from_env(tmp_path: Path) -> None:
    demos = tmp_path / "demos.yaml"
    demos.write_text(f"repos:\n  - {{ref: {DEMO.ref}, commit: '{DEMO.commit}', name: shop-app}}\n")
    settings = ServerSettings.from_env({
        "ROOK_WEB_ORIGINS": "https://rook.vercel.app, http://localhost:3000", "ROOK_DB_PATH": str(tmp_path / "x.db"),
        "ROOK_DEMO_REPOS": str(demos), "ROOK_TRUSTED_PROXY_HOPS": "2", "ROOK_DAILY_COIN_CAP": "5",
        "ROOK_BOB_MODE": "replay", "ROOK_GUEST_SECRET": "k" * 40})
    assert settings.web_origins == ["https://rook.vercel.app", "http://localhost:3000"]
    assert settings.demo(DEMO.ref.upper()) is not None and settings.trusted_proxy_hops == 2
    assert settings.daily_coin_cap == 5.0 and settings.bob_mode == "replay"
    assert "k" * 40 not in repr(settings) and "k" * 40 not in settings.model_dump_json()
    with pytest.raises(ValidationError):
        ServerSettings.from_env({"ROOK_GUEST_SECRET": "short"})


# --- request size limit (64 KB) ---


async def test_a_body_over_64kb_is_413(tmp_path: Path) -> None:
    factory = Factory()
    async with client_for(make_app(tmp_path, factory)) as client:
        big = await client.post(f"{API}/runs", json={**NEW_RUN, "request": "x" * 70_000}, headers=ALICE)

        async def chunks():  # no Content-Length: counted while reading
            for _ in range(20):
                yield b"x" * 4096

        chunked = await client.post(f"{API}/runs", content=chunks(), headers={**ALICE,
                                                                              "Content-Type": "application/json"})
        lying = await client.post(f"{API}/runs", content=b"{}", headers={**ALICE, "Content-Length": "abc"})
    assert big.status_code == 413 and chunked.status_code == 413
    assert big.json() == {"detail": "Request body is larger than the limit"}
    assert lying.status_code in (400, 413)
    assert factory.sessions == {}


async def test_a_body_under_the_limit_passes(tmp_path: Path) -> None:
    factory = Factory()
    async with client_for(make_app(tmp_path, factory)) as client:
        run_id = await create_run(client, ALICE, {**NEW_RUN, "request": "y" * 1_900})
        await client.post(f"{API}/runs/{run_id}/cancel", headers=ALICE)


# --- rate limits ---


async def test_rate_limit_60_per_minute_per_ip(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    async with client_for(app, ip="10.1.1.1") as client:
        codes = [(await client.get(f"{API}/repos", headers=ALICE)).status_code for _ in range(61)]
        limited = await client.get(f"{API}/repos", headers=ALICE)
        health = await client.get(f"{API}/health")  # exempt, for the keep-alive
        async with second_client(app, ip="10.1.1.2") as other:  # another IP has its own budget
            assert (await other.get(f"{API}/repos", headers=ALICE)).status_code == 200
    assert codes[:60] == [200] * 60 and codes[60] == 429
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) >= 1
    assert health.status_code == 200


async def test_rate_limit_10_run_creations_per_minute(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=20, max_queued_runs=20)
    async with client_for(app) as client:
        codes = [(await client.post(f"{API}/runs", json=NEW_RUN, headers=ALICE)).status_code for _ in range(11)]
        for run_id in list(factory.sessions):
            await client.post(f"{API}/runs/{run_id}/cancel", headers=ALICE)
    assert codes == [200] * 10 + [429]


def test_rate_limiter_window_slides() -> None:
    now = [0.0]
    limiter = RateLimiter(2, window=60, clock=lambda: now[0])
    assert limiter.hit("a") == 0 and limiter.hit("a") == 0
    assert limiter.hit("a") == pytest.approx(60)
    assert limiter.hit("b") == 0
    now[0] = 60.5
    assert limiter.hit("a") == 0


def test_client_ip_counts_trusted_proxies_from_the_right() -> None:
    headers = {"x-forwarded-for": "6.6.6.6, 1.2.3.4, 10.0.0.1"}  # spoofed, client, the Vercel hop
    assert client_ip(headers, "10.9.9.9", 0) == "10.9.9.9"
    assert client_ip(headers, "10.9.9.9", 1) == "10.0.0.1"
    assert client_ip(headers, "10.9.9.9", 2) == "1.2.3.4"
    assert client_ip({}, "10.9.9.9", 2) == "10.9.9.9"


PROXY_SECRET = "p" * 40  # a fake value for the tests


def test_with_a_proxy_secret_the_vercel_hop_is_trusted_only_when_proven() -> None:
    chain = "6.6.6.6, 1.2.3.4, 10.0.0.1"  # spoofed, client, the Vercel hop
    proven = {"x-forwarded-for": chain, PROXY_SECRET_HEADER: PROXY_SECRET}
    assert client_ip(proven, "10.9.9.9", 2, PROXY_SECRET) == "1.2.3.4"
    # A caller that skips Vercel sends its own X-Forwarded-For; Caddy appends the address it really saw.
    direct = {"x-forwarded-for": "1.2.3.4, 203.0.113.9"}
    assert client_ip(direct, "10.9.9.9", 2, PROXY_SECRET) == "203.0.113.9"
    wrong = {**direct, PROXY_SECRET_HEADER: "p" * 39 + "q"}
    assert client_ip(wrong, "10.9.9.9", 2, PROXY_SECRET) == "203.0.113.9"
    assert client_ip({**direct, PROXY_SECRET_HEADER: "\u00e9" * 3}, "10.9.9.9", 2, PROXY_SECRET) == "203.0.113.9"
    assert client_ip(direct, "10.9.9.9", 2, None) == "1.2.3.4"  # no secret configured: the ROOK-037 behaviour


def test_the_proxy_secret_setting() -> None:
    settings = ServerSettings.from_env({"ROOK_PROXY_SECRET": PROXY_SECRET, "ROOK_GUEST_SECRET": "k" * 40})
    assert settings.proxy_secret_value() == PROXY_SECRET
    assert PROXY_SECRET not in repr(settings) and PROXY_SECRET not in settings.model_dump_json()
    assert ServerSettings().proxy_secret_value() is None
    with pytest.raises(ValidationError):
        ServerSettings.from_env({"ROOK_PROXY_SECRET": "short"})


async def test_health_says_whether_the_request_came_through_the_proxy(tmp_path: Path) -> None:
    app = make_app(tmp_path, trusted_proxy_hops=2, proxy_secret=PROXY_SECRET)
    async with client_for(app) as client:
        proxied = await client.get(f"{API}/health", headers={PROXY_SECRET_HEADER: PROXY_SECRET})
        direct = await client.get(f"{API}/health", headers={PROXY_SECRET_HEADER: "nope"})
    assert proxied.json()["proxied"] is True and direct.json()["proxied"] is False
    assert PROXY_SECRET not in proxied.text


async def test_the_guest_quota_uses_the_proven_client_ip(tmp_path: Path) -> None:
    """Through Vercel two guests on different IPs don't share a quota; a direct caller can't pick its IP."""
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=20, trusted_proxy_hops=2, proxy_secret=PROXY_SECRET,
                   guest_runs_per_ip_per_day=2, rate_per_minute=1000, runs_per_minute=1000)

    def via_vercel(client_ip: str) -> dict[str, str]:
        return {"X-Forwarded-For": f"{client_ip}, 10.0.0.1", PROXY_SECRET_HEADER: PROXY_SECRET,
                **guest_headers(app)[1]}

    def spoofed(fake_ip: str) -> dict[str, str]:  # direct to Caddy, which appends the real peer 203.0.113.9
        return {"X-Forwarded-For": f"{fake_ip}, 203.0.113.9", **guest_headers(app)[1]}

    async with client_for(app) as client:
        a = [(await client.post(f"{API}/runs", json=NEW_RUN, headers=via_vercel("1.1.1.1"))).status_code
             for _ in range(3)]
        b = (await client.post(f"{API}/runs", json=NEW_RUN, headers=via_vercel("2.2.2.2"))).status_code
        fake = [(await client.post(f"{API}/runs", json=NEW_RUN, headers=spoofed(f"9.9.9.{i}"))).status_code
                for i in range(3)]
        for session in factory.sessions.values():
            session.cancel()
    assert a == [200, 200, 429] and b == 200
    assert fake == [200, 200, 429]


# --- guest cookie and guest limits ---


async def test_guest_cookie_is_httponly_lax_secure(tmp_path: Path) -> None:
    async with client_for(make_app(tmp_path)) as client:
        response = await client.get(f"{API}/runs")
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{GUEST_COOKIE}=")
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie and "path=/" in cookie


def test_guest_cookie_cannot_be_forged() -> None:
    cookies = GuestCookies("x" * 40)
    guest_id, value = cookies.issue()
    assert cookies.read(value) == guest_id
    other_id, _ = GuestCookies("y" * 40).issue()
    forged = f"{other_id}.{value.split('.')[1]}"
    for bad in (forged, guest_id, f"{guest_id}.", f"{guest_id}.{'0' * 64}", "", "a.b.c", f"../x.{'0' * 64}"):
        assert cookies.read(bad) is None
    assert GuestCookies("y" * 40).read(value) is None


async def test_a_forged_cookie_does_not_reach_another_guests_run(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    guest_id, headers = guest_headers(app)
    async with client_for(app) as client:
        run_id = await create_run(client, headers)
        forged = {"Cookie": f"{GUEST_COOKIE}={guest_id}.{'0' * 64}"}
        assert (await client.get(f"{API}/runs/{run_id}", headers=forged)).status_code == 401
        listed = await client.get(f"{API}/runs", headers=forged)  # treated as a brand new guest
        assert listed.json() == [] and "set-cookie" in listed.headers
        await client.post(f"{API}/runs/{run_id}/cancel", headers=headers)


async def test_guest_quota_is_3_runs_per_day(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=10)
    _, guest = guest_headers(app)
    async with client_for(app) as client:
        codes = [(await client.post(f"{API}/runs", json=NEW_RUN, headers=guest)).status_code for _ in range(4)]
        refused = await client.post(f"{API}/runs", json=NEW_RUN, headers=guest)
        user = await client.post(f"{API}/runs", json=NEW_RUN, headers=ALICE)  # users have no guest quota
        for run_id in list(factory.sessions):
            await client.post(f"{API}/runs/{run_id}/cancel", headers=ALICE)
            await client.post(f"{API}/runs/{run_id}/cancel", headers=guest)
    assert codes == [200, 200, 200, 429]
    assert refused.json()["detail"].startswith("Demo limit reached for today")
    assert int(refused.headers["retry-after"]) >= 1
    assert user.status_code == 200


async def test_guest_quota_also_counts_per_ip(tmp_path: Path) -> None:
    """Dropping the cookie (a new guest) doesn't reset the quota from the same address: 10 runs per IP."""
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=20, max_queued_runs=20, runs_per_minute=100)
    assert state_of(app).settings.guest_runs_per_ip_per_day == 10
    async with client_for(app, ip="10.2.2.2") as client:
        codes = []
        for _ in range(11):
            response = await client.post(f"{API}/runs", json=NEW_RUN, headers=guest_headers(app)[1])
            codes.append(response.status_code)
        assert response.json()["detail"].startswith("Demo limit reached")
        async with second_client(app, ip="10.3.3.3") as other:
            other_ip = await other.post(f"{API}/runs", json=NEW_RUN, headers=guest_headers(app)[1])
        for session in factory.sessions.values():
            session.cancel()
    assert codes == [200] * 10 + [429]
    assert other_ip.status_code == 200


async def test_refused_runs_do_not_use_up_the_guest_quota(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=10)
    _, guest = guest_headers(app)
    bad_repo = {**NEW_RUN, "repo": {"kind": "github", "ref": "a/b"}}
    async with client_for(app) as client:
        for _ in range(3):
            assert (await client.post(f"{API}/runs", json=bad_repo, headers=guest)).status_code == 401
        codes = [(await client.post(f"{API}/runs", json=NEW_RUN, headers=guest)).status_code for _ in range(3)]
        for session in factory.sessions.values():
            session.cancel()
    assert codes == [200, 200, 200]


async def test_a_full_queue_is_429(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=1, max_queued_runs=1)
    async with client_for(app) as client:
        first = await create_run(client, ALICE)
        await wait_for(factory.sessions[first].asked.is_set)
        await create_run(client, ALICE)  # queued
        full = await client.post(f"{API}/runs", json=NEW_RUN, headers=ALICE)
        for session in factory.sessions.values():
            session.cancel()
    assert full.status_code == 429 and "busy" in full.json()["detail"]
    assert len(factory.sessions) == 2


async def test_the_daily_coin_cap_stops_new_live_runs(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, bob_mode="live", daily_coin_cap=1.0)
    store = state_of(app).store
    store.insert_run(RunRecord(id="r_aaaaaaaaaaaa", user_id="u_x", repo_kind="demo", repo_ref=DEMO.ref,
                               status="done", created_at=now_ts(), coins=0.6))
    async with client_for(app) as client:
        first = await create_run(client, ALICE)
        assert factory.sessions[first].spec.options.daily_cap == 1.0
        assert factory.sessions[first].spec.options.daily_spent == pytest.approx(0.6)
        store.update_run("r_aaaaaaaaaaaa", coins=1.2)
        refused = await client.post(f"{API}/runs", json=NEW_RUN, headers=ALICE)
        for session in factory.sessions.values():
            session.cancel()
    assert refused.status_code == 429 and "budget" in refused.json()["detail"]


# --- secrets never in responses ---


async def test_secrets_never_appear_in_responses(tmp_path: Path) -> None:
    secret = "bob" + "_prod_TESTVALUE0123456789"  # fake values, built so no secret-looking literal is in git
    register_secret(secret)
    try:
        factory = Factory()
        app = make_app(tmp_path, factory)
        guest_secret = state_of(app).settings.guest_secret.get_secret_value()
        bearer = "ey" + "JhbGciOiJIUzI1NiJ9." + "ey" + "JzdWIiOiJ4In0.c2lnbmF0dXJl"
        async with client_for(app) as client:
            responses: list[httpx.Response] = [
                await client.get(f"{API}/health"),
                await client.get(f"{API}/me", headers={"Authorization": f"Bearer {bearer}"}),
                await client.post(f"{API}/runs", json={"repo": {"kind": "demo", "ref": secret}}, headers=ALICE),
                await client.post(f"{API}/runs", json={**NEW_RUN, "extra": secret}, headers=ALICE),
                await client.post(f"{API}/runs", json={**NEW_RUN, "request": 7}, headers=ALICE),
            ]
            run_id = await create_run(client, ALICE, {**NEW_RUN, "request": f"use key {secret}"})
            await wait_for(factory.sessions[run_id].asked.is_set)
            responses += [
                await client.get(f"{API}/runs", headers=ALICE),
                await client.get(f"{API}/runs/{run_id}", headers=ALICE),
            ]
            await client.post(f"{API}/runs/{run_id}/cancel", headers=ALICE)
            await wait_for(lambda: state_of(app).runs.live(run_id) is None)
            responses.append(await client.get(f"{API}/runs/{run_id}/events", headers=ALICE))
        for response in responses:
            blob = response.text + " ".join(f"{k}: {v}" for k, v in response.headers.items())
            for leaked in (secret, bearer, guest_secret):
                assert leaked not in blob, (response.request.url, leaked[:8])
        assert all(r.status_code != 500 for r in responses)
    finally:
        clear_secrets()


# --- restart recovery ---


async def test_runs_left_running_by_a_dead_process_are_marked_failed(tmp_path: Path) -> None:
    store = Store(tmp_path / "server.db")
    store.insert_run(RunRecord(id="r_bbbbbbbbbbbb", user_id="u_alice", repo_kind="demo", repo_ref=DEMO.ref,
                               status="running", created_at=now_ts()))
    store.close()
    app = make_app(tmp_path)
    async with client_for(app) as client:
        detail = (await client.get(f"{API}/runs/r_bbbbbbbbbbbb", headers=ALICE)).json()
        stream = await client.get(f"{API}/runs/r_bbbbbbbbbbbb/events", headers=ALICE)
    assert detail["run"]["status"] == "failed"
    assert '"type":"run.finished"' in stream.text
