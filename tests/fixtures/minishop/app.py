"""minishop: a tiny FastAPI shop used as a test fixture for the Rook engine.

It ships with four deliberate bugs. `MINISHOP_FIXED=1` (or `create_app(fixed=True)`) fixes all of them:
  1. refunds are checked one at a time, not against the running total
  2. buying checks stock, awaits, then decrements (concurrent buys oversell)
  3. shipping ignores a cancelled order
  4. the admin export only requires a login, not the admin role

State is in memory and belongs to one app instance, so every `create_app()` call starts clean.
"""

import asyncio
import os
import secrets
from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ADMIN_EMAIL = "admin@demo.local"


@dataclass
class User:
    id: int
    email: str
    password: str
    role: str


@dataclass
class Product:
    id: int
    name: str
    price: int
    stock: int


@dataclass
class Order:
    id: int
    owner_id: int
    product_id: int
    quantity: int
    paid: int
    status: str = "paid"
    shipped: bool = False
    refunds: list[int] = field(default_factory=list)

    @property
    def refunded_total(self) -> int:
        return sum(self.refunds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "paid": self.paid,
            "refunded_total": self.refunded_total,
            "status": self.status,
            "shipped": self.shipped,
        }


@dataclass
class Store:
    users: dict[int, User] = field(default_factory=dict)
    products: dict[int, Product] = field(default_factory=dict)
    orders: dict[int, Order] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    next_id: int = 1
    stock_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def new_id(self) -> int:
        value = self.next_id
        self.next_id += 1
        return value


class Credentials(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class NewProduct(BaseModel):
    name: str = Field(min_length=1)
    price: int = Field(ge=0)
    stock: int = Field(ge=0)


class NewOrder(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1)


class NewRefund(BaseModel):
    amount: int = Field(gt=0)


def _is_fixed_from_env() -> bool:
    return os.environ.get("MINISHOP_FIXED", "").strip().lower() in ("1", "true", "yes")


def create_app(fixed: bool | None = None) -> FastAPI:
    """Build a fresh minishop instance. `fixed=None` reads `MINISHOP_FIXED` from the environment."""
    is_fixed = _is_fixed_from_env() if fixed is None else fixed
    store = Store()
    admin_password = os.environ.get("MINISHOP_ADMIN_PASSWORD", "admin-pass")
    admin = User(id=store.new_id(), email=ADMIN_EMAIL, password=admin_password, role="admin")
    store.users[admin.id] = admin

    app = FastAPI(title="minishop")
    app.state.store = store
    app.state.fixed = is_fixed

    @app.exception_handler(RequestValidationError)
    async def _bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc.errors())})

    def current_user(authorization: Annotated[str | None, Header()] = None) -> User:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "missing bearer token")
        user_id = store.tokens.get(authorization.removeprefix("Bearer ").strip())
        if user_id is None:
            raise HTTPException(401, "invalid token")
        return store.users[user_id]

    CurrentUser = Annotated[User, Depends(current_user)]

    def require_admin(user: User) -> None:
        if user.role != "admin":
            raise HTTPException(403, "admin only")

    def get_order(order_id: int, user: User) -> Order:
        order = store.orders.get(order_id)
        if order is None:
            raise HTTPException(404, "order not found")
        if user.role != "admin" and order.owner_id != user.id:
            raise HTTPException(403, "not your order")
        return order

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/auth/signup")
    async def signup(body: Credentials) -> dict[str, int]:
        if any(u.email == body.email for u in store.users.values()):
            raise HTTPException(409, "email already registered")
        user = User(id=store.new_id(), email=body.email, password=body.password, role="customer")
        store.users[user.id] = user
        return {"id": user.id}

    @app.post("/auth/login")
    async def login(body: Credentials) -> dict[str, str]:
        user = next((u for u in store.users.values() if u.email == body.email), None)
        if user is None or not secrets.compare_digest(user.password, body.password):
            raise HTTPException(401, "bad credentials")
        token = secrets.token_urlsafe(24)
        store.tokens[token] = user.id
        return {"token": token}

    @app.post("/products")
    async def create_product(body: NewProduct, user: CurrentUser) -> dict[str, int]:
        require_admin(user)
        product = Product(id=store.new_id(), name=body.name, price=body.price, stock=body.stock)
        store.products[product.id] = product
        return {"id": product.id}

    @app.get("/products/{product_id}")
    async def read_product(product_id: int) -> dict[str, Any]:
        product = store.products.get(product_id)
        if product is None:
            raise HTTPException(404, "product not found")
        return {"id": product.id, "name": product.name, "price": product.price, "stock": product.stock}

    @app.post("/orders")
    async def buy(body: NewOrder, user: CurrentUser) -> dict[str, Any]:
        if user.role != "customer":
            raise HTTPException(403, "only customers can buy")
        product = store.products.get(body.product_id)
        if product is None:
            raise HTTPException(404, "product not found")
        if is_fixed:
            async with store.stock_lock:
                if product.stock < body.quantity:
                    raise HTTPException(409, "out of stock")
                product.stock -= body.quantity
        else:
            if product.stock < body.quantity:
                raise HTTPException(409, "out of stock")
            await asyncio.sleep(0.01)  # BUG 2: another buy can pass the check before this one decrements
            product.stock -= body.quantity
        order = Order(
            id=store.new_id(),
            owner_id=user.id,
            product_id=product.id,
            quantity=body.quantity,
            paid=product.price * body.quantity,
        )
        store.orders[order.id] = order
        return {"id": order.id, "paid": order.paid, "status": order.status}

    @app.get("/orders/{order_id}")
    async def read_order(order_id: int, user: CurrentUser) -> dict[str, Any]:
        return get_order(order_id, user).to_dict()

    @app.post("/orders/{order_id}/refunds")
    async def refund(order_id: int, body: NewRefund, user: CurrentUser) -> dict[str, int]:
        order = get_order(order_id, user)
        # BUG 1 (buggy mode): each refund is compared with the amount paid on its own.
        already = order.refunded_total if is_fixed else 0
        if already + body.amount > order.paid:
            raise HTTPException(400, "refund exceeds amount paid")
        order.refunds.append(body.amount)
        return {"refunded_total": order.refunded_total}

    @app.post("/orders/{order_id}/cancel")
    async def cancel(order_id: int, user: CurrentUser) -> dict[str, Any]:
        order = get_order(order_id, user)
        if order.shipped:
            raise HTTPException(409, "order already shipped")
        order.status = "cancelled"
        return order.to_dict()

    @app.post("/orders/{order_id}/ship")
    async def ship(order_id: int, user: CurrentUser) -> dict[str, Any]:
        order = get_order(order_id, user)
        # BUG 3 (buggy mode): a cancelled order still ships.
        if is_fixed and order.status == "cancelled":
            raise HTTPException(409, "order is cancelled")
        order.shipped = True
        return order.to_dict()

    @app.get("/admin/export")
    async def admin_export(user: CurrentUser) -> list[dict[str, Any]]:
        # BUG 4 (buggy mode): any logged-in user gets the export.
        if is_fixed:
            require_admin(user)
        return [order.to_dict() for order in store.orders.values()]

    return app


app = create_app()
