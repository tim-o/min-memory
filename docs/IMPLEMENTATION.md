# Memory MCP Server - Implementation Document

## Overview
Migration from dual storage (SQLite + Qdrant) to vector-only (Qdrant) with hierarchical memory system supporting global/project/task scopes.

## Architecture Changes

### Storage Migration
**Before:** SQLite for facts, Qdrant for interactions
**After:** Single Qdrant collection "memories" for everything

### Collection Schema
```python
collection_name = "memories"
vector_size = 384  # all-MiniLM-L6-v2
distance = COSINE

# Payload indexes for fast filtering
indexes = ["scope", "project", "memory_type", "entity"]
```

### Memory Schema
```python
{
    # Identity
    "id": "mem_clarity_1728404321_a3f",  # Semantic ID

    # Content
    "text": "Clarity uses hierarchical context loading",
    "embedding": [float] * 384,

    # Type and scope
    "memory_type": "project_context",  # core_identity | project_context | task_instruction | episodic
    "scope": "project",  # global | project | task

    # Context
    "entity": "clarity",
    "project": "clarity",  # Required if scope != global
    "task_id": None,  # Required if scope == task

    # Relations
    "related_to": ["mem_001", "mem_002"],  # List of memory IDs
    "relation_types": {
        "mem_001": "implements",
        "mem_002": "supersedes"
    },

    # Metadata
    "tags": ["architecture", "context_loading"],
    "created_at": "2025-10-08T15:30:00",
    "updated_at": "2025-10-08T15:30:00",

    # Task-specific (optional)
    "status": None,  # active | completed | blocked
    "priority": None
}
```

## Implementation Phases

### Phase 1: Core Storage Refactor

#### 1.1 Update Dependencies
- Remove: `sqlite3`
- Keep: `qdrant-client`, `sentence-transformers`, `mcp`

#### 1.2 Initialize Qdrant Collection
```python
# Remove SQLite db connection
# Create single "memories" collection
# Add payload indexes: scope, project, memory_type, entity
```

#### 1.3 Remove Old Setup
- Delete SQLite table creation
- Delete facts and master_list tables
- Remove interactions collection (merge into memories)

#### 1.4 Helper Functions
```python
def generate_memory_id(entity: str, timestamp: str) -> str:
    """Generate semantic ID: mem_{entity}_{timestamp_hash}"""

def create_memory_point(memory_data: dict) -> PointStruct:
    """Create Qdrant point from memory data"""

def build_filter(scope=None, project=None, memory_type=None, task_id=None):
    """Build Qdrant filter from parameters"""
```

### Phase 2: Implement New Tools

#### 2.1 store_memory()
```python
Tool(
    name="store_memory",
    description="Store any type of memory with appropriate scope",
    inputSchema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "memory_type": {
                "type": "string",
                "enum": ["core_identity", "project_context", "task_instruction", "episodic"]
            },
            "scope": {
                "type": "string",
                "enum": ["global", "project", "task"]
            },
            "entity": {"type": "string"},
            "project": {"type": "string"},  # optional
            "task_id": {"type": "string"},  # optional
            "related_to": {
                "type": "array",
                "items": {"type": "string"}
            },  # optional
            "relation_types": {"type": "object"},  # optional
            "tags": {
                "type": "array",
                "items": {"type": "string"}
            },  # optional
            "status": {"type": "string"},  # optional
            "priority": {"type": "integer"}  # optional
        },
        "required": ["text", "memory_type", "scope", "entity"]
    }
)
```

**Implementation:**
1. Validate scope/project/task_id requirements
2. Generate embedding from text
3. Generate semantic memory ID
4. Create payload with all metadata
5. Upsert to Qdrant
6. Return memory ID

**Validation rules:**
- If scope="project" or scope="task", project is required
- If scope="task", task_id is required
- If related_to provided, relation_types should match

#### 2.2 retrieve_context()
```python
Tool(
    name="retrieve_context",
    description="Hierarchical context retrieval with scoping",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "scope": {"type": "string"},  # optional filter
            "memory_type": {
                "type": "array",
                "items": {"type": "string"}
            },  # optional
            "project": {"type": "string"},  # optional
            "task_id": {"type": "string"},  # optional
            "include_related": {"type": "boolean", "default": True},
            "limit": {"type": "integer", "default": 10},
            "score_threshold": {"type": "number", "default": 0.0}
        },
        "required": ["query"]
    }
)
```

**Implementation:**
1. Generate query embedding
2. Build metadata filter from parameters
3. Search Qdrant with filter
4. Filter by score_threshold
5. If include_related=True, fetch related memories (1 hop)
6. Return results with scores and relations

**Hierarchical retrieval logic:**
- If project provided: return global + project + task (filtered to that project)
- If no project: return only global scope
- Always respect explicit scope filter if provided

