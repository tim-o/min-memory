"""Tests for list_entities enhancement and register_entity tool (AC-15, AC-16, AC-17)."""

import json
from unittest.mock import patch, MagicMock

import pytest
import yaml

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


class FakeEmbedding:
    """Mimics a numpy array with a .tolist() method."""

    def __init__(self, values):
        self._values = values

    def tolist(self):
        return list(self._values)


class FakePoint:
    """Minimal stand-in for a Qdrant point returned by scroll/retrieve."""

    def __init__(self, id, payload):
        self.id = id
        self.payload = dict(payload)


def make_entity_tree():
    """Create an EntityTree loaded from the sample data."""
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
    yaml.dump(SAMPLE_TREE, tmp, default_flow_style=False, sort_keys=False)
    tmp.close()
    tree = EntityTree()
    tree.load(tmp.name)
    os.unlink(tmp.name)
    return tree


@pytest.fixture
def mock_env():
    """Patch qdrant, embedder, auth, and entity_tree for call_tool tests."""
    mock_qdrant = MagicMock()
    mock_embedder = MagicMock()
    tree = make_entity_tree()

    with patch("src.tools.qdrant", mock_qdrant), \
         patch("src.tools.embedder", mock_embedder), \
         patch("src.tools.get_current_user", return_value=TEST_USER), \
         patch("src.tools.entity_tree", tree), \
         patch("src.tools.find_by_entity", return_value=[]):
        yield {
            "qdrant": mock_qdrant,
            "embedder": mock_embedder,
            "entity_tree": tree,
        }


async def call_tool_parsed(name: str, arguments: dict) -> dict:
    """Call a tool and return parsed JSON response."""
    from src.tools import call_tool
    result = await call_tool(name, arguments)
    assert len(result) == 1
    return json.loads(result[0].text)


# --- AC-15: register_entity adds to tree ---


class TestRegisterEntityTool:
    """AC-15: register_entity tool allows adding new entities to the tree at runtime."""

    @pytest.mark.asyncio
    async def test_register_entity_creates_new(self, mock_env):
        """Registering a new entity via the tool returns 'created' status."""
        result = await call_tool_parsed("register_entity", {
            "entity": "slvr.wholesale",
            "description": "Wholesale channel",
        })
        assert result["status"] == "created"
        assert result["entity"] == "slvr.wholesale"
        assert result["parent"] == "slvr"

    @pytest.mark.asyncio
    async def test_register_entity_adds_to_tree_in_memory(self, mock_env):
        """After registration, entity is in the tree's all_entities set."""
        await call_tool_parsed("register_entity", {
            "entity": "slvr.wholesale",
            "description": "Wholesale channel",
        })
        assert "slvr.wholesale" in mock_env["entity_tree"].get_all_entities()

    @pytest.mark.asyncio
    async def test_register_existing_entity_is_noop(self, mock_env):
        """Registering an already-known entity returns 'exists' status."""
        result = await call_tool_parsed("register_entity", {
            "entity": "slvr.marketing",
            "description": "Different description",
        })
        assert result["status"] == "exists"

    @pytest.mark.asyncio
    async def test_register_entity_with_explicit_parent(self, mock_env):
        """Explicit parent overrides dotted-name inference."""
        result = await call_tool_parsed("register_entity", {
            "entity": "new.entity",
            "description": "A new entity",
            "parent": "slvr",
        })
        assert result["parent"] == "slvr"
        assert "new.entity" in mock_env["entity_tree"].get_tree()["slvr"]["children"]

    @pytest.mark.asyncio
    async def test_register_entity_new_root(self, mock_env):
        """Entity with no parent becomes a new root."""
        result = await call_tool_parsed("register_entity", {
            "entity": "clarity",
            "description": "Clarity product",
        })
        assert result["status"] == "created"
        assert result["parent"] is None
        assert "clarity" in mock_env["entity_tree"].get_tree()

    @pytest.mark.asyncio
    async def test_registered_entity_passes_validation(self, mock_env):
        """After registration, entity passes validation."""
        tree = mock_env["entity_tree"]
        assert tree.validate_entity("slvr.wholesale") is not None  # Unknown before
        await call_tool_parsed("register_entity", {
            "entity": "slvr.wholesale",
            "description": "Wholesale channel",
        })
        assert tree.validate_entity("slvr.wholesale") is None  # Known after


# --- AC-16: list_entities show_tree ---


