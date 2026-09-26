import asyncio
import json
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import ValidationError

from rook.core.events import (
    EVENT_TYPES,
    REDACTED,
    Event,
    EventBus,
    clear_secrets,
    redact,
    register_secret,
    validate_data,
)

# Fake secret-shaped strings are assembled at runtime so no secret pattern appears literally in the repo.
FAKE_BOB = "bob" + "_prod_" + "Zx81kLmN0pQ"
FAKE_GHP = "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0"
FAKE_GHS = "gh" + "s_" + "Q9w8E7r6T5y4U3i2O1p0"
FAKE_JWT = "ey" + "JhbGciOiJIUzI1NiJ9" + ".ey" + "JzdWIiOiIxMjMifQ" + ".c2lnbmF0dXJlX2hlcmU"
FAKE_PEM = "-----" + "BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAKj34\n-----END RSA PRIVATE KEY-----"
FAKE_BEARER_TOKEN = "tok" + "en.abc-123_XYZ"

SAMPLES: dict[str, dict[str, Any]] = {
    "run.created": {
        "repo": {"kind": "github", "ref": "main", "name": "acme/shop"},
        "request": "find refund bugs",
        "options": {"auto": False, "budget": 1.5},
    },
    "run.phase": {"phase": "SCOUT"},
    "agent.started": {"agent": "scout", "call_id": "c1", "detail": "reading repo"},
    "agent.progress": {"agent": "rule_critic", "call_id": "c2", "detail": "checking rule 3"},
    "agent.finished": {"agent": "scout", "call_id": "c1", "ok": True, "summary": "done", "cost": 0.02,
                       "recorded": False},
    "engine.started": {"worker": "runner", "label": "searching"},
    "engine.progress": {"worker": "runner", "pct": 42.5, "label": "searching", "count": 1200},
    "engine.finished": {"worker": "shrinker", "ok": True, "summary": "shrunk to 3 steps"},
    "question.asked": {"question_id": "q1", "kind": "approve_rules", "text": "Approve?",
                       "options": [{"id": "yes", "label": "Yes"}], "payload": {"rules": ["r1"]}},
    "question.answered": {"question_id": "q1", "answer": "yes", "by": "user"},
    "repo.summary": {"language": "python", "framework": "fastapi", "entrypoints": ["app.py"],
                     "routes_files": ["routes.py"], "models_files": ["models.py"], "test_command": "pytest",
                     "run_hints": "uvicorn app:app", "business_summary": "a shop"},
    "sandbox.ready": {"base_url_redacted": "http://127.0.0.1:****", "mode": "process"},
    "model.actions": {"actors": [{"id": "alice"}], "actions": [{"id": "buy"}], "state": [{"id": "order"}]},
    "rules.proposed": {"rules": [{"id": "r1", "text": "refunds <= paid"}]},
    "rules.reviewed": {"verdicts": [{"rule_id": "r1", "ok": True}]},
    "rules.approved": {"rule_ids": ["r1"]},
    "search.progress": {"sequences": 5000, "per_sec": 812.3, "rules": {"r1": "holding", "r2": "broken"}},
    "violation.found": {"violation_id": "v1", "rule_id": "r2", "steps_count": 9, "observed": {"refunded": 200}},
    "shrink.step": {"violation_id": "v1", "steps_count": 4},
    "counterexample.saved": {"cx_id": "cx_001", "rule_id": "r2", "rule_text": "refunds <= paid",
                             "steps": [{"action": "buy"}], "observed": 200, "expected": 100,
                             "reproduced": "10/10", "flaky": False, "test_path": "tests/rook_cx_001.py"},
    "diagnosis.ready": {"cx_id": "cx_001", "file": "app/refunds.py", "line": 42, "explanation": "per-refund check",
                        "reviewed": True},
    "fix.ready": {"cx_id": "cx_001", "files": ["app/refunds.py"], "diff": "--- a\n+++ b\n", "reviewed": True},
    "verify.step": {"cx_id": "cx_001", "check": "replay", "status": "passed", "detail": "10/10"},
    "verify.done": {"cx_id": "cx_001", "verified": True, "summary": "all checks passed"},
    "fix.committed": {"cx_id": "cx_001", "branch": "rook/fix-cx-001", "commit": "0123abcd", "files": ["app.py"]},
    "pr.opened": {"url": "https://github.com/acme/shop/pull/7", "number": 7, "branch": "rook/cx_001"},
    "chat.message": {"role": "guide", "text": "The search is at 5000 sequences."},
    "cost.update": {"coins_total": 0.46},
    "log": {"level": "warn", "text": "slow health check"},
    "run.finished": {"status": "done", "summary": "1 bug fixed"},
}


@pytest.fixture(autouse=True)
def _no_secrets() -> Iterator[None]:
    clear_secrets()
    yield
    clear_secrets()


# --- models ------------------------------------------------------------------


def test_samples_cover_every_event_type() -> None:
    assert set(SAMPLES) == set(EVENT_TYPES)
    assert len(EVENT_TYPES) == 30


