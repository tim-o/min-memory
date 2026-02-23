"""Tests for trusted backend key authentication."""

import os
from unittest.mock import patch, MagicMock

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

# We test the auth logic in isolation rather than importing the full app
# (which requires Auth0 config and Qdrant). We replicate the middleware
# and get_current_user logic with the env vars we control.

BACKEND_KEY = "test-secret-key-12345"


# --- Minimal app that mirrors the real auth flow ---

from contextvars import ContextVar
from starlette.requests import Request

_test_request: ContextVar[Request | None] = ContextVar("_test_request", default=None)


def make_get_current_user(trusted_key: str | None):
    """Factory matching the real get_current_user logic."""

    def get_current_user() -> str | None:
        if trusted_key:
            request = _test_request.get()
            if request is not None:
                backend_key = request.headers.get("x-backend-key")
                if backend_key == trusted_key:
                    user_id = request.headers.get("x-user-id")
                    return user_id if user_id else None
        # No OAuth fallback in tests — return None
        return None

    return get_current_user


def create_test_app(trusted_key: str | None):
    """Build a minimal Starlette app with the same middleware logic."""

    get_current_user = make_get_current_user(trusted_key)

    async def protected_endpoint(request: Request):
        user = get_current_user()
        if not user:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return JSONResponse({"user": user})

    class TestAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            token = _test_request.set(request)
            try:
                if trusted_key:
                    backend_key = request.headers.get("x-backend-key")
                    if backend_key == trusted_key:
                        user_id = request.headers.get("x-user-id")
                        if not user_id:
                            return JSONResponse(
                                {"error": "missing_user_id"},
                                status_code=400,
                            )
                        return await call_next(request)

                # No OAuth in test — reject
                return JSONResponse({"error": "oauth_required"}, status_code=401)
            finally:
                _test_request.reset(token)

    app = Starlette(
        routes=[Route("/mcp", endpoint=protected_endpoint, methods=["POST"])],
        middleware=[Middleware(TestAuthMiddleware)],
    )
    return app


# --- Tests ---


class TestBackendKeyAuth:
    """Test trusted backend key authentication."""

    def test_valid_backend_key_bypasses_oauth(self):
        """Valid X-Backend-Key + X-User-Id should authenticate without OAuth."""
        app = create_test_app(BACKEND_KEY)
        client = TestClient(app)

        response = client.post(
            "/mcp",
            headers={
                "X-Backend-Key": BACKEND_KEY,
                "X-User-Id": "user-abc-123",
            },
            json={},
        )

        assert response.status_code == 200
        assert response.json() == {"user": "user-abc-123"}

    def test_invalid_backend_key_falls_through(self):
        """Wrong X-Backend-Key should not bypass OAuth."""
        app = create_test_app(BACKEND_KEY)
        client = TestClient(app)

        response = client.post(
            "/mcp",
            headers={
                "X-Backend-Key": "wrong-key",
                "X-User-Id": "user-abc-123",
            },
            json={},
        )

        # Falls through to OAuth path, which rejects in our test app
        assert response.status_code == 401
        assert response.json()["error"] == "oauth_required"

    def test_missing_user_id_returns_error(self):
        """Valid backend key but missing X-User-Id should return 400."""
        app = create_test_app(BACKEND_KEY)
        client = TestClient(app)

        response = client.post(
            "/mcp",
            headers={
                "X-Backend-Key": BACKEND_KEY,
                # No X-User-Id
            },
            json={},
        )

        assert response.status_code == 400
        assert response.json()["error"] == "missing_user_id"

    def test_no_backend_key_configured(self):
        """When TRUSTED_BACKEND_KEY is not set, backend key headers are ignored."""
        app = create_test_app(None)
        client = TestClient(app)

        response = client.post(
            "/mcp",
            headers={
                "X-Backend-Key": BACKEND_KEY,
                "X-User-Id": "user-abc-123",
            },
            json={},
        )

        # No backend key configured, falls through to OAuth (rejected in test)
        assert response.status_code == 401

    def test_no_headers_at_all(self):
        """Request with no auth headers should be rejected."""
        app = create_test_app(BACKEND_KEY)
        client = TestClient(app)

        response = client.post("/mcp", json={})

        assert response.status_code == 401
