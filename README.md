# autoria-mcp

[![CI](https://github.com/yevhen-kalyna/autoria-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/yevhen-kalyna/autoria-mcp/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/autoria-mcp.svg)](https://pypi.org/project/autoria-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/autoria-mcp.svg)](https://pypi.org/project/autoria-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An [MCP](https://modelcontextprotocol.io) server that exposes the
**AUTO.RIA used-cars REST API** (`auto.ria.com`, via `developers.ria.com`) to AI
agents — programmatic, agent-friendly access to the Ukrainian used-car market
through the sanctioned API, no scraping.

The full tool surface is live — **29 tools, 7 dictionary resources, and 1
templated resource**: curated search/lookup tools, paid statistics tools, thin
endpoint mirrors, and browsable dictionary resources, all backed by tiered
caching and a typed async client.

## Features

- **Curated, high-level tools** that take human-friendly inputs (brand, model,
  region, year/price ranges) and resolve them to AUTO.RIA's numeric IDs for you.
- **Paid statistics tools** (AI average price, price-over-time, VIN decode) that
  fail fast with a clear error when `AUTORIA_USER_ID` is unset — no wasted quota.
- **Thin endpoint mirrors** for the long-tail dictionary/lookup endpoints.
- **Dictionary resources** — browse categories, colours, regions, etc. as
  addressable `autoria://dict/...` documents.
- **Aggressive, tiered caching**: large slow-changing dictionaries are cached on
  disk for 7 days (name→ID resolution costs no quota after the first fetch),
  while volatile search/statistics responses are cached briefly, in memory only.
- **stdio and streamable-HTTP** transports.

## Install

Requires Python 3.11+. The package is distributed on PyPI; run it without a
manual install using [`uvx`](https://docs.astral.sh/uv/):

```sh
uvx autoria-mcp
```

Or install into a tool environment with `pipx` / `uv tool`:

```sh
uv tool install autoria-mcp   # or: pipx install autoria-mcp
```

## Configuration

All settings are read from environment variables (prefix `AUTORIA_`) or a local
`.env` file. Copy [`.env.example`](.env.example) to `.env` and fill in your key.

| Variable             | Default                       | Description                                                        |
| -------------------- | ----------------------------- | ------------------------------------------------------------------ |
| `AUTORIA_API_KEY`    | — (required for API calls)    | Personal API key from <https://developers.ria.com>. Never logged.  |
| `AUTORIA_USER_ID`    | —                             | User id, required only by the paid POST endpoints.                 |
| `AUTORIA_TRANSPORT`  | `stdio`                       | `stdio` or `http` (streamable-HTTP). Also `--transport`.           |
| `AUTORIA_HOST`       | `127.0.0.1`                   | Bind host for the HTTP transport.                                  |
| `AUTORIA_PORT`       | `8000`                        | Bind port for the HTTP transport.                                  |
| `AUTORIA_BASE_URL`   | `https://developers.ria.com`  | API host (only the production host is documented).                 |
| `AUTORIA_CACHE_DIR`  | `~/.cache/autoria-mcp`        | On-disk dictionary cache location.                                 |
| `AUTORIA_CACHE_TTL`  | `604800` (7 days)             | Default dictionary cache TTL, in seconds.                          |
| `AUTORIA_VOLATILE_TTL` | `600` (10 min)              | Memory-only TTL for volatile search/statistics responses.          |
| `AUTORIA_MEMORY_CACHE_MAX` | `256`                   | Max entries per in-memory cache tier (bounded LRU).                |
| `AUTORIA_MAX_RETRIES` | `3`                          | Retry attempts on `429` / `5xx` (backoff + full jitter).           |
| `AUTORIA_BACKOFF_BASE` | `0.5`                       | Base backoff delay, in seconds.                                    |
| `AUTORIA_BACKOFF_CAP` | `8.0`                        | Max delay for a single backoff sleep, in seconds.                  |
| `AUTORIA_QUOTA_HOURLY_LIMIT` | `30`                  | Assumed hourly quota; usage warns near it (never blocks).          |
| `AUTORIA_QUOTA_MONTHLY_LIMIT` | `1000`               | Assumed monthly quota; usage warns near it (never blocks).         |
| `AUTORIA_QUOTA_WARN_RATIO` | `0.9`                   | Warn once usage crosses this fraction of a window limit.           |
| `AUTORIA_LOG_LEVEL`  | `INFO`                        | Package log level.                                                 |

The API key is held in a `SecretStr` and never written to logs.

## Running

```sh
# stdio (default) — how MCP clients launch it
autoria-mcp

# streamable-HTTP
autoria-mcp --transport http --host 127.0.0.1 --port 8000
# or
AUTORIA_TRANSPORT=http autoria-mcp
```

See [`examples/`](examples/) for ready-to-paste MCP client configs (Claude
Desktop and a generic stdio client).

## Quota guidance

The AUTO.RIA free package is metered **per API key across all RIA web services**
and the limits are tight:

- **~1000 requests / month**
- **30 requests / hour** (rolling); exceeding either returns `429 OVER_RATE_LIMIT`
  and temporarily blocks the key.

There are **no** `X-RateLimit-*` response headers, so the client tracks usage
locally (Phase 3). Treat every live call as spending scarce quota: the dictionary
endpoints are cached aggressively, and search/statistics responses should not be
re-fetched needlessly.

## Tool catalog

**Curated tools** — natural inputs (names, ranges), resolved to IDs for you:

| Tool                | Description                                                              |
| ------------------- | ----------------------------------------------------------------------- |
| `search_used_cars`  | Search listings by brand/model/region/year/price/etc.; returns ids + a canonical `search_url`. |
| `get_car_details`   | Compact details for one advert id (price, year, mileage, VIN-if-shown, masked phone, URL). |
| `lookup_brands`     | List passenger-car brands, or resolve one brand name to its id.         |
| `lookup_models`     | List a brand's models, or resolve one model name to its id.             |
| `lookup_regions`    | List regions (oblasts), or resolve one region name to its id.           |
| `lookup_cities`     | List a region's cities, or resolve one city name to its id.             |

**Paid tools** (require `AUTORIA_USER_ID`; fail fast with a clear error otherwise):

| Tool                            | Description                                              |
| ------------------------------- | ------------------------------------------------------- |
| `get_average_price`             | AI average price + comparable listings (by params or `omni_id`). |
| `get_average_price_over_periods`| Monthly average-price time series.                      |
| `get_params_by_vin`             | Decode a VIN / plate / advert id into car-parameter chips. |

**Thin mirrors** (raw passthrough, 7-day cached): `list_categories`,
`list_all_models`, `list_models_grouped`, `list_generations`, `list_modifications`,
`list_modifications_by_body`, `list_equipment`, `list_options`, `list_options_v2`,
`list_colors`, `list_countries`, `list_drive_types`, `list_fuel_types`,
`list_gearboxes`, `list_body_styles`, `list_body_styles_grouped`,
`list_all_body_styles`, `list_bodies_by_generation`, and `raw_search` (raw V1 search).

**Resources**: `autoria://dict/{categories,colors,countries,fuel-types,gearboxes,
body-styles,states}` and the templated `autoria://dict/models/{categoryId}/{markId}`.

**Health**: `ping` — zero-quota liveness/diagnostic check.

## Attribution

AUTO.RIA's API terms require a **visible link back to `auto.ria.com`** wherever you
display data sourced from the API. Every tool that returns listings honours this
for you: `get_car_details` and the paid endpoints include a canonical per-listing
deep link, and `search_used_cars` returns a set-level `search_url` (search itself
returns only ids). Keep these links visible in whatever surface presents the
results to an end user.

## Known limitations

These are deliberate scope/behaviour choices worth knowing before you rely on them:

- **Single brand/model per search.** Multi-brand or multi-model search is not yet
  modelled by `search_used_cars`. For OR-style queries across several brands, drop
  to `raw_search` and pass the raw V1 params yourself.
- **Search returns ids, not full listings.** `search_used_cars` gives you advert
  ids, a `count`, and a set-level `search_url`. Fetch per-listing detail (price,
  year, mileage, URL, masked phone) with `get_car_details` for each id you care
  about — each call spends quota, so resolve only what you need.
- **Search is V1-only and silently ignores unknown params** — a genuine footgun.
  The underlying `/auto/search` endpoint does not validate filter keys: a misspelt
  or unsupported param is dropped, and the search quietly widens to the whole site
  instead of erroring. The curated tool resolves names to the correct V1 ids to
  avoid this, but `raw_search` passes your params through verbatim.
- **Paid POST errors arrive as HTTP 200.** The paid endpoints return errors in the
  body (`noticeType: "error"`) with a 200 status; the paid tools detect and surface
  these as tool errors.
- **`get_average_price_over_periods`** accepts only `period ∈ {30, 90, 180, 365}`.

## Development

```sh
uv sync                     # create venv + install deps (incl. dev group)
uv run ruff check .         # lint
uv run ruff format --check .  # format check
uv run mypy                 # strict type check (src + tests)
uv run pytest               # tests (no network)
pre-commit install          # enable git hooks
```

The OpenAPI 3.1 description lives in
[`openapi/autoria-used-cars.yaml`](openapi/autoria-used-cars.yaml).

## Roadmap

1. ✅ **Phase 1** — OpenAPI spec, live-verified API facts.
2. ✅ **Phase 2** — repo scaffold, tooling, CI, packaging, runnable server.
3. ✅ **Phase 3** — typed async client, TTL dictionary cache, name→ID resolution,
   recorded-fixture tests (zero live quota).
4. ✅ **Phase 4** — curated + paid + thin tools, dictionary MCP resources.
5. ✅ **Phase 5** — docs, examples, first PyPI release (`0.1.0`).

**Post-1.0 backlog** (not scheduled): native multi-brand / multi-model search;
per-endpoint cache TTLs; a cross-process quota lock (current accounting is
per-process, warn-only); an `npx` shim for Node-based MCP clients.

## License

[MIT](LICENSE). This is an unofficial project and is not affiliated with or
endorsed by RIA.com / AUTO.RIA.
