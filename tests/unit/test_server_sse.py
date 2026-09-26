"""ROOK-029: `GET /runs/{id}/events?after=N`: the SSE format the web client (web/lib/sse.ts) reads, resume
after a seq, the live tail, pings, and the fatal 400 for a bad `after`."""

import json
from pathlib import Path

import pytest
from server_helpers import (
    ALICE,
    RECORDED_RUN,
    Factory,
    RawStream,
    RecordedSession,
    client_for,
    create_run,
    make_app,
    parse_sse,
    state_of,
    wait_for,
)

API = "/api/v1"
BOB_PREFIX = "bob" + "_prod_"
GH_PREFIX = "gh" + "p_"


async def test_a_finished_run_replays_every_event_then_ends(tmp_path: Path) -> None:
    factory = Factory(RecordedSession)
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(lambda: state_of(app).runs.live(run_id) is None)
        response = await client.get(f"{API}/runs/{run_id}/events", headers=ALICE)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "no-cache" in response.headers["cache-control"]
    envelopes = parse_sse(response.text)
    recorded = json.loads(RECORDED_RUN.read_text(encoding="utf-8"))
    assert [e["seq"] for e in envelopes] == list(range(1, len(recorded) + 1))
    assert [e["type"] for e in envelopes] == [e["type"] for e in recorded]
    assert all(e["run_id"] == run_id and e["v"] == 1 and e["ts"] for e in envelopes)
    assert envelopes[-1]["type"] == "run.finished"
    progress = [e["data"]["pct"] for e in envelopes if e["type"] == "engine.progress"]
    assert progress and all(0 <= p <= 100 for p in progress)


@pytest.mark.parametrize("after", [0, 1, 300, 368, 369, 5000])
async def test_resume_sends_only_the_events_after_the_seq(tmp_path: Path, after: int) -> None:
    factory = Factory(RecordedSession)
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(lambda: state_of(app).runs.live(run_id) is None)
        response = await client.get(f"{API}/runs/{run_id}/events", params={"after": after}, headers=ALICE)
    assert response.status_code == 200
    assert [e["seq"] for e in parse_sse(response.text)] == list(range(after + 1, 370))


@pytest.mark.parametrize("after", ["-1", "abc", "1.5", str(2**60)])
async def test_a_bad_after_is_400_which_the_client_treats_as_fatal(tmp_path: Path, after: str) -> None:
    factory = Factory(RecordedSession)
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(lambda: state_of(app).runs.live(run_id) is None)
        response = await client.get(f"{API}/runs/{run_id}/events", params={"after": after}, headers=ALICE)
    assert response.status_code == 400


async def test_live_tail_then_resume_from_the_last_seq(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(factory.sessions[run_id].asked.is_set)
        path = f"{API}/runs/{run_id}/events"

        live = RawStream(app, path, "after=0", ALICE)
        await live.read_until('"type":"question.asked"')
        assert live.status == 200 and live.headers["content-type"].startswith("text/event-stream")
        seen = parse_sse(live.text)
        assert [e["type"] for e in seen] == ["run.created", "question.asked"]

        # The client drops, the run goes on, and the client resumes after the last seq it saw.
        await live.close()
        await client.post(f"{API}/runs/{run_id}/chat", json={"text": "status?"}, headers=ALICE)
        await wait_for(lambda: state_of(app).store.last_seq(run_id) == 3)
        resumed = RawStream(app, path, f"after={seen[-1]['seq']}", ALICE)
        await resumed.read_until('"type":"chat.message"')
        assert (await client.post(f"{API}/runs/{run_id}/answers", json={"question_id": "q_fix", "answer": True},
                                  headers=ALICE)).json() == {"ok": True}
        text = await resumed.read_until('"type":"run.finished"')
        await resumed.close()
    tail = parse_sse(text)
    assert [e["seq"] for e in tail] == [3, 4, 5]
    assert [e["type"] for e in tail] == ["chat.message", "question.answered", "run.finished"]


async def test_a_queued_run_streams_once_it_starts(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, max_concurrent_runs=1)
    async with client_for(app) as client:
        first = await create_run(client, ALICE)
        await wait_for(factory.sessions[first].asked.is_set)
        queued = await create_run(client, ALICE)
        stream = RawStream(app, f"{API}/runs/{queued}/events", "", ALICE)
        await stream.read_until(": connected")
        await client.post(f"{API}/runs/{first}/answers", json={"question_id": "q_fix", "answer": False},
                          headers=ALICE)
        text = await stream.read_until('"type":"question.asked"')
        await client.post(f"{API}/runs/{queued}/cancel", headers=ALICE)
        text = await stream.read_until('"type":"run.finished"')
        await stream.close()
    assert [e["type"] for e in parse_sse(text)] == ["run.created", "question.asked", "run.finished"]


async def test_pings_keep_an_idle_stream_open(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory, ping_seconds=0.05)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(factory.sessions[run_id].asked.is_set)
        stream = RawStream(app, f"{API}/runs/{run_id}/events", "after=2", ALICE)
        text = await stream.read_until(": ping")
        await stream.close()
        await client.post(f"{API}/runs/{run_id}/cancel", headers=ALICE)
    assert ": ping" in text and parse_sse(text) == []


async def test_secrets_in_events_are_redacted_on_the_wire(tmp_path: Path) -> None:
    factory = Factory()
    app = make_app(tmp_path, factory)
    async with client_for(app) as client:
        run_id = await create_run(client, ALICE)
        await wait_for(factory.sessions[run_id].asked.is_set)
        fake = f"key {BOB_PREFIX}abc123 token {GH_PREFIX}ABCDEF123456"  # fake values, built so no literal is in git
        await state_of(app).bus.publish(run_id, "log", {"level": "error", "text": fake})
        await client.post(f"{API}/runs/{run_id}/cancel", headers=ALICE)
        await wait_for(lambda: state_of(app).runs.live(run_id) is None)
        response = await client.get(f"{API}/runs/{run_id}/events", headers=ALICE)
    assert BOB_PREFIX not in response.text and GH_PREFIX not in response.text
    assert "[REDACTED]" in response.text
