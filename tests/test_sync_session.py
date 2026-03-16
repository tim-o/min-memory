"""Tests for sync_session tool (AC-01 through AC-09)."""

import json
from datetime import datetime
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from src.entities import EntityTree


# --- Fixtures ---

SAMPLE_TREE = {
    "entities": {
        "slvr": {
            "description": "Saint Lawrence Valley Roasters",
            "children": {
                "slvr.marketing": "Paid acquisition, content, brand",
                "slvr.financials": "Revenue, FCF, compensation",
            }
        },
        "system": {
            "description": "Operating system infrastructure",
            "children": {
                "system.memory-protocol": "Memory conventions",
            }
        }
    }
}

TEST_USER = "test-user-123"

# Fake embedding vector (384-dim for bge-small-en-v1.5)
FAKE_EMBEDDING = [0.1] * 384


class FakeEmbedding:
    """Mimics a numpy array with a .tolist() method."""

    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


def make_entity_tree():
    """Create an EntityTree loaded from the sample data."""
    import tempfile, yaml, os
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(SAMPLE_TREE, tmp, default_flow_style=False, sort_keys=False)
    tmp.close()
    tree = EntityTree()
    tree.load(tmp.name)
    os.unlink(tmp.name)
    return tree


class FakePoint:
    """Minimal stand-in for a Qdrant point returned by scroll/retrieve."""

    def __init__(self, id, payload):
        self.id = id
        self.payload = dict(payload)


@pytest.fixture
def mock_env():
    """Patch qdrant, embedder, auth, and entity_tree for call_tool tests."""
    mock_qdrant = MagicMock()
    mock_embedder = MagicMock()
    mock_embedder.embed.side_effect = lambda texts: iter([FakeEmbedding(FAKE_EMBEDDING)] * len(texts))
    tree = make_entity_tree()

    with patch("src.tools.qdrant", mock_qdrant), \
         patch("src.tools.embedder", mock_embedder), \
         patch("src.tools.get_current_user", return_value=TEST_USER), \
         patch("src.tools.entity_tree", tree), \
         patch("src.tools.find_by_entity") as mock_find:
        # Default: find_by_entity returns no existing records
        mock_find.return_value = []
        yield {
            "qdrant": mock_qdrant,
            "embedder": mock_embedder,
            "entity_tree": tree,
            "find_by_entity": mock_find,
        }


async def call_sync_session(arguments: dict) -> dict:
    """Call the sync_session tool and return parsed JSON response."""
    from src.tools import call_tool
    result = await call_tool("sync_session", arguments)
    assert len(result) == 1
    return json.loads(result[0].text)


# --- AC-01: sync_session registered in list_tools ---


class TestSyncSessionRegistered:
    """AC-01: sync_session tool is registered and callable."""

    @pytest.mark.asyncio
    async def test_sync_session_registered_in_list_tools(self, mock_env):
        from src.tools import list_tools
        tools = await list_tools()
        tool_names = [t.name for t in tools]
        assert "sync_session" in tool_names

    @pytest.mark.asyncio
    async def test_sync_session_has_json_schema(self, mock_env):
        from src.tools import list_tools
        tools = await list_tools()
        sync_tool = next(t for t in tools if t.name == "sync_session")
        schema = sync_tool.inputSchema
        assert schema["type"] == "object"
        assert "project" in schema["properties"]
        assert "decisions" in schema["properties"]
        assert "status_updates" in schema["properties"]
        assert "learnings" in schema["properties"]
        assert "feedback" in schema["properties"]
        assert "project" in schema["required"]


# --- AC-02: auto-sets memory_type and scope ---


