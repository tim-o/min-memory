"""Shared test fixtures.

Pre-mocks heavy modules (storage, auth) so that importing src.tools
does not require a running Qdrant instance or Auth0 configuration.
"""

import sys
from unittest.mock import MagicMock

# --- Pre-mock modules that have side effects on import ---

# storage: connects to Qdrant and calls setup_qdrant() at module level
mock_storage = MagicMock()
mock_storage.qdrant = MagicMock()
mock_storage.embedder = MagicMock()
mock_storage.build_filter = MagicMock()
mock_storage.find_by_entity = MagicMock(return_value=[])
mock_storage.async_update_access_tracking = MagicMock()
mock_storage.setup_qdrant = MagicMock()

# auth: requires AUTH0_DOMAIN and AUTH0_API_AUDIENCE env vars at import
mock_auth = MagicMock()
mock_auth.get_current_user = MagicMock(return_value="test-user-123")

# Only inject if not already imported (avoids clobbering real imports
# if tests are run alongside integration tests that need real modules)
if "src.storage" not in sys.modules:
    sys.modules["src.storage"] = mock_storage
if "src.auth" not in sys.modules:
    sys.modules["src.auth"] = mock_auth
