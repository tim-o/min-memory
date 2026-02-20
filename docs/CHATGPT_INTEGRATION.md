# ChatGPT Integration Plan

Plan for integrating the MCP Memory Server with ChatGPT.

**Status:** Research complete, implementation pending
**Last Updated:** 2025-10-12

---

## Executive Summary

ChatGPT supports MCP (Model Context Protocol) remote servers as of March 2025, following OpenAI's adoption of the standard. There are **two integration paths**:

1. **MCP Connectors** (Remote MCP Servers) - **RECOMMENDED**
   - Native MCP protocol support
   - Uses existing server implementation
   - OAuth 2.1 authentication (Auth0)
   - Minimal server changes required

2. **GPT Actions** (Custom Actions via OpenAPI)
   - Alternative approach using OpenAPI schema
   - Requires creating OpenAPI specification
   - OAuth 2.0 authentication
   - More work, less aligned with MCP standard

**Recommendation:** Pursue MCP Connectors path first. It aligns with the existing architecture and leverages OpenAI's native MCP support.

---

## Option 1: MCP Connectors (RECOMMENDED)

### Overview

ChatGPT (Pro, Team, and Enterprise users) can connect to remote MCP servers via the Connectors feature introduced in 2025.

### Prerequisites

- **ChatGPT Plan:** Pro (as of August 2025), Team, or Enterprise
- **Developer Mode:** Must be enabled in ChatGPT settings
- **OAuth 2.1 Server:** Already implemented (Auth0)
- **Remote MCP Server:** Already implemented (HTTP transport)

### Client Configuration

**User Steps:**

1. **Enable Developer Mode:**
   - Settings → Connectors → Advanced settings
   - Toggle "Developer Mode" to ON

