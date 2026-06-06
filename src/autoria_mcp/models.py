"""Pydantic v2 models for AUTO.RIA API payloads.

Phase 2 ships only the shared base. Concrete per-endpoint models (search results,
car details, average-price, and the dictionary shapes) land in Phase 4.

Design rule (from the project brief): RIA responses carry undocumented fields,
nulls, and mixed UK/RU/EN labels. Models therefore *ignore* extras rather than
reject them, so an upstream schema change never breaks parsing.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


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


# TODO(phase 4): concrete models, e.g.
#   class SearchResult(AutoRiaModel): ...
#   class CarDetails(AutoRiaModel): ...
#   class DictionaryItem(AutoRiaModel): id: int; name: str
