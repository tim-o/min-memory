# OAuth Implementation Plan - Auth0 Integration

**Objective:** Transform the current MCP memory server from static bearer tokens to full OAuth 2.1 compliance using Auth0, enabling Claude Code remote MCP authentication.

**Timeline:** 1-2 days
**Outcome:** Production-ready MCP server with OAuth authentication at `memory.yoursite.com`

---

## ✅ IMPLEMENTATION COMPLETE - 2025-10-11

**Status:** Phases 1-4 successfully completed and deployed to production.

**Deployed Configuration:**
- **Domain:** `your-domain.com`
- **Auth0 Tenant:** `your-tenant.us.auth0.com`
- **API Audience:** `https://your-domain.com`
- **Registry:** `us-central1-docker.pkg.dev/$GCP_PROJECT_ID/mcp-memory/server:latest`

**Verification Results:**
```bash
# Health check shows OAuth status
curl https://your-domain.com/health
{"status":"ok","service":"mcp-memory-server-http","auth":"oauth2","auth_provider":"your-tenant.us.auth0.com"}

# OAuth metadata points to Auth0
curl https://your-domain.com/.well-known/oauth-authorization-server
{"issuer":"https://your-tenant.us.auth0.com/","authorization_endpoint":"https://your-tenant.us.auth0.com/authorize",...}

# Auth0 JWT tokens validate successfully
# MCP endpoint accepts Auth0 tokens (authentication passes)
```

**Key Achievements:**
- ✅ Valid TLS certificate from Let's Encrypt
- ✅ Auth0 OAuth 2.1 integration complete
- ✅ JWT validation with RS256 signatures
- ✅ JWKS caching for performance
- ✅ Dynamic Client Registration (DCR) enabled
- ✅ Backward compatibility with static tokens maintained
- ✅ User isolation working with Auth0 `sub` claims

**Deployment Challenges Resolved:**
1. Docker cache issue - forced rebuild with `--no-cache`
2. Registry mismatch - GCR vs Artifact Registry (resolved to Artifact Registry)
3. Cloudflare proxy interference - disabled proxy (DNS-only mode)
4. Trailing slash in audience - removed for consistency

**Next Steps:** See NEXT_STEPS.md for Claude Code integration testing

---

## Prerequisites

- [ ] GCP VM already deployed and running
- [ ] Domain name you control (yoursite.com)
- [ ] Access to domain DNS settings
- [ ] Auth0 account (free tier)

---

## Phase 1: DNS and TLS Setup (YOU - 30 minutes)

### Step 1.1: Create DNS Subdomain (10 min)

**Action:** Add DNS A record for subdomain

1. **Get your GCP VM external IP:**
   ```bash
   gcloud compute instances describe mcp-memory-server \
     --zone=us-central1-a \
     --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
   ```

   Expected output: `35.x.x.x` (your static IP)

2. **Log into your domain registrar** (GoDaddy/Namecheap/Cloudflare/etc.)

3. **Add DNS A Record:**
   - **Type:** `A`
   - **Name:** `memory` (or `mcp-memory` if you prefer)
   - **Value:** `35.x.x.x` (your GCP IP from step 1)
   - **TTL:** `300` (5 minutes for faster propagation)

4. **Verify DNS propagation** (wait 5-15 minutes):
   ```bash
   # Run this locally until it returns your GCP IP
   dig memory.yoursite.com +short
   # Should return: 35.x.x.x

   # Or use online tool: https://dnschecker.org
   ```

**Output:** `memory.yoursite.com` → `35.x.x.x`

---

### Step 1.2: Update Caddy for Let's Encrypt (10 min)

**Action:** Replace self-signed certs with Let's Encrypt

1. **SSH into GCP VM:**
   ```bash
   gcloud compute ssh mcp-memory-server --zone=us-central1-a
   ```

2. **Update Caddyfile** for domain-based HTTPS:
   ```bash
   # Create new Caddyfile
   sudo mkdir -p /mnt/stateful_partition/caddy
   sudo tee /mnt/stateful_partition/caddy/Caddyfile > /dev/null <<'EOF'
   memory.yoursite.com {
     reverse_proxy localhost:8080 {
       header_up Accept "application/json, text/event-stream"
     }
   }
   EOF
   ```

