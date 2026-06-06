# autoria-mcp

An [MCP](https://modelcontextprotocol.io) server that exposes the
**AUTO.RIA used-cars REST API** (`auto.ria.com`, via `developers.ria.com`) to AI
agents — programmatic, agent-friendly access to the Ukrainian used-car market
through the sanctioned API, no scraping.

> **Status: Phase 2 (scaffold).** The server boots and answers a `ping` health
> check. Real search/lookup tools land in the next releases — see
> [Roadmap](#roadmap).

## Features (planned)

- **Curated, high-level tools** that take human-friendly inputs (brand, model,
  region, year/price ranges) and resolve them to AUTO.RIA's numeric IDs for you.
- **Thin endpoint mirrors** for the long-tail dictionary/lookup endpoints.
- **Aggressive caching** of the large, slow-changing dictionaries so name→ID
  resolution costs no quota after the first fetch.
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

| Tool   | Status     | Description                          |
| ------ | ---------- | ------------------------------------ |
| `ping` | ✅ available | Zero-quota liveness/diagnostic check. |

> Curated tools (`search_used_cars`, `get_car_details`, `get_average_price`,
> `lookup_brands`, `lookup_models`, `lookup_regions`) and thin endpoint mirrors
> for the remaining 27 operations land in Phases 3–4. This table will grow as
> they ship.

## Development

```sh
uv sync                     # create venv + install deps (incl. dev group)
uv run ruff check .         # lint
uv run ruff format --check .  # format check
uv run mypy src             # strict type check
uv run pytest               # tests (no network)
pre-commit install          # enable git hooks
```

The OpenAPI 3.1 description lives in
[`openapi/autoria-used-cars.yaml`](openapi/autoria-used-cars.yaml).

## Roadmap

1. ✅ **Phase 1** — OpenAPI spec, live-verified API facts.
2. ✅ **Phase 2** — repo scaffold, tooling, CI, packaging, runnable server.
3. ⏭️ **Phase 3** — typed async client, TTL dictionary cache, name→ID resolution,
   recorded-fixture tests (zero live quota).
4. ⏭️ **Phase 4** — curated + thin tools, dictionary MCP resources.
5. ⏭️ **Phase 5** — docs, examples, first PyPI release.

## License

[MIT](LICENSE). This is an unofficial project and is not affiliated with or
endorsed by RIA.com / AUTO.RIA.