class TestListEntitiesShowTree:
    """AC-16: list_entities enhanced to optionally return entity tree structure."""

    @pytest.mark.asyncio
    async def test_list_entities_without_show_tree(self, mock_env):
        """Default list_entities does not include tree key."""
        mock_env["qdrant"].scroll.return_value = ([], None)
        result = await call_tool_parsed("list_entities", {})
        assert "entities" in result
        assert "count" in result
        assert "tree" not in result

    @pytest.mark.asyncio
    async def test_list_entities_show_tree_false(self, mock_env):
        """Explicit show_tree=false does not include tree key."""
        mock_env["qdrant"].scroll.return_value = ([], None)
        result = await call_tool_parsed("list_entities", {"show_tree": False})
        assert "tree" not in result

    @pytest.mark.asyncio
    async def test_list_entities_show_tree_true(self, mock_env):
        """show_tree=true includes the configured entity tree."""
        mock_env["qdrant"].scroll.return_value = ([], None)
        result = await call_tool_parsed("list_entities", {"show_tree": True})
        assert "tree" in result
        assert "slvr" in result["tree"]
        assert result["tree"]["slvr"]["description"] == "Saint Lawrence Valley Roasters"
        assert "slvr.marketing" in result["tree"]["slvr"]["children"]

    @pytest.mark.asyncio
    async def test_list_entities_show_tree_includes_full_structure(self, mock_env):
        """Tree includes all root entities and their children."""
        mock_env["qdrant"].scroll.return_value = ([], None)
        result = await call_tool_parsed("list_entities", {"show_tree": True})
        tree = result["tree"]
        assert "system" in tree
        assert "system.memory-protocol" in tree["system"]["children"]

    @pytest.mark.asyncio
    async def test_list_entities_show_tree_with_observed_entities(self, mock_env):
        """show_tree includes tree alongside observed entities from Qdrant."""
        mock_env["qdrant"].scroll.return_value = ([
            FakePoint("id-1", {
                "entity": "slvr.marketing",
                "scope": "project",
                "project": "slvr",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-03-01T00:00:00",
            }),
        ], None)
        result = await call_tool_parsed("list_entities", {"show_tree": True})
        # Observed entities
        assert result["count"] == 1
        assert result["entities"][0]["name"] == "slvr.marketing"
        # Tree also present
        assert "tree" in result
        assert "slvr" in result["tree"]

    @pytest.mark.asyncio
    async def test_list_entities_show_tree_reflects_runtime_registration(self, mock_env):
        """Tree reflects entities registered at runtime."""
        mock_env["qdrant"].scroll.return_value = ([], None)
        # Register a new entity
        mock_env["entity_tree"].register_entity("slvr.wholesale", "Wholesale channel")
        result = await call_tool_parsed("list_entities", {"show_tree": True})
        assert "slvr.wholesale" in result["tree"]["slvr"]["children"]


# --- AC-17: JSON schema for new tools ---


class TestJsonSchemaDefinitions:
    """AC-17: All new tool parameters have JSON Schema definitions in list_tools."""

    @pytest.mark.asyncio
    async def test_register_entity_has_json_schema(self, mock_env):
        """register_entity tool has a complete JSON Schema."""
        from src.tools import list_tools
        tools = await list_tools()
        register_tool = next(t for t in tools if t.name == "register_entity")
        schema = register_tool.inputSchema
        assert schema["type"] == "object"
        assert "entity" in schema["properties"]
        assert "description" in schema["properties"]
        assert "parent" in schema["properties"]
        assert "entity" in schema["required"]
        assert "description" in schema["required"]
        # parent is optional
        assert "parent" not in schema["required"]

    @pytest.mark.asyncio
    async def test_register_entity_schema_property_types(self, mock_env):
        """register_entity schema properties have correct types."""
        from src.tools import list_tools
        tools = await list_tools()
        register_tool = next(t for t in tools if t.name == "register_entity")
        props = register_tool.inputSchema["properties"]
        assert props["entity"]["type"] == "string"
        assert props["description"]["type"] == "string"
        assert props["parent"]["type"] == "string"

    @pytest.mark.asyncio
    async def test_list_entities_show_tree_in_schema(self, mock_env):
        """list_entities schema includes show_tree boolean parameter."""
        from src.tools import list_tools
        tools = await list_tools()
        list_tool = next(t for t in tools if t.name == "list_entities")
        schema = list_tool.inputSchema
        assert "show_tree" in schema["properties"]
        assert schema["properties"]["show_tree"]["type"] == "boolean"

    @pytest.mark.asyncio
    async def test_sync_session_has_json_schema(self, mock_env):
        """sync_session tool (from FU-2) still has a complete JSON Schema."""
        from src.tools import list_tools
        tools = await list_tools()
        sync_tool = next(t for t in tools if t.name == "sync_session")
        schema = sync_tool.inputSchema
        assert schema["type"] == "object"
        assert "project" in schema["properties"]
        assert "project" in schema["required"]

    @pytest.mark.asyncio
    async def test_retrieve_context_recency_weight_in_schema(self, mock_env):
        """retrieve_context schema (from FU-3) includes recency_weight."""
        from src.tools import list_tools
        tools = await list_tools()
        rc_tool = next(t for t in tools if t.name == "retrieve_context")
        schema = rc_tool.inputSchema
        assert "recency_weight" in schema["properties"]
        assert "status_filter" in schema["properties"]

    @pytest.mark.asyncio
    async def test_all_tools_have_input_schema(self, mock_env):
        """Every registered tool has an inputSchema with type=object."""
        from src.tools import list_tools
        tools = await list_tools()
        for tool in tools:
            assert tool.inputSchema is not None, f"Tool {tool.name} has no inputSchema"
            assert tool.inputSchema.get("type") == "object", f"Tool {tool.name} schema type is not 'object'"
