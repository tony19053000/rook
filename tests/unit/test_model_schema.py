import time
from pathlib import Path

import pytest

from rook.model.loader import ModelError, load_model, load_model_str
from rook.model.schema import Choice, IntRange, ParallelStep, RookModel, Step, StringParam
from rook.model.template import render

MODELS = Path(__file__).resolve().parents[1] / "fixtures" / "models"

BASE = """
version: 1
actors:
  - name: customer
actions:
  - name: buy
    actor: customer
    request: {method: POST, path: /orders}
"""


def load(text: str) -> RookModel:
    return load_model_str(text)


def errors_of(text: str) -> str:
    with pytest.raises(ModelError) as exc:
        load_model_str(text)
    return str(exc.value)


# --- valid model ---------------------------------------------------------------------------------


def test_valid_full_model_loads() -> None:
    model = load_model(MODELS / "valid_full.yaml")
    assert model.version == 1
    assert model.app.base_url == "{{sandbox.base_url}}"
    assert model.app.health.path == "/health"
    assert model.app.isolation == "fresh_entities"
    assert [a.name for a in model.actors] == ["customer", "admin"]
    assert model.actors[0].setup[1].capture == {"token": "$.token"}
    assert model.actors[0].auth is not None and model.actors[0].auth.header == "Authorization"

    buy = model.action("buy")
    assert buy.requires == ["product_id"]
    assert buy.capture == {"order_id": "$.id"}
    assert buy.request.json_body == {"product_id": "{{ref.product_id}}", "price": "{{p.price}}"}
    price = buy.params["price"]
    assert isinstance(price, IntRange) and price.int_range == (1, 500) and price.edges == [1, 100, 500]

    product = model.action("create_product")
    assert isinstance(product.params["category"], Choice)
    assert isinstance(product.params["name"], StringParam)
    assert product.weight == 0.5

    assert model.state[0].each == "order_id"
    assert model.state[0].request.actor == "admin"
    assert model.state[0].fields["refunded"] == "$.refunded_total"

    refund_rule, export_rule = model.rules
    assert refund_rule.kind == "state" and refund_rule.scope == "order" and refund_rule.status == "approved"
    assert export_rule.kind == "response" and export_rule.when is not None
    assert export_rule.when.action == "admin_export" and export_rule.when.actor == "customer"


def test_valid_model_templates_render() -> None:
    model = load_model(MODELS / "valid_full.yaml")
    request = model.action("refund").request.model_dump(by_alias=True, exclude_none=True)
    ctx = {"p": {"amount": 60}, "ref": {"order_id": 5}}
    assert render(request, ctx) == {"method": "POST", "path": "/orders/5/refunds", "json": {"amount": 60}}


def test_minimal_model_uses_defaults() -> None:
    model = load(BASE)
    assert model.app.base_url == "{{sandbox.base_url}}"
    assert model.app.isolation == "fresh_entities"
    assert model.actions[0].weight == 1.0
    assert model.rules == []


def test_method_is_normalised_to_upper_case() -> None:
    assert load(BASE.replace("POST", "post")).actions[0].request.method == "POST"


def test_load_from_path_string(tmp_path: Path) -> None:
    f = tmp_path / "rook.yaml"
    f.write_text(BASE)
    assert load_model(str(f)).actions[0].name == "buy"


# --- invalid fixtures ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("invalid_unknown_actor.yaml", "actions.0.actor: unknown actor 'ghost'"),
        ("invalid_absolute_url.yaml", "absolute URLs are not allowed"),
        ("invalid_duplicate_action.yaml", "actions.1.name: duplicate action 'buy'"),
        ("invalid_bad_scope.yaml", "rules.0.scope: 'invoice' is not a state name or 'global'"),
    ],
)
def test_invalid_fixtures(fixture: str, expected: str) -> None:
    with pytest.raises(ModelError) as exc:
        load_model(MODELS / fixture)
    assert expected in str(exc.value)
    assert fixture in str(exc.value)


# --- loader errors -------------------------------------------------------------------------------


def test_yaml_syntax_error() -> None:
    assert "YAML syntax error" in errors_of("version: 1\nactions: [\n")


@pytest.mark.parametrize("text", ["", "- a\n- b\n", "just a string"])
def test_top_level_must_be_mapping(text: str) -> None:
    assert "expected a mapping" in errors_of(text)


def test_missing_file() -> None:
    with pytest.raises(ModelError, match="cannot read file"):
        load_model("/nonexistent/rook.yaml")


