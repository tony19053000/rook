import pytest

from rook.model.jsonpath import JSONPathError, compile_path, extract

DATA = {
    "id": 7,
    "token": "t0k",
    "user": {"profile": {"email": "a@b.c"}},
    "items": [{"id": 1, "qty": 2}, {"id": 2}, {"qty": 5}],
    "tags": ["x", "y"],
    "zero": 0,
    "nothing": None,
}


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("$", DATA),
        ("$.id", 7),
        ("$.user.profile.email", "a@b.c"),
        ("$.tags[0]", "x"),
        ("$.tags[-1]", "y"),
        ("$.items[0].id", 1),
        ("$.items[*].id", [1, 2]),
        ("$.items[*].qty", [2, 5]),
        ("$.tags[*]", ["x", "y"]),
        ("$.zero", 0),
    ],
)
def test_extract(expr: str, expected: object) -> None:
    assert extract(DATA, expr) == expected


@pytest.mark.parametrize(
    "expr",
    ["$.missing", "$.user.nope.email", "$.tags[5]", "$.id.sub", "$.id[0]", "$.user[*]", "$.nothing.x"],
)
def test_missing_path_returns_none(expr: str) -> None:
    assert extract(DATA, expr) is None


def test_extract_on_list_root() -> None:
    assert extract([{"id": 3}], "$[0].id") == 3
    assert extract([{"id": 3}, {"id": 4}], "$[*].id") == [3, 4]


@pytest.mark.parametrize("expr", ["id", "$..id", "$.a[", "$.a['b']", "$ .a", "$.", "$.a.[0]"])
def test_invalid_syntax_raises(expr: str) -> None:
    with pytest.raises(JSONPathError):
        compile_path(expr)
