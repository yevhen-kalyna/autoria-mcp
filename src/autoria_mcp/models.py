"""Pydantic v2 models for AUTO.RIA API payloads.

Phase 2 ships only the shared base. Concrete per-endpoint models (search results,
car details, average-price, and the dictionary shapes) land in Phase 4.

Design rule (from the project brief): RIA responses carry undocumented fields,
nulls, and mixed UK/RU/EN labels. Models therefore *ignore* extras rather than
reject them, so an upstream schema change never breaks parsing.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AutoRiaModel(BaseModel):
    """Base model for every AUTO.RIA payload.

    - ``extra="allow"`` keeps undocumented fields instead of dropping/raising.
    - ``populate_by_name`` lets us alias ria's snake/camel keys to clean names.
    - ``str_strip_whitespace`` normalizes the frequently padded label strings.
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class DictionaryItem(AutoRiaModel):
    """A single entry in an AUTO.RIA dictionary endpoint.

    The wire shape is ``{"name": "...", "value": <id>}`` (``value`` is the numeric
    id RIA uses in ``<option>`` dropdowns). We alias it to a clean ``id``. Some
    dictionaries (e.g. body styles) add ``parentId`` to express grouping.
    """

    id: int = Field(alias="value")
    name: str
    parent_id: int | None = Field(default=None, alias="parentId")


def parse_dictionary(raw: Any) -> list[DictionaryItem]:
    """Parse a dictionary response into a flat list of :class:`DictionaryItem`.

    Handles both the flat endpoints (``[{name, value}, ...]``) and the
    heterogeneous ``_group`` endpoints, whose arrays mix flat items with nested
    sub-arrays of items. Nested sub-arrays are flattened in place; unparsable
    entries are skipped rather than raising, matching the package's
    tolerate-upstream-drift policy.
    """
    items: list[DictionaryItem] = []
    if not isinstance(raw, list):
        return items
    for entry in raw:
        if isinstance(entry, list):
            items.extend(parse_dictionary(entry))
        elif isinstance(entry, dict):
            try:
                items.append(DictionaryItem.model_validate(entry))
            except ValueError:
                continue
    return items