#### 2.3 set_project()
```python
Tool(
    name="set_project",
    description="Validate project exists and return summary",
    inputSchema={
        "type": "object",
        "properties": {
            "project": {"type": "string"}
        },
        "required": ["project"]
    }
)
```

**Implementation:**
1. Query Qdrant for memories with project={project}
2. If none found, create placeholder project memory
3. Count memories by memory_type
4. Get most recent update timestamp
5. Return summary:
```python
{
    "project": "clarity",
    "exists": True,
    "memory_count": 47,
    "by_type": {
        "project_context": 12,
        "task_instruction": 5,
        "episodic": 30
    },
    "last_updated": "2025-10-08T...",
}
```

#### 2.4 get_context_info()
```python
Tool(
    name="get_context_info",
    description="Get environment information for project detection",
    inputSchema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
```

**Implementation:**
1. Get current working directory from os.getcwd()
2. Check if git repo exists
3. If git repo, extract: repo name, branch, remote
4. Return:
```python
{
    "platform": "claude_code",
    "pwd": "/path/to/min-memory",
    "git_info": {
        "repo": "min-memory",
        "branch": "main",
        "remote": "github.com/user/min-memory"
    } or None,
    "timestamp": "2025-10-08T..."
}
```

#### 2.5 link_memories()
```python
Tool(
    name="link_memories",
    description="Create explicit relationship between memories",
    inputSchema={
        "type": "object",
        "properties": {
            "memory_id": {"type": "string"},
            "related_id": {"type": "string"},
            "relation_type": {
                "type": "string",
                "enum": ["supports", "contradicts", "supersedes", "refines",
                        "depends_on", "implements", "example_of"]
            }
        },
        "required": ["memory_id", "related_id", "relation_type"]
    }
)
```

**Implementation:**
1. Retrieve memory_id from Qdrant
2. Add related_id to related_to list
3. Add relation_type to relation_types dict
4. Update point in Qdrant
5. Optionally create bidirectional link (related_id → memory_id)
6. Return confirmation

#### 2.6 list_entities()
```python
Tool(
    name="list_entities",
    description="List all known entities with optional filtering",
    inputSchema={
        "type": "object",
        "properties": {
            "scope": {"type": "string"},
            "project": {"type": "string"},
            "memory_type": {"type": "string"}
        },
        "required": []
    }
)
```

**Implementation:**
1. Query Qdrant with filters (scroll through all points)
2. Aggregate by entity
3. Count memories per entity
4. Get first_seen and last_updated timestamps
5. Return:
```python
{
    "entities": [
        {
            "name": "user_preferences",
            "scope": "global",
            "memory_count": 12,
            "first_seen": "2025-09-15T...",
            "last_updated": "2025-10-08T..."
        },
        ...
    ],
    "count": 15
}
```

#### 2.7 search_entities()
```python
Tool(
    name="search_entities",
    description="Fuzzy search for entities to prevent fragmentation",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "scope": {"type": "string"},
            "limit": {"type": "integer", "default": 5}
        },
        "required": ["query"]
    }
)
```

**Implementation:**
1. Get all entities from Qdrant
2. Use fuzzy string matching (difflib.SequenceMatcher or similar)
3. Return top matches with scores:
```python
{
    "matches": [
        {
            "entity": "clarity",
            "scope": "project",
            "project": "clarity",
            "score": 0.95
        },
        ...
    ]
}
```

### Phase 3: Data Migration

#### 3.1 Migrate Existing Facts
```python
def migrate_facts_to_memories():
    """One-time migration from SQLite facts to Qdrant memories"""

    # Read all facts from SQLite
    facts = db.execute("SELECT entity, attribute, value, timestamp FROM facts").fetchall()

    for entity, attribute, value, timestamp in facts:
        # Determine scope
        if entity in ["user_preferences", "system", "technical"]:
            scope = "global"
            memory_type = "core_identity"
            project = None
        elif entity == "clarity":
            scope = "project"
            memory_type = "project_context"
            project = "clarity"
        else:
            scope = "global"
            memory_type = "core_identity"
            project = None

        # Create memory text
        text = f"{entity}.{attribute}: {value}"

        # Store as memory
        store_memory(
            text=text,
            memory_type=memory_type,
            scope=scope,
            entity=entity,
            project=project
        )
```

**Execution:**
- Run migration function on server startup if SQLite DB exists
- Log migrated facts
- Optionally backup SQLite DB before removal

### Phase 4: Update Configuration

#### 4.1 Local Settings (.claude/settings.local.json)
```json
{
  "permissions": {
    "allow": [
      "mcp__memory__retrieve_context",
      "mcp__memory__get_facts",
      "mcp__memory__get_all_facts",
      "mcp__memory__store_memory",
      "mcp__memory__set_project",
      "mcp__memory__get_context_info",
      "mcp__memory__list_entities"
    ],
    "deny": [],
    "ask": []
  }
}
```

