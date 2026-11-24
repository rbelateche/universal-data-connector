# universal-data-connector

Map any data source to a canonical schema with LLM-powered inference.

- **`backend/`**: FastAPI + DuckDB. Connectors, schema sampler, Claude-based
  schema mapper with confidence scores, transformation engine, review and
  export endpoints.
- **`mcp-app/`**: an MCP App (built with [Skybridge](https://docs.skybridge.tech))
  that brings mapping review into Claude and ChatGPT: the LLM proposes, the human
  decides low-confidence mappings in an interactive table. See
  [mcp-app/README.md](mcp-app/README.md).
- **`cli/`**, **`infra/`**: CLI entry point, Docker Compose and Make targets.

## Quick start (demo)

```bash
make demo-api      # UDC API on :8000 with the fictional retail demo data
make mcp-install
make mcp-dev       # MCP app on :3000 — DevTools at http://localhost:3000/
```

`make help` lists every target.
