"""ROOK-011: counterexample export (cx_NNN.json) and the generated fallback regression test.

The generated test's safety is checked with hostile values in every untrusted field (app responses,
captured ids, params, Bob-written rule text): the source must parse to the template's exact syntax
tree and the embedded data must round-trip unchanged.
"""

import ast
import json
import os
import runpy
from pathlib import Path
from typing import Any

import pytest
from test_shrinker import MODEL, REFUND, executor, search_and_shrink

from rook.core.events import Event, EventBus
from rook.engine.judge import Judge, Violation
from rook.engine.replayer import Replayer, ReplayResult
from rook.engine.shrinker import replay_trace
from rook.export.counterexample import (
    MAX_DEPTH,
    MAX_JSON_BYTES,
    TRUNCATED,
    Counterexample,
    CxParallel,
    CxStep,
    cap_value,
    load_counterexample,
    model_hash,
    next_cx_id,
    publish_saved,
    replay_counterexample,
    save_counterexample,
    write_new_file,
)
from rook.export.tests import (
    UnsafeTestError,
    _data_json,
    check_generated,
    env_names,
    fallback_test_name,
    payload,
    render_fallback_test,
    run_generated_test,
    write_fallback_test,
)

NASTY = [
    '"""; import os; os.system("touch /tmp/rook_pwned") #',
    "'''; import os #",
    "quote ' and \" and \\ backslash",
    "line one\nline two\r\n\tindented",
    "}\n]\n)\nimport os\nos.system('id')\n",
    "__DATA__\n__CX_ID__ __FILE__",
    "\x00\x07\x1b[31m\x7f",
    "unicode     ﻿ é 🎉",
    "\\u0022; import os",
]


async def found_cx(seed: int = 1) -> Counterexample:
    _, shrunk = await search_and_shrink(seed)
    async with executor(REFUND) as ex:
        replay = await Replayer(REFUND, ex, None, "r").replay(shrunk.violation, shrunk.trace)
    return Counterexample.build("cx_001", MODEL, shrunk.violation, shrunk.trace, replay, seed)


def nasty_cx() -> Counterexample:
    """A refund counterexample whose untrusted fields all hold hostile strings."""
    return Counterexample(
        cx_id="cx_007",
        rule={
            "id": "refund_le_paid",
            "text": " | ".join(NASTY),
            "kind": "state",
            "scope": "order",
            "check": "order.refunded <= order.paid",
        },
        steps=[
            CxStep(action="create_product", actor="admin", params={"price": 100, "stock": 1}),
            CxStep(action="buy", actor="customer", params={"quantity": 1}, refs={"product_id": 0}),
            CxParallel(
                parallel=[
                    CxStep(action="refund", actor="customer", params={"amount": 60}, refs={"order_id": 0}),
                    CxStep(action="refund", actor="customer", params={"amount": 60}, refs={"order_id": 0}),
                ]
            ),
        ],
        violated_at_step=2,
        observed={n: n for n in NASTY} | {"ids": NASTY, "nested": [{"k": NASTY[0]}]},
        expected="order.refunded <= order.paid",
        reproduced="10/10",
        flaky=False,
        seed=NASTY[0],
        model_hash=model_hash(MODEL),
    )


# --- cx JSON ---


async def test_build_save_and_load_round_trip(tmp_path: Path) -> None:
    cx = await found_cx()
    assert cx.rule.id == "refund_le_paid" and cx.expected == "order.refunded <= order.paid"
    assert [s.action for s in cx.steps] == ["create_product", "buy", "refund", "refund"]  # type: ignore[union-attr]
    assert cx.violated_at_step == 3 and cx.reproduced == "10/10" and not cx.flaky
    assert cx.observed["refunded"] > cx.observed["paid"]
    assert cx.model_hash == model_hash(MODEL) and cx.model_hash.startswith("sha256:")
    assert cx.seed == 1

    assert next_cx_id(tmp_path) == "cx_001"
    path = save_counterexample(tmp_path, cx)
    assert path == tmp_path / "rook" / "counterexamples" / "cx_001.json"
    data = json.loads(path.read_text())
    assert {"steps", "rule", "observed", "expected", "seed", "model_hash"} <= data.keys()
    assert load_counterexample(path) == cx
    assert next_cx_id(tmp_path) == "cx_002"
    with pytest.raises(FileExistsError):
        save_counterexample(tmp_path, cx)  # never overwrites


