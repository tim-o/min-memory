# MCP Memory Server - HTTP Deployment Plan

## Overview

Convert the stdio-based MCP memory server to HTTP+SSE transport for multi-client concurrent access, deployed on GCP.

## Requirements

- **Single user** (Tim) accessing from multiple clients (Desktop, Code, Mobile, etc.)
- **One shared memory store** with optional user namespacing
- **Public internet access** with OAuth authentication
- **GCP deployment** using $300/90-day credits
- **Zero-cost backups** to GCS
- **Cost-conscious** ingress/egress

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Clients (Desktop, Code, Mobile, etc.)          │
│  - Configure HTTP endpoint URL                  │
│  - Provide OAuth bearer token                   │
└────────────────┬────────────────────────────────┘
                 │
                 │ HTTPS (TLS via Cloud Run or LB)
                 ↓
┌─────────────────────────────────────────────────┐
│  GCP Compute Instance / Cloud Run               │
│                                                 │
│  ┌───────────────────────────────────────────┐ │
│  │  HTTP MCP Server (FastAPI)                │ │
│  │  - Streamable HTTP transport              │ │
│  │  - OAuth middleware (Bearer token)        │ │
│  │  - User namespace support (optional)      │ │
│  └─────────────────┬─────────────────────────┘ │
│                    │                             │
│  ┌─────────────────▼─────────────────────────┐ │
│  │  Qdrant Vector Database                   │ │
│  │  - Persistent disk storage                │ │
│  │  - Nightly snapshots to GCS               │ │
│  └───────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## Implementation Components

### 1. HTTP Transport Layer

**Tech Stack:**
- FastAPI for HTTP server (native ASGI, SSE support)
- uvicorn as ASGI server
- MCP Python SDK (v1.16.0)

**Endpoints:**
- `POST /mcp` - Main MCP endpoint (Streamable HTTP transport)
- `GET /health` - Health check
- `GET /metrics` - Optional observability

**Transport Protocol:**
- Client sends JSON-RPC messages via POST
- Server responds with SSE stream or single JSON response
- Session IDs generated per connection (optional)

### 2. Authentication & User Isolation

**Strategy: Bearer Token → User Mapping**
- Each client gets a unique bearer token (64 hex chars)
- Server maps token → user ID via environment variables
- All database operations filtered by user ID
- **User A cannot read/write user B's data**

**Implementation:**
```python
# Environment variables
TIM_TOKEN=<generated_token_1>

# Server-side mapping
USER_TOKENS = {
    os.getenv("TIM_TOKEN"): "tim",
    # Future users: os.getenv("USER2_TOKEN"): "user2",
}

def get_user_from_token(token: str) -> Optional[str]:
    return USER_TOKENS.get(token)  # None if invalid

# All Qdrant queries include user filter
filter = Filter(must=[
    FieldCondition(key="user", match=MatchValue(value=current_user)),
    # ... other filters
])
```

**Security measures:**
- HTTPS only (no plain HTTP)
- Token stored in env vars, never in code
- Automatic user isolation at database level
- Invalid token = 401 Unauthorized

### 3. User Namespacing

**Implementation:**
- `user` field extracted from bearer token (not from client request)
- Stored automatically in all Qdrant records
- All queries filtered by current user
- Clients never specify user (prevents spoofing)

**Schema addition:**
```python
payload = {
    "user": current_user,  # Derived from bearer token, NOT client input
    "text": "...",
    "memory_type": "...",
    "scope": "...",
    # ... rest of fields
}
```

**Data Migration:**
- Existing memories (currently 1 record) need `user: "tim"` backfilled
- Migration script or lazy migration on first access

### 4. GCP Deployment Options

**Option A: Cloud Run (Serverless)**
- Pros: Auto-scaling, HTTPS built-in, pay-per-use
- Cons: Cold starts, persistent disk tricky, state management
- Cost: ~$0 for low usage (free tier generous)

**Option B: Compute Engine (VM)**
- Pros: Full control, persistent disk simple, no cold starts
- Cons: Always-on billing, manual scaling, need to configure HTTPS
- Cost: e2-micro (free tier) or e2-small (~$13/month)

**Option C: Cloud Run + Cloud SQL/Managed Qdrant**
- Pros: Serverless + managed storage
- Cons: More expensive, overkill for single user
- Cost: Not recommended

**Decision: Compute Engine e2-small**
- Qdrant needs persistent storage (easier on VM)
- Always-on service expected (no cold starts)
- Simple systemd service management
- Can use self-signed cert or Caddy for TLS
- ~$13/month after credits

**Specs:**
- e2-small (2 vCPU, 2GB RAM) - sufficient for current use, easy to upgrade
- 20GB persistent SSD (for OS + Qdrant)
- Ubuntu 24.04 LTS
- us-central1 region (cheapest)

**Note on RAM:** 2GB sufficient for embeddings + Qdrant with small dataset (<10K memories). Bottleneck likely sentence-transformers model loading (~1GB), not Qdrant. Can upgrade to e2-medium (4GB) if needed (~$13/month more).

### 5. Backup Strategy (Zero Cost)

**Qdrant Snapshot to GCS:**
- Qdrant has built-in snapshot API
- Cron job (daily 2am UTC): create snapshot, upload to GCS
- GCS free tier: 5GB storage, 5000 uploads/month (plenty)
- Retention: keep last 7 days, monthly archives

**Script:**
```bash
#!/bin/bash
# /opt/mcp-memory/backup.sh
DATE=$(date +%Y%m%d)
qdrant-cli snapshot create --collection memories --output /tmp/snapshot-$DATE.tar.gz
gsutil cp /tmp/snapshot-$DATE.tar.gz gs://mcp-memory-backups/
rm /tmp/snapshot-$DATE.tar.gz
# Cleanup: keep last 7 daily
gsutil ls gs://mcp-memory-backups/ | head -n -7 | xargs -r gsutil rm
```

