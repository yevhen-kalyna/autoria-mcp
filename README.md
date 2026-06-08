# autoria-mcp

<!-- mcp-name: io.github.yevhen-kalyna/autoria-mcp -->

[![CI](https://github.com/yevhen-kalyna/autoria-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/yevhen-kalyna/autoria-mcp/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/autoria-mcp.svg)](https://pypi.org/project/autoria-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/autoria-mcp.svg)](https://pypi.org/project/autoria-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

An [MCP](https://modelcontextprotocol.io) server that exposes the
**AUTO.RIA used-cars REST API** (`auto.ria.com`, via `developers.ria.com`) to AI
agents — programmatic, agent-friendly access to the Ukrainian used-car market
through the sanctioned API, no scraping.

The full tool surface is live — **30 tools, 7 dictionary resources, and 1
templated resource**: curated search/lookup tools (single and batch listing
details), paid statistics tools, thin endpoint mirrors, and browsable dictionary
resources, all backed by tiered caching and a typed async client.

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

## Quickstart: Claude Desktop (no coding required)

Want to use AUTO.RIA from the **Claude desktop app**? Follow these steps — no
programming needed, just some copy-and-paste. Pick your platform:
[macOS](#macos) · [Windows](#windows).

### macOS

**1. Install `uv`** (the small tool that runs `autoria-mcp` for you). Open the
**Terminal** app and paste this, then press Enter:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

(Full instructions: <https://docs.astral.sh/uv/getting-started/installation/>.)

**2. Get a free AUTO.RIA API key** at <https://developers.ria.com>. Keep it handy.
A `user_id` is optional — you only need it for the paid price-statistics tools.

**3. Find the full path to `uvx`.** The desktop app can't see your Terminal's
settings, so it needs the *full* path. In Terminal, run:

```sh
which uvx
```

Copy what it prints — usually `/opt/homebrew/bin/uvx` (Apple-Silicon Mac) or
`/usr/local/bin/uvx` (Intel Mac).

> **This is the #1 reason setup fails.** If you use just `uvx` instead of the full
> path, the app says it can't find it. Always paste the full path from `which uvx`.

**4. Open Claude Desktop's config file.** In the Claude app: **Settings →
Developer → Edit Config**. This opens a file called `claude_desktop_config.json`
(on macOS it lives at
`~/Library/Application Support/Claude/claude_desktop_config.json`).

**5. Add the `autoria` server.** Paste the block below. If the file already has a
`"mcpServers"` section, add `"autoria"` *inside* it next to your other servers;
otherwise paste the whole thing. Replace the two placeholder values:

```json
{
  "mcpServers": {
    "autoria": {
      "command": "/opt/homebrew/bin/uvx",
      "args": ["autoria-mcp"],
      "env": { "AUTORIA_API_KEY": "paste-your-api-key-here" }
    }
  }
}
```

- `command` → the full path from step 3.
- `AUTORIA_API_KEY` → your key from step 2.
- For the paid tools (average price, VIN lookup), add `"AUTORIA_USER_ID": "..."`
  to `env` — put a comma after the API-key line when you do, e.g.
  `"env": { "AUTORIA_API_KEY": "...", "AUTORIA_USER_ID": "..." }`.

Save the file.

**6. Fully quit and reopen Claude.** Press **`Cmd + Q`** (just closing the window
isn't enough), then open Claude again. The **first** start takes a few seconds
while it downloads the tool; after that it's instant.

**7. Try it.** Ask Claude something like:
*"Use autoria to find used BMW 3 Series cars in Kyiv and show me a few with prices."*

> **Heads-up on limits:** the free AUTO.RIA key allows roughly **30 requests/hour**
> and **1000/month** — so ask focused questions rather than broad ones.

**If autoria doesn't show up** after restarting, the log file usually says why:

```sh
tail -50 ~/Library/Logs/Claude/mcp-server-autoria.log
```

Most common fixes: use the **full `uvx` path** (step 3), and make sure you
**fully quit** Claude with `Cmd + Q`.

### Windows

The same flow on Windows — the commands and a couple of Windows-only gotchas
differ from macOS.

**1. Install `uv`** (it ships the `uvx` command that runs `autoria-mcp`). Open
**PowerShell** and run either:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

or, if you use [winget](https://learn.microsoft.com/windows/package-manager/):

```powershell
winget install --id=astral-sh.uv -e
```

Then **open a new terminal window** so the updated `PATH` takes effect.
(Full instructions: <https://docs.astral.sh/uv/getting-started/installation/>.)

**2. Get a free AUTO.RIA API key** at <https://developers.ria.com>. Keep it
handy. A `user_id` is optional — you only need it for the paid price-statistics
tools.

**3. Find the full path to `uvx.exe`.** The desktop app can't see your terminal's
`PATH`, so it needs the *full* path. In **PowerShell**, run:

```powershell
Get-Command uvx | Select-Object -ExpandProperty Source
```

or in **Command Prompt** (`cmd`):

```bat
where.exe uvx
```

Copy what it prints — usually `C:\Users\<you>\.local\bin\uvx.exe`.

> **In PowerShell, use `where.exe`, not `where`.** Plain `where` is an alias for
> `Where-Object` and won't find the executable.

> **This is the #1 reason setup fails.** If you use just `uvx` instead of the full
> path, the app says it can't find it. Always paste the full path from step 3.

**4. Open Claude Desktop's config file — use the in-app button.** In the Claude
app: **Settings → Developer → Edit Config**. This opens the correct
`claude_desktop_config.json` for your install.

> **Don't hand-edit the `%APPDATA%` file.** The documented location is
> `%APPDATA%\Claude\claude_desktop_config.json`
> (= `C:\Users\<you>\AppData\Roaming\Claude\claude_desktop_config.json`), but the
> **Microsoft Store / MSIX** build of Claude *virtualizes* that folder — it
> actually reads from
> `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`.
> Editing the plain `%APPDATA%` copy then makes your MCP servers **silently fail
> to load**. The **Edit Config** button always opens the right file — use it.

**5. Add the `autoria` server.** Paste the block below. If the file already has a
`"mcpServers"` section, add `"autoria"` *inside* it next to your other servers;
otherwise paste the whole thing. On Windows, backslashes in JSON must be
**doubled** (`\\`) — or use forward slashes (`C:/Users/you/.local/bin/uvx.exe`):

```json
{
  "mcpServers": {
    "autoria": {
      "command": "C:\\Users\\you\\.local\\bin\\uvx.exe",
      "args": ["autoria-mcp"],
      "env": { "AUTORIA_API_KEY": "paste-your-api-key-here" }
    }
  }
}
```

- `command` → the full path from step 3, with doubled backslashes.
- `AUTORIA_API_KEY` → your key from step 2.
- For the paid tools (average price, VIN lookup), add `"AUTORIA_USER_ID": "..."`
  to `env` — put a comma after the API-key line when you do, e.g.
  `"env": { "AUTORIA_API_KEY": "...", "AUTORIA_USER_ID": "..." }`.

Save the file. A ready-to-edit copy is at
[`examples/claude_desktop_config_windows.json`](examples/claude_desktop_config_windows.json).

> Prefer not to keep your key in the config? Omit the `env` block and instead put
> `AUTORIA_API_KEY` in a `.env` file in the working directory, or set it as a
> Windows user/system environment variable.

**6. Fully restart Claude.** Right-click the Claude icon in the **system tray**
(near the clock) and choose **Quit** — just closing the window isn't enough —
then open Claude again. The **first** start takes a few seconds while it
downloads the tool; after that it's instant.

**7. Try it.** Ask Claude something like:
*"Use autoria to find used BMW 3 Series cars in Kyiv and show me a few with prices."*

The same [limits](#quickstart-claude-desktop-no-coding-required) and most-common
fixes apply: use the **full `uvx.exe` path** (step 3), edit the config via the
**in-app button** (step 4), and **fully quit** from the tray (step 6). Logs are at
`%APPDATA%\Claude\logs\mcp-server-autoria.log`.

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
| `search_used_cars`  | Search by brand/model/region/year/price/engine-volume/power/generation/etc.; returns the match `count` + advert ids. |
| `get_car_details`   | Compact details for one advert id: price, year, mileage, structured engine volume/power, labelled body/fuel/gearbox, plus `condition`/`risk`/`verification`/`seller`/`photo` provenance, VIN-if-shown, masked phone, URL. |
| `get_car_details_batch` | Details for up to 50 advert ids in one call (deduped; a dead id returns a sparse entry). |
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
`list_all_body_styles`, `list_bodies_by_generation`, and `raw_search` (raw V1
search; compact `{count, ids}` by default, `verbose=True` for the full payload).

**Resources**: `autoria://dict/{categories,colors,countries,fuel-types,gearboxes,
body-styles,states}` and the templated `autoria://dict/models/{categoryId}/{markId}`.

**Health**: `ping` — zero-quota liveness/diagnostic check.

## Attribution

AUTO.RIA's API terms require a **visible link back to `auto.ria.com`** wherever you
display data sourced from the API. `get_car_details` and the paid endpoints include
a canonical per-listing deep link (`url`); keep it visible in whatever surface
presents a listing to an end user. (`search_used_cars` returns only ids + a count —
the Public API specifies no set-level search link, so none is invented.)

## Known limitations

These are deliberate scope/behaviour choices worth knowing before you rely on them:

- **Single brand/model per search.** Multi-brand or multi-model search is not yet
  modelled by `search_used_cars`. For OR-style queries across several brands, drop
  to `raw_search` and pass the raw V1 params yourself.
- **Search returns ids, not full listings.** `search_used_cars` gives you advert
  ids and a `count`. Fetch per-listing detail with `get_car_details` (or
  `get_car_details_batch` for a whole page of ids) — each lookup spends quota, so
  resolve only what you need.
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
