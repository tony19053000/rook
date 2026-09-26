"""minishop's own "normal" test suite: happy paths only, so it passes on the buggy version too."""

import importlib.util
from pathlib import Path

import httpx
import pytest

_spec = importlib.util.spec_from_file_location("minishop_app_under_test", Path(__file__).parent / "app.py")
assert _spec is not None and _spec.loader is not None
minishop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(minishop)


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=minishop.create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://minishop") as c:
        yield c


async def _login(client: httpx.AsyncClient, email: str, password: str) -> dict[str, str]:
    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def _admin(client: httpx.AsyncClient) -> dict[str, str]:
    return await _login(client, "admin@demo.local", "admin-pass")


async def _customer(client: httpx.AsyncClient, email: str = "c@x.io") -> dict[str, str]:
    r = await client.post("/auth/signup", json={"email": email, "password": "pw"})
    assert r.status_code == 200 and isinstance(r.json()["id"], int)
    return await _login(client, email, "pw")


async def _product(client: httpx.AsyncClient, price: int = 100, stock: int = 5) -> int:
    r = await client.post(
        "/products", json={"name": "mug", "price": price, "stock": stock}, headers=await _admin(client)
    )
    assert r.status_code == 200
    return r.json()["id"]


async def _order(client: httpx.AsyncClient, headers: dict[str, str], price: int = 100) -> int:
    product_id = await _product(client, price=price)
    r = await client.post("/orders", json={"product_id": product_id}, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


async def test_health(client: httpx.AsyncClient) -> None:
    r = await client.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


async def test_signup_and_login(client: httpx.AsyncClient) -> None:
    await _customer(client)
    r = await client.post("/auth/login", json={"email": "c@x.io", "password": "wrong"})
    assert r.status_code == 401 and "detail" in r.json()


async def test_duplicate_signup_conflicts(client: httpx.AsyncClient) -> None:
    await _customer(client)
    r = await client.post("/auth/signup", json={"email": "c@x.io", "password": "pw"})
    assert r.status_code == 409


async def test_missing_token_is_401(client: httpx.AsyncClient) -> None:
    assert (await client.post("/orders", json={"product_id": 1})).status_code == 401


async def test_customer_cannot_create_product(client: httpx.AsyncClient) -> None:
    r = await client.post("/products", json={"name": "x", "price": 1, "stock": 1}, headers=await _customer(client))
    assert r.status_code == 403


async def test_bad_payload_is_400(client: httpx.AsyncClient) -> None:
    r = await client.post("/products", json={"name": "x", "price": -1, "stock": 1}, headers=await _admin(client))
    assert r.status_code == 400 and "detail" in r.json()


async def test_buy_decrements_stock(client: httpx.AsyncClient) -> None:
    headers = await _customer(client)
    product_id = await _product(client, price=100, stock=5)
    r = await client.post("/orders", json={"product_id": product_id, "quantity": 2}, headers=headers)
    assert r.status_code == 200
    assert r.json()["paid"] == 200 and r.json()["status"] == "paid"
    assert (await client.get(f"/products/{product_id}")).json()["stock"] == 3


async def test_buy_out_of_stock_conflicts(client: httpx.AsyncClient) -> None:
    headers = await _customer(client)
    product_id = await _product(client, stock=0)
    r = await client.post("/orders", json={"product_id": product_id}, headers=headers)
    assert r.status_code == 409


async def test_single_refund(client: httpx.AsyncClient) -> None:
    headers = await _customer(client)
    order_id = await _order(client, headers)
    r = await client.post(f"/orders/{order_id}/refunds", json={"amount": 60}, headers=headers)
    assert r.status_code == 200 and r.json() == {"refunded_total": 60}
    too_big = await client.post(f"/orders/{order_id}/refunds", json={"amount": 101}, headers=headers)
    assert too_big.status_code == 400


async def test_cancel(client: httpx.AsyncClient) -> None:
    headers = await _customer(client)
    order_id = await _order(client, headers)
    assert (await client.post(f"/orders/{order_id}/cancel", headers=headers)).status_code == 200
    assert (await client.get(f"/orders/{order_id}", headers=headers)).json()["status"] == "cancelled"


async def test_ship_paid_order(client: httpx.AsyncClient) -> None:
    headers = await _customer(client)
    order_id = await _order(client, headers)
    assert (await client.post(f"/orders/{order_id}/ship", headers=headers)).status_code == 200
    body = (await client.get(f"/orders/{order_id}", headers=headers)).json()
    assert body == {"id": order_id, "paid": 100, "refunded_total": 0, "status": "paid", "shipped": True}


async def test_other_customer_cannot_read_order(client: httpx.AsyncClient) -> None:
    order_id = await _order(client, await _customer(client, "a@x.io"))
    r = await client.get(f"/orders/{order_id}", headers=await _customer(client, "b@x.io"))
    assert r.status_code == 403


async def test_admin_export_as_admin(client: httpx.AsyncClient) -> None:
    order_id = await _order(client, await _customer(client))
    r = await client.get("/admin/export", headers=await _admin(client))
    assert r.status_code == 200 and [o["id"] for o in r.json()] == [order_id]
