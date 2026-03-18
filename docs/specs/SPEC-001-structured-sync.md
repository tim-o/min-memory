# SPEC-001: Structured Session Sync, Recency-Weighted Retrieval, and Entity Validation

> **Status:** Draft
> **Author:** Tim + Claude
> **Created:** 2026-03-16
> **Updated:** 2026-03-16

---

## What

### Goal

Replace ad-hoc `store_memory` calls from agents with a structured `sync_session` tool that enforces consistent memory categorization, automatic type/scope inference, and upsert semantics. Enhance `retrieve_context` with recency weighting so recent memories surface appropriately alongside semantically relevant ones. Add a server-side entity tree so entity names are validated and discoverable.

Together these changes make the memory layer more structured (fewer malformed writes), more useful (recency-aware reads), and more navigable (entity tree as a shared ontology between agents and humans).

### Acceptance Criteria

- [ ] **AC-01:** `sync_session` tool is registered and callable via MCP transport and the REST `/api/tools/call` endpoint.
- [ ] **AC-02:** `sync_session` accepts the structured payload (decisions, status_updates, learnings, feedback arrays) and stores each item with the correct `memory_type` and `scope` auto-set per the category mapping.
- [ ] **AC-03:** `decisions` and `learnings` items always create new memory records (append-only).
- [ ] **AC-04:** `status_updates` items upsert: find existing record by `(entity, user, project, memory_type="project_context")`, update if found, create if not.
- [ ] **AC-05:** `feedback` items upsert: find existing record by `(entity, user, memory_type="core_identity")`, update if found, create if not.
- [ ] **AC-06:** When `supersedes` is provided on a decisions or learnings item, a `supersedes` relation is created via the existing `link_memories` logic.
- [ ] **AC-07:** `sync_session` returns a structured summary: counts of created/updated records, list of memory IDs, and any warnings.
- [ ] **AC-08:** `sync_session` validates the `project` field against a known set (entity tree root nodes plus "global"); rejects unknown projects with an error.
- [ ] **AC-09:** `sync_session` validates entity names against the entity tree; unknown entities produce a warning in the response (not a hard error).
- [ ] **AC-10:** `retrieve_context` accepts a `recency_weight` parameter (float 0.0-1.0, default 0.3) that blends similarity and recency scores.
- [ ] **AC-11:** `retrieve_context` accepts a `status_filter` parameter (optional list of strings) for filtering `project_context` memories by status.
- [ ] **AC-12:** When `retrieve_context` queries project scope without an explicit `status_filter`, `project_context` type results are auto-filtered to `status=active`.
- [ ] **AC-13:** Recency scoring uses exponential decay: `recency_score = exp(-lambda * age_days)` where `lambda = ln(2) / half_life_days`, with a default half-life of 30 days.
- [ ] **AC-14:** Entity tree is loaded from a YAML config file at server startup.
- [ ] **AC-15:** A `register_entity` tool allows adding new entities to the tree at runtime (persisted back to the config file).
- [ ] **AC-16:** `list_entities` is enhanced to optionally return the configured entity tree structure (not just entities observed in stored memories).
- [ ] **AC-17:** All new tool parameters have JSON Schema definitions in the `list_tools` registration.
- [ ] **AC-18:** Existing `store_memory`, `retrieve_context`, and `list_entities` tools continue to work unchanged for callers that do not use the new parameters.
- [ ] **AC-19:** `retrieve_context` and `search` increment an `access_count` field and update `last_accessed_at` on every memory returned in results. Updates are fire-and-forget (async, non-blocking on response).
- [ ] **AC-20:** `access_count` defaults to 0 and `last_accessed_at` defaults to null for existing memories that have never been accessed through the new code path.

### Scope

**Create:**
| File/Artifact | Purpose |
|---------------|---------|
| `src/entities.py` | Entity tree loading, validation, registration, persistence |
| `config/entities.yaml` | Default entity tree configuration |
| `tests/test_sync_session.py` | Unit tests for sync_session tool |
| `tests/test_recency.py` | Unit tests for recency weighting logic |
| `tests/test_entities.py` | Unit tests for entity validation and registration |

