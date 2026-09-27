"""ROOK-039b: volatile app values are masked deterministically in what Bob sees; real evidence stays."""

import json
import secrets
import uuid

from rook.agents.coordinator import state_summary
from rook.agents.volatile import TIME, Masker, is_time_key, is_token_key, looks_random, mask_text
from rook.core.rails import RunState


def test_token_and_time_keys() -> None:
    for key in ("token", "access_token", "refreshToken", "Authorization", "api_key", "sessionId", "password"):
        assert is_token_key(key), key
    for key in ("created_at", "paidAt", "updated", "timestamp", "expires", "ts", "due_date"):
        assert is_time_key(key), key
    for key in ("amount", "paid", "status", "refunded_total", "tokens_left", "count", "add_on", "seat"):
        assert not is_token_key(key) and not is_time_key(key), key


def test_random_words_are_told_from_real_ones() -> None:
    assert looks_random(secrets.token_hex(16))
    assert looks_random("3fZ8kQ2mV9xL1pR7tB4nW6yH0cJ5")
    for word in ("SuperLongProductName2024Edition", "refund_le_paid_total", "item-description-long",
                 "cancelled_never_ships", "/workspace/src/services/refunds"):
        assert not looks_random(word), word


def test_value_masks_tokens_times_and_random_ids_but_keeps_evidence() -> None:
    token = secrets.token_urlsafe(24)
    receipt = str(uuid.uuid4())
    body = {
        "token": token, "user": {"accessToken": token, "id": 7},
        "created_at": "2026-09-27T10:11:12.345Z", "paidAt": "2026-09-27 10:11:12", "updated": 1790000000,
        "expires_in": 3600, "receipt": receipt, "nonce_hex": secrets.token_hex(20), "note": "Bearer " + token,
        "amount": 1790000000, "paid": 100, "refunded": 120, "status": "refunded", "count": 3, "ok": True,
        "deleted_at": None, "name": "Blue mug", "due": "2026-10-01",
    }
    out = Masker().value(body)
    assert out["token"] == out["user"]["accessToken"] == "<token#1>"  # the same token keeps its label
    assert out["note"] == "Bearer <token#1>"
    assert out["created_at"] == out["paidAt"] == out["updated"] == TIME
    assert out["receipt"] == "<uuid#1>" and out["nonce_hex"] == "<random#1>"
    # evidence: amounts (even a large one), counts, statuses, booleans, nulls, names, durations, dates
    for key in ("amount", "paid", "refunded", "status", "count", "ok", "deleted_at", "name", "expires_in", "due"):
        assert out[key] == body[key], key
    assert out["user"]["id"] == 7


def test_two_runs_with_different_random_values_look_the_same() -> None:
    def response() -> dict:
        return {"token": secrets.token_urlsafe(24), "session": secrets.token_hex(16),
                "created_at": f"2026-09-27T10:11:{secrets.randbelow(60):02d}Z", "id": str(uuid.uuid4()),
                "items": [{"sku": "A-1", "qty": 2}]}

    assert json.dumps(Masker().value(response())) == json.dumps(Masker().value(response()))


def test_fresh_values_rook_sent_are_masked() -> None:
    fresh = secrets.token_hex(5)
    masker = Masker((fresh,))
    assert masker.value({"email": f"u{fresh}x1@rook.test", "name": f"item-{fresh}"}) == \
        {"email": "u<fresh>x1@rook.test", "name": "item-<fresh>"}
    assert masker.text(f"created item-{fresh}") == "created item-<fresh>"


def test_text_masks_in_place() -> None:
    token = secrets.token_urlsafe(24)
    line = (f"2026-09-27T01:31:08Z login ok token={token} Authorization: Bearer {token} "
            f"request {uuid.uuid4()} from 10.0.0.5:5432 in 3 ms; order 7 paid 100")
    out = mask_text(line)
    assert out == ("<time> login ok token=<token#1> Authorization: Bearer <token#1> "
                   "request <uuid#1> from <addr> in <ms>; order 7 paid 100")
    assert mask_text(json.dumps({"access_token": token, "amount": 50})) == '{"access_token": "<token#1>", "amount": 50}'


def test_coordinator_notes_are_masked() -> None:
    note = f"verify failed at 2026-09-27T10:00:00Z with token={secrets.token_urlsafe(24)}"
    summary = state_summary(RunState(), "verify_failed", None, None, [note])
    assert summary["notes"] == ["verify failed at <time> with token=<token#1>"]
