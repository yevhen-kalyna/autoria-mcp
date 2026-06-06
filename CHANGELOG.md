# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-06

First public release — the full MCP surface for the AUTO.RIA used-cars API,
backed by a typed async client, tiered caching, and an OIDC release pipeline.

### Added

- **MCP tool surface** — 29 tools, 7 dictionary resources, and 1 templated
  resource over the `autoria` FastMCP server:
  - Curated tools: `search_used_cars` (name→V1-ID resolution, single request,
    OfferOfTheDay `100500` filtering, V1 silent-ignore sanity check, canonical
    set-level `search_url`), `get_car_details`, and `lookup_brands`/`lookup_models`/
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
- **Async I/O core** — typed `AutoRiaClient` (bounded retry + exponential
  backoff with full jitter, dual error-shape mapping), a two-tier dictionary
  cache (7-day on-disk + bounded-LRU memory) and a memory-only volatile cache
  for search/statistics, a warn-only quota tracker, and a name→ID dictionary
  resolver. Recorded-fixture tests run with zero live quota.
- **Server & config** — runnable FastMCP server with stdio (default) and
  streamable-HTTP transports (`--transport` / `AUTORIA_TRANSPORT`), a zero-quota
  `ping` health tool, and `pydantic-settings` configuration from env / `.env`
  (`AUTORIA_*`, API key held in `SecretStr` and never logged).
- **Project & release** — uv project with `src/` layout and console entry point
  `autoria-mcp`; ruff (lint + format), mypy `--strict`, pytest, pre-commit; CI
  on Python 3.11/3.12; tag-triggered PyPI release via OIDC Trusted Publishing
  with a TestPyPI dry-run path.
- **Docs** — OpenAPI 3.1 spec (`openapi/autoria-used-cars.yaml`) and Phase 1
  audit trail, README (config + tool catalog + quota guidance + known
  limitations), runnable `examples/`, `CONTRIBUTING.md`, and `SECURITY.md`.

[Unreleased]: https://github.com/yevhen-kalyna/autoria-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/yevhen-kalyna/autoria-mcp/releases/tag/v0.1.0
