# src/entities.py

import logging
import os
import yaml

logger = logging.getLogger(__name__)

# Default config path relative to project root
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "entities.yaml")


class EntityTree:
    """Hierarchical entity tree loaded from YAML config.

    The tree is configuration, not user data. It provides validation
    and discoverability for entity names used in memory operations.
    """

    def __init__(self):
        self._tree: dict = {}
        self._all_entities: set[str] = set()
        self._config_path: str | None = None

    def load(self, config_path: str | None = None) -> None:
        """Load entity tree from a YAML config file.

        If the file is missing, starts with an empty tree and logs a warning.
        """
        self._config_path = config_path or DEFAULT_CONFIG_PATH

        if not os.path.exists(self._config_path):
            logger.warning(f"Entity config not found at {self._config_path} - starting with empty tree")
            self._tree = {}
            self._all_entities = set()
            return

        try:
            with open(self._config_path, "r") as f:
                data = yaml.safe_load(f)

            if not data or "entities" not in data:
                logger.warning(f"Entity config at {self._config_path} has no 'entities' key - starting with empty tree")
                self._tree = {}
                self._all_entities = set()
                return

            self._tree = data["entities"]
            self._rebuild_entity_set()
            logger.info(f"Loaded entity tree with {len(self._all_entities)} entities from {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to load entity config from {self._config_path}: {e}")
            self._tree = {}
            self._all_entities = set()

    def _rebuild_entity_set(self) -> None:
        """Rebuild the flat set of all known entity names from the tree."""
        self._all_entities = set()
        for root_name, root_data in self._tree.items():
            self._all_entities.add(root_name)
            if isinstance(root_data, dict):
                children = root_data.get("children", {})
                if isinstance(children, dict):
                    for child_name in children:
                        self._all_entities.add(child_name)

    def validate_entity(self, entity: str) -> str | None:
        """Validate an entity name against the tree.

        Returns a warning string if the entity is unknown, or None if valid.
        Unknown entities produce warnings, not errors.
        """
        if not self._all_entities:
            return None  # No tree loaded, skip validation
        if entity in self._all_entities:
            return None
        return f"Unknown entity '{entity}' - not in entity tree"

    def validate_project(self, project: str) -> str | None:
        """Validate a project name against root entities in the tree.

        Projects must match a root entity name or be 'global'.
        Returns an error string if invalid, or None if valid.
        """
        if project == "global":
            return None
        if not self._tree:
            return None  # No tree loaded, skip validation
        if project in self._tree:
            return None
        return f"Unknown project '{project}' - must be a root entity or 'global'"

    def register_entity(self, entity: str, description: str, parent: str | None = None) -> dict:
        """Add a new entity to the tree at runtime.

        If the entity already exists, returns the existing entry as a no-op.
        Infers parent from dotted prefix if not provided.
        Persists back to the YAML config file if writable.
        """
        if entity in self._all_entities:
            return {
                "status": "exists",
                "entity": entity,
                "parent": parent or self._infer_parent(entity),
                "persisted": False
            }

        # Infer parent from dotted name if not provided
        if not parent:
            parent = self._infer_parent(entity)

        # Add to tree
        if parent and parent in self._tree:
            # Add as child of existing root
            if "children" not in self._tree[parent] or not isinstance(self._tree[parent].get("children"), dict):
                self._tree[parent]["children"] = {}
            self._tree[parent]["children"][entity] = description
        elif parent and parent in self._all_entities:
            # Parent is a child entity — find its root and add as sibling
            root = self._find_root(parent)
            if root and root in self._tree:
                if "children" not in self._tree[root] or not isinstance(self._tree[root].get("children"), dict):
                    self._tree[root]["children"] = {}
                self._tree[root]["children"][entity] = description
            else:
                # Can't find root, add as new root
                self._tree[entity] = {"description": description, "children": {}}
        else:
            # No valid parent, add as new root
            self._tree[entity] = {"description": description, "children": {}}

        self._all_entities.add(entity)

        # Persist to YAML
        persisted = self._persist()

        return {
            "status": "created",
            "entity": entity,
            "parent": parent,
            "persisted": persisted
        }

    def _infer_parent(self, entity: str) -> str | None:
        """Infer parent entity from dotted name (e.g., 'slvr.wholesale' -> 'slvr')."""
        if "." in entity:
            return entity.rsplit(".", 1)[0]
        return None

    def _find_root(self, entity: str) -> str | None:
        """Find the root entity that contains a given child entity."""
        for root_name, root_data in self._tree.items():
            if isinstance(root_data, dict):
                children = root_data.get("children", {})
                if isinstance(children, dict) and entity in children:
                    return root_name
        return None

    def _persist(self) -> bool:
        """Write the current tree back to the YAML config file.

        Returns True if successful, False if the file is not writable.
        """
        if not self._config_path:
            logger.warning("No config path set - cannot persist entity tree")
            return False

        try:
            data = {"entities": self._tree}
            with open(self._config_path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            logger.info(f"Persisted entity tree to {self._config_path}")
            return True
        except (OSError, IOError) as e:
            logger.warning(f"Failed to persist entity tree to {self._config_path}: {e}")
            return False

    def get_tree(self) -> dict:
        """Return the full entity tree structure."""
        return self._tree

    def get_root_entities(self) -> list[str]:
        """Return the list of root entity names (valid project names)."""
        return list(self._tree.keys())

    def get_all_entities(self) -> set[str]:
        """Return the set of all known entity names."""
        return set(self._all_entities)


# Module-level singleton — auto-loads from default config
entity_tree = EntityTree()
entity_tree.load()
