import time

import pytest

from rook.model.template import MAX_DEPTH, TemplateError, placeholders, render

CTX = {
    "p": {"price": 100, "name": "widget"},
    "ref": {"order_id": 42},
    "fresh": {"email": "u1@rook.test", "id": "u1"},
    "env": {"ADMIN_PASSWORD": "from-sandbox-env"},
    "actor": {"token": "abc"},
    "sandbox": {"base_url": "http://127.0.0.1:8000"},
    "order_id": 9,
    "flag": True,
}


def test_whole_placeholder_keeps_native_type() -> None:
    assert render("{{p.price}}", CTX) == 100
    assert render("{{ p.price }}", CTX) == 100
    assert render("{{flag}}", CTX) is True
    assert render("{{ref.order_id}}", CTX) == 42


def test_embedded_placeholders_become_text() -> None:
    assert render("/orders/{{ref.order_id}}/refunds", CTX) == "/orders/42/refunds"
    assert render("Bearer {{actor.token}}", CTX) == "Bearer abc"
    assert render("pw-{{fresh.id}}", CTX) == "pw-u1"
    assert render("/orders/{{order_id}}", CTX) == "/orders/9"
    assert render("{{flag}}-{{p.name}}", CTX) == "true-widget"


def test_all_namespaces() -> None:
    assert render("{{env.ADMIN_PASSWORD}}", CTX) == "from-sandbox-env"
    assert render("{{fresh.email}}", CTX) == "u1@rook.test"
    assert render("{{sandbox.base_url}}", CTX) == "http://127.0.0.1:8000"


def test_renders_recursively_over_dicts_and_lists() -> None:
    body = {
        "email": "{{fresh.email}}",
        "items": [{"price": "{{p.price}}"}, "{{ref.order_id}}", 3, None],
        "note": "plain",
    }
    assert render(body, CTX) == {
        "email": "u1@rook.test",
        "items": [{"price": 100}, 42, 3, None],
        "note": "plain",
    }


def test_render_does_not_mutate_input() -> None:
    body = {"a": ["{{p.price}}"]}
    render(body, CTX)
    assert body == {"a": ["{{p.price}}"]}


@pytest.mark.parametrize("text", ["{{p.missing}}", "x-{{nope}}", "{{ref.order_id.deeper}}", "{{env.SECRET}}"])
def test_unknown_variable_is_a_clear_error(text: str) -> None:
    with pytest.raises(TemplateError, match="unknown template variable"):
        render(text, CTX)


def test_unknown_variable_message_names_the_variable() -> None:
    with pytest.raises(TemplateError) as exc:
        render({"a": ["{{p.qty}}"]}, CTX)
    assert "{{p.qty}}" in str(exc.value)
    assert "price" in str(exc.value)  # lists what is available


@pytest.mark.parametrize("text", ["{{}}", "{{ p..x }}", "{{1abc}}", "{{p.x", "a }} b", "{{p-x}}"])
def test_malformed_placeholder_raises(text: str) -> None:
    with pytest.raises(TemplateError):
        render(text, CTX)


def test_placeholders_collects_names() -> None:
    obj = {"path": "/o/{{ref.order_id}}", "json": {"a": ["{{p.price}}", "{{ fresh.id }}"]}, "n": 1}
    assert placeholders(obj) == {"ref.order_id", "p.price", "fresh.id"}


# --- robustness: linear-time parsing and a depth guard -------------------------------------------

PATHOLOGICAL = ["{{" * 50000 + "a" * 50000, "{{a" * 50000, "}}" * 50000, "{{a}}" * 50000 + "{{"]


@pytest.mark.parametrize("text", PATHOLOGICAL, ids=["open-then-text", "open-a", "close", "many-then-open"])
def test_pathological_strings_are_rejected_fast(text: str) -> None:
    for fn in (lambda: render(text, CTX), lambda: placeholders(text)):
        start = time.perf_counter()
        with pytest.raises(TemplateError):
            fn()
        assert time.perf_counter() - start < 0.5


def test_many_valid_placeholders_render_fast() -> None:
    text = "{{p.name}}-" * 50000
    start = time.perf_counter()
    assert render(text, CTX) == "widget-" * 50000
    assert placeholders(text) == {"p.name"}
    assert time.perf_counter() - start < 0.5


def test_long_placeholder_name_is_linear() -> None:
    start = time.perf_counter()
    with pytest.raises(TemplateError):
        render("{{" + "a." * 50000 + "!}}", CTX)
    assert time.perf_counter() - start < 0.5


def nested(depth: int) -> object:
    obj: object = "{{p.price}}"
    for i in range(depth):
        obj = [obj] if i % 2 else {"k": obj}
    return obj


def test_depth_guard() -> None:
    assert placeholders(nested(MAX_DEPTH)) == {"p.price"}
    render(nested(MAX_DEPTH), CTX)
    with pytest.raises(TemplateError, match="nested deeper"):
        render(nested(5000), CTX)
    with pytest.raises(TemplateError, match="nested deeper"):
        placeholders(nested(5000))
