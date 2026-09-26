"""Scripted sequences proving each minishop bug reproduces, and that fixed mode blocks all four."""

import asyncio
import importlib.util
from pathlib import Path

import httpx
import pytest
import yaml

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "minishop"

_spec = importlib.util.spec_from_file_location("minishop_app_bugs", FIXTURE_DIR / "app.py")
assert _spec is not None and _spec.loader is not None
minishop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(minishop)


class Shop:
    """A client with a logged-in admin and customer, for scripting sequences."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self.admin: dict[str, str] = {}
        self.customer: dict[str, str] = {}

    async def login(self, email: str, password: str) -> dict[str, str]:
        r = await self.client.post("/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {r.json()['token']}"}

    async def setup(self) -> None:
        self.admin = await self.login("admin@demo.local", "admin-pass")
        await self.client.post("/auth/signup", json={"email": "c@x.io", "password": "pw"})
        self.customer = await self.login("c@x.io", "pw")

    async def product(self, price: int, stock: int) -> int:
        body = {"name": "mug", "price": price, "stock": stock}
        return (await self.client.post("/products", json=body, headers=self.admin)).json()["id"]

    async def buy(self, product_id: int) -> httpx.Response:
        return await self.client.post("/orders", json={"product_id": product_id}, headers=self.customer)

    async def order(self, order_id: int) -> dict:
        return (await self.client.get(f"/orders/{order_id}", headers=self.admin)).json()


async def _shop(fixed: bool):
    transport = httpx.ASGITransport(app=minishop.create_app(fixed=fixed))
    async with httpx.AsyncClient(transport=transport, base_url="http://minishop") as client:
        shop = Shop(client)
        await shop.setup()
        yield shop


@pytest.fixture
async def buggy():
    async for shop in _shop(fixed=False):
        yield shop


@pytest.fixture
async def fixed():
    async for shop in _shop(fixed=True):
        yield shop


async def _refund_60_then_50(shop: Shop) -> tuple[httpx.Response, dict]:
    order_id = (await shop.buy(await shop.product(price=100, stock=1))).json()["id"]
    first = await shop.client.post(f"/orders/{order_id}/refunds", json={"amount": 60}, headers=shop.customer)
    assert first.status_code == 200
    second = await shop.client.post(f"/orders/{order_id}/refunds", json={"amount": 50}, headers=shop.customer)
    return second, await shop.order(order_id)


async def _two_buys_of_last_item(shop: Shop) -> tuple[list[httpx.Response], int]:
    product_id = await shop.product(price=10, stock=1)
    responses = await asyncio.gather(shop.buy(product_id), shop.buy(product_id))
    stock = (await shop.client.get(f"/products/{product_id}")).json()["stock"]
    return list(responses), stock


async def _ship_after_cancel(shop: Shop) -> tuple[httpx.Response, dict]:
    order_id = (await shop.buy(await shop.product(price=10, stock=1))).json()["id"]
    assert (await shop.client.post(f"/orders/{order_id}/cancel", headers=shop.customer)).status_code == 200
    shipped = await shop.client.post(f"/orders/{order_id}/ship", headers=shop.customer)
    return shipped, await shop.order(order_id)


# --- bugs reproduce on the buggy app ---


async def test_bug1_refunds_exceed_paid(buggy: Shop) -> None:
    second, order = await _refund_60_then_50(buggy)
    assert second.status_code == 200 and second.json() == {"refunded_total": 110}
    assert order["refunded_total"] == 110 and order["paid"] == 100


async def test_bug2_concurrent_buys_oversell(buggy: Shop) -> None:
    responses, stock = await _two_buys_of_last_item(buggy)
    assert [r.status_code for r in responses] == [200, 200]
    assert stock == -1


async def test_bug3_ship_after_cancel(buggy: Shop) -> None:
    shipped, order = await _ship_after_cancel(buggy)
    assert shipped.status_code == 200
    assert order["status"] == "cancelled" and order["shipped"] is True


async def test_bug4_customer_opens_admin_export(buggy: Shop) -> None:
    r = await buggy.client.get("/admin/export", headers=buggy.customer)
    assert r.status_code == 200


# --- fixed mode blocks all four ---


async def test_fixed_refunds_are_cumulative(fixed: Shop) -> None:
    second, order = await _refund_60_then_50(fixed)
    assert second.status_code == 400 and "detail" in second.json()
    assert order["refunded_total"] == 60


async def test_fixed_concurrent_buys_do_not_oversell(fixed: Shop) -> None:
    responses, stock = await _two_buys_of_last_item(fixed)
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert stock == 0


async def test_fixed_ship_after_cancel_conflicts(fixed: Shop) -> None:
    shipped, order = await _ship_after_cancel(fixed)
    assert shipped.status_code == 409 and "detail" in shipped.json()
    assert order["shipped"] is False


async def test_fixed_admin_export_forbidden_for_customer(fixed: Shop) -> None:
    r = await fixed.client.get("/admin/export", headers=fixed.customer)
    assert r.status_code == 403
    assert (await fixed.client.get("/admin/export", headers=fixed.admin)).status_code == 200


async def test_cancel_after_ship_is_refused_in_both_modes(buggy: Shop, fixed: Shop) -> None:
    for shop in (buggy, fixed):
        order_id = (await shop.buy(await shop.product(price=10, stock=1))).json()["id"]
        assert (await shop.client.post(f"/orders/{order_id}/ship", headers=shop.customer)).status_code == 200
        assert (await shop.client.post(f"/orders/{order_id}/cancel", headers=shop.customer)).status_code == 409


# --- mode selection and model file ---


def test_fixed_mode_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINISHOP_FIXED", "1")
    assert minishop.create_app().state.fixed is True
    monkeypatch.delenv("MINISHOP_FIXED")
    assert minishop.create_app().state.fixed is False
    assert minishop.create_app(fixed=True).state.fixed is True


async def test_admin_password_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINISHOP_ADMIN_PASSWORD", "other-pass")
    transport = httpx.ASGITransport(app=minishop.create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://minishop") as client:
        creds = {"email": "admin@demo.local"}
        assert (await client.post("/auth/login", json={**creds, "password": "admin-pass"})).status_code == 401
        assert (await client.post("/auth/login", json={**creds, "password": "other-pass"})).status_code == 200


def test_rook_yaml_parses_and_has_the_four_rules() -> None:
    model = yaml.safe_load((FIXTURE_DIR / "rook.yaml").read_text())
    assert model["version"] == 1
    assert {a["name"] for a in model["actors"]} == {"customer", "admin"}
    assert {a["name"] for a in model["actions"]} == {
        "create_product", "buy", "refund", "cancel", "ship", "admin_export",
    }
    assert {s["name"] for s in model["state"]} == {"order", "product"}
    rules = {r["id"]: r for r in model["rules"]}
    assert set(rules) == {"refund_le_paid", "stock_non_negative", "cancelled_never_ships", "admin_export_forbidden"}
    assert all(r["status"] == "approved" for r in rules.values())
    assert rules["admin_export_forbidden"]["kind"] == "response"
    assert rules["admin_export_forbidden"]["when"] == {"action": "admin_export", "actor": "customer"}
    assert rules["cancelled_never_ships"]["check"] == 'not (order.status == "cancelled" and order.shipped)'