3. **Restart Caddy** with new config:
   ```bash
   docker rm -f caddy

   docker run -d \
     --name caddy \
     --restart=always \
     --network=host \
     -v /mnt/stateful_partition/caddy/Caddyfile:/etc/caddy/Caddyfile \
     -v /mnt/stateful_partition/caddy/data:/data \
     -v /mnt/stateful_partition/caddy/config:/config \
     caddy:2-alpine
   ```

4. **Verify Let's Encrypt certificate** (takes ~30 seconds):
   ```bash
   # Check Caddy logs
   docker logs caddy
   # Should see: "certificate obtained successfully"

   # Test HTTPS locally on VM
   curl https://memory.yoursite.com/health
   # Should return: {"status":"ok","service":"mcp-memory-server-http"}
   ```

5. **Test from your local machine:**
   ```bash
   curl https://memory.yoursite.com/health
   # Should return: {"status":"ok",...} with valid cert (no warnings)
   ```

**Output:** Valid HTTPS certificate from Let's Encrypt

---

### Step 1.3: Update Startup Script for Persistence (5 min)

**Action:** Ensure Caddy config survives VM reboots

1. **Still SSH'd into VM, update startup script:**
   ```bash
   sudo tee /mnt/stateful_partition/startup-script.sh > /dev/null <<'EOF'
   #!/bin/bash
   # GCE startup script - runs on every boot

   # Wait for docker to be ready
   while ! docker info >/dev/null 2>&1; do
     echo "Waiting for docker..."
     sleep 2
   done

   # Create Caddyfile if it doesn't exist
   mkdir -p /mnt/stateful_partition/caddy
   if [ ! -f /mnt/stateful_partition/caddy/Caddyfile ]; then
     cat > /mnt/stateful_partition/caddy/Caddyfile <<'CADDY'
   memory.yoursite.com {
     reverse_proxy localhost:8080 {
       header_up Accept "application/json, text/event-stream"
     }
   }
   CADDY
   fi

   # Check if caddy container exists
   if docker ps -a --format '{{.Names}}' | grep -q '^caddy$'; then
     docker restart caddy
   else
     docker run -d \
       --name caddy \
       --restart=always \
       --network=host \
       -v /mnt/stateful_partition/caddy/Caddyfile:/etc/caddy/Caddyfile \
       -v /mnt/stateful_partition/caddy/data:/data \
       -v /mnt/stateful_partition/caddy/config:/config \
       caddy:2-alpine
   fi

   echo "Startup script complete"
   EOF

   chmod +x /mnt/stateful_partition/startup-script.sh
   ```

2. **Configure VM to run startup script on boot:**
   ```bash
   exit  # Exit SSH

   # From your local machine:
   gcloud compute instances add-metadata mcp-memory-server \
     --zone=us-central1-a \
     --metadata-from-file=startup-script=/dev/stdin <<'EOF'
   #!/bin/bash
   /mnt/stateful_partition/startup-script.sh
   EOF
   ```

3. **Test reboot persistence:**
   ```bash
   gcloud compute instances reset mcp-memory-server --zone=us-central1-a

   # Wait 60 seconds, then verify
   sleep 60
   curl https://memory.yoursite.com/health
   ```

**Output:** Caddy automatically starts with Let's Encrypt on every boot

---

### Step 1.4: Verify Phase 1 Complete (5 min)

**Checklist:**
- [ ] `dig memory.yoursite.com` returns your GCP IP
- [ ] `curl https://memory.yoursite.com/health` returns 200 OK with valid cert
- [ ] No browser SSL warnings when visiting https://memory.yoursite.com/health
- [ ] Certificate is from Let's Encrypt (not "Caddy Local Authority")
- [ ] Survives VM reboot

**If any fail, troubleshoot before proceeding to Phase 2**

---

## Phase 2: Auth0 Setup (YOU - 30 minutes)

### Step 2.1: Create Auth0 Account (5 min)

1. **Sign up:** https://auth0.com/signup
   - Use your email
   - Free tier (no credit card required)
   - Choose region closest to you (e.g., US)

