# Example MCP client configurations

Two ready-to-adapt configs for wiring `autoria-mcp` into an MCP client.

## `claude_desktop_config.json` — stdio (recommended)

The standard way clients launch MCP servers. The client spawns `uvx autoria-mcp`
and talks to it over stdio; credentials are passed via `env`.

Merge the `mcpServers.autoria` block into your Claude Desktop config:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Replace the placeholder `AUTORIA_API_KEY` (and `AUTORIA_USER_ID` if you use the
paid POST endpoints) with your own values from <https://developers.ria.com>, then
restart the client.

> Prefer not to put secrets in the client config? Omit the `env` block and put
> `AUTORIA_API_KEY` in a `.env` file in your working directory or your shell env.

## `mcp_http_config.json` — streamable-HTTP

For clients that connect to an already-running HTTP endpoint. Start the server
yourself first:

```sh
AUTORIA_API_KEY=... AUTORIA_TRANSPORT=http autoria-mcp --host 127.0.0.1 --port 8000
```

then point the client at `http://127.0.0.1:8000/mcp`.