2. **Add Connector:**
   - Click "Create" in Connectors section
   - **Name:** `memory` (or user's choice)
   - **URL:** `https://your-domain.com`
   - **Authentication:** Select `OAuth`

3. **Authenticate:**
   - Click "Connect"
   - Browser opens to Auth0 OAuth flow
   - Complete authentication
   - Redirects back to ChatGPT

4. **Use Memory Tools:**
   - MCP tools automatically available in ChatGPT sessions
   - ChatGPT discovers tools via MCP protocol
   - User interacts naturally: "Store this as a memory..." or "What do you remember about my preferences?"

### Server Requirements (Current State)

✅ **Already Implemented:**
- Remote HTTP MCP server (`/mcp` endpoint)
- OAuth 2.1 with Auth0 as authorization server
- JWT validation via MCPAuth
- RFC 9728 protected resource metadata
- Dynamic Client Registration (DCR) proxy to Auth0

❓ **Potentially Needed:**
- Verify ChatGPT callback URL whitelisted in Auth0
- Test OAuth flow end-to-end with ChatGPT

### Implementation Steps

#### Phase 1: Auth0 Configuration (30 minutes)

1. **Update Auth0 Callback URLs:**
   - Go to Auth0 Dashboard → Applications → [Your Application]
   - Add ChatGPT callback URL to "Allowed Callback URLs":
     - Format: `https://chat.openai.com/aip/[connector-id]/oauth/callback`
     - Or: Use wildcard `https://chat.openai.com/aip/*/oauth/callback` (if Auth0 supports)

2. **Verify Allowed Origins:**
   - Add to "Allowed Web Origins": `https://chat.openai.com`
   - Add to "Allowed Origins (CORS)": `https://chat.openai.com`

3. **Test DCR Endpoint:**
   ```bash
   curl -X POST https://your-domain.com/register \
     -H "Content-Type: application/json" \
     -d '{
       "client_name": "ChatGPT Test",
       "redirect_uris": ["https://chat.openai.com/aip/test/oauth/callback"]
     }'
   # Should return client_id and client_secret from Auth0
   ```

#### Phase 2: Server Verification (1 hour)

1. **Test OAuth Metadata Endpoints:**
   ```bash
   # Protected resource metadata
   curl https://your-domain.com/.well-known/oauth-protected-resource | jq

   # OpenID configuration
   curl https://your-domain.com/.well-known/openid-configuration | jq

   # Verify "authorization_servers" points to Auth0
   ```

2. **Test MCP Tools Discovery:**
   ```bash
   # Get Auth0 token
   TOKEN=$(curl -s --request POST \
     --url https://your-tenant.us.auth0.com/oauth/token \
     --header 'content-type: application/json' \
     --data '{
       "client_id":"YOUR_CLIENT_ID",
       "client_secret":"YOUR_CLIENT_SECRET",
       "audience":"https://your-domain.com",
       "grant_type":"client_credentials"
     }' | jq -r '.access_token')

   # Test MCP tools/list
   curl -X POST https://your-domain.com/mcp \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' | jq
   ```

3. **Monitor Server Logs:**
   ```bash
   # Watch for ChatGPT connection attempts
   docker logs -f <container-id> | grep -E "(ChatGPT|OpenAI|chat\.openai)"
   ```

#### Phase 3: ChatGPT Testing (1 hour)

1. **Add Connector in ChatGPT:**
   - Follow user configuration steps above
   - Document any errors or unexpected behavior

2. **Test OAuth Flow:**
   - Verify Auth0 login page displays correctly
   - Complete authentication
   - Verify redirect back to ChatGPT succeeds
   - Check for "Connected" status in Connectors

3. **Test MCP Tool Usage:**
   - Start ChatGPT conversation
   - Ask: "Store a memory: I prefer concise technical documentation"
   - Verify `store_memory` tool is called
   - Ask: "What do you know about my preferences?"
   - Verify `retrieve_context` tool is called and returns stored memory

4. **Verify User Isolation:**
   - Test with second ChatGPT account (or ask colleague)
   - Verify memories are NOT shared between users
   - Check server logs for different Auth0 `sub` claims

#### Phase 4: Documentation (30 minutes)

1. **Update README.md:**
   - Add ChatGPT to "Tested Clients" list
   - Update Quick Start with ChatGPT instructions

2. **Update TROUBLESHOOTING.md:**
   - Add ChatGPT-specific issues (callback URL problems, etc.)

3. **Create User Guide:**
   - Document ChatGPT setup process with screenshots
   - Provide example prompts for using memory tools

### Expected Challenges

1. **Callback URL Discovery:**
   - ChatGPT may generate dynamic callback URLs per connector
   - May need to use Auth0 wildcard or add multiple URLs
   - **Mitigation:** Test with real connector, document actual callback URL pattern

2. **OAuth Flow Compatibility:**
   - ChatGPT may have specific OAuth flow requirements
   - May need PKCE parameters (already supported by Auth0)
   - **Mitigation:** Monitor Auth0 logs during testing, adjust configuration

3. **MCP Protocol Version:**
   - ChatGPT may require specific MCP protocol version
   - Current server uses `mcp` Python library (version?)
   - **Mitigation:** Verify MCP version compatibility, upgrade if needed

4. **Rate Limiting:**
   - ChatGPT may make many rapid requests
   - No rate limiting currently implemented
   - **Mitigation:** Monitor usage, add rate limiting if abuse occurs

### Success Criteria

- ✅ ChatGPT can authenticate via Auth0 OAuth flow
- ✅ ChatGPT can discover MCP tools (`tools/list`)
- ✅ ChatGPT can call `store_memory` and `retrieve_context` successfully
- ✅ User isolation works (different ChatGPT users = different memories)
- ✅ OAuth tokens refresh properly (long sessions don't break)

---

## Option 2: GPT Actions (Alternative)

### Overview

GPT Actions allow custom ChatGPT integrations via OpenAPI schema. This predates MCP Connectors and is more widely available (including Free tier with API key auth).

### Prerequisites

- OpenAPI 3.0+ specification describing our API
- OAuth 2.0 authentication (Auth0 compatible)
- REST API endpoints (not MCP protocol)

### Why NOT Recommended

1. **Requires Reimplementation:**
   - Need to create REST API endpoints (duplicate MCP tools)
   - Need to write OpenAPI schema manually
   - More code to maintain

2. **Not Standards-Aligned:**
   - MCP is the emerging standard for AI context
   - GPT Actions are OpenAI-specific
   - Other AI assistants (Claude, etc.) use MCP, not OpenAPI Actions

3. **Less Flexible:**
   - OpenAPI actions are stateless REST calls
   - MCP supports stateful sessions, streaming, prompts, resources
   - Future MCP features not available via Actions

4. **More Work for Same Result:**
   - MCP Connectors provide same functionality with less effort
   - Only benefit: Works with ChatGPT Free (if using API key auth)

### When to Consider

- **ChatGPT Free Tier:** If you need to support ChatGPT Free users (no OAuth, API key only)
- **Existing REST API:** If you already have a non-MCP REST API
- **Broad Compatibility:** If you need to integrate with non-MCP clients and don't want to run two servers

### Implementation Effort

**Estimated:** 2-3 days

1. **Create REST API Endpoints** (1 day)
   - POST `/api/memories` - Store memory
   - GET `/api/memories/search?query=...` - Retrieve context
   - GET `/api/memories/entities` - List entities
   - etc.

2. **Write OpenAPI Schema** (1 day)
   - Define all endpoints, parameters, responses
   - Add OAuth 2.0 authentication configuration
   - Test with OpenAPI validator

3. **Configure GPT Action** (0.5 day)
   - Create Custom GPT
   - Add OpenAPI schema
   - Configure OAuth (Auth0)
   - Test end-to-end

4. **Maintenance** (ongoing)
   - Keep OpenAPI schema in sync with changes
   - Maintain both MCP and REST endpoints

**Recommendation:** Only pursue if MCP Connectors path fails or if specific requirement for ChatGPT Free support.

---

## Comparison Matrix

| Feature | MCP Connectors | GPT Actions |
|---------|----------------|-------------|
| **Effort to Implement** | Low (minimal changes) | High (new REST API) |
| **Standards Alignment** | High (MCP standard) | Low (OpenAI-specific) |
| **Code Reuse** | High (existing MCP server) | Low (duplicate logic) |
| **ChatGPT Free Support** | No (requires Pro+) | Yes (with API key) |
| **Future Compatibility** | High (MCP adoption growing) | Medium (OpenAI-specific) |
| **Maintenance Burden** | Low (one codebase) | High (two APIs) |
| **Feature Completeness** | Full MCP protocol | Limited to REST |
| **User Experience** | Native MCP integration | Custom action |

---

## Research Findings

### MCP Support in ChatGPT

From web research (October 2025):

- **March 2025:** OpenAI officially adopted MCP standard
- **August 2025:** MCP Connectors rolled out to Pro users
- **Current Status:** Supported in ChatGPT Desktop, Web, and (likely) mobile
- **Authentication:** OAuth 2.1 required for remote MCP servers
- **Developer Mode:** Required to create custom connectors

### Key Documentation

- **OpenAI MCP Docs:** `platform.openai.com/docs/mcp` (403 error when fetched, may be behind login)
- **Community Examples:** Multiple reports of successful MCP server connections to ChatGPT
- **Auth0 MCP Guide:** Auth0 published guide on securing MCP servers for ChatGPT

### Known Working Configurations

- **HubSpot:** First third-party CRM connector for ChatGPT using MCP (February 2025)
- **Community Servers:** Multiple community members report successful connections
- **Auth0 OAuth:** Confirmed working with Auth0 as authorization server

---

## Implementation Timeline

### Immediate (Week 1)

- [x] Research ChatGPT MCP support (completed)
- [ ] Update Auth0 callback URLs for ChatGPT
- [ ] Test OAuth metadata endpoints
- [ ] Test MCP tools discovery with bearer token

### Short-term (Week 2)

- [ ] Configure ChatGPT connector with test account
- [ ] Complete end-to-end OAuth flow
- [ ] Test basic memory operations (store, retrieve)
- [ ] Document any issues or required changes

### Medium-term (Week 3-4)

- [ ] Test with multiple users (verify isolation)
- [ ] Test edge cases (token expiration, refresh, etc.)
- [ ] Update documentation (README, TROUBLESHOOTING)
- [ ] Create user guide with examples

### Long-term (Future)

- [ ] Monitor usage patterns
- [ ] Add rate limiting if needed
- [ ] Consider GPT Actions if Free tier support requested
- [ ] Evaluate ChatGPT-specific optimizations (if any)

---

## Open Questions

1. **Callback URL Pattern:**
   - What is the actual callback URL format ChatGPT uses?
   - Is it stable or does it change per connector instance?
   - **Answer Method:** Create test connector, inspect OAuth redirect URL

2. **MCP Protocol Version:**
   - What MCP protocol version does ChatGPT support?
   - Is our server version compatible?
   - **Answer Method:** Check ChatGPT MCP docs, test connection, review MCP library version

3. **OAuth Scopes:**
   - Does ChatGPT request specific OAuth scopes?
   - Do we need to implement scope validation?
   - **Answer Method:** Monitor Auth0 logs during OAuth flow

4. **Rate Limiting:**
   - What are reasonable rate limits for ChatGPT usage?
   - Does OpenAI provide guidance?
   - **Answer Method:** Monitor initial usage, implement conservative limits

5. **Error Handling:**
   - How does ChatGPT display MCP tool errors to users?
   - Should we adjust error messages for better UX?
   - **Answer Method:** Test various error conditions, iterate on messaging

---

## Server Changes Required

### Likely: None

Current server implementation should work as-is with ChatGPT MCP Connectors:

✅ **Already Implemented:**
- Remote HTTP MCP server (`/mcp` endpoint via `FastApiHttpSessionManager`)
- OAuth 2.1 with Auth0 (authorization server)
- JWT validation via MCPAuth
- RFC 9728 protected resource metadata
- OpenID configuration endpoint
- Dynamic Client Registration proxy

### Possible: Configuration Only

**Auth0 Callback URLs:**
- Add ChatGPT callback URL(s) to Auth0 allowed callback URLs
- No server code changes required

**CORS Configuration:**
- May need to add `chat.openai.com` to CORS allowed origins
- Currently using `*` in some endpoints (lines 179, 181, 211-213)
- Should verify CORS headers are set correctly for ChatGPT

### Unlikely: Code Changes

**If Needed:**
- Update MCP library version (if ChatGPT requires newer version)
- Adjust OAuth metadata (if ChatGPT expects different format)
- Add ChatGPT-specific logging/monitoring
- Implement rate limiting (if abuse occurs)

---

## Risk Assessment

### Low Risk

- **Server Compatibility:** Current server follows MCP spec and OAuth 2.1 standard
- **Auth0 Support:** Auth0 is widely used, well-documented, ChatGPT-compatible
- **User Isolation:** Already enforced at every query, tested with Codex/Claude

### Medium Risk

- **OAuth Callback URL:** May need to iterate on Auth0 configuration
- **Rate Limiting:** No current protection against abuse
- **Error Handling:** May need to adjust error messages for ChatGPT UX

### High Risk

- **None identified** - Standard-compliant implementation should work

### Mitigation Strategies

1. **Test Early:** Configure test connector ASAP to identify issues
2. **Monitor Closely:** Watch server logs during initial testing
3. **Iterate Quickly:** Be prepared to adjust Auth0 config based on OAuth flow behavior
4. **Document Everything:** Record actual callback URLs, OAuth flow details for future reference

---

## Success Metrics

### Technical Metrics

- OAuth flow completion rate: >95%
- MCP tool call success rate: >99%
- Average tool call latency: <500ms
- Error rate: <1%

### User Experience Metrics

- Setup time: <5 minutes for new user
- Natural language queries work without special syntax
- Memory retrieval accuracy: >90% relevant results
- User isolation: 100% (zero cross-contamination)

### Adoption Metrics

- Number of connected ChatGPT users
- Daily active users
- Average memories per user
- Most-used tools (store_memory vs retrieve_context vs others)

---

## Next Actions

**Immediate (Tim):**
1. Update Auth0 callback URLs to include ChatGPT pattern
2. Test OAuth metadata endpoints are accessible
3. Create test ChatGPT Pro account (if needed)

**Phase 1 (Tim or Collaborator):**
1. Enable Developer Mode in ChatGPT
2. Create MCP Connector pointing to `your-domain.com`
3. Complete OAuth flow and document actual callback URL
4. Test basic memory operations

**Phase 2 (After successful Phase 1):**
1. Test with multiple users
2. Document any issues in TROUBLESHOOTING.md
3. Update README.md with ChatGPT instructions
4. Announce availability to users

---

## References

- **OpenAI MCP Documentation:** platform.openai.com/docs/mcp (requires login)
- **Auth0 MCP Guide:** auth0.com/blog/add-remote-mcp-server-chatgpt
- **MCP Specification:** modelcontextprotocol.io
- **RFC 9728 (OAuth Protected Resource):** datatracker.ietf.org/doc/html/rfc9728

---

## Appendix: GPT Actions Implementation (If Needed)

<details>
<summary>Click to expand GPT Actions implementation details</summary>

### REST API Endpoints

```python
# /api/v1/memories - Store memory
POST /api/v1/memories
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "text": "User prefers concise documentation",
  "memory_type": "core_identity",
  "scope": "global",
  "entity": "user_preferences",
  "tags": ["preferences", "communication"]
}

Response: {"memory_id": "uuid", "status": "stored"}
```

```python
# /api/v1/memories/search - Retrieve context
GET /api/v1/memories/search?query=preferences&limit=10
Authorization: Bearer <jwt>

Response: [
  {
    "id": "uuid",
    "text": "User prefers concise documentation",
    "memory_type": "core_identity",
    "score": 0.95,
    ...
  }
]
```

### OpenAPI Schema (Partial)

```yaml
openapi: 3.0.0
info:
  title: MCP Memory API
  version: 1.0.0
servers:
  - url: https://your-domain.com/api/v1

paths:
  /memories:
    post:
      operationId: storeMemory
      summary: Store a new memory
      security:
        - OAuth2: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Memory'
      responses:
        '200':
          description: Memory stored successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/StorageResult'

  /memories/search:
    get:
      operationId: searchMemories
      summary: Search memories by query
      security:
        - OAuth2: []
      parameters:
        - name: query
          in: query
          required: true
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
            default: 10
      responses:
        '200':
          description: Search results
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/MemoryResult'

components:
  securitySchemes:
    OAuth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://your-tenant.us.auth0.com/authorize
          tokenUrl: https://your-tenant.us.auth0.com/oauth/token
          scopes:
            read:memories: Read memories
            write:memories: Write memories

  schemas:
    Memory:
      type: object
      required: [text, memory_type, scope, entity]
      properties:
        text:
          type: string
        memory_type:
          type: string
          enum: [core_identity, project_context, task_instruction, episodic]
        scope:
          type: string
          enum: [global, project, task]
        entity:
          type: string
        tags:
          type: array
          items:
            type: string

    StorageResult:
      type: object
      properties:
        memory_id:
          type: string
        status:
          type: string

    MemoryResult:
      type: object
      properties:
        id:
          type: string
        text:
          type: string
        memory_type:
          type: string
        score:
          type: number
```

</details>

---

**End of Document**