**Modify:**
| File/Artifact | Change |
|---------------|--------|
| `src/tools.py` | Add `sync_session` and `register_entity` tool definitions and handlers; enhance `retrieve_context` with recency weighting and status filter; enhance `list_entities` with tree output |
| `src/storage.py` | Add `find_by_entity` helper for upsert lookups; add `build_status_filter` or extend `build_filter` with status conditions |
| `requirements.txt` | Add `pyyaml>=6.0` |

**Out of Scope:**
- Migration of existing memories to the entity tree (existing data is unaffected)
- Changes to authentication or the REST API layer
- UI or client-side changes (callers adopt `sync_session` at their own pace)
- Batch retrieval or bulk export tools
- Configurable half-life per project or memory type (use a single global default; can be extended later)

### Dependencies

- Qdrant payload index on `entity` field already exists (confirmed in `storage.py:setup_qdrant`)
- Qdrant payload index on `status` field does NOT exist; must be added
- `pyyaml` package must be added to requirements

### Edge Cases

- **Empty arrays in sync_session payload:** All category arrays are optional. A call with `{"project": "slvr"}` and no arrays returns a success summary with zero operations.
- **Duplicate entity in single sync call:** Two status_updates with the same entity in one call -- process sequentially, second overwrites first (last-write-wins within a single call).
- **Upsert finds multiple existing records:** If `find_by_entity` returns more than one match (data inconsistency from prior ad-hoc writes), update the most recently updated one and log a warning.
- **Entity tree file missing at startup:** Server starts with an empty tree and logs a warning. All entity validation warnings fire, but nothing blocks.
- **Recency weight on memories with no `created_at`:** Treat as maximally old (recency_score = 0.0).
- **`supersedes` references a non-existent memory ID:** Return a warning in the response; still store the new memory (do not create the link).
- **`register_entity` with an entity that already exists:** No-op, return the existing entry.
- **Access tracking on large result sets:** If `retrieve_context` returns 20 results, 20 async upserts fire. This is acceptable for typical usage; Qdrant handles concurrent point updates well. If performance becomes an issue, batch into a single `upsert` call.
- **Access tracking on memories without `access_count`:** Treat missing field as 0; set to 1 on first tracked access.
- **Config file not writable (e.g., in container):** `register_entity` updates the in-memory tree and logs a warning that persistence failed. Tree is rebuilt from file on next restart, so ephemeral additions are lost. This is acceptable since the primary use case is manual config edits.

---

## Who

### Agent Roles

| Agent | Model | Scope | Responsibilities |
|-------|-------|-------|-----------------|
| orchestrator | opus | Coordination | Break down into FUs, delegate, review integration |
| backend | sonnet | `src/`, `config/`, `tests/` | Implement all code changes |
| reviewer | opus | Read-only | Review against ACs and project conventions |

### Collaborator Map

- backend implements FU-1 through FU-4 sequentially (FU-2 depends on FU-1, FU-3 depends on FU-1)
- reviewer checks after each FU is complete
- Escalate to orchestrator when: upsert semantics are ambiguous, or Qdrant query patterns need architectural review

---

## How

### Approach

The implementation follows the existing patterns in `tools.py`: tools are defined in `list_tools()` and handled in the `call_tool()` if/elif chain. New helper modules keep the main tools file from growing unwieldy.

The entity tree is a simple hierarchical data structure loaded from YAML. It is deliberately not stored in Qdrant -- it is configuration, not user data, and must be readable without authentication.

Recency weighting is applied post-query: Qdrant returns results by vector similarity, then scores are re-ranked in Python. This avoids needing Qdrant-side scoring customization and keeps the change localized.

1. **Build entity module** -- load/validate/register entities from YAML config
2. **Build sync_session tool** -- structured write path with auto-typing, upsert, and entity validation
3. **Enhance retrieve_context** -- add recency blending and status filtering
4. **Enhance list_entities and add register_entity** -- expose the entity tree

### Functional Units