async def test_loaded_counterexample_replays_like_the_shrunk_trace(tmp_path: Path) -> None:
    cx = load_counterexample(save_counterexample(tmp_path, await found_cx(2)))
    for fixed, broken in ((False, True), (True, False)):
        async with executor(REFUND, fixed=fixed) as ex:
            violation, _ = await replay_trace(ex, Judge(REFUND), cx.to_trace(REFUND))
        assert (violation is not None and violation.rule_id == "refund_le_paid") is broken


async def test_replay_counterexample_is_judged_and_never_vacuous() -> None:
    cx = await found_cx()
    async with executor(MODEL) as ex:
        buggy = await replay_counterexample(ex, MODEL, cx)
    assert not buggy.holds and buggy.violation is not None and "broken again" in buggy.message
    async with executor(MODEL, fixed=True) as ex:
        fixed = await replay_counterexample(ex, MODEL, cx)
    assert fixed.holds and fixed.steps_run == 4

    # A replay whose steps cannot run (the admin login fails) proves nothing: it does not hold.
    bad = executor(MODEL, fixed=True)
    bad.env["MINISHOP_ADMIN_PASSWORD"] = "wrong"
    async with bad as ex:
        vacuous = await replay_counterexample(ex, MODEL, cx)
    assert vacuous.violation is None and not vacuous.holds
    assert "did not fully run" in vacuous.message and "no response" in vacuous.message


def test_cx_id_and_file_names_are_validated(tmp_path: Path) -> None:
    good = nasty_cx()
    for bad in ["cx_1", "cx_001\n", "cx_001; import os", "../cx_001", "cx_0000001", ""]:
        with pytest.raises(ValueError):
            Counterexample.model_validate({**good.model_dump(), "cx_id": bad})
        with pytest.raises(ValueError):
            fallback_test_name(bad)
    (tmp_path / "rook" / "counterexamples").mkdir(parents=True)
    for name in ["cx_004.json", "cx_010.json.bak", "notes.json", "cx_9.json"]:
        (tmp_path / "rook" / "counterexamples" / name).write_text("{}")
    assert next_cx_id(tmp_path) == "cx_005"


def _write_cx(root: Path) -> Path:
    return save_counterexample(root, nasty_cx())


def _write_test(root: Path) -> Path:
    return write_fallback_test(root, nasty_cx(), MODEL)


def _leaf(write: Any) -> Path:
    if write is _write_cx:
        return Path("rook/counterexamples/cx_007.json")
    return Path("rook/tests") / fallback_test_name("cx_007")


def _tree(path: Path) -> dict[str, str]:
    """Everything under `path` (names and file contents), to prove nothing was created or changed."""
    return {str(p.relative_to(path)): p.read_text() if p.is_file() else "<dir>" for p in path.rglob("*")}


@pytest.mark.parametrize("write", [_write_cx, _write_test])
@pytest.mark.parametrize("link", ["rook", "rook/counterexamples", "rook/tests"])
def test_writes_refuse_symlinks_out_of_the_root(tmp_path: Path, write: Any, link: str) -> None:
    """(a) `<root>/rook -> outside` and (b) `<root>/rook/{tests,counterexamples} -> outside`: the
    writer that goes through the link refuses, and nothing at all appears outside the root."""
    root, outside = tmp_path / "repo", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    (root / link).parent.mkdir(parents=True, exist_ok=True)
    (root / link).symlink_to(outside, target_is_directory=True)
    if _leaf(write).is_relative_to(link):
        with pytest.raises(PermissionError, match="not a plain directory"):
            write(root)
    else:
        assert write(root).is_file()  # the other directory is unaffected
    assert _tree(outside) == {"keep.txt": "keep"}  # no directory, no file created outside


@pytest.mark.parametrize("write", [_write_cx, _write_test])
@pytest.mark.parametrize("dangling", [False, True])
def test_writes_refuse_a_symlinked_leaf_file(tmp_path: Path, write: Any, dangling: bool) -> None:
    """(c) The file itself is a symlink out of the root (to an existing file or to a missing one)."""
    root, outside = tmp_path / "repo", tmp_path / "outside"
    outside.mkdir()
    (outside / "victim.txt").write_text("keep")
    leaf = root / _leaf(write)
    leaf.parent.mkdir(parents=True)
    leaf.symlink_to(outside / ("new.txt" if dangling else "victim.txt"))
    with pytest.raises(OSError):
        write(root)
    assert _tree(outside) == {"victim.txt": "keep"}
    assert leaf.is_symlink()  # left as it was, not replaced