class TestAutoSetsTypeAndScope:
    """AC-02: sync_session auto-sets memory_type and scope per category mapping."""

    @pytest.mark.asyncio
    async def test_decisions_set_episodic_and_project_scope(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "decisions": [{"text": "Use paid ads", "entity": "slvr.marketing"}],
        })
        # Verify upsert was called with correct payload
        call_args = mock_env["qdrant"].upsert.call_args_list[0]
        point = call_args.kwargs["points"][0] if "points" in call_args.kwargs else call_args[1]["points"][0]
        assert point.payload["memory_type"] == "episodic"
        assert point.payload["scope"] == "project"

    @pytest.mark.asyncio
    async def test_status_updates_set_project_context(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "status_updates": [{"entity": "slvr.marketing", "status": "active", "text": "Running campaigns"}],
        })
        call_args = mock_env["qdrant"].upsert.call_args_list[0]
        point = call_args.kwargs["points"][0] if "points" in call_args.kwargs else call_args[1]["points"][0]
        assert point.payload["memory_type"] == "project_context"
        assert point.payload["scope"] == "project"
        assert point.payload["status"] == "active"

    @pytest.mark.asyncio
    async def test_learnings_set_episodic_and_project_scope(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "learnings": [{"text": "SEO takes 6 months", "entity": "slvr.marketing"}],
        })
        call_args = mock_env["qdrant"].upsert.call_args_list[0]
        point = call_args.kwargs["points"][0] if "points" in call_args.kwargs else call_args[1]["points"][0]
        assert point.payload["memory_type"] == "episodic"
        assert point.payload["scope"] == "project"

    @pytest.mark.asyncio
    async def test_feedback_set_core_identity_and_global_scope(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "feedback": [{"entity": "system.memory-protocol", "text": "Always validate entities"}],
        })
        call_args = mock_env["qdrant"].upsert.call_args_list[0]
        point = call_args.kwargs["points"][0] if "points" in call_args.kwargs else call_args[1]["points"][0]
        assert point.payload["memory_type"] == "core_identity"
        assert point.payload["scope"] == "global"

    @pytest.mark.asyncio
    async def test_global_project_sets_global_scope(self, mock_env):
        result = await call_sync_session({
            "project": "global",
            "decisions": [{"text": "Always use structured sync", "entity": "system"}],
        })
        call_args = mock_env["qdrant"].upsert.call_args_list[0]
        point = call_args.kwargs["points"][0] if "points" in call_args.kwargs else call_args[1]["points"][0]
        assert point.payload["scope"] == "global"
        assert point.payload["project"] is None


# --- AC-03: decisions always append ---


class TestDecisionsAlwaysAppend:
    """AC-03: decisions and learnings always create new records."""

    @pytest.mark.asyncio
    async def test_two_decisions_create_two_records(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "decisions": [
                {"text": "Decision one", "entity": "slvr.marketing"},
                {"text": "Decision two", "entity": "slvr.marketing"},
            ],
        })
        assert result["summary"]["created"] == 2
        assert len(result["details"]["decisions"]) == 2
        assert all(d["action"] == "created" for d in result["details"]["decisions"])

    @pytest.mark.asyncio
    async def test_learnings_always_create_new_records(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "learnings": [
                {"text": "Learning one", "entity": "slvr.marketing"},
                {"text": "Learning two", "entity": "slvr.financials"},
            ],
        })
        assert result["summary"]["created"] == 2
        assert all(d["action"] == "created" for d in result["details"]["learnings"])


# --- AC-04: status_updates upsert ---


class TestStatusUpdateUpsert:
    """AC-04: status_updates upsert by (entity, user, project, memory_type='project_context')."""

    @pytest.mark.asyncio
    async def test_status_update_creates_when_no_existing(self, mock_env):
        mock_env["find_by_entity"].return_value = []
        result = await call_sync_session({
            "project": "slvr",
            "status_updates": [{"entity": "slvr.marketing", "status": "active", "text": "Running"}],
        })
        assert result["summary"]["created"] == 1
        assert result["summary"]["updated"] == 0
        assert result["details"]["status_updates"][0]["action"] == "created"

    @pytest.mark.asyncio
    async def test_status_update_updates_when_existing(self, mock_env):
        existing_point = FakePoint(
            id="existing-id-123",
            payload={
                "user": TEST_USER,
                "text": "Old status text",
                "memory_type": "project_context",
                "scope": "project",
                "entity": "slvr.marketing",
                "project": "slvr",
                "task_id": None,
                "related_to": [],
                "relation_types": {},
                "tags": [],
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "status": "active",
                "priority": None,
                "deleted": False,
            }
        )
        mock_env["find_by_entity"].return_value = [existing_point]
        result = await call_sync_session({
            "project": "slvr",
            "status_updates": [{"entity": "slvr.marketing", "status": "completed", "text": "Done"}],
        })
        assert result["summary"]["updated"] == 1
        assert result["summary"]["created"] == 0
        detail = result["details"]["status_updates"][0]
        assert detail["action"] == "updated"
        assert detail["memory_id"] == "existing-id-123"
        assert detail["previous_id"] == "existing-id-123"


