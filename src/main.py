# src/main.py

import hmac
import logging
import json
import os
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi_mcp.transport.http import FastApiHttpSessionManager

# Local module imports
from . import auth
from .auth import _current_request, TRUSTED_BACKEND_KEY
from . import tools

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def get_base_url(request: Request) -> str:
    """Return normalized base URL for the current request"""
    return str(request.base_url).rstrip("/")

# --- Route Handlers ---

async def oauth_protected_resource_metadata(request: Request) -> JSONResponse:
    """Serve RFC 9728 protected resource metadata pointing to Auth0."""
    if not auth.api_audience:
        return JSONResponse({"error": "auth0_not_configured"}, status_code=503)

    auth0_domain = os.getenv("AUTH0_DOMAIN", "")
    authorization_servers = [f"https://{auth0_domain}/"] if auth0_domain else []
    return JSONResponse({
        "resource": auth.api_audience,
        "authorization_servers": authorization_servers,
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp:read", "mcp:write"],
        "default_scopes": ["mcp:read"],
    })

async def openid_configuration(request: Request) -> JSONResponse:
    """Surface minimal OpenID configuration, delegating to Auth0."""
    auth0_domain = os.getenv("AUTH0_DOMAIN")
    if not auth0_domain:
        return JSONResponse({"error": "auth0_not_configured"}, status_code=503)

    issuer = f"https://{auth0_domain}/"
    return JSONResponse({
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}authorize",
        "token_endpoint": f"{issuer}oauth/token",
        "jwks_uri": f"{issuer}.well-known/jwks.json",
        "registration_endpoint": f"{issuer}oidc/register",
    })

async def register_redirect(request: Request) -> JSONResponse:
    """Proxy Dynamic Client Registration requests to Auth0."""
    # This is a complex function that involves proxying a request to Auth0.
    # The implementation is copied from the original file.
    if request.method.upper() == "OPTIONS":
        logger.debug("Received OPTIONS request for /register")
        response = Response(status_code=204)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    if request.method.upper() != "POST":
        return JSONResponse({"error": "method_not_allowed"}, status_code=405)

    auth0_domain = os.getenv("AUTH0_DOMAIN")
    if not auth0_domain:
        return JSONResponse({"error": "auth0_not_configured"}, status_code=503)

    try:
        registration_payload = await request.json()
    except json.JSONDecodeError:
        return JSONResponse({"error": "invalid_request", "error_description": "Body must be valid JSON"}, status_code=400)
    except Exception as exc:
        logger.error(f"Failed to parse registration payload: {exc}")
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    dcr_url = f"https://{auth0_domain}/oidc/register"
    headers = {"Content-Type": "application/json"}
    logger.info("Forwarding client registration to Auth0 for client_name=%s", registration_payload.get("client_name"))

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            auth0_response = await client.post(dcr_url, json=registration_payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.error(f"Auth0 DCR request failed: {exc}")
        return JSONResponse({"error": "server_error", "error_description": "Failed to register client"}, status_code=502)

    response_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    }

    if auth0_response.headers.get("content-type", "").startswith("application/json"):
        return JSONResponse(auth0_response.json(), status_code=auth0_response.status_code, headers=response_headers)

    return Response(auth0_response.text, status_code=auth0_response.status_code, headers=response_headers, media_type=auth0_response.headers.get("content-type", "text/plain"))

async def oauth_token_redirect(request: Request) -> JSONResponse:
    """Inform clients that Auth0 hosts the OAuth token endpoint."""
    auth0_domain = os.getenv("AUTH0_DOMAIN", "")
    return JSONResponse({
        "error": "use_auth0",
        "message": "Token endpoint handled by Auth0",
        "token_endpoint": f"https://{auth0_domain}/oauth/token" if auth0_domain else None
    }, status_code=400)

# --- MCP Transport ---

http_session_manager = FastApiHttpSessionManager(tools.mcp_server, json_response=True)

