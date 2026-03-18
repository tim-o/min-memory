"""Tests for entity tree loading, validation, and registration."""

import os
import tempfile

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


@pytest.fixture
def config_file(tmp_path):
    """Write a sample entity tree to a temp YAML file."""
    path = tmp_path / "entities.yaml"
    with open(path, "w") as f:
        yaml.dump(SAMPLE_TREE, f, default_flow_style=False, sort_keys=False)
    return str(path)


@pytest.fixture
def tree(config_file):
    """Return an EntityTree loaded from the sample config."""
    t = EntityTree()
    t.load(config_file)
    return t


# --- AC-14: Entity tree loads from YAML ---


class TestEntityTreeLoadsFromYaml:
    """AC-14: Entity tree is loaded from a YAML config file at server startup."""

    def test_loads_root_entities(self, tree):
        """Root entities are present after loading."""
        roots = tree.get_root_entities()
        assert "slvr" in roots
        assert "system" in roots

    def test_loads_child_entities(self, tree):
        """Child entities are present in the all-entities set."""
        all_entities = tree.get_all_entities()
        assert "slvr.marketing" in all_entities
        assert "slvr.financials" in all_entities
        assert "system.memory-protocol" in all_entities

    def test_total_entity_count(self, tree):
        """All entities (roots + children) are counted."""
        all_entities = tree.get_all_entities()
        # 2 roots + 3 children = 5
        assert len(all_entities) == 5

    def test_get_tree_returns_structure(self, tree):
        """get_tree returns the full hierarchical structure."""
        result = tree.get_tree()
        assert "slvr" in result
        assert result["slvr"]["description"] == "Saint Lawrence Valley Roasters"
        assert "slvr.marketing" in result["slvr"]["children"]

    def test_missing_config_file_starts_empty(self, tmp_path):
        """Missing config file results in empty tree with no error."""
        t = EntityTree()
        t.load(str(tmp_path / "nonexistent.yaml"))
        assert t.get_tree() == {}
        assert t.get_all_entities() == set()

    def test_empty_config_file_starts_empty(self, tmp_path):
        """Empty config file results in empty tree."""
        path = tmp_path / "empty.yaml"
        path.write_text("")
        t = EntityTree()
        t.load(str(path))
        assert t.get_tree() == {}

    def test_config_without_entities_key(self, tmp_path):
        """Config file without 'entities' key results in empty tree."""
        path = tmp_path / "bad.yaml"
        with open(path, "w") as f:
            yaml.dump({"other_key": "value"}, f)
        t = EntityTree()
        t.load(str(path))
        assert t.get_tree() == {}

    def test_validate_known_entity_returns_none(self, tree):
        """Known entities pass validation without warnings."""
        assert tree.validate_entity("slvr") is None
        assert tree.validate_entity("slvr.marketing") is None

    def test_validate_unknown_entity_returns_warning(self, tree):
        """Unknown entities produce a warning string."""
        warning = tree.validate_entity("slvr.wholesale")
        assert warning is not None
        assert "Unknown entity" in warning
        assert "slvr.wholesale" in warning

    def test_validate_entity_with_empty_tree(self):
        """Validation is skipped (returns None) when tree is empty."""
        t = EntityTree()
        t.load("/nonexistent/path.yaml")
        assert t.validate_entity("anything") is None

    def test_validate_project_known(self, tree):
        """Known root entities are valid projects."""
        assert tree.validate_project("slvr") is None
        assert tree.validate_project("system") is None

    def test_validate_project_global(self, tree):
        """'global' is always a valid project."""
        assert tree.validate_project("global") is None

    def test_validate_project_unknown(self, tree):
        """Unknown project names return an error string."""
        error = tree.validate_project("unknown_project")
        assert error is not None
        assert "Unknown project" in error


# --- AC-15: register_entity adds to tree ---


class TestRegisterEntityAddsToTree:
    """AC-15: register_entity tool allows adding new entities to the tree at runtime."""

    def test_register_new_child_entity(self, tree):
        """Registering a new child entity adds it under the correct parent."""
        result = tree.register_entity("slvr.wholesale", "Wholesale channel")
        assert result["status"] == "created"
        assert result["entity"] == "slvr.wholesale"
        assert result["parent"] == "slvr"
        assert "slvr.wholesale" in tree.get_all_entities()

    def test_register_infers_parent_from_dotted_name(self, tree):
        """Parent is inferred from the dotted prefix."""
        result = tree.register_entity("system.hooks", "Lifecycle hooks")
        assert result["parent"] == "system"
        assert "system.hooks" in tree.get_tree()["system"]["children"]

    def test_register_with_explicit_parent(self, tree):
        """Explicit parent overrides dotted-name inference."""
        result = tree.register_entity("new.entity", "A new entity", parent="slvr")
        assert result["parent"] == "slvr"
        assert "new.entity" in tree.get_tree()["slvr"]["children"]

    def test_register_new_root_entity(self, tree):
        """Entity with no parent becomes a new root."""
        result = tree.register_entity("clarity", "Clarity product")
        assert result["status"] == "created"
        assert result["parent"] is None
        assert "clarity" in tree.get_tree()
        assert tree.get_tree()["clarity"]["description"] == "Clarity product"

    def test_register_existing_entity_is_noop(self, tree):
        """Registering an entity that already exists returns 'exists' status."""
        result = tree.register_entity("slvr.marketing", "Different description")
        assert result["status"] == "exists"
        # Original description is preserved
        assert tree.get_tree()["slvr"]["children"]["slvr.marketing"] == "Paid acquisition, content, brand"

    def test_register_persists_to_yaml(self, tree, config_file):
        """Registered entity is persisted back to the YAML file."""
        tree.register_entity("slvr.wholesale", "Wholesale channel")

        # Re-read the file
        with open(config_file, "r") as f:
            data = yaml.safe_load(f)

        assert "slvr.wholesale" in data["entities"]["slvr"]["children"]
        assert data["entities"]["slvr"]["children"]["slvr.wholesale"] == "Wholesale channel"

    def test_register_persisted_flag_on_success(self, tree):
        """Result includes persisted=True when file write succeeds."""
        result = tree.register_entity("slvr.wholesale", "Wholesale channel")
        assert result["persisted"] is True

    def test_register_persisted_flag_on_failure(self, tmp_path):
        """Result includes persisted=False when file write fails."""
        config_path = str(tmp_path / "entities.yaml")
        with open(config_path, "w") as f:
            yaml.dump(SAMPLE_TREE, f)

        t = EntityTree()
        t.load(config_path)

        # Make the file unwritable
        os.chmod(config_path, 0o444)
        try:
            result = t.register_entity("slvr.wholesale", "Wholesale channel")
            assert result["status"] == "created"
            assert result["persisted"] is False
            # Entity is still in memory even though persistence failed
            assert "slvr.wholesale" in t.get_all_entities()
        finally:
            os.chmod(config_path, 0o644)

    def test_registered_entity_passes_validation(self, tree):
        """After registration, the entity passes validation."""
        assert tree.validate_entity("slvr.wholesale") is not None  # Unknown before
        tree.register_entity("slvr.wholesale", "Wholesale channel")
        assert tree.validate_entity("slvr.wholesale") is None  # Known after