def test_python_yaml_tags_are_refused() -> None:
    # yaml.safe_load refuses arbitrary Python object construction.
    assert "YAML syntax error" in errors_of("version: !!python/object/apply:os.system ['true']\n")


def test_error_carries_field_path() -> None:
    msg = errors_of(BASE.replace("path: /orders", "path: /orders, bogus: 1"))
    assert "actions.0.request.bogus" in msg


def test_multiple_errors_are_all_reported() -> None:
    text = BASE + "  - name: buy\n    actor: ghost\n    request: {method: GET, path: /x}\n"
    with pytest.raises(ModelError) as exc:
        load(text)
    assert len(exc.value.errors) == 2


# --- specific validators -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ("path: /orders", "path: orders", "must start with a single '/'"),
        ("path: /orders", "path: //evil.example.com/x", "must start with a single '/'"),
        ("path: /orders", 'path: "/r?next=https://evil.example.com"', "absolute URLs"),
        ("path: /orders", "path: /orders, headers: {X-Forward: 'ftp://h/x'}", "absolute URLs"),
        ("path: /orders", "path: /orders, json: {cb: {url: 'http://h/x'}}", "absolute URLs"),
        ("version: 1", "version: 2", "version"),
        ("method: POST", "method: FETCH", "method"),
    ],
)
def test_request_validation(old: str, new: str, expected: str) -> None:
    assert expected in errors_of(BASE.replace(old, new))


def test_base_url_must_be_sandbox_template() -> None:
    assert "base_url" in errors_of(BASE + "app: {base_url: 'http://prod.example.com'}\n")


def test_absolute_url_in_actor_setup_and_auth() -> None:
    setup = BASE.replace(
        "  - name: customer\n",
        "  - name: customer\n    setup: [{method: POST, path: /login, json: {next: 'https://x.io'}}]\n",
    )
    assert "absolute URLs" in errors_of(setup)
    auth = BASE.replace(
        "  - name: customer\n",
        "  - name: customer\n    auth: {header: Authorization, value: 'Bearer http://x.io'}\n",
    )
    assert "absolute URLs" in errors_of(auth)


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ("{a: {int: [5, 1]}}", "low bound is greater"),
        ("{a: {int: [1, 5], edges: [9]}}", "outside the range"),
        ("{a: {choice: []}}", "at least 1"),
        ("{a: {string: {}}}", "exactly one of 'pattern' or 'values'"),
        ("{a: {string: {pattern: 'x', values: [y]}}}", "exactly one of 'pattern' or 'values'"),
        ("{a: {string: {pattern: '('}}}", "invalid regex"),
        ("{a: {float: [1, 2]}}", "a param needs one of"),
    ],
)
def test_param_validation(params: str, expected: str) -> None:
    text = BASE.replace("path: /orders}", "path: /orders}\n    params: " + params)
    assert expected in errors_of(text)


def test_param_template_must_be_declared() -> None:
    text = BASE.replace("path: /orders}", "path: /orders, json: {x: '{{p.qty}}'}}")
    assert "not declared in params" in errors_of(text)


def test_ref_template_must_be_required() -> None:
    text = BASE.replace("path: /orders}", "path: '/orders/{{ref.order_id}}'}")
    assert "not listed in requires" in errors_of(text)


def test_unknown_template_namespace_in_action() -> None:
    text = BASE.replace("path: /orders}", "path: '/orders/{{order_id}}'}")
    assert "is not allowed in an action request" in errors_of(text)


def test_malformed_template_in_action() -> None:
    text = BASE.replace("path: /orders}", "path: '/orders/{{ p. }}'}")
    assert "malformed placeholder" in errors_of(text)


def test_state_reader_template_must_use_each_var() -> None:
    text = BASE + (
        "state:\n  - name: order\n    each: order_id\n"
        "    request: {method: GET, path: '/orders/{{id}}'}\n    fields: {paid: '$.paid'}\n"
    )
    assert "not allowed in state reader 'order'" in errors_of(text)


def test_state_reader_bad_jsonpath() -> None:
    text = BASE + (
        "state:\n  - name: order\n    each: order_id\n"
        "    request: {method: GET, path: '/orders/{{order_id}}'}\n    fields: {paid: 'paid'}\n"
    )
    msg = errors_of(text)
    assert "state.0.fields" in msg and "must start with '$'" in msg


