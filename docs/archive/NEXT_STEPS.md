# Next Steps – MCPAuth Alignment

**Last updated:** 2025-10-12  
**Status:** Reopened – bearer-token approach failed Codex handshake

---

## 1. Settle on the authentication model (Blocking)
- **Decision:** Do we let MCPAuth issue first-party sessions (recommended) or keep Auth0 as the primary issuer and plug it into `authenticate_user`?
- **Owner:** Tim  
- **Deliverable:** short design note posted in this repo describing the chosen flow.

## 2. Prototype MCPAuth session enforcement (High)
- Remove the `bearer_auth_middleware` guard from `memory_mcp_server_http.py`.
- Add middleware that calls the MCPAuth session helper and stores `request.state.user`.
- Update tool handlers to read from the per-request user context.
- **Verification:** local unit/integration test asserting that a request with a valid MCPAuth session proceeds, while one without receives a 401 that includes `resource_metadata`.

## 3. Adjust transports if needed (Medium)
- Confirm `FastApiHttpSessionManager` can access the user context. If not, port the Streamable HTTP transport pattern from the MCPAuth Express example.
- **Deliverable:** note in code or docs describing which approach we adopted and why.

## 4. End-to-end testing with Codex (Critical)
- Run the Codex CLI against the staging server.
- Validate the OAuth browser loop succeeds, `initialize` completes, and tools operate under the authenticated user.
- Capture logs to confirm the MCPAuth session is populated rather than blocking on bearer tokens.

## 5. Update documentation (Medium)
- Revise `README.md`, deployment notes, and connector instructions to describe the new flow.
- Document any remaining Auth0 integration details if we keep it in the stack.

## 6. Clean up legacy paths (Low, post-E2E)
- Remove static bearer token fallbacks and unused Auth0 JWKS helpers.
- Drop unused environment variables once the new flow is stable.

---

Please raise any blockers (e.g., required MCPAuth features missing in the Python package) before starting implementation.***
