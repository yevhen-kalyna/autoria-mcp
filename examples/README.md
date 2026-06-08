# Example MCP client configurations

Two ready-to-adapt configs for wiring `autoria-mcp` into an MCP client.

## `claude_desktop_config.json` — stdio (recommended)

The standard way clients launch MCP servers. The client spawns `uvx autoria-mcp`
and talks to it over stdio; credentials are passed via `env`.

Merge the `mcpServers.autoria` block into your Claude Desktop config:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json` — but on the
  Microsoft Store / MSIX build that path is virtualized, so don't hand-edit it.
  Open it via **Settings → Developer → Edit Config** in the app instead, or your
  MCP servers may silently fail to load. Start from
  [`claude_desktop_config_windows.json`](claude_desktop_config_windows.json),
  which uses a placeholder absolute `uvx.exe` path.

Replace the placeholder `AUTORIA_API_KEY` (and `AUTORIA_USER_ID` if you use the
paid POST endpoints) with your own values from <https://developers.ria.com>, then
**fully quit** the client (`Cmd + Q` on macOS, or right-click → **Quit** from the
system tray on Windows) and reopen it.

> **Use the full path to `uvx`, not just `uvx`.** Desktop apps are launched by the
> OS without your shell's `PATH`, so a bare `"command": "uvx"` often fails with
> "command not found". Find the absolute path and use it:
>
> - **macOS:** `which uvx` — e.g. `/opt/homebrew/bin/uvx` (Apple Silicon) or
>   `/usr/local/bin/uvx` (Intel).
> - **Windows:** `Get-Command uvx | Select-Object -ExpandProperty Source` in
>   PowerShell, or `where.exe uvx` in `cmd` — e.g.
>   `C:\Users\you\.local\bin\uvx.exe`. (In PowerShell use `where.exe`; plain
>   `where` is an alias for `Where-Object`.) In JSON, double the backslashes
>   (`C:\\Users\\you\\...`) or use forward slashes.
>
> The sample `claude_desktop_config.json` uses the bare name for brevity — swap in
> your full path. The Windows sample
> [`claude_desktop_config_windows.json`](claude_desktop_config_windows.json) ships
> a placeholder absolute path.

> Prefer not to put secrets in the client config? Omit the `env` block and put
> `AUTORIA_API_KEY` in a `.env` file in your working directory or your shell env.

> **New to this?** The main [README](../README.md#quickstart-claude-desktop-no-coding-required)
> has a step-by-step, non-technical walkthrough for Claude Desktop.

## `mcp_http_config.json` — streamable-HTTP

For clients that connect to an already-running HTTP endpoint. Start the server
yourself first:

```sh
AUTORIA_API_KEY=... AUTORIA_TRANSPORT=http autoria-mcp --host 127.0.0.1 --port 8000
```

then point the client at `http://127.0.0.1:8000/mcp`.

## A typical agent flow

Once wired in, an agent answers a question like *"what do used BMW 3 Series go for
in Kyiv?"* by chaining a few tools — resolving names to ids before searching, then
pulling detail only for the listings it cares about (each call spends scarce quota):

1. **`lookup_brands` / `lookup_models`** — resolve `"BMW"` and `"3 Series"` to their
   numeric ids (cached for 7 days, so this costs quota only once). The curated
   `search_used_cars` does this resolution for you, so you can also skip straight to
   step 2 with plain names.
2. **`search_used_cars`** — search by brand/model/region/year/price/engine-volume;
   returns advert `ids` and a `count`.
3. **`get_car_details`** — for each interesting id, fetch the compact listing (price,
   year, mileage, condition/risk provenance, VIN-if-shown, masked phone, and the
   canonical per-listing URL). Use `get_car_details_batch` to look up many at once.
4. **`get_average_price`** — *(paid; needs `AUTORIA_USER_ID`)* get AUTO.RIA's AI
   average price plus comparable listings to judge whether an asking price is fair.

## `inproc_session.py` — drive the server from Python

[`inproc_session.py`](inproc_session.py) connects an in-memory MCP client to the
server in a single process, lists the full tool/resource surface, and calls the
zero-quota `ping` tool. It needs no API key and makes no network calls — a quick way
to confirm the server is wired correctly:

```sh
uv run python examples/inproc_session.py
```