def test_state_reader_unknown_actor() -> None:
    text = BASE + (
        "state:\n  - name: order\n    each: order_id\n"
        "    request: {method: GET, path: '/orders/{{order_id}}', actor: ghost}\n    fields: {paid: '$.paid'}\n"
    )
    assert "state.0.request.actor: unknown actor 'ghost'" in errors_of(text)


def test_capture_jsonpath_is_validated() -> None:
    text = BASE.replace("path: /orders}", "path: /orders}\n    capture: {order_id: '$..id'}")
    assert "unsupported JSONPath" in errors_of(text)


def test_duplicate_actor_state_and_rule_ids() -> None:
    text = BASE.replace("  - name: customer\n", "  - name: customer\n  - name: customer\n") + (
        "rules:\n"
        "  - {id: r1, text: t, kind: state, check: 'x'}\n"
        "  - {id: r1, text: t, kind: state, check: 'y'}\n"
    )
    msg = errors_of(text)
    assert "actors.1.name: duplicate actor 'customer'" in msg
    assert "rules.1.id: duplicate rule id 'r1'" in msg


RULE = "rules:\n  - {id: r1, text: t, kind: KIND, check: CHECK EXTRA}\n"


def rule(kind: str = "state", check: str = "'x > 0'", extra: str = "") -> str:
    return BASE + RULE.replace("KIND", kind).replace("CHECK", check).replace(" EXTRA", extra)


def test_rule_defaults_and_global_scope() -> None:
    r = load(rule()).rules[0]
    assert r.scope == "global" and r.status == "proposed" and r.evidence == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (rule(check="''"), "at least 1 character"),
        (rule(check="'   '"), "must not be blank"),
        (rule(check="'" + "x" * 501 + "'"), "at most 500 characters"),
        (rule(kind="response"), "needs 'when"),
        (rule(kind="response", extra=", when: {action: nope}"), "rules.0.when.action: unknown action 'nope'"),
        (
            rule(kind="response", extra=", when: {action: buy, actor: ghost}"),
            "rules.0.when.actor: unknown actor 'ghost'",
        ),
        (rule(extra=", status: maybe"), "status"),
        (rule(kind="invariant"), "kind"),
    ],
)
def test_rule_validation(text: str, expected: str) -> None:
    assert expected in errors_of(text)


def test_check_is_not_evaluated() -> None:
    # Evaluation belongs to model/expr.py (ROOK-004); the schema stores the text only.
    assert load(rule(check="'__import__(\"os\")'")).rules[0].check == '__import__("os")'


def test_check_at_limit_is_accepted() -> None:
    assert len(load(rule(check="'" + "x" * 500 + "'")).rules[0].check) == 500


# --- sequence steps (parallel) -------------------------------------------------------------------


def test_parallel_step() -> None:
    model = load_model(MODELS / "valid_full.yaml")
    step = ParallelStep.model_validate(
        {"parallel": [{"action": "buy", "params": {"price": 1}}, {"action": "buy", "actor": "customer"}]}
    )
    model.check_step(step)
    model.check_step(Step(action="refund"))
    with pytest.raises(ValueError, match="unknown action"):
        model.check_step(ParallelStep(parallel=[Step(action="buy"), Step(action="steal")]))
    with pytest.raises(ValueError, match="unknown actor"):
        model.check_step(Step(action="buy", actor="ghost"))
    with pytest.raises(ValueError):
        ParallelStep(parallel=[Step(action="buy")])


# --- robustness -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["a" * 200_000, "{{" * 50000 + "a" * 50000, "{{a" * 50000, "}}" * 50000, "http" * 50000],
    ids=["letters", "open-then-text", "open-a", "close", "scheme-like"],
)
def test_pathological_request_strings_load_fast(value: str) -> None:
    text = BASE.replace("path: /orders}", f"path: /orders, json: {{x: '{value}'}}}}")
    start = time.perf_counter()
    try:
        load(text)
    except ModelError:
        pass
    assert time.perf_counter() - start < 0.5


def test_deeply_nested_request_body_is_a_clean_error() -> None:
    body = "[" * 300 + "1" + "]" * 300
    msg = errors_of(BASE.replace("path: /orders}", f"path: /orders, json: {body}}}"))
    assert "nested deeper than" in msg


def test_long_absolute_url_message_is_truncated() -> None:
    msg = errors_of(BASE.replace("path: /orders}", f"path: /orders, json: {{u: 'http://{'a' * 5000}'}}}}"))
    assert "absolute URLs" in msg and len(msg) < 1000
