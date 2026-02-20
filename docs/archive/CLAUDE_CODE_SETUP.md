# Claude Code HTTP MCP Server Setup

## Testing Locally

### 1. Start the HTTP MCP Server

```bash
cd /home/tim/github/min-memory
TIM_TOKEN="your_secret_token_here" .venv/bin/python memory_mcp_server_http.py
```

The server will start on `http://localhost:8080`

### 2. Configure Claude Code

Create or edit `~/.config/claude-code/mcp_config.json`:

```json
{
  "mcpServers": {
    "memory-http": {
      "command": "node",
      "args": [
        "/usr/local/bin/mcp-client-sse",
        "http://localhost:8080"
      ],
      "env": {
        "MCP_AUTH_TOKEN": "your_secret_token_here"
      }
    }
  }
}
```

**Note:** The HTTP MCP server uses SSE transport. Claude Code's stdio-based config needs an SSE client wrapper. Options:

#### Option A: Use `@modelcontextprotocol/client-sse` (if available)

```bash
npm install -g @modelcontextprotocol/client-sse
```

Then use config above.

#### Option B: Direct HTTP Configuration (if Claude Code supports it)

```json
{
  "mcpServers": {
    "memory-http": {
      "url": "http://localhost:8080/sse",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer your_secret_token_here"
      }
    }
  }
}
```

#### Option C: Keep stdio server for Claude Code, use HTTP for other clients

For local Claude Code development, keep using the stdio server:

```json
{
  "mcpServers": {
    "memory": {
      "command": "/home/tim/github/min-memory/.venv/bin/python",
      "args": ["/home/tim/github/min-memory/memory_mcp_server.py"]
    }
  }
}
```

Use HTTP server only for:
- Claude Desktop (can use HTTP)
- Claude Mobile (via Extensions)
- Remote access from other machines

### 3. Restart Claude Code

After updating the config, restart Claude Code to load the new MCP server configuration.

### 4. Test the Connection

In Claude Code, try using memory tools:

```
/mcp
```

Then test a memory operation:
- Store a memory
- Retrieve context
- List entities

## Production Deployment (GCP)

### 1. Generate Production Token

```bash
# Generate a secure 64-character token
openssl rand -hex 32
```

Save this token - you'll need it for:
- Server environment variable: `TIM_TOKEN`
- Client configuration: `Authorization: Bearer <token>`

### 2. Deploy to GCP

Follow instructions in `HTTP_DEPLOYMENT.md` Phase 2-3.

### 3. Update Client Configuration

Once deployed, update configs to use your GCP instance:

```json
{
  "mcpServers": {
    "memory": {
      "url": "https://<YOUR_GCP_IP>/sse",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer <YOUR_PRODUCTION_TOKEN>"
      }
    }
  }
}
```

## Troubleshooting

### "MCP server failed to start"

1. Check server is running: `curl http://localhost:8080/health`
2. Check logs: `cat /tmp/http_server.log` (if running with `tee`)
3. Verify token matches between server and client

### "Unauthorized" errors

- Verify `TIM_TOKEN` environment variable is set on server
- Verify `Authorization: Bearer` header in client config
- Check token matches exactly (no extra spaces/newlines)

### Database locked errors

- Only one process can access Qdrant database at a time
- Stop stdio server before running HTTP server on same database
- Use separate databases:
  - stdio: `~/.local/share/mcp-memory/`
  - HTTP: `~/.local/share/mcp-memory-http/`

### Tools not showing up

- Check MCP client supports SSE/HTTP transport
- Verify client configuration syntax
- Restart client after config changes

## Current Status

- ✅ HTTP server implemented with SSE transport
- ✅ Bearer token authentication
- ✅ User namespace isolation
- ✅ Database migrated (59 memories with `user: "tim"`)
- ✅ Health check endpoint: `/health`
- ✅ All 7 MCP tools working with user filtering
- ⏳ Need to verify Claude Code HTTP/SSE support
- ⏳ GCP deployment pending

## Next Steps

1. Verify Claude Code supports HTTP/SSE MCP servers
2. If not, document "stdio for local, HTTP for remote" workflow
3. Deploy to GCP for remote access
4. Test multi-client concurrent access (Desktop + Code)
5. Set up automated backups to GCS
