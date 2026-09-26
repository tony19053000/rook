"""ROOK-006: the HTTP executor, run in-process against minishop via httpx.ASGITransport."""

import asyncio
import importlib.util
import random
import re
from pathlib import Path

import httpx
import pytest

from rook.engine.executor import EgressError, Executor, SequenceContext, StepResult
from rook.model.loader import load_model, load_model_str
from rook.model.schema import ParallelStep, Step

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "minishop"
BASE = "http://minishop.test"
ENV = {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}  # the fixture's built-in default, not a secret

_spec = importlib.util.spec_from_file_location("minishop_app_executor", FIXTURE_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
minishop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(minishop)

MODEL = load_model(FIXTURE_DIR / "rook.yaml")


def _executor(app, **kwargs) -> Executor:
    return Executor(MODEL, BASE, transport=httpx.ASGITransport(app=app), env=ENV, **kwargs)


@pytest.fixture
async def ex():
    async with _executor(minishop.create_app(fixed=False)) as executor:
        yield executor


async def _step(ex: Executor, ctx: SequenceContext, action: str, **params) -> StepResult:
    result = await ex.run_step(ctx, Step(action=action, params=params), random.Random(0))
    assert isinstance(result, StepResult)
    return result


async def test_actor_setup_gives_working_token(ex: Executor) -> None:
    ctx = ex.new_context()
    namespace = await ex.setup_actor(ctx, "customer")
    assert isinstance(namespace["token"], str) and namespace["token"]
    assert ctx.auth_headers["customer"] == {"Authorization": f"Bearer {namespace['token']}"}
    # Each actor setup gets its own fresh values, so a second customer signs up fine.
    other = await ex.setup_actor(ctx, "customer")
    assert other["token"] != namespace["token"]
    # The token works: the export endpoint (login required) answers 200.
    result = await _step(ex, ctx, "admin_export")
    assert result.status == 200 and result.error is None


async def test_refund_60_then_50_exceeds_paid_in_buggy_mode(ex: Executor) -> None:
    ctx = ex.new_context()
    created = await _step(ex, ctx, "create_product", price=100, stock=5)
    assert created.status == 200
    bought = await _step(ex, ctx, "buy", quantity=1)
    assert bought.status == 200 and bought.refs_used == {"product_id": created.response_json["id"]}
    assert (await _step(ex, ctx, "refund", amount=60)).status == 200
    second = await _step(ex, ctx, "refund", amount=50)
    assert second.status == 200
    assert second.request == {
        "method": "POST",
        "path": f"/orders/{bought.response_json['id']}/refunds",
        "json": {"amount": 50},
    }
    state = await ex.read_state(ctx)
    order_id = bought.response_json["id"]
    assert state["order"][order_id]["paid"] == 100
    assert state["order"][order_id]["refunded"] == 110
    assert state["product"][created.response_json["id"]] == {"stock": 4}
    assert await ex.read_state(ctx, "order", only_ids=[order_id]) == {
        "order": {order_id: state["order"][order_id]}
    }


async def test_refund_blocked_in_fixed_mode() -> None:
    async with _executor(minishop.create_app(fixed=True)) as ex:
        ctx = ex.new_context()
        await _step(ex, ctx, "create_product", price=100, stock=5)
        await _step(ex, ctx, "buy", quantity=1)
        await _step(ex, ctx, "refund", amount=60)
        assert (await _step(ex, ctx, "refund", amount=50)).status == 400
        (order,) = (await ex.read_state(ctx, "order"))["order"].values()
        assert order["refunded"] == 60


async def test_captures_fill_the_pool(ex: Executor) -> None:
    ctx = ex.new_context()
    p1 = await _step(ex, ctx, "create_product", price=10, stock=3)
    p2 = await _step(ex, ctx, "create_product", price=20, stock=3)
    assert ctx.pool["product_id"] == [p1.response_json["id"], p2.response_json["id"]]
    await _step(ex, ctx, "buy", quantity=1)
    assert len(ctx.pool["order_id"]) == 1
    # A failed request captures nothing.
    before = list(ctx.pool["order_id"])
    ctx.pool["product_id"] = [999_999]
    failed = await _step(ex, ctx, "buy", quantity=1)
    assert failed.status == 404 and ctx.pool["order_id"] == before


async def test_missing_ref_is_recorded(ex: Executor) -> None:
    ctx = ex.new_context()
    result = await _step(ex, ctx, "refund", amount=1)
    assert result.status is None and "order_id" in (result.error or "")


async def test_parallel_buys_of_last_item_run_concurrently(ex: Executor) -> None:
    ctx = ex.new_context()
    product = await _step(ex, ctx, "create_product", price=10, stock=1)
    step = ParallelStep(parallel=[Step(action="buy", params={"quantity": 1})] * 2)
    results = await ex.run_step(ctx, step, random.Random(1))
    assert isinstance(results, list) and [r.status for r in results] == [200, 200]
    assert len(ctx.pool["order_id"]) == 2
    state = await ex.read_state(ctx, "product")
    assert state["product"][product.response_json["id"]]["stock"] == -1


async def test_egress_violation_raises(ex: Executor) -> None:
    with pytest.raises(EgressError):
        ex.check_egress(httpx.URL("http://evil.test/x"))
    with pytest.raises(EgressError):
        ex.check_egress(httpx.URL("http://minishop.test:8080/x"))
    with pytest.raises(EgressError):
        ex.check_egress(httpx.URL("https://minishop.test/x"))
    ex.check_egress(httpx.URL("http://minishop.test:80/ok"))  # same origin, explicit default port


EVIL_MODEL = load_model_str(
    """
version: 1
actors: [{name: u}]
actions:
  - {name: seed, actor: u, request: {method: GET, path: /seed}, capture: {x: "$.x"}}
  - {name: go, actor: u, request: {method: GET, path: "/{{ref.x}}"}, requires: [x]}
  - {name: slow, actor: u, request: {method: GET, path: /slow}, capture: {y: "$.y"}}
state:
  - {name: thing, each: x, request: {method: GET, path: "/{{x}}"}, fields: {v: "$.v"}}
"""
)


async def _slow_sibling_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/slow" or request.url.path == "/ok":
        await asyncio.sleep(0.05)  # still in flight when the refused sibling fails
    return httpx.Response(200, json={"y": 7, "v": 1})


def _other_tasks() -> set[asyncio.Task]:
    return asyncio.all_tasks() - {asyncio.current_task()}


async def test_egress_in_parallel_step_waits_for_siblings_and_keeps_their_captures() -> None:
    transport = httpx.MockTransport(_slow_sibling_handler)
    async with Executor(EVIL_MODEL, "http://127.0.0.1:9000", transport=transport) as ex:
        ctx = ex.new_context()
        ctx.pool["x"] = ["/evil.test/steal"]
        before = _other_tasks()
        step = ParallelStep(parallel=[Step(action="go"), Step(action="slow")])
        with pytest.raises(EgressError) as info:
            await ex.run_step(ctx, step, random.Random(0))
        assert _other_tasks() == before  # no request left running in the background
        assert ctx.pool["y"] == [7]  # the sibling finished and its capture was applied
        refused, sibling = info.value.results or []
        assert "EgressError" in (refused.error or "") and refused.status is None
        assert sibling.status == 200 and sibling.error is None


async def test_egress_in_read_state_waits_for_all_reads() -> None:
    transport = httpx.MockTransport(_slow_sibling_handler)
    async with Executor(EVIL_MODEL, "http://127.0.0.1:9000", transport=transport) as ex:
        ctx = ex.new_context()
        ctx.pool["x"] = ["ok", "/evil.test/steal"]
        before = _other_tasks()
        with pytest.raises(EgressError):
            await ex.read_state(ctx, "thing")
        assert _other_tasks() == before
        ctx.pool["x"] = ["ok"]
        assert await ex.read_state(ctx, "thing") == {"thing": {"ok": {"v": 1}}}


INJECT_MODEL = load_model_str(
    r"""
version: 1
actors: [{name: u}]
actions:
  - name: hdr
    actor: u
    request: {method: GET, path: /h, headers: {X-A: "{{p.h}}"}}
    params: {h: {choice: ["a\r\nX-Evil: 1"]}}
  - name: pth
    actor: u
    request: {method: GET, path: "/p/{{p.h}}"}
    params: {h: {choice: ["a\r\nHost: evil.test", "tab\there", "del\x7f"]}}
"""
)


async def test_control_characters_in_headers_and_paths_are_refused_before_sending() -> None:
    seen: list[str] = []

    async def app(scope, receive, send) -> None:
        seen.append(scope["path"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async with Executor(INJECT_MODEL, BASE, transport=httpx.ASGITransport(app=app)) as ex:
        ctx = ex.new_context()
        rng = random.Random(0)
        results = [await ex.run_step(ctx, Step(action="hdr"), rng)]
        results += [await ex.run_step(ctx, Step(action="pth"), rng) for _ in range(12)]
    for r in results:
        assert isinstance(r, StepResult) and r.status is None
        assert "control characters" in (r.error or "")
    assert seen == []


async def test_pinned_refs_use_the_pool_index(ex: Executor) -> None:
    ctx = ex.new_context()
    first = await _step(ex, ctx, "create_product", price=10, stock=5)
    second = await _step(ex, ctx, "create_product", price=20, stock=5)
    for index, product in ((0, first), (1, second), (0, first)):
        result = await ex.run_step(
            ctx, Step(action="buy", params={"quantity": 1}), random.Random(9), {"product_id": index}
        )
        assert isinstance(result, StepResult) and result.status == 200
        assert result.refs_index == {"product_id": index}
        assert result.refs_used == {"product_id": product.response_json["id"]}
        assert result.response_json["paid"] == product.request["json"]["price"]

    # Random picks record their index too, consistent with the pool.
    rnd = await _step(ex, ctx, "refund", amount=1)
    assert ctx.pool["order_id"][rnd.refs_index["order_id"]] == rnd.refs_used["order_id"]

    out_of_range = await ex.run_step(
        ctx, Step(action="refund", params={"amount": 1}), random.Random(0), {"order_id": 3}
    )
    assert isinstance(out_of_range, StepResult) and out_of_range.status is None
    assert "out of range" in (out_of_range.error or "")
    negative = await ex.run_step(
        ctx, Step(action="refund", params={"amount": 1}), random.Random(0), {"order_id": -1}
    )
    assert isinstance(negative, StepResult) and "out of range" in (negative.error or "")

    # A parallel step takes one pin mapping per sub-step.
    step = ParallelStep(parallel=[Step(action="refund", params={"amount": 1})] * 2)
    pair = await ex.run_step(ctx, step, random.Random(0), [{"order_id": 2}, {"order_id": 0}])
    assert isinstance(pair, list) and [r.refs_index for r in pair] == [{"order_id": 2}, {"order_id": 0}]
    with pytest.raises(ValueError):
        await ex.run_step(ctx, step, random.Random(0), [{"order_id": 0}])


async def test_egress_via_captured_value_raises_and_is_never_sent() -> None:
    sent: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.url)
        return httpx.Response(200, json={"x": "/evil.test/steal"})

    async with Executor(EVIL_MODEL, "http://127.0.0.1:9000", transport=httpx.MockTransport(handler)) as ex:
        ctx = ex.new_context()
        await ex.run_step(ctx, Step(action="seed"), random.Random(0))
        assert ctx.pool["x"] == ["/evil.test/steal"]
        with pytest.raises(EgressError):
            await ex.run_step(ctx, Step(action="go"), random.Random(0))
        # A host-like value in the middle of a path stays a path on the sandbox host.
        ctx.pool["x"] = ["a@evil.test:1/x"]
        result = await ex.run_step(ctx, Step(action="go"), random.Random(0))
        assert isinstance(result, StepResult) and result.status == 200
    assert [u.host for u in sent] == ["127.0.0.1", "127.0.0.1"]


async def test_redirects_are_not_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/admin/export":
            return httpx.Response(302, headers={"location": "http://evil.test/"})
        return httpx.Response(200, json={"token": "t", "id": 1})

    async with Executor(
        MODEL, "http://127.0.0.1:9000", transport=httpx.MockTransport(handler), env=ENV
    ) as ex:
        result = await ex.run_step(ex.new_context(), Step(action="admin_export"), random.Random(0))
    assert isinstance(result, StepResult) and result.status == 302 and result.error is None


async def test_transport_error_is_recorded_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with Executor(
        MODEL, "http://127.0.0.1:9000", transport=httpx.MockTransport(handler), env=ENV
    ) as ex:
        ctx = ex.new_context()
        # The actor setup itself fails: recorded on the step.
        result = await ex.run_step(ctx, Step(action="admin_export"), random.Random(0))
        assert isinstance(result, StepResult)
        assert result.status is None and "ConnectError" in (result.error or "")
        # State reads fail quietly into ctx.state_errors.
        ctx.pool["order_id"] = [1]
        assert await ex.read_state(ctx, "order") == {"order": {}}
        assert ctx.state_errors


async def _slow_app(scope, receive, send) -> None:
    assert scope["type"] == "http"
    await asyncio.sleep(5)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


def _auth_ok_then(app_for_actions):
    """Actor setup answers immediately; actions go to `app_for_actions`."""

    async def app(scope, receive, send) -> None:
        if scope["path"].startswith("/auth/"):
            body = b'{"token": "t", "id": 1}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})
        else:
            await app_for_actions(scope, receive, send)

    return app


async def test_timeout_is_recorded_not_raised() -> None:
    app = _auth_ok_then(_slow_app)
    async with _executor(app, timeout=0.05) as ex:
        result = await ex.run_step(ex.new_context(), Step(action="admin_export"), random.Random(0))
    assert isinstance(result, StepResult)
    assert result.status is None and "timeout" in (result.error or "")


def _body_app(body: bytes, content_length: bool):
    async def app(scope, receive, send) -> None:
        headers = [(b"content-type", b"application/json")]
        if content_length:
            headers.append((b"content-length", str(len(body)).encode()))
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        # Stream in chunks so the cap is enforced while reading, not after.
        for i in range(0, len(body), 64_000):
            await send({"type": "http.response.body", "body": body[i : i + 64_000], "more_body": True})
        await send({"type": "http.response.body", "body": b""})

    return app


@pytest.mark.parametrize("content_length", [True, False])
async def test_response_size_cap(content_length: bool) -> None:
    big = b'"' + b"a" * 1_100_000 + b'"'
    app = _auth_ok_then(_body_app(big, content_length))
    async with _executor(app) as ex:
        result = await ex.run_step(ex.new_context(), Step(action="admin_export"), random.Random(0))
    assert isinstance(result, StepResult)
    assert "too large" in (result.error or "") and result.response_json is None


async def test_small_response_under_cap_and_non_json() -> None:
    app = _auth_ok_then(_body_app(b"not json", content_length=True))
    async with _executor(app) as ex:
        result = await ex.run_step(ex.new_context(), Step(action="admin_export"), random.Random(0))
    assert isinstance(result, StepResult)
    assert result.status == 200 and "not JSON" in (result.error or "")


def test_choose_params_is_deterministic_for_a_seed() -> None:
    ex = Executor(MODEL, BASE)
    draws = [[ex.choose_params(a, random.Random(42)) for a in MODEL.actions] for _ in range(2)]
    assert draws[0] == draws[1]
    rng = random.Random(7)
    many = [ex.choose_params("refund", rng)["amount"] for _ in range(2000)]
    assert all(1 <= v <= 500 for v in many)
    edge_share = sum(v in (1, 50, 60, 100) for v in many) / len(many)
    assert 0.25 < edge_share < 0.4  # ~30% edge bias plus a little uniform luck


def test_choose_params_choice_and_strings() -> None:
    model = load_model_str(
        """
version: 1
actors: [{name: u}]
actions:
  - name: a
    actor: u
    request: {method: POST, path: /x, json: {c: "{{p.c}}", v: "{{p.v}}", s: "{{p.s}}", g: "{{p.g}}"}}
    params:
      c: {choice: [red, green]}
      v: {string: {values: [x, y]}}
      s: {string: {pattern: "^[a-z]{3}-\\\\d{2,4}$"}}
      g: {string: {pattern: "(a|b)+"}}
"""
    )
    ex = Executor(model, BASE)
    rng = random.Random(3)
    for _ in range(50):
        params = ex.choose_params("a", rng)
        assert params["c"] in ("red", "green") and params["v"] in ("x", "y")
        assert re.fullmatch(r"[a-z]{3}-\d{2,4}", params["s"])
        assert re.fullmatch(r"s\d{1,4}", params["g"])  # unsupported pattern falls back


def test_base_url_must_be_http() -> None:
    with pytest.raises(ValueError):
        Executor(MODEL, "ftp://x")
