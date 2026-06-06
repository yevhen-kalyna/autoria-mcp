# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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