# --- AC-05: feedback upsert ---


class TestFeedbackUpsert:
    """AC-05: feedback upserts by (entity, user, memory_type='core_identity')."""

    @pytest.mark.asyncio
    async def test_feedback_creates_when_no_existing(self, mock_env):
        mock_env["find_by_entity"].return_value = []
        result = await call_sync_session({
            "project": "slvr",
            "feedback": [{"entity": "system", "text": "Be concise"}],
        })
        assert result["summary"]["created"] == 1
        assert result["details"]["feedback"][0]["action"] == "created"

    @pytest.mark.asyncio
    async def test_feedback_updates_when_existing(self, mock_env):
        existing_point = FakePoint(
            id="feedback-id-456",
            payload={
                "user": TEST_USER,
                "text": "Old feedback",
                "memory_type": "core_identity",
                "scope": "global",
                "entity": "system",
                "project": None,
                "task_id": None,
                "related_to": [],
                "relation_types": {},
                "tags": [],
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "status": None,
                "priority": None,
                "deleted": False,
            }
        )
        mock_env["find_by_entity"].return_value = [existing_point]
        result = await call_sync_session({
            "project": "slvr",
            "feedback": [{"entity": "system", "text": "Be very concise"}],
        })
        assert result["summary"]["updated"] == 1
        detail = result["details"]["feedback"][0]
        assert detail["action"] == "updated"
        assert detail["memory_id"] == "feedback-id-456"


# --- AC-06: supersedes creates link ---


class TestSupersedesCreatesLink:
    """AC-06: When supersedes is provided, a supersedes relation is created."""

    @pytest.mark.asyncio
    async def test_supersedes_links_decision(self, mock_env):
        old_point = FakePoint(
            id="old-decision-id",
            payload={
                "user": TEST_USER,
                "text": "Old decision",
                "related_to": [],
                "relation_types": {},
                "updated_at": "2026-01-01T00:00:00",
            }
        )
        mock_env["qdrant"].retrieve.return_value = [old_point]

        result = await call_sync_session({
            "project": "slvr",
            "decisions": [{"text": "New decision", "entity": "slvr.marketing", "supersedes": "old-decision-id"}],
        })

        assert result["summary"]["created"] == 1
        # Verify set_payload was called to create the link on the old memory
        set_payload_calls = mock_env["qdrant"].set_payload.call_args_list
        assert len(set_payload_calls) >= 1

    @pytest.mark.asyncio
    async def test_supersedes_nonexistent_warns(self, mock_env):
        mock_env["qdrant"].retrieve.return_value = []

        result = await call_sync_session({
            "project": "slvr",
            "decisions": [{"text": "New decision", "entity": "slvr.marketing", "supersedes": "nonexistent-id"}],
        })

        assert result["summary"]["created"] == 1
        assert any("not found" in w for w in result["summary"]["warnings"])


# --- AC-07: returns structured summary ---


