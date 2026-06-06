"""DictionaryItem aliasing and parse_dictionary flattening."""

from __future__ import annotations

from autoria_mcp.models import DictionaryItem, parse_dictionary
from tests.conftest import load_fixture


def test_dictionary_item_aliases_value_to_id() -> None:
    item = DictionaryItem.model_validate({"name": "BMW", "value": 9})
    assert item.id == 9
    assert item.name == "BMW"
    assert item.parent_id is None


def test_dictionary_item_keeps_parent_id_and_extras() -> None:
    item = DictionaryItem.model_validate({"name": "Седан", "value": 3, "parentId": 0})
    assert item.id == 3
    assert item.parent_id == 0


def test_parse_flat_dictionary() -> None:
    items = parse_dictionary(load_fixture("marks"))
    assert [i.id for i in items] == [98, 3, 5, 6, 9]


def test_parse_grouped_dictionary_flattens_nested_arrays() -> None:
    items = parse_dictionary(load_fixture("models_group"))
    ids = {i.id for i in items}
    # Flat entries and entries nested one level deep are all surfaced.
    assert {2161, 63521, 48926, 47380, 47386, 3219, 3597, 1866, 96} == ids


def test_parse_skips_unparsable_entries() -> None:
    raw = [{"name": "ok", "value": 1}, {"name": "no id"}, "junk", 42]
    items = parse_dictionary(raw)
    assert [i.id for i in items] == [1]


def test_parse_non_list_returns_empty() -> None:
    assert parse_dictionary({"not": "a list"}) == []