1. **FU-1: Entity tree module** -- backend -- `src/entities.py`, `config/entities.yaml` -- depends on: none
2. **FU-2: sync_session tool** -- backend -- `src/tools.py`, `src/storage.py` -- depends on: FU-1
3. **FU-3: retrieve_context enhancements** -- backend -- `src/tools.py`, `src/storage.py` -- depends on: none (can parallel with FU-2)
4. **FU-4: list_entities enhancement and register_entity tool** -- backend -- `src/tools.py` -- depends on: FU-1

### Contracts

#### sync_session input schema

```json
{
  "type": "object",
  "properties": {
    "project": {
      "type": "string",
      "description": "Project identifier. Must match a root entity in the entity tree, or 'global'."
    },
    "decisions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "text": {"type": "string"},
          "entity": {"type": "string"},
          "tags": {"type": "array", "items": {"type": "string"}},
          "supersedes": {"type": "string", "description": "Memory ID this decision supersedes"}
        },
        "required": ["text", "entity"]
      }
    },
    "status_updates": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "entity": {"type": "string"},
          "status": {"type": "string", "enum": ["active", "completed", "superseded", "parked"]},
          "text": {"type": "string"}
        },
        "required": ["entity", "status", "text"]
      }
    },
    "learnings": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "text": {"type": "string"},
          "entity": {"type": "string"},
          "tags": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["text", "entity"]
      }
    },
    "feedback": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "entity": {"type": "string"},
          "text": {"type": "string"}
        },
        "required": ["entity", "text"]
      }
    }
  },
  "required": ["project"]
}
```

#### Category-to-storage mapping

| Category | `memory_type` | `scope` | Write mode |
|----------|--------------|---------|------------|
| decisions | `episodic` | `project` (or `global` if project="global") | Append (always new) |
| status_updates | `project_context` | `project` | Upsert by `(entity, user, project)` |
| learnings | `episodic` | `project` (or `global` if project="global") | Append (always new) |
| feedback | `core_identity` | `global` | Upsert by `(entity, user)` |

#### sync_session response shape

```json
{
  "summary": {
    "created": 3,
    "updated": 1,
    "warnings": ["Unknown entity 'slvr.roasting' - not in entity tree"]
  },
  "details": {
    "decisions": [
      {"memory_id": "uuid-1", "action": "created"}
    ],
    "status_updates": [
      {"memory_id": "uuid-2", "action": "updated", "previous_id": "uuid-2"}
    ],
    "learnings": [
      {"memory_id": "uuid-3", "action": "created"}
    ],
    "feedback": [
      {"memory_id": "uuid-4", "action": "created"}
    ]
  }
}
```

#### Upsert lookup (new storage helper)

```python
def find_by_entity(user: str, entity: str, project: str | None = None,
                   memory_type: str | None = None) -> list[ScoredPoint]:
    """Find memories matching exact entity + user + optional project/type.
    Returns points sorted by updated_at descending. Used for upsert logic."""
```

This uses `qdrant.scroll()` with `build_filter(user=user, entity=entity, project=project, memory_type=memory_type)`, which is already supported by the existing `build_filter` function (it has an `entity` parameter).

#### retrieve_context enhanced parameters

New parameters added to existing schema:

```json
{
  "recency_weight": {
    "type": "number",
    "minimum": 0.0,
    "maximum": 1.0,
    "default": 0.3,
    "description": "Blend weight for recency vs similarity. 0.0=pure similarity, 1.0=heavily favor recent."
  },
  "status_filter": {
    "type": "array",
    "items": {"type": "string"},
    "description": "Filter project_context memories by status. Default: ['active'] for project-scoped queries."
  }
}
```

#### Recency scoring formula

```python
import math
from datetime import datetime

def compute_recency_score(created_at: str | None, half_life_days: float = 30.0) -> float:
    """Exponential decay from 1.0 (now) toward 0.0."""
    if not created_at:
        return 0.0
    try:
        created = datetime.fromisoformat(created_at)
        age_days = (datetime.now() - created).total_seconds() / 86400.0
        decay_lambda = math.log(2) / half_life_days
        return math.exp(-decay_lambda * max(age_days, 0.0))
    except (ValueError, TypeError):
        return 0.0

def blend_scores(similarity: float, recency: float, recency_weight: float) -> float:
    """Combine similarity and recency into a final ranking score."""
    return similarity * (1.0 - recency_weight) + recency * recency_weight
```

