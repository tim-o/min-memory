# min-memory

A hierarchical, persistent memory system for AI assistants using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io). Enables Claude Code, Codex, and other MCP clients to maintain long-term memory across sessions with OAuth 2.1 authentication.

## Features

- **Structured session sync** — `sync_session` tool with auto-typing, upsert semantics, and entity validation
- **Hierarchical memory scopes** — global, project, and task-level context
- **Recency-weighted retrieval** — blends semantic similarity with temporal relevance
- **Entity tree** — YAML-configured entity hierarchy with runtime registration and validation
- **Semantic search** — vector similarity via Qdrant + FastEmbed
- **Access tracking** — automatic access_count and last_accessed_at on retrieval
- **OAuth 2.1 authentication** — Auth0 integration with per-user data isolation
- **Streaming HTTP transport** — MCP-compliant `/mcp` endpoint

### MCP Tools

| Tool | Description |
|------|-------------|
| `sync_session` | **Structured session sync** — store decisions, status updates, learnings, and feedback with auto-typing and upsert semantics |
| `store_memory` | Store a single memory with explicit type/scope (use `sync_session` for structured writes) |
| `retrieve_context` | Semantic search with recency weighting and status filtering |
| `search` | Quick search across all memories |
| `fetch` | Retrieve a specific memory by ID |
| `set_project` | Validate/create a project context |
| `get_context_info` | Environment detection (pwd, git, etc.) |
| `list_entities` | Browse known entities with optional entity tree view |
| `search_entities` | Fuzzy entity matching |
| `register_entity` | Add new entities to the entity tree at runtime |
| `link_memories` | Create relationships between memories |
| `update_memory` | Modify an existing memory's text or metadata |
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
│  Qdrant Vector DB (standalone)   │
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

# Run server (requires a Qdrant instance at localhost:6333)
python -m src.main
```

### Docker Compose (recommended)

Runs Qdrant, the MCP server, and Caddy (HTTPS) together:

```bash
# Create .env with your secrets
cat > .env <<EOF
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_API_AUDIENCE=https://your-domain.com
TRUSTED_BACKEND_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
EOF

docker compose up -d
```

Qdrant dashboard available at `http://localhost:6333/dashboard`.

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
- **Vector DB:** [Qdrant](https://qdrant.tech) (standalone, via docker-compose)
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
