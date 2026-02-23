# src/auth.py

import hmac
import logging
import os
from contextvars import ContextVar

from starlette.requests import Request
from mcpauth import MCPAuth
from mcpauth.config import AuthServerType
from mcpauth.utils import fetch_server_config

logger = logging.getLogger(__name__)

# Context variable set by middleware so get_current_user() can read request headers
_current_request: ContextVar[Request | None] = ContextVar("_current_request", default=None)

# Trusted backend key for server-to-server calls (bypasses OAuth)
TRUSTED_BACKEND_KEY = os.getenv("TRUSTED_BACKEND_KEY")

def init_mcp_auth() -> MCPAuth | None:
    """Initialize mcpauth from the configured Auth0 tenant."""
    auth0_domain = os.getenv("AUTH0_DOMAIN")
    if not auth0_domain:
        logger.warning("AUTH0_DOMAIN not set, OAuth disabled")
        return None

    issuer = f"https://{auth0_domain}/"

    try:
        server_config = fetch_server_config(
            issuer=issuer,
            type=AuthServerType.OIDC,
        )
        logger.info("Loaded Auth0 metadata from %s", issuer)
        return MCPAuth(server=server_config)
    except Exception as exc:
        logger.error("Failed to initialize MCPAuth: %s", exc)
        return None


# --- Initialize Auth Clients ---
logger.info("Initializing authentication...")
mcp_auth = init_mcp_auth()
api_audience = os.getenv("AUTH0_API_AUDIENCE")

# Auth0 default audience ensures JWT access tokens are issued. If opaque tokens are returned in the
# future, configure a custom verification function that performs token introspection and pass it to
# `bearer_auth_middleware` instead of "jwt".
if not mcp_auth or not api_audience:
    raise RuntimeError("AUTH0_DOMAIN and AUTH0_API_AUDIENCE must be set for OAuth authentication")


def get_current_user() -> str | None:
    """Return the authenticated user from the current request context.

    Checks trusted backend key first (server-to-server), then falls through to OAuth.
    """
    # 1. Check for trusted backend key auth
    if TRUSTED_BACKEND_KEY:
        request = _current_request.get()
        if request is not None:
            backend_key = request.headers.get("x-backend-key")
            if backend_key and hmac.compare_digest(backend_key, TRUSTED_BACKEND_KEY):
                user_id = request.headers.get("x-user-id")
                if not user_id:
                    logger.warning("Backend key auth: missing X-User-Id header")
                    return None
                return user_id

    # 2. Fall through to OAuth
    if not mcp_auth:
        return None
    auth_info = mcp_auth.auth_info
    return auth_info.subject if auth_info else None