@pytest.mark.parametrize("relative_dir", ["/tmp/rook", "../rook", "rook/../../x"])
def test_write_new_file_rejects_escaping_components(tmp_path: Path, relative_dir: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(PermissionError, match="refused path"):
        write_new_file(root, Path(relative_dir), "x.json", "{}")
    for name in ["", "..", "a/b"]:
        with pytest.raises(PermissionError, match="refused path"):
            write_new_file(root, Path("rook"), name, "{}")
    assert _tree(tmp_path) == {"repo": "<dir>"}


def _nest(levels: int) -> Any:
    deep: Any = "bottom"
    for _ in range(levels):
        deep = [deep]
    return deep


def _depth(value: Any) -> int:
    if isinstance(value, dict):
        return 1 + max(map(_depth, value.values()), default=0)
    if isinstance(value, list):
        return 1 + max(map(_depth, value), default=0)
    return 0


def test_observed_is_capped_in_depth_with_a_marker() -> None:
    good = nasty_cx().model_dump()
    cx = Counterexample.model_validate({**good, "observed": {"a": _nest(5_000)}})
    assert _depth(cx.observed) == MAX_DEPTH
    marker = cx.observed["a"]
    while isinstance(marker, list):
        (marker,) = marker
    assert marker == f"<{TRUNCATED}: nested deeper than {MAX_DEPTH} levels>"
    # Shallow values are untouched; odd scalars are made JSON-safe; capping is idempotent.
    assert cap_value({"a": [[[1]]], 2: None}) == {"a": [[[1]]], "2": None}
    assert cap_value([float("nan"), float("inf"), b"x"]) == ["nan", "inf", "b'x'"]
    assert cap_value(cx.observed) == cx.observed
    assert Counterexample.model_validate_json(cx.to_json()) == cx


def test_observed_is_capped_in_size_with_a_marked_preview() -> None:
    good = nasty_cx().model_dump()
    cx = Counterexample.model_validate({**good, "observed": {"blob": "x" * 2_000_000}})
    assert set(cx.observed) == {TRUNCATED, "preview"}
    assert "2000012 bytes of JSON" in cx.observed[TRUNCATED]
    assert cx.observed["preview"].startswith('{"blob": "xxx') and len(cx.observed["preview"]) == 4096
    assert len(cx.to_json()) < MAX_JSON_BYTES
    assert cap_value(cx.observed) == cx.observed
    with pytest.raises(ValueError, match="seed is longer"):
        Counterexample.model_validate({**good, "seed": "s" * 1_000})


def test_a_capped_observed_value_is_what_the_generated_test_embeds(tmp_path: Path) -> None:
    hostile = {"deep": _nest(5_000), "blob": "y" * 100_000, "nasty": NASTY}
    cx = nasty_cx().model_copy(update={"observed": cap_value(hostile)})
    source = render_fallback_test(cx, MODEL)
    assert len(source) < 3 * MAX_JSON_BYTES
    path = tmp_path / fallback_test_name(cx.cx_id)
    path.write_text(source)
    embedded = runpy.run_path(str(path), run_name="generated")["COUNTEREXAMPLE"]
    assert embedded["counterexample"]["observed"] == cx.observed
    assert TRUNCATED in cx.observed


async def test_counterexample_saved_event_matches_the_contract() -> None:
    bus = EventBus()
    cx = await found_cx()
    await publish_saved(bus, "r_test", cx, "rook/tests/test_rook_cx_001.py")
    await bus.close("r_test")
    events: list[Event] = [e async for e in bus.subscribe("r_test")]
    (event,) = events
    assert event.type == "counterexample.saved"
    assert event.data["cx_id"] == "cx_001" and event.data["reproduced"] == "10/10"
    assert event.data["steps"] == cx.steps_json() and event.data["test_path"].endswith("cx_001.py")


def test_build_rejects_a_rule_not_in_the_model() -> None:
    violation = Violation("no_such_rule", 0, None, {}, "true")
    with pytest.raises(ValueError, match="not in the model"):
        Counterexample.build("cx_001", MODEL, violation, [], ReplayResult("no_such_rule", 1, [None]), 0)


# --- the generated fallback test ---


def _strip_data(tree: ast.Module) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.List):
            node.elts = []
    return ast.dump(tree)


