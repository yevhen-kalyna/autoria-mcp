# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-06-08

Follow-up correctness fixes from a real agent session (Peugeot 508). The
`get_average_price` headline was found, via a live A/B, to be a **model-level** AI
estimate that does not honour tight cohort filters (two different `engine_volume`
ranges returned an identical average); and hybrid fuel could not be searched in one
call. Additive fields plus a more honest `status`; no params removed.

### Added

- **`cohort_estimate_usd` on `get_average_price`** — the median of the comparable
  listings, surfaced as the cohort-appropriate figure to prefer over the
  model-level `avg_price_usd` headline when a tight cohort was queried.
- **One-call hybrid search** — `search_used_cars(fuel="Гібрид")` (or `"hybrid"`)
  now expands to every hybrid subtype (HEV/PHEV/MHEV/REEV) via multiple `type[i]`
  wire params, instead of erroring on ambiguity and forcing 3–4 separate queries.
  A specific subtype (e.g. `"Гібрид (PHEV)"`) still resolves to one id. New
  resolver method `DictionaryResolver.fuel_ids()`.

### Changed

- **`get_average_price` `status` is now demoted to `insufficient_sample`** when the
  comparable sample is thin (< 5 listings) or when a narrowing cohort
  (`engine_volume`/`modification`/`generation`) was requested yet the headline
  falls outside its own comps — i.e. the model-level estimate ignored the cohort.
- **Corrected `get_average_price` docs** — removed the misleading claim that
  `engine_volume_from`/`_to` constrain the headline "to avoid mixing cohorts"; the
  bounds narrow the comparable **sample**, not the model-level headline. Field and
  docstring guidance now point at `cohort_estimate_usd` for cohort fair value.

### Docs

- Documented the `order_by="relevance"` default caveat (may bury cheapest/newest;
  pass an explicit sort for an exhaustive sweep).
- Marked `CarDetails.fuel` as a display label that merges type+volume
  inconsistently — use `fuel_id` / `engine_volume_l` for logic.
- Noted that Kyiv city and Kyiv oblast are distinct, region-scoped ids.

## [0.2.0] - 2026-06-08

Agent-facing correctness, data-richness, and efficiency overhaul, driven by real
multi-turn agent sessions that produced wrong answers or forced heavy
workarounds. Almost entirely additive (new fields, params, and tools). The one
breaking response-contract change is the removal of the `search_url` field from
`search_used_cars` results (see **Changed** below) — acceptable under a pre-1.0
minor bump, but call it out when upgrading.

### Added

- **`get_car_details_batch(auto_ids)`** — fetch up to 50 listings in one call
  (deduped, order-preserving, concurrency-bounded); a dead id returns a sparse
  entry instead of failing the whole batch.
- **Labelled + structured `get_car_details` fields** — every dictionary attribute
  now ships as both id and label (`body_id`+`body_name`, `fuel_id`+`fuel`,
  `gearbox_id`+`gearbox`+`gearbox_class`, `drive_id`+`drive`); engine
  displacement/power are lifted out of free-text into `engine_volume_l`,
  `engine_volume_class` (nominal), and `power_hp`.
- **Due-diligence provenance on `get_car_details`** — `condition` (1–4 severity),
  the `risk` block (damaged / for_parts / under_credit / confiscated / imported /
  needs_customs), `verification` (VIN/inspection), `seller` trust, `photo` links,
  plus `is_sold`/`sold_date`/`is_leasing`/`price_negotiable`/`exchange_possible`
  and the seller `description`.
- **New `search_used_cars` filters** — `engine_volume_from`/`_to` (litres),
  `power_hp_from`/`_to`, `generation_id[]`, `modification_id[]` (previously
  reachable only via `raw_search`); plus engine-volume filters on the
  average-price tools.
- **Reliability metadata on `get_average_price`** — `avg_price_usd`/`_uah`
  (AUTO.RIA's AI estimate, labelled as such), `sample_count`,
  `sample_min`/`median`/`max_usd`, a `price_consistency` flag that trips when the
  headline falls outside its own comparables, `cohort`, `period`, `status`, and
  `quota`; plus an `include_samples` flag for a lighter stats-only response.
- **English/transliterated filter aliases** (`Diesel`→`Дизель`, `wagon`→
  `Унiверсал`, `automatic`→`Автомат`, …) with Latin/Cyrillic homoglyph folding,
  and near-miss suggestions that rank the right localized option first.
- **Named `order_by`** values (`price_asc`, `year_desc`, …) alongside legacy ints.

### Changed

- **Removed `search_url`** from `search_used_cars`. The Public API mandates no
  attribution backlink and returns only ids + count; the field was a server
  invention that reproduced a broader query than was run and was modelled on the
  front-end site, not the API. Per-listing URLs still come from `get_car_details`.
- **`raw_search` is compact by default** (`{count, page, page_size, ids}`,
  OfferOfTheDay filtered); pass `verbose=True` for the full raw payload.
- **Server instructions** reframed around the resolve → search → details → price
  workflow and a "seller-declared, verify `risk`/`condition`" posture.

### Fixed

- **`search_used_cars` count no longer includes new cars.** The query now sends
  `searchType=4` (used-only) instead of `1`; the default search mixed NEW autos
  into the results, inflating the reported `count` even though the `ids` were
  used-only. Verified live against the API (a brand query dropped from 19,688 to
  19,598). Response shape and OfferOfTheDay filtering are unchanged.

### Notes

- `get_average_price` reliability fields describe the visible sample only — the
  API exposes no population distribution, so no percentiles are fabricated.

## [0.1.1] - 2026-06-06

Docs/registry-only release — no tool, resource, or API changes.

### Added

- **Official MCP Registry listing** as `io.github.yevhen-kalyna/autoria-mcp`:
  added a root `server.json` (metadata pointing at the PyPI package, `stdio`
  transport, documented env vars) and a `mcp-name` ownership marker in the README
  (= PyPI description). The release pipeline now publishes to the registry via OIDC
  after the PyPI upload, with a tag/version guard so `pyproject`, `server.json`,
  and the git tag can't drift.

### Fixed

- **Claude Desktop config example** in the README — the previous block told users
  to delete the `AUTORIA_USER_ID` line, which left an invalid trailing comma after
  `AUTORIA_API_KEY`. Replaced with a valid minimal block (API key only) and
  documented `AUTORIA_USER_ID` as an optional key to add for the paid tools.
- **`examples/README.md`** — corrected a sentence that referred to a non-existent
  inline config block; it now points at the sample `claude_desktop_config.json`.

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

[Unreleased]: https://github.com/yevhen-kalyna/autoria-mcp/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/yevhen-kalyna/autoria-mcp/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/yevhen-kalyna/autoria-mcp/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/yevhen-kalyna/autoria-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/yevhen-kalyna/autoria-mcp/releases/tag/v0.1.0