#### retrieve_context status filter behavior

When querying with a project and no explicit `status_filter`:
1. Query Qdrant as before (no status filter at the Qdrant level -- status is not always present).
2. Post-filter: for results where `memory_type == "project_context"`, exclude those with `status` not in `["active"]` (or `status is None`, which passes through for backward compatibility).
3. If `status_filter` is explicitly provided, apply it to `project_context` results instead of the default.
4. Non-`project_context` results are never status-filtered.

This post-filter approach avoids splitting queries by memory type and keeps the Qdrant query simple.

#### entities.yaml schema

```yaml
# config/entities.yaml
entities:
  tim:
    description: "User identity and preferences"
    children:
      tim.preferences: "Communication style, workflow preferences"
  slvr:
    description: "Saint Lawrence Valley Roasters"
    children:
      slvr.marketing: "Paid acquisition, content, brand"
      slvr.financials: "Revenue, FCF, compensation"
      slvr.operations: "Production, shipping, roaster"
  tsc:
    description: "The Sunday Carpenter"
    children:
      tsc.classes: "Teaching events"
      tsc.marketing: "Content, community"
  system:
    description: "Operating system infrastructure"
    children:
      system.memory-protocol: "Memory conventions"
      system.sdlc: "Development workflow"
```

#### register_entity input schema

```json
{
  "type": "object",
  "properties": {
    "entity": {
      "type": "string",
      "description": "Dotted entity name (e.g., 'slvr.wholesale')"
    },
    "description": {
      "type": "string",
      "description": "Human-readable description of this entity"
    },
    "parent": {
      "type": "string",
      "description": "Parent entity name. Inferred from dotted prefix if omitted."
    }
  },
  "required": ["entity", "description"]
}
```

#### register_entity response shape

```json
{
  "status": "created",
  "entity": "slvr.wholesale",
  "parent": "slvr",
  "persisted": true
}
```

#### list_entities enhanced response (when `show_tree=true`)

New optional parameter `show_tree` (boolean, default false). When true, response includes the configured tree alongside the observed entities:

```json
{
  "entities": [ ... ],
  "count": 5,
  "tree": {
    "slvr": {
      "description": "Saint Lawrence Valley Roasters",
      "children": {
        "slvr.marketing": "Paid acquisition, content, brand",
        "slvr.financials": "Revenue, FCF, compensation"
      }
    }
  }
}
```

#### Qdrant index addition

A payload index on `status` (keyword type) must be added. This should be handled in `setup_qdrant()` using `create_payload_index` with the same pattern as existing indexes. Since the collection already exists in production, this needs to be an additive migration -- call `create_payload_index` and catch the "already exists" case gracefully (Qdrant handles this idempotently).

### Testing Requirements

- **Unit tests:** All new functions in `entities.py` (load, validate, register, persist). Recency score computation. sync_session category mapping logic. Upsert find-and-update logic.
- **Integration tests:** Full `sync_session` call through `call_tool` with a mock Qdrant client. `retrieve_context` with recency weighting against mock results. `register_entity` persistence round-trip.
- **Backward compatibility:** Existing `store_memory` and `retrieve_context` calls with no new parameters produce identical results.

---

## Validation

### Review Criteria

- [ ] Every AC is met
- [ ] New tool definitions follow the existing pattern in `list_tools()` / `call_tool()`
- [ ] User isolation is maintained (all queries include user filter)
- [ ] Soft-delete exclusion is maintained in new queries
- [ ] No breaking changes to existing tool signatures
- [ ] Entity tree config is not user-specific data (no auth needed to read it)
- [ ] Tests pass

### AC-to-Test Mapping