def test_generated_test_embeds_hostile_values_only_as_data(tmp_path: Path) -> None:
    cx = nasty_cx()
    source = render_fallback_test(cx, MODEL)
    benign = render_fallback_test(cx.model_copy(update={"observed": 1, "seed": 1}), MODEL)
    # Same code, only the data strings differ.
    assert _strip_data(ast.parse(source)) == _strip_data(ast.parse(benign))
    # Every data line is one plain str literal on its own source line (no raw newline or NUL).
    assert "\x00" not in source and "\r" not in source and "\u2028" not in source

    # Loading the module gives back exactly the embedded data (and defines nothing else).
    path = tmp_path / fallback_test_name(cx.cx_id)
    path.write_text(source)
    module = runpy.run_path(str(path), run_name="generated")
    assert {k for k in module if not k.startswith("__")} == {
        "json",
        "os",
        "pytest",
        "COUNTEREXAMPLE",
        "test_rook_cx_007",
    }
    assert module["COUNTEREXAMPLE"] == json.loads(json.dumps(payload(cx, MODEL)))
    assert Counterexample.model_validate(module["COUNTEREXAMPLE"]["counterexample"]) == cx
    assert not Path("/tmp/rook_pwned").exists()
    assert "test_rook_cx_007" in source and "def test_rook_cx_007() -> None:" in source


def test_generated_test_only_approves_the_counterexample_rule() -> None:
    data = payload(nasty_cx(), MODEL)
    rules = data["model"]["rules"]
    assert [(r["id"], r["status"]) for r in rules] == [("refund_le_paid", "approved")]
    assert env_names(MODEL) == ["MINISHOP_ADMIN_PASSWORD"]


@pytest.mark.parametrize(
    "tamper",
    [
        lambda s: s.replace("            '{',", "            '{' + __import__('os').getcwd(),", 1),
        lambda s: s.replace("    outcome = run_regression", "    os.getcwd()\n    outcome = run_regression"),
        lambda s: s.replace("            '{',", "            '{',\n            1,", 1),
        lambda s: s + "\nimport os\n",
        lambda s: s.replace("assert outcome.holds", "assert True or outcome.holds"),
    ],
)
def test_tampered_generated_code_is_refused(tmp_path: Path, tamper: Any) -> None:
    cx = nasty_cx()
    source = render_fallback_test(cx, MODEL)
    bad = tamper(source)
    assert bad != source
    with pytest.raises(UnsafeTestError):
        check_generated(bad, cx.cx_id, _data_json(payload(cx, MODEL)))
    path = tmp_path / fallback_test_name(cx.cx_id)
    path.write_text(bad)
    with pytest.raises(UnsafeTestError):
        run_generated_test(path, "http://127.0.0.1:9")


def test_tampered_generated_data_is_refused_at_render_check() -> None:
    cx = nasty_cx()
    source = render_fallback_test(cx, MODEL)
    bad = source.replace('"reproduced": "10/10"', '"reproduced": "0/10"')
    assert bad != source
    with pytest.raises(UnsafeTestError, match="does not match"):
        check_generated(bad, cx.cx_id, _data_json(payload(cx, MODEL)))


def test_run_generated_test_refuses_other_files(tmp_path: Path) -> None:
    other = tmp_path / "test_something.py"
    other.write_text("def test_x():\n    assert True\n")
    with pytest.raises(UnsafeTestError):
        run_generated_test(other, "http://127.0.0.1:9")


def test_generated_test_skips_without_base_url_and_fails_in_strict_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_fallback_test(tmp_path, nasty_cx(), MODEL)
    assert path.name == "test_rook_cx_007.py" and path.parent.name == "tests"
    module = runpy.run_path(str(path), run_name="generated")
    monkeypatch.delenv("ROOK_BASE_URL", raising=False)
    monkeypatch.delenv("ROOK_REGRESSION_STRICT", raising=False)
    with pytest.raises(pytest.skip.Exception):
        module["test_rook_cx_007"]()
    monkeypatch.setenv("ROOK_REGRESSION_STRICT", "1")
    with pytest.raises(pytest.fail.Exception):
        module["test_rook_cx_007"]()


def test_run_generated_test_env_is_minimal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing reachable: the test fails (strict), and host secrets never reach the child."""
    monkeypatch.setenv("BOB_API_KEY", "sentinel-host-value")
    path = write_fallback_test(tmp_path, nasty_cx(), MODEL)
    with pytest.raises(ValueError):
        run_generated_test(path, "http://127.0.0.1:9", {"BAD-NAME": "x"})
    result = run_generated_test(
        path, "http://127.0.0.1:9", {"MINISHOP_ADMIN_PASSWORD": "admin-pass"}, timeout=60
    )
    assert result.exit_code == 1, result.stdout + result.stderr
    assert "did not fully run" in result.stdout
    assert "sentinel-host-value" not in result.stdout + result.stderr
    assert os.environ["BOB_API_KEY"] == "sentinel-host-value"
