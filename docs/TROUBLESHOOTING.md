# Troubleshooting Guide

Common issues and solutions for the MCP Memory Server.

## Codex CLI Authentication Issues

### Issue: "Auth required" error with Codex

**Symptoms:**
```bash
codex
# Error: Auth required
```

**Root Cause:** Incorrect `config.toml` structure - `rcmp` settings nested under `[features]` instead of at root level.

**Solution:**

Edit `~/.codex/config.toml` and ensure `rcmp` settings are at the **root level**, NOT under `[features]`:

**❌ WRONG:**
```toml
[features]
experimental_use_rcmp_client = true

[[features.rcmp_servers]]
name = "memory"
url = "https://your-domain.com"
```

**✅ CORRECT:**
```toml
experimental_use_rcmp_client = true

[[rcmp_servers]]
name = "memory"
url = "https://your-domain.com"
```

After fixing, restart Codex and complete the OAuth flow when prompted.

---

## Claude Code Connection Issues

### Issue: "Unauthorized" error when connecting

**Symptoms:**
- Connector shows "Authentication required"
- OAuth flow completes but connection still fails

**Solutions:**

1. **Re-authenticate:**
   - Go to Settings → Connectors
   - Find "memory" connector
   - Click "Disconnect" then "Connect"
   - Complete OAuth flow again

2. **Check Developer Mode:**
   - Settings → Connectors → Advanced settings
   - Ensure "Developer Mode" is ON

3. **Verify URL:**
   - Connector URL should be: `https://your-domain.com`
   - NO trailing slash
   - Authentication type: `OAuth`

---

## OAuth Flow Issues

### Issue: OAuth redirect fails or hangs

**Symptoms:**
- Browser opens but shows error page
- Redirect never completes
- "Could not complete authentication" message

**Solutions:**

1. **Check Auth0 callback URLs:**
   - Verify your Auth0 app has correct callback URLs configured
   - For Claude Code: `https://claude.ai/api/mcp/auth_callback`
   - For Codex: Dynamic, handled automatically

2. **Clear browser cookies:**
   - Clear Auth0 session cookies for `your-tenant.us.auth0.com`
   - Try OAuth flow again

3. **Check server health:**
   ```bash
   curl https://your-domain.com/health
   # Should return: {"status":"ok","service":"mcp-memory-server-http","auth":"oauth2","auth_provider":"..."}
   ```

---

## MCP Tool Errors

### Issue: "Unauthorized - no valid user context"

**Symptoms:**
- Tools return error: `Error: Unauthorized - no valid user context`
- Connection appears successful but tools don't work

**Root Cause:** Bearer token not being sent or validated correctly.

**Solutions:**

1. **Re-authenticate:**
   - Disconnect and reconnect the MCP server
   - Complete OAuth flow fresh

2. **Check logs (server-side):**
   ```bash
   # On GCP VPS
   docker logs <container-id> | grep "Authenticated"
   # Should see: "Authenticated Auth0 user: auth0|..."
   ```

3. **Verify token in request:**
   - Server expects `Authorization: Bearer <jwt>` header
   - If missing, check MCP client configuration

---

## Memory Retrieval Issues

### Issue: Memories not found / empty results

**Symptoms:**
- `retrieve_context()` returns no results
- Memories stored but not retrieved

**Solutions:**

1. **Check user isolation:**
   - Each user (Auth0 `sub`) has separate memory space
   - Verify you're authenticated as the same user who stored the memories

2. **Verify memory was stored:**
   ```
   # Use list_entities() to see what exists
   list_entities(scope="global")
   list_entities(scope="project", project="your-project")
   ```

3. **Check score threshold:**
   - `retrieve_context()` has `score_threshold` parameter (default: 0.0)
   - Lower threshold to include more results
   - Semantic search requires query similarity

4. **Verify scope/project filters:**
   - If searching with `project="foo"`, memories must have `project="foo"`
   - Global memories always included in hierarchical retrieval

---

## Server Health Issues

### Issue: Server unreachable / connection timeout

**Symptoms:**
- `curl https://your-domain.com/health` times out
- Connection refused errors

**Solutions:**

1. **Check server status (GCP):**
   ```bash
   gcloud compute instances describe <instance-name> --zone=us-central1-a
   # Check: status should be "RUNNING"
   ```

2. **Check Docker container:**
   ```bash
   # SSH into GCP VPS
   gcloud compute ssh <instance-name> --zone=us-central1-a

   # Verify container running
   docker ps | grep memory-server

   # Check logs
   docker logs <container-id>
   ```

3. **Verify Caddy reverse proxy:**
   ```bash
   # Check Caddy logs
   docker logs caddy

   # Test local endpoint
   curl http://localhost:8080/health
   ```