**Crontab:**
```
0 2 * * * /opt/mcp-memory/backup.sh
```

### 6. Cost Estimation

**Compute:**
- e2-small: ~$13.21/month (730 hours × $0.0181/hr)
- 20GB persistent SSD: ~$3.40/month

**Network:**
- Egress: First 1GB free, then $0.12/GB (likely <1GB/month for text)
- Ingress: Free

**Storage (GCS):**
- Free tier: 5GB (snapshots ~100MB each = 7 days covered)

**Total: ~$16.61/month** (after credits, ~$12 left for other GCP services)

### 7. Client Configuration

**No custom domain needed - use static IP directly**

**Claude Code (`~/.config/claude-code/mcp_config.json`):**
```json
{
  "mcpServers": {
    "memory": {
      "url": "https://<STATIC_IP>/mcp",
      "transport": "http",
      "headers": {
        "Authorization": "Bearer <YOUR_TOKEN>"
      }
    }
  }
}
```

**Claude Desktop (`claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "memory": {
      "url": "https://<STATIC_IP>/mcp",
      "transport": "http",
      "headers": {
        "Authorization": "Bearer <YOUR_TOKEN>"
      }
    }
  }
}
```

**Claude Mobile:**
- Set up as "Extension" via web interface
- Uses same endpoint + token configuration
- MCP servers appear as extensions in mobile app

## Implementation Steps

### Phase 1: Local Development

1. **Update `memory_mcp_server.py`:**
   - Replace stdio transport with FastAPI
   - Add SSE streaming support for responses
   - Implement bearer token auth middleware
   - Add `user` namespace parameter (default "tim")

2. **Add dependencies:**
   ```
   fastapi
   uvicorn[standard]
   python-multipart
   ```

3. **Test locally:**
   - Run: `uvicorn memory_mcp_server:app --host 0.0.0.0 --port 8080`
   - Test with curl/httpie
   - Verify multi-client connections work

### Phase 2: GCP Setup

4. **Provision infrastructure:**
   - Create GCP project (or use existing)
   - Provision e2-small compute instance
   - Configure firewall: allow 80, 443, 22
   - Set up static external IP

5. **Install software:**
   ```bash
   sudo apt update && sudo apt install -y python3.12 python3.12-venv caddy
   ```

6. **Deploy application:**
   - Copy code to `/opt/mcp-memory/`
   - Create venv: `python3.12 -m venv /opt/mcp-memory/.venv`
   - Install deps: `/opt/mcp-memory/.venv/bin/pip install -r requirements.txt`
   - Copy existing Qdrant data from `~/.local/share/mcp-memory/qdrant/` to `/opt/mcp-memory/data/qdrant/`
   - Run migration script to backfill `user: "tim"` on existing memories
   - Create systemd service

7. **Configure TLS:**
   - Use Caddy with self-signed cert for IP-based HTTPS
   - Or use Caddy's automatic HTTPS (works with IPs via self-signed)

### Phase 3: Production Setup

9. **Systemd service (`/etc/systemd/system/mcp-memory.service`):**
   ```ini
   [Unit]
   Description=MCP Memory Server
   After=network.target

   [Service]
   Type=simple
   User=mcp
   WorkingDirectory=/opt/mcp-memory
   Environment="TIM_TOKEN=<YOUR_GENERATED_TOKEN>"
   ExecStart=/opt/mcp-memory/.venv/bin/uvicorn memory_mcp_server:app --host 127.0.0.1 --port 8080
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

10. **Caddy reverse proxy (`/etc/caddy/Caddyfile`):**
    ```
    https://<STATIC_IP> {
        reverse_proxy localhost:8080
        encode gzip
        tls internal  # Self-signed cert for IP
    }
    ```

11. **Set up backups:**
    - Create GCS bucket: `gsutil mb gs://mcp-memory-backups`
    - Add backup script to `/opt/mcp-memory/backup.sh`
    - Add cron job

12. **Data already migrated in step 6**

### Phase 4: Client Configuration

13. **Update all clients:**
    - Claude Code: update MCP config with `https://<STATIC_IP>/mcp`
    - Claude Desktop: update config with same endpoint
    - Claude Mobile: set up as Extension via web interface
    - Other tools: provide URL + token

14. **Test multi-client:**
    - Open Desktop and Code simultaneously
    - Store memory in one, retrieve in other
    - Verify concurrent access works
    - Verify user isolation (should only see own memories)

## Decisions Made

1. ✅ **No domain name** - use static IP directly
2. ✅ **User namespace parameterized** - token maps to user ID, all queries filtered
3. ✅ **No monitoring** - just logs
4. ✅ **Mobile support** - Claude Mobile uses Extensions (MCP servers)
5. ✅ **Keep existing memory** - migrate in deployment step

## Security Considerations

- Token in transit: HTTPS only
- Token at rest: Environment variables, never committed
- DDoS mitigation: GCP Cloud Armor (free tier) or rate limiting
- Firewall: Only 80/443 exposed, SSH key-only
- Updates: Auto security updates enabled

## Rollback Plan

If HTTP deployment fails:
- Keep stdio version in separate branch
- Can always revert to local-only usage
- Data preserved in Qdrant (transport-agnostic)

## Next Steps

1. **Review & approve this plan**
2. **Answer open questions**
3. **Start Phase 1: local development**
4. **Test thoroughly before GCP deployment**
5. **Document client setup for each platform**

---

**Estimated timeline:** 1-2 days development + testing, 1-2 hours deployment
**Risk level:** Low (can always revert to stdio)
**Cost:** ~$0 for 90 days, ~$17/month after