async def handle_http_transport(request: Request):
    return await http_session_manager.handle_fastapi_request(request)

# --- Health Check ---

async def health_check(request: Request):
    auth0_domain = os.getenv("AUTH0_DOMAIN", "not-configured")
    return Response(json.dumps({
        "status": "ok",
        "service": "mcp-memory-server-http",
        "auth": "oauth2",
        "auth_provider": auth0_domain
    }), media_type="application/json")

# --- Middleware ---

auth_middleware_cls = auth.mcp_auth.bearer_auth_middleware(
    "jwt",
    audience=auth.api_audience,
    required_scopes=None,
    show_error_details=False,
)

EXEMPT_PATHS = {"/health", "/register", "/oauth/token"}
EXEMPT_PREFIXES = ("/.well-known",)

class AuthGuardMiddleware(BaseHTTPMiddleware):
    """Runs mcpauth bearer authentication for protected routes."""
    def __init__(self, app):
        super().__init__(app)
        self._bearer = auth_middleware_cls(app)

    async def dispatch(self, request: Request, call_next):
        # Always set the context var so get_current_user() can read headers
        token = _current_request.set(request)
        try:
            path = request.url.path
            if (
                request.method.upper() == "OPTIONS"
                or path in EXEMPT_PATHS
                or any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES)
            ):
                return await call_next(request)

            # Trusted backend key bypasses OAuth entirely
            if TRUSTED_BACKEND_KEY:
                backend_key = request.headers.get("x-backend-key")
                if backend_key and hmac.compare_digest(backend_key, TRUSTED_BACKEND_KEY):
                    user_id = request.headers.get("x-user-id")
                    if not user_id:
                        return JSONResponse(
                            {"error": "missing_user_id", "error_description": "X-User-Id header required with backend key auth"},
                            status_code=400,
                        )
                    return await call_next(request)

            if path == "/mcp" and "authorization" not in request.headers:
                logger.info(f"MCP request without auth header from {request.client.host if request.client else 'unknown'}")
                return Response(status_code=401, content=b"", headers={"Content-Length": "0"})
            return await self._bearer.dispatch(request, call_next)
        finally:
            _current_request.reset(token)

class WWWAuthenticateMiddleware(BaseHTTPMiddleware):
    """Ensures 401/403 responses advertise resource metadata per RFC 9728."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if response.status_code in (401, 403):
            metadata_url = f"{get_base_url(request)}/.well-known/oauth-protected-resource"
            challenge = f'Bearer resource_metadata="{metadata_url}"'
            response.headers["WWW-Authenticate"] = challenge
        return response

# --- App Lifecycle ---

async def app_lifespan(app):
    try:
        yield
    finally:
        await http_session_manager.shutdown()

# --- App Factory ---

def create_app():
    logger.info("MCP HTTP server starting up")
    app = Starlette(
        debug=False,
        routes=[
            Route("/health", endpoint=health_check, methods=["GET"]),
            Route("/mcp", endpoint=handle_http_transport, methods=["GET", "POST"]),
            Route("/register", endpoint=register_redirect, methods=["POST", "OPTIONS"]),
            Route("/oauth/token", endpoint=oauth_token_redirect, methods=["GET", "POST"]),
            Route("/.well-known/oauth-protected-resource", endpoint=oauth_protected_resource_metadata, methods=["GET"]),
            Route("/.well-known/oauth-protected-resource/mcp", endpoint=oauth_protected_resource_metadata, methods=["GET"]),
            Route("/.well-known/openid-configuration", endpoint=openid_configuration, methods=["GET"]),
            auth.mcp_auth.metadata_route(),
        ],
        middleware=[
            Middleware(WWWAuthenticateMiddleware),
            Middleware(AuthGuardMiddleware),
        ],
        lifespan=app_lifespan
    )
    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    logger.info(f"Starting HTTP MCP server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