@pytest.mark.parametrize("event_type", sorted(EVENT_TYPES))
def test_every_event_type_round_trips_to_json(event_type: str) -> None:
    event = Event(seq=1, ts="2026-09-26T08:10:00.123Z", run_id="r_8f2c", type=event_type,
                  data=validate_data(event_type, SAMPLES[event_type]))
    text = event.model_dump_json()
    parsed = json.loads(text)
    assert parsed["v"] == 1 and parsed["type"] == event_type and parsed["data"] == SAMPLES[event_type]
    again = Event.model_validate_json(text)
    assert again == event
    assert again.typed_data() == EVENT_TYPES[event_type].model_validate(SAMPLES[event_type])


def test_engine_progress_count_is_optional() -> None:
    assert validate_data("engine.progress", {"worker": "judge", "pct": 1, "label": "x"})["count"] is None


def test_invalid_event_data_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown event type"):
        validate_data("nope", {})
    with pytest.raises(ValidationError):
        validate_data("engine.started", {"worker": "wizard", "label": "x"})
    with pytest.raises(ValidationError):
        validate_data("log", {"level": "info", "text": "x", "extra": 1})
    with pytest.raises(ValidationError):
        validate_data("counterexample.saved", {**SAMPLES["counterexample.saved"], "reproduced": "ten"})


# --- redaction ---------------------------------------------------------------


@pytest.mark.parametrize("secret", [FAKE_BOB, FAKE_GHP, FAKE_GHS, FAKE_JWT, FAKE_PEM])
def test_redact_scrubs_each_pattern(secret: str) -> None:
    out = redact(f"before {secret} after")
    assert secret not in out
    assert REDACTED in out
    assert out.startswith("before ")


def test_redact_bearer_keeps_scheme() -> None:
    out = redact(f"Authorization: Bearer {FAKE_BEARER_TOKEN}")
    assert out == f"Authorization: Bearer {REDACTED}"


def test_redact_unterminated_pem() -> None:
    out = redact("key: -----" + "BEGIN OPENSSH PRIVATE KEY-----\nAAAAB3Nza")
    assert out == f"key: {REDACTED}"


def test_redact_registered_secret_values_in_nested_structures() -> None:
    register_secret("sup3r-s3cret-value")
    register_secret("ab")  # too short to register; must not scrub ordinary text
    obj = {
        "a": ["x", {"b": "token=sup3r-s3cret-value;", "c": [FAKE_GHP, 3, None, True]}],
        "sup3r-s3cret-value": ("t", f"Bearer {FAKE_BEARER_TOKEN}"),
        "n": 1.5,
        "plain": "about tables",
    }
    out = redact(obj)
    dumped = json.dumps(out, default=list)
    for secret in ("sup3r-s3cret-value", FAKE_GHP, FAKE_BEARER_TOKEN):
        assert secret not in dumped
    assert out["a"][1]["b"] == f"token={REDACTED};"
    assert out["a"][1]["c"][1:] == [3, None, True]
    assert out["n"] == 1.5 and out["plain"] == "about tables"
    assert obj["a"][1]["b"] == "token=sup3r-s3cret-value;"  # input not mutated


def test_redact_leaves_harmless_text() -> None:
    text = "the ghost of eyJ and bob_pro and BEGIN"
    assert redact(text) == text


async def test_bus_redacts_before_delivery() -> None:
    register_secret("sup3r-s3cret-value")
    bus = EventBus()
    event = await bus.publish("r1", "log", {"level": "error", "text": f"failed with sup3r-s3cret-value {FAKE_JWT}"})
    assert event.data["text"] == f"failed with {REDACTED} {REDACTED}"


# --- bus ---------------------------------------------------------------------


async def test_seq_is_monotonic_under_concurrent_publishes() -> None:
    bus = EventBus()
    events = await asyncio.gather(
        *(bus.publish("r1", "log", {"level": "info", "text": str(i)}) for i in range(200))
    )
    assert sorted(e.seq for e in events) == list(range(1, 201))
    other = await bus.publish("r2", "log", {"level": "info", "text": "x"})
    assert other.seq == 1  # seq is per run

    received = [e.seq async for e in _take(bus.subscribe("r1"), 200)]
    assert received == list(range(1, 201))


async def test_late_subscriber_gets_replay_then_live() -> None:
    bus = EventBus()
    for i in range(3):
        await bus.publish("r1", "log", {"level": "info", "text": f"old {i}"})

    got: list[Event] = []

    async def consume() -> None:
        async for event in bus.subscribe("r1", after=1):
            got.append(event)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    for i in range(2):
        await bus.publish("r1", "log", {"level": "info", "text": f"new {i}"})
    await bus.close("r1")
    await asyncio.wait_for(task, 1)
    assert [e.seq for e in got] == [2, 3, 4, 5]
    assert [e.data["text"] for e in got] == ["old 1", "old 2", "new 0", "new 1"]


async def test_subscribe_after_close_gets_replay_only() -> None:
    bus = EventBus()
    await bus.publish("r1", "run.finished", {"status": "done", "summary": "ok"})
    await bus.close("r1")
    assert [e.seq async for e in bus.subscribe("r1")] == [1]
    with pytest.raises(RuntimeError):
        await bus.publish("r1", "log", {"level": "info", "text": "late"})


async def _take(it: Any, n: int) -> Any:
    count = 0
    async for item in it:
        yield item
        count += 1
        if count == n:
            return
