# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Phase 4 — MCP tool surface.**
  - Curated tools: `search_used_cars` (name→V1-ID resolution, single request,
    OfferOfTheDay `100500` filtering, V1 silent-ignore sanity check, canonical
    `search_url`), `get_car_details`, and `lookup_brands`/`lookup_models`/
    `lookup_regions`/`lookup_cities`.
  - Paid tools (fail fast without `AUTORIA_USER_ID`): `get_average_price`,
    `get_average_price_over_periods`, `get_params_by_vin`. Natural-name inputs
    with a raw-id escape hatch for generation/modification; `period` validation;
    notice-error mapping.
  - Thin endpoint mirrors for the long-tail dictionary/lookup endpoints, plus a
    raw `raw_search`.
  - Browsable dictionary MCP resources (`autoria://dict/...`) including a
    templated models-by-brand resource.
  - Compact response models and pure shaping/URL helpers with mandatory
    auto.ria.com attribution links.
  - Shared async `RuntimeContext` + FastMCP lifespan; bounded-LRU memory cache
    tier and a memory-only volatile cache; `AUTORIA_VOLATILE_TTL` and
    `AUTORIA_MEMORY_CACHE_MAX` settings.
  - `AutoRiaClient.post_json` now supports a JSON request body for paid POSTs.
- Phase 3: typed async client (retry/backoff, dual error-shape mapping),
  two-tier dictionary cache, warn-only quota tracker, and name→ID dictionary
  resolver, with recorded-fixture tests (zero live quota).
- Project scaffold (Phase 2): uv project, `src/` layout, console entry point
  `autoria-mcp`.
- `pydantic-settings` configuration loaded from env / `.env` (`AUTORIA_*`).
- Runnable FastMCP server (`autoria`) with stdio (default) and streamable-HTTP
  transports, selectable via `--transport` / `AUTORIA_TRANSPORT`.
- Zero-quota `ping` health tool.
- Typed module stubs for the upcoming client, cache, models, and dictionary
  resolver layers.
- Tooling: ruff (lint + format), mypy `--strict`, pytest, pre-commit.
- CI (ruff + mypy + pytest on 3.11/3.12) and a tag-triggered PyPI release
  workflow using Trusted Publishing (OIDC).
- OpenAPI 3.1 spec (`openapi/autoria-used-cars.yaml`) and Phase 1 audit trail.

## [0.1.0] - Unreleased

Initial scaffold release. Not yet published to PyPI.

[Unreleased]: https://github.com/yevhen-kalyna/autoria-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yevhen-kalyna/autoria-mcp/releases/tag/v0.1.0