4. **DNS resolution:**
   ```bash
   dig your-domain.com +short
   # Should return GCP external IP
   ```

---

## JWT Validation Errors

### Issue: "Invalid token" or "Token validation failed"

**Symptoms:**
- Server logs show JWT validation errors
- Authentication flow completes but requests fail

**Solutions:**

1. **Check Auth0 configuration:**
   - Verify `AUTH0_DOMAIN` environment variable is correct
   - Verify `AUTH0_API_AUDIENCE` matches Auth0 API configuration

2. **Token expiration:**
   - JWT tokens expire (typically 24 hours)
   - Re-authenticate to get fresh token

3. **Clock skew:**
   - Ensure server clock is synchronized
   - JWT validation checks `exp` and `iat` claims

4. **JWKS refresh:**
   - Server caches Auth0 public keys (JWKS)
   - If Auth0 keys rotate, restart server to refresh cache:
     ```bash
     docker restart <container-id>
     ```

---

## Data Isolation Issues

### Issue: Seeing other users' memories

**Symptoms:**
- Memories from different users appearing in results
- Privacy concern

**Root Cause:** This should NOT happen - critical bug if it does.

**Immediate Action:**

1. **Verify in code:**
   - Check `memory_mcp_server_http.py:59-79` - `build_filter()` ALWAYS includes user filter
   - Check line 413 - user from auth token stored with every memory

2. **Check logs:**
   ```bash
   # Verify user context logged correctly
   docker logs <container-id> | grep "Request authenticated for user"
   ```

3. **If confirmed:** This is a security issue - report immediately and shut down server until fixed.

---

## Performance Issues

### Issue: Slow response times

**Symptoms:**
- Tool calls taking >5 seconds
- Timeouts on large retrievals

**Solutions:**

1. **Check Qdrant performance:**
   - Vector search should be <100ms for most queries
   - Check Qdrant collection size:
     ```python
     # In Python shell on server
     from qdrant_client import QdrantClient
     qdrant = QdrantClient(path="/path/to/data/qdrant")
     info = qdrant.get_collection("memories")
     print(f"Point count: {info.points_count}")
     ```

2. **Reduce `limit` parameter:**
   - `retrieve_context(limit=10)` - fewer results = faster
   - Default is 10, consider reducing for large collections

3. **Check network latency:**
   - Test from client location to server
   - Consider Cloudflare proxy (future work)

---

## Environment Variable Issues

### Issue: "AUTH0_DOMAIN not set" or similar errors

**Symptoms:**
- Server fails to start
- Error: `RuntimeError: AUTH0_DOMAIN and AUTH0_API_AUDIENCE must be set`

**Solutions:**

1. **Verify environment variables in Docker:**
   ```bash
   docker inspect <container-id> | grep -A 10 Env
   # Should show: AUTH0_DOMAIN, AUTH0_API_AUDIENCE
   ```

2. **Check container startup:**
   ```bash
   docker logs <container-id> | head -20
   # Look for: "Loaded Auth0 metadata from https://..."
   ```

3. **Restart with correct env vars:**
   ```bash
   docker stop <container-id>
   docker rm <container-id>
   # Run with correct -e flags
   docker run -d -e AUTH0_DOMAIN=... -e AUTH0_API_AUDIENCE=... ...
   ```

---

## Debugging Tips

### Enable verbose logging

Edit `memory_mcp_server_http.py` line 39:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Test OAuth discovery endpoints

```bash
# OAuth authorization server metadata
curl https://your-domain.com/.well-known/oauth-authorization-server | jq

# OpenID configuration
curl https://your-domain.com/.well-known/openid-configuration | jq

# Protected resource metadata (RFC 9728)
curl https://your-domain.com/.well-known/oauth-protected-resource | jq
```

### Test bearer token manually

```bash
# Get token from Auth0 (machine-to-machine)
TOKEN=$(curl -s --request POST \
  --url https://your-tenant.us.auth0.com/oauth/token \
  --header 'content-type: application/json' \
  --data '{
    "client_id":"YOUR_CLIENT_ID",
    "client_secret":"YOUR_CLIENT_SECRET",
    "audience":"https://your-domain.com",
    "grant_type":"client_credentials"
  }' | jq -r '.access_token')

# Test MCP endpoint
curl -X POST https://your-domain.com/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' | jq
```

---

## Getting Help

If issues persist:

1. **Check server logs:**
   ```bash
   docker logs --tail=100 <container-id>
   ```

2. **Verify Auth0 logs:**
   - Go to Auth0 Dashboard → Monitoring → Logs
   - Look for failed authentication attempts

3. **Test with MCP Inspector:**
   - Use official MCP debugging tools
   - Verify protocol compliance

4. **Open GitHub issue:**
   - Include: error messages, logs (redact sensitive info), steps to reproduce
   - [Repository URL here]