class TestReturnsSummary:
    """AC-07: sync_session returns structured summary with counts, IDs, warnings."""

    @pytest.mark.asyncio
    async def test_summary_structure(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "decisions": [{"text": "D1", "entity": "slvr.marketing"}],
            "learnings": [{"text": "L1", "entity": "slvr.marketing"}],
        })
        assert "summary" in result
        assert "details" in result
        assert "created" in result["summary"]
        assert "updated" in result["summary"]
        assert "warnings" in result["summary"]
        assert "decisions" in result["details"]
        assert "status_updates" in result["details"]
        assert "learnings" in result["details"]
        assert "feedback" in result["details"]

    @pytest.mark.asyncio
    async def test_summary_counts_correct(self, mock_env):
        existing = FakePoint(
            id="existing-fb",
            payload={
                "user": TEST_USER, "text": "Old", "memory_type": "core_identity",
                "scope": "global", "entity": "system", "project": None,
                "task_id": None, "related_to": [], "relation_types": {},
                "tags": [], "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00", "status": None,
                "priority": None, "deleted": False,
            }
        )
        # find_by_entity returns existing only for the feedback call
        mock_env["find_by_entity"].side_effect = [
            [],  # status_update: no existing
            [existing],  # feedback: existing found
        ]
        result = await call_sync_session({
            "project": "slvr",
            "decisions": [{"text": "D1", "entity": "slvr.marketing"}],
            "status_updates": [{"entity": "slvr.marketing", "status": "active", "text": "Running"}],
            "learnings": [{"text": "L1", "entity": "slvr.marketing"}],
            "feedback": [{"entity": "system", "text": "Updated feedback"}],
        })
        assert result["summary"]["created"] == 3  # 1 decision + 1 status + 1 learning
        assert result["summary"]["updated"] == 1  # 1 feedback

    @pytest.mark.asyncio
    async def test_memory_ids_in_details(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "decisions": [{"text": "D1", "entity": "slvr.marketing"}],
        })
        assert "memory_id" in result["details"]["decisions"][0]
        assert result["details"]["decisions"][0]["memory_id"]  # Not empty

    @pytest.mark.asyncio
    async def test_empty_arrays_returns_zero_ops(self, mock_env):
        result = await call_sync_session({"project": "slvr"})
        assert result["summary"]["created"] == 0
        assert result["summary"]["updated"] == 0
        assert result["summary"]["warnings"] == []
        assert result["details"]["decisions"] == []
        assert result["details"]["status_updates"] == []
        assert result["details"]["learnings"] == []
        assert result["details"]["feedback"] == []


# --- AC-08: rejects unknown project ---


class TestRejectsUnknownProject:
    """AC-08: sync_session validates project and rejects unknown."""

    @pytest.mark.asyncio
    async def test_unknown_project_returns_error(self, mock_env):
        result = await call_sync_session({
            "project": "unknown_project",
            "decisions": [{"text": "Should fail", "entity": "slvr.marketing"}],
        })
        assert "error" in result
        assert "Unknown project" in result["error"]

    @pytest.mark.asyncio
    async def test_known_project_accepted(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "decisions": [{"text": "Should work", "entity": "slvr.marketing"}],
        })
        assert "error" not in result
        assert result["summary"]["created"] == 1

    @pytest.mark.asyncio
    async def test_global_project_accepted(self, mock_env):
        result = await call_sync_session({
            "project": "global",
            "decisions": [{"text": "Global decision", "entity": "system"}],
        })
        assert "error" not in result
        assert result["summary"]["created"] == 1


# --- AC-09: warns on unknown entity ---


class TestWarnsUnknownEntity:
    """AC-09: sync_session warns on unknown entities but does not reject."""

    @pytest.mark.asyncio
    async def test_unknown_entity_produces_warning(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "decisions": [{"text": "Decision about wholesale", "entity": "slvr.wholesale"}],
        })
        assert result["summary"]["created"] == 1  # Still created
        assert any("slvr.wholesale" in w for w in result["summary"]["warnings"])

    @pytest.mark.asyncio
    async def test_known_entity_no_warning(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "decisions": [{"text": "Decision about marketing", "entity": "slvr.marketing"}],
        })
        assert result["summary"]["warnings"] == []

    @pytest.mark.asyncio
    async def test_multiple_unknown_entities_multiple_warnings(self, mock_env):
        result = await call_sync_session({
            "project": "slvr",
            "decisions": [
                {"text": "D1", "entity": "slvr.wholesale"},
                {"text": "D2", "entity": "slvr.roasting"},
            ],
        })
        assert result["summary"]["created"] == 2
        assert len(result["summary"]["warnings"]) == 2
