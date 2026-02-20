# src/auth.py

import logging
import os
from mcpauth import MCPAuth
from mcpauth.config import AuthServerType
from mcpauth.utils import fetch_server_config

logger = logging.getLogger(__name__)

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
    """Return the authenticated user (Auth0 subject) from the current request context."""
    if not mcp_auth:
        return None
    auth_info = mcp_auth.auth_info
    return auth_info.subject if auth_info else None
