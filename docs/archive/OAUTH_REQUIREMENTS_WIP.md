MCP Server Authentication Requirements
Core OAuth 2.0 Requirements
1. OAuth 2.0 Authorization Server

Authorization endpoint (/oauth/authorize)

Must display login UI to user
Must support client_id, redirect_uri, state, scope parameters
Must support PKCE parameters: code_challenge, code_challenge_method


Token endpoint (/oauth/token)

Must support authorization_code grant type
Must support refresh_token grant type
Must return access_token, refresh_token, token_type, expires_in
Must support PKCE verification via code_verifier parameter


Token refresh functionality

Must accept refresh tokens and issue new access tokens
Must handle token expiration gracefully



2. Dynamic Client Registration (DCR) - RFC 7591
Required for: Claude web, Claude mobile, Claude Desktop (remote MCP)

Registration endpoint (/oauth/register)

Must accept redirect_uris (array of allowed callback URLs)
Must accept client_name (human-readable name)
Must dynamically generate client_id and client_secret
Must return client credentials immediately
Must store client configurations persistently


Client deletion signaling

Must return HTTP 401 with invalid_client error when client is deleted
Must trigger client re-registration in Claude



3. OAuth Discovery Metadata - RFC 8414
Required for: All OAuth clients

Discovery endpoint (/.well-known/oauth-authorization-server)

Must return JSON with:

issuer: Your server's base URL
authorization_endpoint: Full URL to authorization endpoint
token_endpoint: Full URL to token endpoint
registration_endpoint: Full URL to DCR endpoint
grant_types_supported: ["authorization_code", "refresh_token"]
response_types_supported: ["code"]
token_endpoint_auth_methods_supported: Authentication methods





4. PKCE Support - RFC 7636
Required for: ChatGPT Apps, recommended for all OAuth flows

Must support code_challenge and code_challenge_method in authorization request
Must support S256 method (SHA-256 hash)
Must verify code_verifier matches original code_challenge during token exchange
Should reject token requests with mismatched PKCE values


MCP Protocol Requirements
5. Remote MCP Server Implementation
Required for: Claude Code, Claude Desktop, Claude Mobile, Codex

Transport protocols

SSE (Server-Sent Events) transport
Streamable HTTP transport (recommended)
Note: SSE may be deprecated in future


MCP endpoints

/mcp/sse - SSE transport endpoint
/mcp/message - HTTP POST endpoint for messages


Authentication

Must verify OAuth Bearer token on every MCP request
Must extract user context from token
Must reject requests with invalid/expired tokens


MCP capabilities

Must expose tools via MCP protocol
Must support tool invocation with user context
Should support resources (optional)
Should support prompts (optional)



6. Local MCP Server (Optional)
Required for: Claude Desktop, Claude Code (local mode)

Configuration

Must support stdio transport
Must read credentials from environment variables
Must be configured via JSON config files:

Claude Desktop: ~/.config/Claude/claude_desktop_config.json
Codex: ~/.codex/config.toml




No OAuth required - credentials passed via environment


Platform-Specific Requirements
7. Claude Platform Requirements
Callback URLs (must whitelist):

Current: https://api.claude.com/api/mcp/auth_callback
Future: https://claude.com/api/mcp/auth_callback

Configuration:

Users configure via claude.ai website (Settings → Connectors)
Configuration syncs automatically to Desktop, Mobile, and Web
Users cannot configure directly on mobile apps
Optional: Support custom client ID/secret for non-DCR setups

Supported features:

OAuth-based and authless servers
Tools, resources, and prompts
Text and image-based tool results
Text and binary resources

8. ChatGPT Platform Requirements
OAuth Requirements:

Must support OAuth 2.1 with PKCE
Must support dynamic client registration (for Apps)
Authorization and API endpoints must share same root domain

✅ Good: https://api.example.com/auth and https://api.example.com/tools
❌ Bad: https://auth.example.com and https://api.example.com



Callback URLs:

GPT Actions: https://chat.openai.com/aip/g-{gpt-id}/oauth/callback
Apps: Provided via Apps SDK (OAuth 2.1 + PKCE)

API Schema:

Must provide OpenAPI specification
Must define all endpoints, parameters, and responses
ChatGPT uses schema to understand available actions

9. OpenAI Codex Requirements
Authentication:

Users authenticate via ChatGPT account login
Alternative: API key authentication
No custom OAuth flow needed for Codex itself

MCP Support:

Supports stdio (local) MCP servers
Supports streamable HTTP (remote) MCP servers
Configuration via ~/.codex/config.toml
OAuth support via experimental_use_rmcp_client flag
Can use Bearer tokens for authenticated MCP calls


REST API Requirements
10. REST API Endpoints (for ChatGPT Actions/Apps)

Authentication

All endpoints must verify Bearer token from Authorization header
Must return 401 for missing/invalid tokens


Endpoint structure

Should follow RESTful conventions
Should match OpenAPI specification exactly
Should return appropriate HTTP status codes


Response format

Must return JSON responses
Should include error messages for failures
Should be documented in OpenAPI spec




Security Requirements
11. Token Management

Access tokens

Should expire (recommended: 1 hour)
Must be cryptographically random
Must be associated with specific user and scopes


Refresh tokens

Should be long-lived but revocable
Must be stored securely
Must be rotated on use (optional but recommended)


Token storage

Must encrypt tokens at rest
Must prevent token leakage in logs
Must support token revocation



12. Security Best Practices

HTTPS required for all endpoints
CORS configuration for web-based OAuth flows
Rate limiting to prevent abuse
Scope enforcement - verify user permissions before tool execution
Input validation on all parameters
Audit logging for authentication events


Optional but Recommended
13. Enhanced Features

User management

User registration and login UI
Password reset functionality
Multi-factor authentication (2FA)


Admin dashboard

View registered OAuth clients
Monitor token usage
Revoke tokens/clients


Webhook support

Notify on token revocation
Notify on client deletion


Developer documentation

Setup guides for each platform
Code examples
Troubleshooting guides




Testing Requirements
14. Must Test With

MCP Inspector - Official testing tool for MCP servers
Claude Desktop - Local and remote MCP testing
Claude Code - Terminal-based testing with /mcp command
Claude Web (claude.ai) - Web connector testing
Claude Mobile - iOS and Android testing
ChatGPT - Custom GPT Actions testing
Codex CLI - Command-line MCP integration testing