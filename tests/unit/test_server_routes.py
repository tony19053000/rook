"""ROOK-029: every route of 02 §11 (except auth/GitHub), owner isolation and guest restrictions."""

from pathlib import Path
from typing import Any

import pytest
from server_helpers import (
    ALICE,
    BOB,
    DEMO,
    NEW_RUN,
    CrashingSession,
    Factory,
    QuestionSession,
    RecordedSession,
    client_for,
    create_run,
    guest_headers,
    make_app,
    state_of,
    wait_for,
)

from rook.server.auth import Caller
from rook.server.runs import RunSession, RunSpec
from rook.server.schemas import RepoOption
from rook.store.repo import CounterexampleRecord

API = "/api/v1"


class FakeGitHub:
    def connected(self, user: Caller) -> bool:
        return user.id == "u_alice"

    async def list_repos(self, user: Caller) -> list[RepoOption]:
        return [RepoOption(kind="github", ref="alice/private-app", name="private-app", private=True,
                           language="Go")]


def gone(app: Any, run_id: str) -> bool:
    """The run has ended and left the live set."""
    return state_of(app).runs.live(run_id) is None


# --- /health, /me, /repos ---


async def test_health(tmp_path: Path) -> None:
    async with client_for(make_app(tmp_path)) as client:
        response = await client.get(f"{API}/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "version": "0.1.0", "bob_mode": "replay", "proxied": False}


async def test_me_for_a_user_and_not_for_a_guest(tmp_path: Path) -> None:
    app = make_app(tmp_path, github=FakeGitHub())
    async with client_for(app) as client:
        me = await client.get(f"{API}/me", headers=ALICE)
        bob = await client.get(f"{API}/me", headers=BOB)
        guest = await client.get(f"{API}/me", headers=guest_headers(app)[1])
        anonymous = await client.get(f"{API}/me")
        bad = await client.get(f"{API}/me", headers={"Authorization": "Bearer nope"})
        not_bearer = await client.get(f"{API}/me", headers={"Authorization": "Basic abc"})
    assert me.json() == {"id": "u_alice", "email": "alice@example.com", "github_connected": True}
    assert bob.json()["github_connected"] is False
    assert (guest.status_code, anonymous.status_code, bad.status_code, not_bearer.status_code) == (401,) * 4


async def test_a_bad_token_is_401_even_with_a_guest_cookie(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    headers = {**guest_headers(app)[1], "Authorization": "Bearer forged"}
    async with client_for(app) as client:
        assert (await client.get(f"{API}/runs", headers=headers)).status_code == 401
        assert (await client.post(f"{API}/runs", json=NEW_RUN, headers=headers)).status_code == 401


async def test_repos_guest_sees_only_demo_repos(tmp_path: Path) -> None:
    app = make_app(tmp_path, github=FakeGitHub())
    async with client_for(app) as client:
        guest = await client.get(f"{API}/repos")
        user = await client.get(f"{API}/repos", headers=ALICE)
    demo = {"kind": "demo", "ref": DEMO.ref, "name": "shop-app", "private": False, "language": "TypeScript"}
    assert guest.json() == [demo]
    assert "rook_guest=" in guest.headers["set-cookie"]  # the guest is created here
    assert [r["kind"] for r in user.json()] == ["github", "demo"]


# --- creating runs: demo repos only ---


async def test_create_run_for_a_user_and_a_guest(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        user_run = await create_run(client, ALICE)
        guest_response = await client.post(f"{API}/runs", json=NEW_RUN)  # no cookie yet: one is issued
        assert guest_response.status_code == 200
        guest_run = guest_response.json()["run_id"]
        await wait_for(lambda: all(s.asked.is_set() for s in factory.sessions.values()))
    spec = factory.sessions[user_run].spec
    assert spec.repo.kind == "demo" and spec.repo.ref == DEMO.ref and spec.repo.commit == DEMO.commit
    assert spec.options.hosted is True and spec.options.auto is False and spec.request == "find a refund bug"
    assert spec.user_id == "u_alice"
    assert factory.sessions[guest_run].spec.user_id.startswith("g_")
    assert "rook_guest=" in guest_response.headers["set-cookie"]


@pytest.mark.parametrize("repo, who, detail", [
    ({"kind": "github", "ref": "alice/private-app"}, "guest", "Guests can only run the demo repos"),
    ({"kind": "demo", "ref": "evil/unknown"}, "guest", "run arbitrary repos with the CLI"),
    ({"kind": "github", "ref": "alice/private-app"}, "user", "run arbitrary repos with the CLI"),
    ({"kind": "demo", "ref": "evil/unknown"}, "user", "run arbitrary repos with the CLI"),
])
async def test_only_allowlisted_demo_repos_run(tmp_path: Path, repo: dict[str, str], who: str, detail: str) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    headers = ALICE if who == "user" else guest_headers(app)[1]
    async with client_for(app) as client:
        response = await client.post(f"{API}/runs", json={**NEW_RUN, "repo": repo}, headers=headers)
    assert response.status_code == 403
    assert detail in response.json()["detail"]
    assert factory.sessions == {}


@pytest.mark.parametrize("body", [
    {"repo": {"kind": "local", "ref": "a/b"}, "request": ""},
    {"repo": {"kind": "demo", "ref": "../../etc"}, "request": ""},
    {"repo": {"kind": "demo", "ref": DEMO.ref}, "request": "x" * 2001},
    {"repo": {"kind": "demo", "ref": DEMO.ref}, "options": {"auto": True, "budget": 99}},
    {"repo": {"kind": "demo", "ref": DEMO.ref}, "extra": 1},
    {"request": "no repo"},
])
async def test_create_run_rejects_bad_bodies_with_400(tmp_path: Path, body: dict[str, Any]) -> None:
    async with client_for(make_app(tmp_path)) as client:
        response = await client.post(f"{API}/runs", json=body, headers=ALICE)
    assert response.status_code == 400
    assert response.json()["detail"].startswith("Invalid request")


async def test_auto_option_is_passed_on(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE, {**NEW_RUN, "options": {"auto": True}})
    assert factory.sessions[run_id].spec.options.auto is True


# --- listing and reading runs ---


async def test_list_runs_shows_only_the_callers_runs(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        alice_1 = await create_run(client, ALICE)
        alice_2 = await create_run(client, ALICE, {**NEW_RUN, "request": ""})
        bob_run = await create_run(client, BOB)
        await wait_for(lambda: all(s.asked.is_set() for s in factory.sessions.values()))
        alice = (await client.get(f"{API}/runs", headers=ALICE)).json()
        bob = (await client.get(f"{API}/runs", headers=BOB)).json()
        empty = (await client.get(f"{API}/runs", headers=guest_headers(app)[1])).json()
    assert {r["id"] for r in alice} == {alice_1, alice_2}
    assert [r["id"] for r in bob] == [bob_run]
    assert empty == []
    first = next(r for r in alice if r["id"] == alice_1)
    assert first["repo"] == {"kind": "demo", "ref": DEMO.ref, "name": "shop-app"}
    assert first["status"] == "running" and first["headline"] == "find a refund bug"
    assert first["finished_at"] is None and first["result"] is None and first["last_seq"] == 2
    assert next(r for r in alice if r["id"] == alice_2)["headline"] == "shop-app"


async def test_queued_runs_are_listed_and_readable(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=1)
    async with client_for(app) as client:
        first = await create_run(client, ALICE)
        await wait_for(lambda: factory.sessions[first].asked.is_set())
        second = await create_run(client, ALICE)
        listed = (await client.get(f"{API}/runs", headers=ALICE)).json()
        detail = (await client.get(f"{API}/runs/{second}", headers=ALICE)).json()
        assert {r["id"]: r["status"] for r in listed} == {first: "running", second: "queued"}
        assert detail["run"]["status"] == "queued" and detail["counterexamples"] == []
        # Answering the first run frees the slot: the second starts.
        assert (await client.post(f"{API}/runs/{first}/answers", json={"question_id": "q_fix", "answer": True},
                                  headers=ALICE)).json() == {"ok": True}
        await wait_for(lambda: factory.sessions[second].asked.is_set())


async def test_get_run_with_counterexamples_from_the_recorded_run(tmp_path: Path) -> None:
    factory = Factory(RecordedSession)
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(lambda: factory.sessions[run_id].finished)
        await wait_for(lambda: gone(app, run_id))
        detail = (await client.get(f"{API}/runs/{run_id}", headers=ALICE)).json()
    run = detail["run"]
    assert run["status"] == "done" and run["result"] == "fixed" and run["finished_at"]
    assert run["last_seq"] == 369  # every event of the recorded run
    [cx] = detail["counterexamples"]
    assert cx["id"] == f"{run_id}_cx_001" and cx["cx_id"] == "cx_001" and cx["status"] == "verified"
    assert cx["rule_id"] == "refunded_total_le_paid" and cx["rule_text"]


# --- answers, chat, cancel ---


async def test_answer_chat_and_cancel(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        session = factory.sessions[run_id]
        await wait_for(session.asked.is_set)
        url = f"{API}/runs/{run_id}"
        wrong_q = await client.post(f"{url}/answers", json={"question_id": "q_other", "answer": True}, headers=ALICE)
        wrong_shape = await client.post(f"{url}/answers", json={"question_id": "q_fix", "answer": "maybe"},
                                        headers=ALICE)
        chat = await client.post(f"{url}/chat", json={"text": "what are you doing?"}, headers=ALICE)
        empty_chat = await client.post(f"{url}/chat", json={"text": ""}, headers=ALICE)
        answer = await client.post(f"{url}/answers", json={"question_id": "q_fix", "answer": True}, headers=ALICE)
        await wait_for(lambda: session.finished)
        await wait_for(lambda: gone(app, run_id))
        again = await client.post(f"{url}/answers", json={"question_id": "q_fix", "answer": True}, headers=ALICE)
        late_chat = await client.post(f"{url}/chat", json={"text": "hi"}, headers=ALICE)
        late_cancel = await client.post(f"{url}/cancel", headers=ALICE)
    assert wrong_q.json() == {"ok": False} and wrong_shape.json() == {"ok": False}
    assert chat.json() == {"ok": True} and session.chats == ["what are you doing?"]
    assert empty_chat.status_code == 400
    assert answer.json() == {"ok": True}
    assert again.json() == late_chat.json() == late_cancel.json() == {"ok": False}


async def test_cancel_a_running_run(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(factory.sessions[run_id].asked.is_set)
        assert (await client.post(f"{API}/runs/{run_id}/cancel", headers=ALICE)).json() == {"ok": True}
        await wait_for(lambda: gone(app, run_id))
        detail = (await client.get(f"{API}/runs/{run_id}", headers=ALICE)).json()
    assert detail["run"]["status"] == "cancelled"


async def test_cancel_a_queued_run_ends_it_without_a_slot(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=1)
    async with client_for(app) as client:
        first = await create_run(client, ALICE)
        await wait_for(factory.sessions[first].asked.is_set)
        queued = await create_run(client, ALICE)
        assert (await client.post(f"{API}/runs/{queued}/cancel", headers=ALICE)).json() == {"ok": True}
        await wait_for(lambda: gone(app, queued))
        detail = (await client.get(f"{API}/runs/{queued}", headers=ALICE)).json()
        assert detail["run"]["status"] == "cancelled"
        assert state_of(app).runs.live(first) is not None  # the first run still holds its slot


async def test_a_crashing_session_still_finishes_its_run(tmp_path: Path) -> None:
    factory = Factory(CrashingSession)
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(lambda: gone(app, run_id))
        detail = (await client.get(f"{API}/runs/{run_id}", headers=ALICE)).json()
        stream = await client.get(f"{API}/runs/{run_id}/events", headers=ALICE)
    assert detail["run"]["status"] == "failed"
    assert '"type":"run.finished"' in stream.text


# --- owner isolation: someone else's run is a 404 ---


async def test_every_owner_route_is_404_for_someone_else(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    _, guest = guest_headers(app)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        session = factory.sessions[run_id]
        await wait_for(session.asked.is_set)
        url = f"{API}/runs/{run_id}"
        for headers in (BOB, guest):
            responses = [
                await client.get(url, headers=headers),
                await client.get(f"{url}/events", headers=headers),
                await client.post(f"{url}/answers", json={"question_id": "q_fix", "answer": True}, headers=headers),
                await client.post(f"{url}/chat", json={"text": "hi"}, headers=headers),
                await client.post(f"{url}/cancel", headers=headers),
            ]
            assert [r.status_code for r in responses] == [404] * 5
            assert all(r.json() == {"detail": "Run not found"} for r in responses)
        missing = await client.get(f"{API}/runs/r_aaaaaaaaaaaa", headers=ALICE)
        malformed = await client.get(f"{API}/runs/..%2F..%2Fetc", headers=ALICE)
        assert session.cancel_calls == 0 and not session.finished and session.chats == []
        await client.post(f"{url}/cancel", headers=ALICE)
    assert missing.status_code == 404 and malformed.status_code == 404


async def test_owner_routes_need_a_caller(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        response = await client.get(f"{API}/runs/{run_id}")
        assert response.status_code == 401
        assert "set-cookie" not in response.headers  # an owner route never mints a guest
        await client.post(f"{API}/runs/{run_id}/cancel", headers=ALICE)


async def test_guest_owns_its_runs_across_requests(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    _, guest = guest_headers(app)
    async with client_for(app) as client:
        run_id = await create_run(client, guest)
        await wait_for(factory.sessions[run_id].asked.is_set)
        assert (await client.get(f"{API}/runs/{run_id}", headers=guest)).status_code == 200
        assert (await client.get(f"{API}/runs/{run_id}", headers=ALICE)).status_code == 404
        assert [r["id"] for r in (await client.get(f"{API}/runs", headers=guest)).json()] == [run_id]
        await client.post(f"{API}/runs/{run_id}/cancel", headers=guest)


# --- counterexample replay ---


async def test_replay_is_501_without_a_replay_runner(tmp_path: Path) -> None:
    factory = Factory(RecordedSession)
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(lambda: gone(app, run_id))
        response = await client.post(f"{API}/counterexamples/{run_id}_cx_001/replay", headers=ALICE)
    assert response.status_code == 501


async def test_replay_starts_a_run_for_the_owner_only(tmp_path: Path) -> None:
    factory = Factory(RecordedSession)
    replays: list[tuple[RunSpec, CounterexampleRecord]] = []

    def replay_factory(spec: RunSpec, cx: CounterexampleRecord) -> RunSession:
        replays.append((spec, cx))
        return QuestionSession(spec)

    app = make_app(tmp_path, factory, replay_factory=replay_factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(lambda: gone(app, run_id))
        cx_url = f"{API}/counterexamples/{run_id}_cx_001/replay"
        stranger = await client.post(cx_url, headers=BOB)
        missing = await client.post(f"{API}/counterexamples/{run_id}_cx_999/replay", headers=ALICE)
        response = await client.post(cx_url, headers=ALICE)
        assert response.status_code == 200
        new_run = response.json()["run_id"]
        assert new_run != run_id
        assert (await client.get(f"{API}/runs/{new_run}", headers=ALICE)).status_code == 200
        await client.post(f"{API}/runs/{new_run}/cancel", headers=ALICE)
    assert stranger.status_code == 404 and missing.status_code == 404
    [(spec, cx)] = replays
    assert cx.id == f"{run_id}_cx_001" and spec.repo.ref == DEMO.ref and spec.user_id == "u_alice"
