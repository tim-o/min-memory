# MCPAuth Migration Plan

**Last updated:** 2025-10-12  
**Owner:** Tim O’Brien  
**Status:** Draft – revisions required before implementation

---

## Context

We attempted to “migrate to MCPAuth” by wrapping our Starlette app with `mcp_auth.bearer_auth_middleware("jwt", audience=AUTH0_API_AUDIENCE)`. In practice that keeps Auth0 as the authorization server and treats MCPAuth purely as a JWT validator. Codex (and any MCP client that follows the MCP OAuth profile) expects MCPAuth to run the full authorization flow on the MCP host, issue a first‑party session, and let the JSON-RPC transport resume without a bearer header. That mismatch is why Codex fails while Claude can be coaxed into working only with a manually supplied Auth0 token.

This document replaces the earlier (incorrect) plan that proposed “use mcpauth to validate Auth0 JWTs.” The new plan aligns with the reference Express/Hono integrations published by the MCPAuth project.

---

## Findings

- **Current wiring (`memory_mcp_server_http.py:825-959`)** forces every `/mcp`, `/messages`, and `/sse` request through the `bearer_auth_middleware`, rejecting anything without an Auth0 JWT that matches `AUTH0_API_AUDIENCE`.
- **MCPAuth session is never consulted.** `get_current_user()` reads `mcp_auth.auth_info`, but `auth_info` is populated only when MCPAuth’s own session middleware runs. Because the bearer middleware blocks requests before that happens, `auth_info` remains `None`.
- **OAuth metadata points at Auth0 (`lines 142-229`).** We proxy dynamic client registration, advertise Auth0’s issuer, and never expose a callback/authorize route on `your-domain.com`. The MCP client therefore completes login with Auth0, returns with an MCPAuth cookie, but our server ignores it and still demands a bearer token.
- **Codex failure mode.** Codex opens the Auth0 login page as directed by MCPAuth, then retries the JSON-RPC `initialize` call without any Authorization header (per MCPAuth’s expectations). The middleware responds `401 Auth required`, producing the `Auth required` error we observed.
- **Claude “success.”** Claude’s UI allows pasting a raw bearer token; when we paste an Auth0 API token, the middleware accepts it. That path bypasses MCPAuth entirely and is not standards compliant.

---

## Recommended Migration

### 1. Let MCPAuth act as the authorization server
- Configure `MCPAuth` with `issuer_url=https://your-domain.com` (or the deployed origin) and register its Starlette routes (`app.mount("/oauth", mcp_auth.app)` equivalent).
- Stop proxying `/authorize`, `/token`, `/callback`, etc., to Auth0. Instead, bridge Auth0 via MCPAuth’s `authenticate_user` hook if we still need Auth0 credentials (see deviations below).

### 2. Replace bearer middleware with session checks
- Remove `mcp_auth.bearer_auth_middleware(...)`.
- Add a Starlette middleware that calls `await mcp_auth.require_session(request)` (or equivalent helper) for `/mcp`, `/messages`, and SSE routes. On success, attach the session/user info to `request.state`.
- Update `get_current_user()` to read `request.state.user` (with proper fallback).

### 3. Advertise local OAuth metadata
- Serve `.well-known/oauth-protected-resource` and `.well-known/openid-configuration` pointing back to `your-domain.com`.
- Keep the RFC 9728 `WWW-Authenticate` hints but ensure they reference our own issuer URLs.

### 4. Transport alignment
- Confirm `FastApiHttpSessionManager` can work with request-scoped session data. If not, switch to the explicit `StreamableHTTPServerTransport` pattern used in the MCPAuth examples to tie session IDs to transports post-auth.

### 5. Decommission Auth0-only bearer flow
- Remove the static token fallback and the Auth0 audience gate once the MCPAuth session flow is live.

---

## Deviations / Open Questions

1. **Auth0 reuse:** If we must keep Auth0 for credential backing, MCPAuth needs a custom `authenticate_user` implementation that validates the Auth0 session (via cookie, token exchange, or management API) but still issues its own MCP session cookie. This requires additional design—please confirm whether full Auth0 deprecation is acceptable.
2. **Python MCPAuth capabilities:** The reference adapters are TypeScript. We need to confirm the Python package exposes session helpers comparable to `getMcpSession`. If not, we may need to port or wrap the TypeScript approach.
3. **Session storage:** MCPAuth defaults to in-memory stores; production deployment will require either Redis or database-backed session storage. Decide early to avoid accidental logouts on restart.

---

## Action Checklist

1. **Design decision:** choose between “MCPAuth as primary issuer” vs. “MCPAuth bridged to Auth0 via authenticate_user”. _Owner: Tim. Status: Pending._
2. **Spike:** prototype request middleware that resolves an MCPAuth session and exposes `request.state.user`. _Owner: engineering. Status: Pending._
3. **Transport audit:** verify `FastApiHttpSessionManager` behavior or plan to port the Streamable HTTP transport. _Owner: engineering. Status: Pending._
4. **Documentation:** update public and internal docs once design decisions land. _Owner: documentation. Status: Pending._

Please escalate any blockers (e.g., MCPAuth Python limitations, Auth0 contract constraints) before implementation.  

— End of plan —