2. **Create Tenant:**
   - Tenant name: `mcp-memory` (or similar)
   - This becomes: `mcp-memory.us.auth0.com`
   - Save this URL: `https://mcp-memory.us.auth0.com/`

**Output:** Auth0 tenant URL

---

### Step 2.2: Configure Auth0 API (10 min)

**Action:** Register your MCP server as an Auth0 API

1. **Navigate to:** Applications → APIs → Create API

2. **Create API:**
   - **Name:** `MCP Memory Server`
   - **Identifier:** `https://memory.yoursite.com/` (your MCP server URL)
   - **Signing Algorithm:** `RS256`
   - Click **Create**

3. **Configure API Settings:**
   - Go to: APIs → MCP Memory Server → Settings
   - **RBAC Settings:**
     - ✅ Enable RBAC
     - ✅ Add Permissions in the Access Token
   - **Token Settings:**
     - Token Expiration: `86400` (24 hours)
     - Token Expiration For Browser Flows: `7200` (2 hours)
   - Click **Save**

4. **Save these values** (you'll need them later):
   ```bash
   # Save to local file for reference
   cat > ~/auth0-config.txt <<EOF
   AUTH0_DOMAIN=mcp-memory.us.auth0.com
   AUTH0_API_AUDIENCE=https://memory.yoursite.com/
   AUTH0_API_IDENTIFIER=https://memory.yoursite.com/
   EOF
   ```

**Output:** Auth0 API configured

---

### Step 2.3: Enable Dynamic Client Registration (DCR) (5 min)

**Action:** Allow Claude Code to auto-register as a client

1. **Navigate to:** Applications → APIs → MCP Memory Server → Settings

2. **Scroll to "Third Party Applications":**
   - Toggle **"Allow Third-Party Applications"** → ON

3. **Navigate to:** Applications → Applications → Create Application

4. **Create Machine-to-Machine App (for testing):**
   - **Name:** `MCP Test Client`
   - **Type:** Machine to Machine Applications
   - **Authorize:** Select "MCP Memory Server" API
   - **Permissions:** Select all (or leave default)
   - Click **Create**

5. **Get Test Credentials:**
   - Go to: Applications → MCP Test Client → Settings
   - **Save these values:**
     ```bash
     # Append to auth0-config.txt
     cat >> ~/auth0-config.txt <<EOF
     TEST_CLIENT_ID=<copy from "Client ID">
     TEST_CLIENT_SECRET=<copy from "Client Secret">
     EOF
     ```

**Output:** DCR enabled + test credentials

---

### Step 2.4: Configure CORS and Allowed Callbacks (5 min)

**Action:** Allow Claude Code to complete OAuth flows

1. **Navigate to:** Applications → Applications → Default App (or create new)

2. **Configure Application URIs:**
   - **Allowed Callback URLs:**
     ```
     https://claude.ai/api/mcp/auth_callback
     http://localhost:*/callback
     ```
   - **Allowed Logout URLs:**
     ```
     https://claude.ai
     http://localhost
     ```
   - **Allowed Web Origins:**
     ```
     https://memory.yoursite.com
     https://claude.ai
     http://localhost
     ```
   - **Allowed Origins (CORS):**
     ```
     https://memory.yoursite.com
     https://claude.ai
     http://localhost
     ```

3. **Click Save**

**Output:** CORS and callbacks configured

---

### Step 2.5: Get Auth0 Public Keys (5 min)

**Action:** Download JWKS for token validation

1. **Get JWKS URL:**
   ```
   https://mcp-memory.us.auth0.com/.well-known/jwks.json
   ```

2. **Verify it works:**
   ```bash
   curl https://mcp-memory.us.auth0.com/.well-known/jwks.json
   # Should return JSON with public keys
   ```

3. **Get OpenID Configuration:**
   ```bash
   curl https://mcp-memory.us.auth0.com/.well-known/openid-configuration
   # Should return full OAuth metadata
   ```

4. **Verify Discovery Endpoint:**
   ```bash
   curl https://mcp-memory.us.auth0.com/.well-known/oauth-authorization-server
   # Should return OAuth 2.0 metadata
   ```

**Output:** Auth0 is fully configured and discoverable

---

### Step 2.6: Verify Phase 2 Complete

**Checklist:**
- [ ] Auth0 tenant created (`mcp-memory.us.auth0.com`)
- [ ] API registered with audience `https://memory.yoursite.com/`
- [ ] DCR enabled for third-party apps
- [ ] Test M2M credentials saved
- [ ] JWKS endpoint returns public keys
- [ ] Callback URLs configured

**Save all credentials from ~/auth0-config.txt - you'll need them next**

---

## Phase 3: Update MCP Server Code (ASSISTANT - 2 hours)

### Step 3.1: Add Dependencies

**Action:** Update `requirements.txt`

**Changes needed:**
```diff
# requirements.txt
+ python-jose[cryptography]==3.3.0  # JWT validation
+ requests==2.31.0                   # Fetch JWKS
```

**File:** `requirements.txt`

---

### Step 3.2: Update OAuth Metadata Endpoints

**Action:** Point to Auth0 instead of self

**Changes needed in `memory_mcp_server_http.py`:**

```python
# Replace build_oauth_metadata() (lines 109-121)
def build_oauth_metadata(base_url: str) -> dict:
    """Return Auth0 OAuth metadata"""
    auth0_domain = os.getenv("AUTH0_DOMAIN", "mcp-memory.us.auth0.com")
    return {
        "issuer": f"https://{auth0_domain}/",
        "authorization_endpoint": f"https://{auth0_domain}/authorize",
        "token_endpoint": f"https://{auth0_domain}/oauth/token",
        "registration_endpoint": f"https://{auth0_domain}/oidc/register",
        "jwks_uri": f"https://{auth0_domain}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
    }

# Replace build_protected_resource_metadata() (lines 131-138)
def build_protected_resource_metadata(base_url: str) -> dict:
    """Return MCP resource server metadata pointing to Auth0"""
    auth0_domain = os.getenv("AUTH0_DOMAIN", "mcp-memory.us.auth0.com")
    return {
        "resource": f"{base_url}/",
        "authorization_servers": [f"https://{auth0_domain}/"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["openid", "profile", "email"],
    }
```

**Files:** `memory_mcp_server_http.py`
**Lines:** 109-138

---

### Step 3.3: Implement JWT Token Validation

**Action:** Replace static token lookup with Auth0 JWT validation

**Add new imports (top of file):**
```python
from jose import jwt, jwk
from jose.exceptions import JWTError
import requests
from functools import lru_cache
```

**Add JWKS fetching function (after imports):**
```python
@lru_cache(maxsize=1)
def get_jwks():
    """Fetch and cache Auth0 JWKS (public keys)"""
    auth0_domain = os.getenv("AUTH0_DOMAIN", "mcp-memory.us.auth0.com")
    jwks_url = f"https://{auth0_domain}/.well-known/jwks.json"

    try:
        response = requests.get(jwks_url, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Failed to fetch JWKS: {e}")
        return {"keys": []}

def validate_auth0_token(token: str) -> str:
    """Validate Auth0 JWT and return user identifier"""
    auth0_domain = os.getenv("AUTH0_DOMAIN", "mcp-memory.us.auth0.com")
    api_audience = os.getenv("AUTH0_API_AUDIENCE", "https://memory.yoursite.com/")

    try:
        # Get JWKS
        jwks = get_jwks()

        # Decode header to get kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        # Find matching key
        rsa_key = None
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"]
                }
                break

        if not rsa_key:
            raise ValueError("Unable to find appropriate key")

        # Validate token
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=api_audience,
            issuer=f"https://{auth0_domain}/"
        )

        # Extract user identifier (sub = subject)
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Token missing 'sub' claim")

        # Auth0 sub format: "auth0|<id>" or "google-oauth2|<id>"
        # Use full sub as user identifier for multi-tenant support
        return user_id

    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise ValueError(f"Invalid token: {e}")
    except Exception as e:
        logger.error(f"Token validation error: {e}")
        raise ValueError(f"Token validation failed: {e}")
```

**Files:** `memory_mcp_server_http.py`
**Lines:** Add after line 56

---

### Step 3.4: Update Authentication Middleware

**Action:** Use JWT validation instead of static tokens

**Replace AuthMiddleware.dispatch() method (lines 736-809):**
```python
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # Skip auth for health check and OAuth discovery endpoints
        if path == "/health":
            return await call_next(request)

        if ".well-known/oauth-authorization-server" in path:
            base_url = get_base_url(request)
            return JSONResponse(build_oauth_metadata(base_url))

        if ".well-known/openid-configuration" in path:
            base_url = get_base_url(request)
            return JSONResponse(build_openid_configuration(base_url))

        if ".well-known/oauth-protected-resource" in path:
            base_url = get_base_url(request)
            return JSONResponse(build_protected_resource_metadata(base_url))

        # Remove /register endpoint (Auth0 handles DCR)
        if path == "/register":
            # Redirect to Auth0 DCR
            auth0_domain = os.getenv("AUTH0_DOMAIN", "mcp-memory.us.auth0.com")
            return JSONResponse({
                "error": "use_auth0_dcr",
                "message": "Use Auth0 Dynamic Client Registration",
                "registration_endpoint": f"https://{auth0_domain}/oidc/register"
            }, status_code=400)

        # Remove /oauth/token endpoint (Auth0 handles this)
        if path == "/oauth/token":
            auth0_domain = os.getenv("AUTH0_DOMAIN", "mcp-memory.us.auth0.com")
            return JSONResponse({
                "error": "use_auth0",
                "message": "Token endpoint handled by Auth0",
                "token_endpoint": f"https://{auth0_domain}/oauth/token"
            }, status_code=400)

        # Extract bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return Response(
                "Unauthorized: Missing or invalid Authorization header",
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="MCP Memory Server"'}
            )

        token = auth_header[7:]  # Remove "Bearer " prefix

        # Validate token (try Auth0 JWT first, fallback to static tokens for testing)
        user = None
        try:
            user = validate_auth0_token(token)
            logger.info(f"Authenticated Auth0 user: {user}")
        except ValueError as e:
            # Fallback to static tokens (for testing only)
            if token in USER_TOKENS:
                user = USER_TOKENS[token]
                logger.info(f"Authenticated static token user: {user}")
            else:
                logger.warning(f"Token validation failed: {e}")
                return Response(
                    f"Unauthorized: {e}",
                    status_code=401,
                    headers={"WWW-Authenticate": 'Bearer realm="MCP Memory Server"'}
                )

        if not user:
            return Response(
                "Unauthorized: Invalid token",
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="MCP Memory Server"'}
            )

        # Set current user in context
        token_var = current_user_var.set(user)
        logger.info(f"Request authenticated for user: {user}")

        try:
            response = await call_next(request)
        finally:
            current_user_var.reset(token_var)

        return response
```

**Files:** `memory_mcp_server_http.py`
**Lines:** 735-809 (replace entire class method)

---

### Step 3.5: Update Environment Variables

**Action:** Add Auth0 configuration to deployment

**Update Dockerfile to accept new env vars:**
```diff
# Dockerfile (no changes needed, env vars passed at runtime)
```

**Update container environment variables:**
```bash
# On GCP VM, update container with new env vars
gcloud compute ssh mcp-memory-server --zone=us-central1-a

# Update container with Auth0 config
docker stop $(docker ps -q --filter ancestor=gcr.io/$PROJECT_ID/mcp-memory:latest)

# Set env vars (replace with your values from ~/auth0-config.txt)
export AUTH0_DOMAIN="mcp-memory.us.auth0.com"
export AUTH0_API_AUDIENCE="https://memory.yoursite.com/"
export TIM_TOKEN="<your-existing-token>"

# Restart container with new env vars
# (Will be automated in deployment update)
```

**Files:** Deployment configuration
**Action:** Manual update (automated in Step 4.2)

---

### Step 3.6: Update Startup Script with Auth0 Env Vars

**Action:** Persist Auth0 config across reboots

**Add to container-config.yaml:**
```yaml
spec:
  containers:
  - name: mcp-memory
    image: gcr.io/$PROJECT_ID/mcp-memory:latest
    env:
    - name: AUTH0_DOMAIN
      value: "mcp-memory.us.auth0.com"
    - name: AUTH0_API_AUDIENCE
      value: "https://memory.yoursite.com/"
    - name: TIM_TOKEN
      value: "$TIM_TOKEN"
    - name: MCP_DATA_DIR
      value: /var/lib/data
    - name: PORT
      value: "8080"
    # ... rest unchanged
```

**Files:** `container-config.yaml` (for future deployments)

---

### Step 3.7: Code Review Checklist

**Assistant verifies:**
- [ ] JWT validation handles RS256 correctly
- [ ] JWKS caching works (LRU cache)
- [ ] Error handling for network failures (JWKS fetch)
- [ ] WWW-Authenticate header in 401 responses
- [ ] Backward compatibility with static tokens (testing)
- [ ] User ID extraction works with Auth0 `sub` format
- [ ] All OAuth metadata points to Auth0
- [ ] No hardcoded values (use env vars)

---

## Phase 4: Deploy and Test (BOTH - 1 hour)

### Step 4.1: Build and Push Updated Container (YOU - 10 min)

```bash
# From local machine, in /home/tim/github/min-memory

# Build new image with Auth0 integration
docker build -t gcr.io/$PROJECT_ID/mcp-memory:latest .

# Push to GCR
docker push gcr.io/$PROJECT_ID/mcp-memory:latest

# Verify image pushed
gcloud container images list-tags gcr.io/$PROJECT_ID/mcp-memory
```

---

### Step 4.2: Update GCP Instance (YOU - 10 min)

```bash
# Update instance metadata with Auth0 env vars
gcloud compute instances update-container mcp-memory-server \
  --zone=us-central1-a \
  --container-image=gcr.io/$PROJECT_ID/mcp-memory:latest \
  --container-env="\
AUTH0_DOMAIN=mcp-memory.us.auth0.com,\
AUTH0_API_AUDIENCE=https://memory.yoursite.com/,\
TIM_TOKEN=$TIM_TOKEN,\
MCP_DATA_DIR=/var/lib/data,\
PORT=8080"

# Wait for container to restart
sleep 30

# Verify container is running
gcloud compute ssh mcp-memory-server --zone=us-central1-a -- \
  "docker ps | grep mcp-memory"
```

---

### Step 4.3: Test OAuth Discovery (YOU - 5 min)

```bash
# Test OAuth metadata points to Auth0
curl https://memory.yoursite.com/.well-known/oauth-authorization-server | jq

# Should return Auth0 URLs:
# {
#   "issuer": "https://mcp-memory.us.auth0.com/",
#   "authorization_endpoint": "https://mcp-memory.us.auth0.com/authorize",
#   ...
# }

# Test resource metadata
curl https://memory.yoursite.com/.well-known/oauth-protected-resource | jq

# Should return:
# {
#   "resource": "https://memory.yoursite.com/",
#   "authorization_servers": ["https://mcp-memory.us.auth0.com/"],
#   ...
# }
```

---

### Step 4.4: Test Token Validation (YOU - 10 min)

**Test with M2M token from Auth0:**

```bash
# Get token from Auth0 (using test credentials from Phase 2.3)
TOKEN=$(curl -s --request POST \
  --url https://mcp-memory.us.auth0.com/oauth/token \
  --header 'content-type: application/json' \
  --data '{
    "client_id":"<TEST_CLIENT_ID>",
    "client_secret":"<TEST_CLIENT_SECRET>",
    "audience":"https://memory.yoursite.com/",
    "grant_type":"client_credentials"
  }' | jq -r '.access_token')

echo "Token: $TOKEN"

# Test MCP endpoint with Auth0 token
curl -X POST https://memory.yoursite.com/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/list",
    "id": 1
  }' | jq

# Should return list of MCP tools (success!)
```

---

### Step 4.5: Test with Claude Code (YOU - 15 min)

**Configure Claude Code to use OAuth:**

1. **Update MCP config** (`~/.config/claude-code/mcp_config.json`):
   ```json
   {
     "mcpServers": {
       "memory": {
         "url": "https://memory.yoursite.com",
         "transport": "http"
       }
     }
   }
   ```

2. **Add server via CLI:**
   ```bash
   claude mcp add --transport http memory https://memory.yoursite.com/mcp
   ```

3. **Authenticate:**
   ```bash
   claude mcp auth memory
   ```

   - Should open browser to Auth0 login
   - Complete OAuth flow
   - Returns to Claude Code with token

4. **Test MCP connection:**
   ```bash
   # In Claude Code
   /mcp
   # Should show: memory (connected)
   ```

5. **Test memory operation:**
   ```
   # In Claude Code conversation
   "Store a memory: My name is Tim and I prefer concise technical communication"
   ```

   - Should succeed with Auth0 token
   - Verify in logs: `docker logs <container>`

---

### Step 4.6: Monitor and Debug (BOTH - 10 min)

**Watch logs:**
```bash
# Real-time logs
gcloud compute ssh mcp-memory-server --zone=us-central1-a -- \
  "docker logs -f \$(docker ps -q --filter ancestor=gcr.io/$PROJECT_ID/mcp-memory:latest)"

# Look for:
# - "Authenticated Auth0 user: auth0|..."
# - JWT validation success/failure
# - JWKS fetch operations
```

**Debug checklist:**
- [ ] HTTPS working (Let's Encrypt cert valid)
- [ ] OAuth discovery returns Auth0 URLs
- [ ] M2M token validates successfully
- [ ] Claude Code can authenticate
- [ ] MCP tools accessible with Auth0 token
- [ ] User isolation working (check sub claim)

---

## Phase 5: Documentation and Cleanup (ASSISTANT - 30 min)

### Step 5.1: Update Documentation

**Files to update:**
- [ ] `README.md` - Add Auth0 setup instructions
- [ ] `DEPLOYMENT_RUNBOOK.md` - Update with Auth0 steps
- [ ] `CLAUDE_CODE_SETUP.md` - OAuth flow instead of bearer tokens
- [ ] `HTTP_DEPLOYMENT.md` - Auth0 configuration

---

### Step 5.2: Remove Legacy Code

**Remove static token authentication:**
```python
# Remove or comment out USER_TOKENS dict (line 42-45)
# Keep for emergency fallback or remove entirely
```

**Update health check to show auth status:**
```python
async def health_check(request: Request):
    auth0_domain = os.getenv("AUTH0_DOMAIN", "not-configured")
    return Response(json.dumps({
        "status": "ok",
        "service": "mcp-memory-server-http",
        "auth": "oauth2",
        "auth_provider": auth0_domain
    }), media_type="application/json")
```

---

### Step 5.3: Create Quick Start Guide

**File:** `QUICKSTART_OAUTH.md`

**Contents:**
- DNS setup (1 step)
- Auth0 setup (3 steps)
- Claude Code connection (2 steps)
- Troubleshooting (common issues)

---

## Phase 6: Validation and Rollout (YOU - 30 min)

### Step 6.1: End-to-End Test

**Full OAuth flow test:**

1. **Clear Claude Code credentials:**
   ```bash
   claude mcp remove memory
   ```

2. **Re-add with OAuth:**
   ```bash
   claude mcp add --transport http memory https://memory.yoursite.com/mcp
   claude mcp auth memory
   ```

3. **Complete OAuth flow in browser:**
   - Login to Auth0
   - Consent to permissions
   - Return to Claude Code

4. **Use MCP tools:**
   ```
   # In Claude Code
   "List all entities I've stored"
   "Store a new memory about my project preferences"
   "Retrieve context about my coding style"
   ```

5. **Verify multi-user isolation:**
   - Create second Auth0 user (or use different social login)
   - Authenticate with second user
   - Verify separate memory spaces

---

### Step 6.2: Performance Validation

**Benchmark token validation:**
```bash
# Test token validation performance
time curl -X POST https://memory.yoursite.com/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Should be < 200ms (JWKS cached)
```

**Test JWKS caching:**
```bash
# First request (fetches JWKS)
time curl ...

# Second request (cached)
time curl ...

# Should be faster (no network call to Auth0)
```

---

### Step 6.3: Security Validation

**Security checklist:**
- [ ] Tokens expire (check `exp` claim)
- [ ] Invalid tokens rejected (test with modified token)
- [ ] Audience validation works (test with wrong audience)
- [ ] Issuer validation works (test with different issuer)
- [ ] HTTPS enforced (http:// redirects to https://)
- [ ] User isolation verified (different subs = different data)

---

## Success Criteria

**Phase 1 Complete:**
- ✅ `memory.yoursite.com` resolves to GCP IP
- ✅ Valid Let's Encrypt certificate
- ✅ HTTPS working without warnings

**Phase 2 Complete:**
- ✅ Auth0 tenant configured
- ✅ API registered with correct audience
- ✅ DCR enabled
- ✅ JWKS endpoint accessible

**Phase 3 Complete:**
- ✅ JWT validation code implemented
- ✅ OAuth metadata points to Auth0
- ✅ Token validation working
- ✅ Code reviewed and tested

**Phase 4 Complete:**
- ✅ Updated container deployed
- ✅ M2M token validates
- ✅ Claude Code connects via OAuth
- ✅ MCP tools accessible

**Phase 5 Complete:**
- ✅ Documentation updated
- ✅ Legacy code removed
- ✅ Quick start guide created

**Phase 6 Complete:**
- ✅ End-to-end OAuth flow works
- ✅ Performance acceptable (< 200ms)
- ✅ Security validated

---

## Rollback Plan

**If OAuth fails, revert to static tokens:**

1. **Restore previous container:**
   ```bash
   gcloud compute ssh mcp-memory-server --zone=us-central1-a

   # Find previous image
   docker images | grep mcp-memory

   # Revert to previous version (get image ID from above)
   docker stop $(docker ps -q)
   docker run -d --restart=always ... <previous-image-id>
   ```

2. **Revert Caddy config:**
   ```bash
   # Use IP-based self-signed certs
   cat > /mnt/stateful_partition/caddy/Caddyfile <<'EOF'
   :443 {
     tls internal
     reverse_proxy localhost:8080
   }
   EOF
   docker restart caddy
   ```

3. **Update Claude Code config:**
   ```json
   {
     "mcpServers": {
       "memory": {
         "url": "https://<static-ip>",
         "transport": "http",
         "headers": {
           "Authorization": "Bearer <TIM_TOKEN>"
         }
       }
     }
   }
   ```

**Estimated rollback time:** 10 minutes

---

## Timeline Summary

| Phase | Owner | Time | Cumulative |
|-------|-------|------|------------|
| 1. DNS & TLS | YOU | 30 min | 30 min |
| 2. Auth0 Setup | YOU | 30 min | 1 hour |
| 3. Code Updates | ASSISTANT | 2 hours | 3 hours |
| 4. Deploy & Test | BOTH | 1 hour | 4 hours |
| 5. Documentation | ASSISTANT | 30 min | 4.5 hours |
| 6. Validation | YOU | 30 min | 5 hours |

**Total: ~5 hours (spread over 1-2 days)**

---

## Next Steps

1. **YOU:** Complete Phase 1 (DNS & TLS) - 30 min
2. **YOU:** Complete Phase 2 (Auth0) - 30 min
3. **Report back:** Share Auth0 credentials (domain, audience)
4. **ASSISTANT:** Implement Phase 3 (code updates)
5. **BOTH:** Deploy and test (Phase 4)
6. **Success!** 🎉

---

## Support Resources

**Auth0 Documentation:**
- API Setup: https://auth0.com/docs/get-started/apis
- DCR: https://auth0.com/docs/api/management/v2#!/Client_Grants
- JWKS: https://auth0.com/docs/secure/tokens/json-web-tokens/json-web-key-sets

**MCP Specification:**
- Authorization: https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- Resource Servers: RFC 9728

**Troubleshooting:**
- Let's Encrypt: https://caddyserver.com/docs/automatic-https
- Auth0 Logs: Dashboard → Monitoring → Logs
- GCP Logs: Cloud Console → Logging

**Questions?** Document issues in `TROUBLESHOOTING.md` as they arise.