| AC | Test | Type |
|----|------|------|
| AC-01 | `test_sync_session_registered_in_list_tools` | unit |
| AC-02 | `test_sync_session_auto_sets_type_and_scope` | unit |
| AC-03 | `test_sync_session_decisions_always_append` | integration |
| AC-04 | `test_sync_session_status_upsert_creates_and_updates` | integration |
| AC-05 | `test_sync_session_feedback_upsert_creates_and_updates` | integration |
| AC-06 | `test_sync_session_supersedes_creates_link` | integration |
| AC-07 | `test_sync_session_returns_summary` | unit |
| AC-08 | `test_sync_session_rejects_unknown_project` | unit |
| AC-09 | `test_sync_session_warns_unknown_entity` | unit |
| AC-10 | `test_retrieve_context_recency_weight_parameter` | integration |
| AC-11 | `test_retrieve_context_status_filter_parameter` | integration |
| AC-12 | `test_retrieve_context_auto_filters_active_status` | integration |
| AC-13 | `test_recency_score_exponential_decay` | unit |
| AC-14 | `test_entity_tree_loads_from_yaml` | unit |
| AC-15 | `test_register_entity_adds_to_tree` | unit |
| AC-16 | `test_list_entities_show_tree` | integration |
| AC-17 | `test_new_tools_have_json_schema` | unit |
| AC-18 | `test_existing_tools_backward_compatible` | integration |
| AC-19 | `test_access_tracking_increments_count` | integration |
| AC-20 | `test_access_tracking_defaults_for_existing_memories` | unit |

### UAT Plan

- [ ] Call `sync_session` with all four category types populated; verify each stored memory has correct `memory_type` and `scope` by fetching with `fetch` tool.
- [ ] Call `sync_session` twice with the same `status_updates` entity; verify only one memory exists for that entity (upserted, not duplicated) by calling `list_entities`.
- [ ] Call `sync_session` with a `supersedes` field; verify the link exists by fetching the new memory and checking `related_to`.
- [ ] Call `sync_session` with an unknown entity; verify the response includes a warning but all records are still stored.
- [ ] Call `sync_session` with an unknown project; verify the response is an error.
- [ ] Call `retrieve_context` with `recency_weight=0.0`; verify results are ordered by similarity only (same as current behavior).
- [ ] Call `retrieve_context` with `recency_weight=0.9`; verify a recently stored memory ranks higher than an older but more similar memory.
- [ ] Call `retrieve_context` for a project without `status_filter`; verify `project_context` results only include `status=active` or `status=null`.
- [ ] Call `register_entity` with a new entity; verify it appears in `list_entities` with `show_tree=true`.
- [ ] Call existing `store_memory` and `retrieve_context` without new parameters; verify behavior is unchanged.
- [ ] Call `retrieve_context` twice for the same query; fetch a returned memory and verify `access_count` is 2 and `last_accessed_at` is recent.

### Completeness Checklist

- [x] Every AC has a stable ID
- [x] Every AC maps to at least one test
- [x] Every cross-domain boundary has a contract (sync_session input/output, retrieve_context params, entity config schema, register_entity input/output)
- [x] Out-of-scope is explicit
- [x] Edge cases documented with expected behavior
- [x] Testing requirements map to ACs

---

## Decisions Requiring Your Input

1. **Status index migration strategy**: The `status` payload index needs to be added to the existing Qdrant collection. Qdrant's `create_payload_index` is idempotent, so calling it on an existing collection is safe. The plan is to add it to `setup_qdrant()` alongside the other index creations. This will run automatically on next deploy. **Confirm this is acceptable**, or if you want a separate migration script.

2. **Entity tree file location**: Spec proposes `config/entities.yaml` at the project root. Alternative: `src/entities.yaml` to keep it closer to code. The `config/` directory does not exist yet. **Your preference?**

3. **register_entity persistence in containers**: When running in Docker, the config file may be on a read-only filesystem. The spec handles this gracefully (in-memory only, warning logged, lost on restart). If you want registered entities to survive restarts in production, we would need to either mount the config directory as a writable volume or store the tree in Qdrant as a system record. **Is the current "best-effort persistence" approach acceptable for now?**
