# min-memory

A hierarchical, persistent memory system for AI assistants using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io). Enables Claude Code, Codex, and other MCP clients to maintain long-term memory across sessions with OAuth 2.1 authentication.

## Features

- **Hierarchical memory scopes** — global, project, and task-level context
- **Semantic search** — vector similarity via Qdrant + FastEmbed
- **OAuth 2.1 authentication** — Auth0 integration with per-user data isolation
- **Streaming HTTP transport** — MCP-compliant `/mcp` endpoint
- **Soft delete** — non-destructive memory removal

### MCP Tools

| Tool | Description |
|------|-------------|
| `store_memory` | Store memories with hierarchical scoping |
| `retrieve_context` | Semantic search with metadata filtering |
| `search` | Quick search across all memories |
| `fetch` | Retrieve a specific memory by ID |
| `set_project` | Validate/create a project context |
| `get_context_info` | Environment detection (pwd, git, etc.) |
| `list_entities` | Browse known entities |
| `search_entities` | Fuzzy entity matching |
| `link_memories` | Create relationships between memories |
| `delete_memory` | Soft-delete a memory |

## Architecture

```
┌──────────────────────────┐
│   Auth0 (OAuth 2.1)      │
│   Authorization Server   │
└────────────┬─────────────┘
             │ Issues JWT tokens
             ▼
┌──────────────────────────────────┐
│  MCP Client (Claude/Codex/etc)   │
│  OAuth 2.1 + Streaming HTTP      │
└────────────┬─────────────────────┘
             │ HTTPS + Bearer JWT
             ▼
┌──────────────────────────────────┐
│  Caddy (Reverse Proxy)           │
│  TLS termination (Let's Encrypt) │
└────────────┬─────────────────────┘
             │ HTTP (localhost:8080)
             ▼
┌──────────────────────────────────┐
│  MCP Memory Server (Python)      │
│  MCPAuth JWT validation          │
│  Per-user memory isolation       │
└────────────┬─────────────────────┘
             │
             ▼
┌──────────────────────────────────┐
│  Qdrant Vector DB (local file)   │
│  BAAI/bge-small-en-v1.5 (384d)  │
└──────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.12+
- An [Auth0](https://auth0.com) tenant with:
  - An API (audience) configured
  - Dynamic Client Registration enabled

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AUTH0_DOMAIN="your-tenant.us.auth0.com"
export AUTH0_API_AUDIENCE="https://your-domain.com"
export MCP_DATA_DIR="$HOME/.local/share/mcp-memory-http"

# Run server
python -m src.main
```

### Docker

```bash
# Build
docker build -t min-memory .

# Run
docker run -p 8080:8080 \
  -e AUTH0_DOMAIN="your-tenant.us.auth0.com" \
  -e AUTH0_API_AUDIENCE="https://your-domain.com" \
  -v mcp-data:/var/lib/data \
  min-memory
```

Or with the included `docker-compose.yml` (also runs Caddy for HTTPS):

```bash
AUTH0_DOMAIN="your-tenant.us.auth0.com" \
AUTH0_API_AUDIENCE="https://your-domain.com" \
docker compose up
```

### Connecting Claude Code

1. Enable Developer Mode: **Settings > Connectors > Advanced settings > Developer Mode (ON)**
2. Click **Create** in Connectors
3. Name: `memory`, URL: `https://your-domain.com`, Authentication: `OAuth`
4. Click **Connect** and complete the Auth0 OAuth flow

## Technology Stack

- **Protocol:** [MCP](https://modelcontextprotocol.io) (Model Context Protocol)
- **Server:** Python + Starlette (ASGI)
- **Transport:** `fastapi-mcp` (Streaming HTTP)
- **Auth:** Auth0 (OAuth 2.1) + [MCPAuth](https://mcp-auth.dev) (JWT validation)
- **Vector DB:** [Qdrant](https://qdrant.tech) (local storage)
- **Embeddings:** [FastEmbed](https://qdrant.github.io/fastembed/) (`BAAI/bge-small-en-v1.5`, 384-dim)
- **Reverse Proxy:** Caddy (automatic HTTPS)

## Documentation

See the [`docs/`](docs/) directory:

- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — Technical architecture and implementation details
- [DEPLOYMENT_RUNBOOK.md](docs/DEPLOYMENT_RUNBOOK.md) — Production deployment procedures
- [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — Common issues and solutions
- [INSTRUCTIONS.md](docs/INSTRUCTIONS.md) — AI client integration instructions

## License

MIT
