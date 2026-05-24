import pytest
from app.copilot.agent.boundary.schema_filter import apply


def test_strips_unlisted_top_level_fields():
    row = {"id": 1, "name": "Sarah", "email": "s@x.com"}
    out = apply(row, allowed_fields=["id", "name"])
    assert out == {"id": 1, "name": "Sarah"}


def test_strips_unlisted_fields_in_list_of_dicts():
    rows = [{"id": 1, "name": "A", "phone": "555"}, {"id": 2, "name": "B", "phone": "666"}]
    out = apply(rows, allowed_fields=["id", "name"])
    assert out == [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]


def test_preserves_nested_structure_when_listed():
    row = {"id": 1, "module": {"name": "Forces", "owner_id": 47}}
    out = apply(row, allowed_fields=["id", "module.name"])
    assert out == {"id": 1, "module": {"name": "Forces"}}


def test_empty_result_when_nothing_allowed():
    assert apply({"x": 1}, allowed_fields=[]) == {}


def test_scalar_parent_dropped_when_nested_rule_specified():
    assert apply({"module": "Forces"}, allowed_fields=["module.name"]) == {}
    assert apply({"module": None}, allowed_fields=["module.name"]) == {}
    assert apply({"module": 42}, allowed_fields=["module.name"]) == {}


def test_deeply_nested_three_levels():
    row = {"a": {"b": {"c": 1, "d": 2}}}
    assert apply(row, allowed_fields=["a.b.c"]) == {"a": {"b": {"c": 1}}}


def test_missing_parent_key_no_error():
    assert apply({"id": 1}, allowed_fields=["module.name", "id"]) == {"id": 1}


def test_none_value_passes_through_when_field_allowed():
    """None at an allowed key should be kept, not dropped (None is a real value)."""
    assert apply({"id": None, "x": 1}, allowed_fields=["id"]) == {"id": None}


def test_missing_keys_are_simply_absent():
    """An allowed field that's not in the source row simply isn't in the output."""
    assert apply({"id": 1}, allowed_fields=["id", "name"]) == {"id": 1}