#### 4.2 Remove Old Tools
Delete from tool list:
- `store_interaction` (replaced by store_memory with memory_type=episodic)
- `store_fact` (replaced by store_memory)
- `store_facts` (use store_memory in loop)
- `get_facts` (use retrieve_context with entity filter)
- `get_all_facts` (use list_entities or retrieve_context with no filters)

### Phase 5: Testing

#### Test 1: Basic Storage & Retrieval
```python
# Store global memory
store_memory(
    text="User prefers concise communication",
    memory_type="core_identity",
    scope="global",
    entity="user_preferences"
)

# Retrieve it
retrieve_context(
    query="communication style",
    scope="global"
)
# Expected: Returns the memory with high score
```

#### Test 2: Project Context
```python
# Set project
set_project(project="clarity")
# Expected: Returns project summary

# Store project memory
store_memory(
    text="Clarity uses vector-only storage",
    memory_type="project_context",
    scope="project",
    entity="clarity",
    project="clarity"
)

# Retrieve with project filter
retrieve_context(
    query="storage architecture",
    project="clarity"
)
# Expected: Returns project memory + relevant global memories
```

#### Test 3: Hierarchical Retrieval
```python
# Store global
store_memory(text="User values elegance", scope="global", ...)

# Store project
store_memory(text="Clarity architecture", scope="project", project="clarity", ...)

# Retrieve hierarchically
retrieve_context(
    query="system design",
    project="clarity"
)
# Expected: Returns both global and project memories
```

#### Test 4: Relations
```python
# Store two memories
id1 = store_memory(text="Proposed dual storage", ...)
id2 = store_memory(text="Decided vector-only", ...)

# Link them
link_memories(
    memory_id=id2,
    related_id=id1,
    relation_type="supersedes"
)

# Retrieve with relations
retrieve_context(query="storage decision", include_related=True)
# Expected: Returns id2 with id1 in related_memories
```

#### Test 5: Server Restart Persistence
```bash
# Store memories
# Restart MCP server (restart Claude Code)
# Retrieve memories
# Expected: All memories persist
```

#### Test 6: Entity Management
```python
# List entities
list_entities()
# Expected: Returns user_preferences, clarity, etc.

# Search entities
search_entities(query="clar")
# Expected: Finds "clarity" with high score
```

## Implementation Order

1. **Phase 1:** Refactor storage (remove SQLite, create unified collection)
2. **Phase 2.1:** Implement store_memory()
3. **Phase 2.2:** Implement retrieve_context()
4. **Phase 3:** Migrate existing facts
5. **Test 1-3:** Verify basic functionality
6. **Phase 2.3-2.7:** Implement remaining tools
7. **Phase 4:** Update configuration
8. **Test 4-6:** Verify advanced functionality

## Files to Modify

- `memory_mcp_server.py` - Complete rewrite of tool handlers
- `.claude/settings.local.json` - Update permissions
- `IMPLEMENTATION.md` - This document (tracking progress)

## Files to Create

- None (migration is one-time, can be inline)

## Files to Remove/Archive

- SQLite database handling code
- Old tool definitions

## Success Criteria

✅ All 12 existing facts migrated to vector storage
✅ Global scope memories retrievable across sessions
✅ Project scope memories filter correctly
✅ Hierarchical retrieval works (global + project)
✅ Memory relations track correctly
✅ Entity management prevents fragmentation
✅ Server restart preserves all data
✅ No SQLite dependencies remain

## Rollback Plan

If migration fails:
1. Backup current `memory_mcp_server.py`
2. Keep SQLite database file
3. Can revert to current implementation
4. Qdrant data is separate, won't interfere

## Notes

- Memory IDs use format: `mem_{entity}_{timestamp_hash}`
- set_project() is stateless - just validates and returns summary
- retrieve_context() requires explicit project parameter for project context
- All timestamps in ISO 8601 format
- Embeddings cached in Qdrant (no re-computation on retrieval)

## Git Integration Details

```python
import git

def get_git_info(path: str) -> dict:
    """Extract git repository information"""
    try:
        repo = git.Repo(path, search_parent_directories=True)
        return {
            "repo": repo.working_dir.split("/")[-1],
            "branch": repo.active_branch.name,
            "remote": repo.remotes.origin.url if repo.remotes else None
        }
    except (git.InvalidGitRepositoryError, git.NoSuchPathError):
        return None
```

Requires: `gitpython` dependency

---

**Status:** Ready for implementation
**Estimated time:** 2-3 hours
**Risk level:** Low (can rollback, data preserved)
