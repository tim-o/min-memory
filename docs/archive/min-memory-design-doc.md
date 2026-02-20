# MCP-Based Memory System Design Document

## Executive Summary

This document outlines the design for a persistent, hierarchical memory system using the Model Context Protocol (MCP) to enable AI assistants (initially Claude via Claude Code, with path to local models) to maintain long-term memory across sessions. The system uses vector-only storage with metadata-based scoping to provide three memory layers: global (core identity), project (context-specific), and task (objective-specific), with explicit memory relations and automatic project detection.

## System Overview

### Core Concept
Enable Claude Code (and eventually local models) to remember conversations, facts, and context across sessions by exposing memory operations as MCP tools. The system automatically loads context based on a three-tier hierarchy: always-on core identity, project-specific context, and task-specific instructions.

### Architecture

```
┌─────────────────────────────────────────────────┐
│  AI Client (Claude Code / Desktop / Local)      │
│  - Auto-detects project from environment        │
│  - Loads hierarchical context                   │
│  - Uses memory tools via MCP                    │
└─────────────────┬───────────────────────────────┘
                  │
                  │ MCP Protocol (JSON-RPC over stdio)
                  ↓
┌─────────────────────────────────────────────────┐
│  MCP Memory Server                              │
│                                                 │
│  Tools:                                         │
│  • get_context_info() - Environment detection   │
│  • store_memory() - Hierarchical storage        │
│  • retrieve_context() - Scoped retrieval        │
│  • set_project() - Explicit project selection   │
│  • link_memories() - Create relationships       │
│  • list_entities() - Entity discovery           │
│  • search_entities() - Fuzzy entity matching    │
│                                                 │
│  Components:                                    │
│  • Sentence Transformer (embeddings)           │
│  • Qdrant (vector storage + metadata)          │
│  • Project detection logic                      │
└─────────────────────────────────────────────────┘
                  │
                  ↓
         ┌────────────────┐
         │  Qdrant DB      │
         │  (vector-only)  │
         │                 │
         │  All memory     │
         │  types stored   │
         │  with metadata  │
         └─────────────────┘
```

## Memory Hierarchy

### Three-Tier Scope System

#### 1. Global Scope
**Purpose:** Core identity - universal facts and preferences across all projects/tasks

**When loaded:** ALWAYS, at every session start

**Examples:**
- Communication preferences ("User prefers concise, no fluff")
- Working style ("Values deep understanding over quick answers")
- General technical preferences ("Prefers async/await over callbacks")
- Cross-project knowledge about the user

**Storage:**
```python
{
    "text": "User prefers concise communication without fluff",
    "memory_type": "core_identity",
    "scope": "global",
    "entity": "user_preferences",
    "attribute": "communication_style"
}
```

#### 2. Project Scope
**Purpose:** Context for specific project or client work

**When loaded:** When project is detected or specified

**Examples:**
- Project architecture ("Clarity uses MCP + Qdrant vector storage")
- Client voice guidelines ("Brand X: friendly, conversational, use 'you'")
- Project-specific requirements ("STLVR Shopify theme: minimal, fast loading")
- Technical constraints ("This codebase uses Python 3.11+")

**Storage:**
```python
{
    "text": "Clarity: MCP-based memory system with hierarchical context loading",
    "memory_type": "project_context",
    "scope": "project",
    "project": "clarity",
    "entity": "clarity",
    "tags": ["architecture", "mcp", "memory_system"]
}
```

#### 3. Task Scope
**Purpose:** Instructions for specific objectives within a project

**When loaded:** When task is active or relevant to current work

**Examples:**
- "Debug entity fragmentation: check normalization in store_fact()"
- "Write blog post about MCP: conversational tone, 1000 words"
- "Refactor authentication: migrate from JWT to session-based"

**Storage:**
```python
{
    "text": "Implement entity fuzzy search with score threshold > 0.8",
    "memory_type": "task_instruction",
    "scope": "task",
    "project": "clarity",
    "task_id": "implement_fuzzy_search_001",
    "status": "active",
    "related_to": ["clarity_architecture_mem_id"]
}
```

## Memory Relations

### Explicit Relationship Schema

```python
{
    "id": "mem_clarity_arch_001",
    "text": "Clarity uses vector-only storage instead of SQL+vector dual storage",
    "memory_type": "project_context",
    "scope": "project",
    "project": "clarity",
    
    # Explicit relationships
    "related_to": [
        "mem_vector_decision_001",      # Architectural decision
        "mem_clarity_requirements_001"  # Project requirements
    ],
    "relation_types": {
        "mem_vector_decision_001": "implements",
        "mem_clarity_requirements_001": "satisfies"
    },
    
    "embedding": [...]
}
```

### Relation Types

- **supports:** Reinforcing relationship (fact A supports fact B)
- **contradicts:** Conflicting information (newer supersedes older)
- **supersedes:** Replaces previous decision/fact
- **refines:** Adds detail to existing memory
- **depends_on:** Prerequisite relationship
- **implements:** Task implements architectural decision
- **example_of:** Specific instance of general principle

### Use Cases for Relations

**1. Decision chains:**
```python
# Original proposal
{
    "id": "mem_001",
    "text": "Proposed dual storage: SQL for facts, Qdrant for interactions"
}

# Updated decision
{
    "id": "mem_002", 
    "text": "Decided vector-only storage with metadata filtering",
    "related_to": ["mem_001"],
    "relation_types": {"mem_001": "supersedes"}
}
```

**2. Task → Project linkage:**
```python
{
    "text": "Implement entity fuzzy search",
    "scope": "task",
    "related_to": ["clarity_entity_management_architecture"],
    "relation_types": {"clarity_entity_management_architecture": "implements"}
}
```

**3. Supporting facts:**
```python
{
    "text": "User values elegant solutions",
    "scope": "global",
    "related_to": ["user_prefers_simplicity"],
    "relation_types": {"user_prefers_simplicity": "supports"}
}
```

## Automatic Project Detection

### Detection Strategy

```python
def detect_project_context():
    """Auto-detect project from environment"""
    
    # Get environment info
    context_info = get_context_info()
    
    # Strategy 1: Claude Code - use pwd and git info
    if context_info.platform == "claude_code":
        if context_info.git_repo:
            # Direct mapping from git repo name
            return context_info.git_repo
        elif context_info.pwd:
            # Extract from path: /home/tim/projects/clarity → "clarity"
            return extract_project_from_path(context_info.pwd)
    
    # Strategy 2: Parse conversation title
    if context_info.conversation_title:
        # "Clarity Memory System" → check if "Clarity" is known project
        entities = search_entities(
            query=context_info.conversation_title,
            scope="project"
        )
        if entities and entities[0].score > 0.8:
            return entities[0].project
    
    # Strategy 3: Semantic search on first message
    first_message = get_first_user_message()
    project_matches = retrieve_context(
        query=first_message,
        memory_type="project_context",
        limit=3
    )
    if project_matches and project_matches[0].score > 0.85:
        return project_matches[0].project
    
    # Strategy 4: Ask user (fallback)
    return None
```

### Context Sources by Platform

**Claude Code:**
```python
{
    "platform": "claude_code",
    "pwd": "/home/tim/projects/clarity",
    "git_repo": "clarity",
    "git_branch": "main",
    "git_remote": "github.com/user/clarity"
}
# Best detection: git repo name or pwd
```

**Claude Desktop:**
```python
{
    "platform": "claude_desktop",
    "conversation_title": "Clarity Memory System",
    "workspace": None
}
# Detection: parse title, semantic search
```

**Claude Mobile:**
```python
{
    "platform": "claude_mobile",
    "conversation_title": "STLVR Shopify Theme"
}
# Detection: parse title, semantic search
```

### MCP Environment Tool

**New tool required:**
```python
get_context_info()

# Returns:
{
    "platform": "claude_code",
    "pwd": "/home/tim/projects/clarity",
    "conversation_title": "Memory System Design",
    "timestamp": "2025-10-08T...",
    "git_info": {
        "repo": "clarity",
        "branch": "main",
        "remote": "github.com/user/clarity"
    }
}
```

**Implementation note:** Requires MCP server to access environment variables or client-provided context. May need custom configuration:

```json
// ~/.config/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "memory": {
      "command": "python3",
      "args": ["/path/to/memory_mcp_server.py"],
      "env": {
        "CONVERSATION_TITLE": "${conversation.title}",
        "WORKSPACE_PATH": "${workspace.path}"
      }
    }
  }
}
```

## MCP Tool Definitions

### get_context_info
**Purpose:** Get environment information for project detection

**Parameters:** None

**Returns:**
```python
{
    "platform": "claude_code",
    "pwd": "/home/tim/projects/clarity",
    "git_repo": "clarity",
    "conversation_title": "Memory System Design",
    "timestamp": "2025-10-08T15:30:00"
}
```

### store_memory
**Purpose:** Store any type of memory with appropriate scope

**Parameters:**
- `text` (string): The memory content
- `memory_type` (string): "core_identity", "project_context", "task_instruction", or "episodic"
- `scope` (string): "global", "project", or "task"
- `entity` (string): Primary entity this memory is about
- `project` (string, optional): Project name if scope is "project" or "task"
- `task_id` (string, optional): Task identifier if scope is "task"
- `related_to` (list[string], optional): IDs of related memories
- `relation_types` (dict, optional): Mapping of memory_id to relation type
- `tags` (list[string], optional): Searchable tags
- `metadata` (dict, optional): Additional structured data

**Behavior:**
1. Generate embedding for semantic search
2. Store in Qdrant with all metadata
3. Auto-register entity if new
4. Create bidirectional links if relations specified
5. Return memory ID

**Example:**
```python
store_memory(
    text="Clarity uses hierarchical context loading: global, project, task",
    memory_type="project_context",
    scope="project",
    project="clarity",
    entity="clarity",
    tags=["architecture", "context_loading"],
    related_to=["mem_clarity_requirements_001"],
    relation_types={"mem_clarity_requirements_001": "satisfies"}
)
```

### retrieve_context
**Purpose:** Hierarchical context retrieval with scoping

**Parameters:**
- `query` (string, optional): Semantic search query
- `scope` (string, optional): Filter by "global", "project", or "task"
- `memory_type` (string or list, optional): Filter by memory type(s)
- `project` (string, optional): Filter to specific project
- `task_id` (string, optional): Filter to specific task
- `include_related` (bool, default=True): Include linked memories
- `relation_depth` (int, default=1): How many hops to traverse
- `limit` (int, default=10): Maximum results
- `score_threshold` (float, default=0.0): Minimum similarity score

**Returns:**
```python
[
    {
        "id": "mem_001",
        "text": "User prefers concise communication",
        "memory_type": "core_identity",
        "scope": "global",
        "score": 0.92,
        "related_memories": [
            {
                "id": "mem_002",
                "text": "User values elegant solutions",
                "relation": "supports"
            }
        ]
    },
    ...
]
```

**Hierarchical retrieval example:**
```python
# Load everything relevant for current session
context = retrieve_context(
    query=user_message,
    project="clarity",
    include_global=True,  # Always include global scope
    include_related=True,
    limit=50
)
# Returns: global memories + clarity project + semantically relevant
```

### set_project
**Purpose:** Explicitly set current project context

**Parameters:**
- `project` (string): Project name

**Behavior:**
1. Validates project exists (or creates if new)
2. Sets session context variable
3. Loads project-scoped memories
4. Returns project summary

**Returns:**
```python
{
    "project": "clarity",
    "description": "MCP-based memory system with hierarchical context",
    "memory_count": 47,
    "last_updated": "2025-10-08T...",
    "related_projects": ["local_ai", "mcp_servers"]
}
```

### link_memories
**Purpose:** Create explicit relationship between memories

**Parameters:**
- `memory_id` (string): Source memory
- `related_id` (string): Target memory
- `relation_type` (string): Type of relationship

**Example:**
```python
link_memories(
    memory_id="mem_vector_decision_001",
    related_id="mem_clarity_arch_001",
    relation_type="implements"
)
```

### list_entities
**Purpose:** List all known entities with optional filtering

**Parameters:**
- `scope` (string, optional): Filter by scope
- `project` (string, optional): Filter to specific project
- `memory_type` (string, optional): Filter by memory type

**Returns:**
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
        {
            "name": "clarity",
            "scope": "project",
            "project": "clarity",
            "memory_count": 47,
            "tags": ["architecture", "mcp", "memory"]
        }
    ],
    "count": 2
}
```

### search_entities
**Purpose:** Fuzzy search for entities to prevent fragmentation

**Parameters:**
- `query` (string): Entity name or partial match
- `scope` (string, optional): Filter by scope
- `limit` (int, default=5): Maximum results

**Returns:**
```python
{
    "matches": [
        {
            "entity": "Clarity",
            "scope": "project",
            "project": "clarity",
            "score": 0.95
        },
        {
            "entity": "clarity_project",
            "scope": "project", 
            "project": "clarity_project",
            "score": 0.73
        }
    ]
}
```

## Complete Session Flow

### Session Start Pattern (MANDATORY)

```python
# Step 1: Get environment info
context_info = get_context_info()

# Step 2: Detect or confirm project
project = detect_project(context_info)
if project and confidence > 0.8:
    set_project(project)
elif project:
    # Ask for confirmation
    "I think you're working on {project}. Is that correct?"
else:
    # Ask user
    "What project are you working on?"

# Step 3: Load hierarchical context
context = retrieve_context(
    query=user_message,
    project=project,
    include_global=True,  # Always load core identity
    include_related=True,
    limit=50
)

# Context now contains:
# - Global: User's core identity (always)
# - Project: Project-specific context (if detected)
# - Task: Active tasks for this project
# - Episodic: Semantically relevant past conversations
```

### Storage Pattern

```python
# During conversation
store_memory(
    text="User decided vector-only storage with metadata filtering",
    memory_type="project_context",
    scope="project",
    project="clarity",
    entity="architecture_decision",
    related_to=["mem_dual_storage_proposal"],
    relation_types={"mem_dual_storage_proposal": "supersedes"},
    tags=["architecture", "storage", "decision"]
)
```

## Storage Schema (Vector-Only)

### All Memory in Qdrant

```python
{
    # Core content
    "id": "mem_clarity_arch_001",
    "text": "Clarity uses vector-only storage with metadata-based scoping",
    "embedding": [float] * 384,
    
    # Type and scope
    "memory_type": "project_context",  # or "core_identity", "task_instruction", "episodic"
    "scope": "project",  # or "global", "task"
    
    # Context
    "entity": "clarity",
    "project": "clarity",
    "task_id": None,
    
    # Relations
    "related_to": ["mem_001", "mem_002"],
    "relation_types": {
        "mem_001": "implements",
        "mem_002": "supersedes"
    },
    
    # Metadata
    "tags": ["architecture", "storage", "vector_db"],
    "created_at": "2025-10-08T15:30:00",
    "updated_at": "2025-10-08T15:30:00",
    
    # Detection hints
    "detection_keywords": ["clarity", "memory system", "mcp"],
    
    # Task-specific
    "status": None,  # "active", "completed", "blocked" for tasks
    "priority": None  # For task prioritization
}
```

### Query Examples with Metadata Filtering

```python
# Global scope only
qdrant.search(
    collection_name="memories",
    query_vector=query_embedding,
    query_filter={
        "must": [
            {"key": "scope", "match": {"value": "global"}}
        ]
    }
)

# Project-scoped
qdrant.search(
    collection_name="memories",
    query_vector=query_embedding,
    query_filter={
        "must": [
            {"key": "project", "match": {"value": "clarity"}},
            {"key": "scope", "match": {"any": ["project", "task"]}}
        ]
    }
)

# Active tasks only
qdrant.search(
    collection_name="memories",
    query_vector=query_embedding,
    query_filter={
        "must": [
            {"key": "scope", "match": {"value": "task"}},
            {"key": "status", "match": {"value": "active"}},
            {"key": "project", "match": {"value": "clarity"}}
        ]
    }
)
```

## Agent Instructions

### Context File: .clinerules or INSTRUCTIONS.md

```markdown
# Memory System Instructions

You have a hierarchical persistent memory system. Memory usage is MANDATORY.

## Three-Tier Context Hierarchy

1. **Global (scope=global):** Core identity - loaded ALWAYS
   - User preferences, communication style, values
   - Cross-project knowledge
   
2. **Project (scope=project):** Project-specific context - loaded by project
   - Architecture, requirements, voice guidelines
   - Project-specific decisions and constraints
   
3. **Task (scope=task):** Specific objectives - loaded by relevance
   - Active instructions for current work
   - Explicit goals and acceptance criteria

## MANDATORY Session Start Pattern

EVERY conversation MUST begin with:

1. **Get environment info:**
   ```
   context_info = get_context_info()
   ```

2. **Detect project:**
   ```
   # Auto-detect from pwd, git, or conversation title
   project = detect_project_context()
   
   # If confident, set automatically:
   if project and confidence > 0.8:
       set_project(project)
   
   # If uncertain, confirm with user:
   "I see you're working on {project}. Is that correct?"
   ```

3. **Load hierarchical context:**
   ```
   context = retrieve_context(
       query=user_message,
       project=project,
       include_global=True,
       include_related=True
   )
   ```

NOW you have:
- Who the user is (global)
- What project you're working on (project)
- Relevant history and active tasks (task + episodic)

## When to Store Memories

**Global scope - Core identity:**
- User reveals preferences, values, recurring patterns
- Cross-project knowledge about the user
```
store_memory(
    text="User prefers async/await over callbacks",
    memory_type="core_identity",
    scope="global",
    entity="user_preferences"
)
```

**Project scope - Project context:**
- Project architecture, requirements, decisions
- Client voice guidelines, constraints
```
store_memory(
    text="STLVR Shopify theme: minimal design, fast loading priority",
    memory_type="project_context",
    scope="project",
    project="stlvr_shopify",
    entity="stlvr_shopify"
)
```

**Task scope - Specific objectives:**
- Explicit instructions for current work
- Acceptance criteria, blockers
```
store_memory(
    text="Debug entity normalization: check lowercase conversion in store_memory()",
    memory_type="task_instruction",
    scope="task",
    project="clarity",
    task_id="debug_entity_norm_001",
    status="active"
)
```

**Episodic - This conversation:**
- Important discussions, decisions made
- User corrections or clarifications
```
store_memory(
    text="User decided vector-only storage after discussing tradeoffs",
    memory_type="episodic",
    scope="project",
    project="clarity",
    related_to=["mem_dual_storage_discussion"],
    relation_types={"mem_dual_storage_discussion": "supersedes"}
)
```

## Preventing Entity Fragmentation

BEFORE creating a new entity:
1. Call `list_entities()` to see what exists
2. Call `search_entities(query)` to check for similar names
3. Use normalized names (lowercase, no extra spaces)
4. Link related entities with `link_memories()`

Example:
```
User: "What do you know about my preferences?"

You: 
1. search_entities("preferences") → finds "user_preferences"
2. retrieve_context(entity="user_preferences", scope="global")
3. Return facts about user_preferences (not creating "my preferences")
```

## Memory Relations

Link related memories explicitly:
```
link_memories(
    memory_id="current_decision",
    related_id="previous_proposal", 
    relation_type="supersedes"
)
```

Relation types:
- **supports**: Reinforcing information
- **supersedes**: Replaces old decision
- **implements**: Task implements design
- **depends_on**: Prerequisite relationship
- **refines**: Adds detail to existing

## Examples

### Coding Task on Clarity
```
User: "Continue working on Clarity"

You:
1. get_context_info() → pwd="/home/tim/projects/clarity"
2. detect_project() → "clarity" (from pwd)
3. set_project("clarity")
4. retrieve_context(query="last session clarity", project="clarity")

Result: You load:
- User's coding preferences (global)
- Clarity architecture and requirements (project)
- Last conversation and active tasks (episodic + task)

Response: "I see you're working on Clarity. Based on our last session, 
you were implementing entity fuzzy search. Let me check the current state..."
```

### Copywriting for Brand X
```
User: "Write landing page copy for Brand X"

You:
1. get_context_info() → no git context
2. search_entities("Brand X") → finds "brand_x"
3. set_project("brand_x")
4. retrieve_context(query="brand x voice guidelines", project="brand_x")

Result: You load:
- User's writing preferences (global)
- Brand X voice, tone, examples (project)
- Previous successful copy (episodic)

Response: "Got it. Brand X uses a friendly, conversational tone. 
Let me draft landing page copy following those guidelines..."
```

### New Project
```
User: "Starting a new project called Nebula"

You:
1. search_entities("Nebula") → no matches
2. Ask: "What should I know about Nebula?"
3. Store project context as user explains
4. set_project("nebula")

Result: Nebula now exists as a project with initial context
```

## Critical Rules

- ALWAYS start with get_context_info() and project detection
- NEVER skip loading global context
- CHECK existing entities before creating new ones
- STORE important information immediately, not at end of conversation
- LINK related memories to build knowledge graph
- USE semantic search liberally - storage is cheap

Forgetting is a critical failure. The user expects continuity.
```

## Technical Implementation

### Dependencies
```python
# Core MCP
mcp>=0.1.0

# Storage (vector-only)
qdrant-client>=1.7.0

# Embeddings
sentence-transformers>=2.2.0

# Utilities
asyncio
json
datetime
pathlib
gitpython  # For git repo detection
```

### Embedding Model
**Model:** `all-MiniLM-L6-v2`
- **Size:** ~80-120MB loaded in RAM
- **Dimensions:** 384
- **Performance:** Fast on CPU
- **Quality:** Good for conversational text

### Qdrant Configuration

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# Persistent storage
qdrant = QdrantClient(path="~/.local/share/mcp-memory/qdrant")

# Single collection for all memory types
qdrant.create_collection(
    collection_name="memories",
    vectors_config=VectorParams(
        size=384,
        distance=Distance.COSINE
    )
)

# Payload indexing for fast filtering
qdrant.create_payload_index(
    collection_name="memories",
    field_name="scope",
    field_schema="keyword"
)
qdrant.create_payload_index(
    collection_name="memories",
    field_name="project",
    field_schema="keyword"
)
qdrant.create_payload_index(
    collection_name="memories",
    field_name="memory_type",
    field_schema="keyword"
)
```

## Use Case Examples

### Use Case 1: Coding Across Multiple Projects

**Scenario:** User works on multiple coding projects with different tech stacks

**Memory structure:**
```python
# Global - applies to all coding
{
    "text": "User prefers TypeScript over JavaScript",
    "scope": "global",
    "memory_type": "core_identity"
}

# Project 1 - Clarity (Python)
{
    "text": "Clarity: Python 3.11+, uses MCP, Qdrant, sentence-transformers",
    "scope": "project",
    "project": "clarity",
    "memory_type": "project_context"
}

# Project 2 - Web Dashboard (TypeScript)
{
    "text": "Dashboard: Next.js 14, TypeScript, Tailwind, Supabase",
    "scope": "project",
    "project": "web_dashboard",
    "memory_type": "project_context"
}
```

**Session behavior:**
```
User starts Claude Code in /projects/clarity
→ Auto-detects project="clarity"
→ Loads: global preferences + Clarity context
→ Agent knows: Python project, MCP architecture, user's coding style

User starts Claude Code in /projects/web-dashboard  
→ Auto-detects project="web_dashboard"
→ Loads: global preferences + Dashboard context
→ Agent knows: TypeScript/Next.js project, different tech stack
```

### Use Case 2: Copywriting for Multiple Brands

**Scenario:** User writes copy for different clients with distinct voices

**Memory structure:**
```python
# Global - writing style
{
    "text": "User writes concise, benefit-driven copy",
    "scope": "global",
    "memory_type": "core_identity"
}

# Brand X - formal B2B
{
    "text": "Brand X: Professional tone, focus on ROI, avoid casual language",
    "scope": "project",
    "project": "brand_x_copy",
    "memory_type": "project_context",
    "tags": ["copywriting", "b2b", "formal"]
}

# Brand Y - consumer DTC
{
    "text": "Brand Y: Playful, emoji-friendly, speak directly to consumer",
    "scope": "project",
    "project": "brand_y_copy",
    "memory_type": "project_context",
    "tags": ["copywriting", "dtc", "casual"]
}
```

**Session behavior:**
```
User: "Write product page for Brand X"
→ Detects project="brand_x_copy" (semantic search)
→ Loads: global writing style + Brand X voice
→ Generates: Professional, ROI-focused copy

User: "Write social post for Brand Y"
→ Detects project="brand_y_copy"
→ Loads: global writing style + Brand Y voice
→ Generates: Playful, emoji-laden post
```

## Advantages of This Architecture

### 1. Intelligent Context Loading
- Only loads relevant memories (not everything)
- Hierarchical: global always, project when relevant, task when needed
- Prevents context pollution (Brand X voice doesn't leak into Brand Y)

### 2. Automatic Project Switching
- No manual configuration per project
- Works across platforms (Code, Desktop, Mobile)
- Graceful fallback to user confirmation

### 3. Single Storage Backend
- Vector-only = simpler implementation
- Metadata filtering = fast, scoped queries
- No sync issues between multiple databases

### 4. Explicit Relations
- Track decision evolution (supersedes)
- Link tasks to architecture (implements)
- Build knowledge graph over time

### 5. Model Agnostic
- Same MCP server works with Claude, local models, etc.
- Memory persists across AI providers
- Portable and future-proof

### 6. Scales Naturally
- Small overhead for personal use (~MB of storage)
- Hierarchical loading prevents context bloat
- Can scale to thousands of projects/memories

## Limitations and Trade-offs

### 1. Requires Explicit Agent Instructions
**Reality:** AI assistants don't proactively use tools without strong prompting

**Mitigation:**
- Context files with MANDATORY patterns
- Session-start verification
- Potential programmatic enforcement

**Remaining risk:** Some models may ignore instructions

### 2. Project Detection Not Perfect
**Challenges:**
- Conversation titles may be ambiguous
- Semantic search has false positives
- User may not follow naming conventions

**Mitigation:**
- Confidence thresholds (ask if uncertain)
- Multiple detection strategies (fallback chain)
- User can explicitly set with `set_project()`

### 3. Entity Management Requires Discipline
**Challenge:** Preventing entity fragmentation still requires:
- AI following naming conventions
- User correcting mistakes when they occur
- Regular entity cleanup/consolidation

**Mitigation:**
- `search_entities()` for fuzzy matching
- Entity normalization (lowercase, strip spaces)
- Agent instructions emphasize checking existing entities
- Future: automated entity deduplication

### 4. Memory Growth Over Time
**Not a real concern for individual use:**
- 1.5 KB per memory
- 10,000 memories ≈ 15 MB
- Even 100K memories = 150 MB

**Future considerations:**
- Archiving old/irrelevant memories
- Importance-based retention
- User-controlled deletion

### 5. Relation Management Complexity
**Challenge:** Relations must be created explicitly by AI or user

**Trade-off:**
- More manual than automatic graph building
- But more accurate and intentional
- Can add automatic relation suggestion later

## Validation Strategy

### Phase 1: Proof of Concept (Current)
**Goals:**
- Implement core MCP server with hierarchical storage
- Test with Claude Code on single project (Clarity)
- Validate memory persistence across sessions
- Verify project detection works

**Success criteria:**
- Memory survives Claude Code restart
- Project auto-detected from pwd
- Context properly scoped (global + project)
- Relations work correctly

### Phase 2: Multi-Project Testing
**Goals:**
- Test with 2-3 different projects
- Validate project switching works
- Test entity management across projects
- Measure retrieval quality

**Success criteria:**
- No context bleed between projects
- Entity discovery prevents fragmentation
- Retrieval returns relevant memories
- Project detection accuracy > 90%

### Phase 3: Extended Usage
**Goals:**
- Use system for real work over 2-4 weeks
- Accumulate 500+ memories
- Test various query patterns
- Identify missing features

**Success criteria:**
- System feels natural to use
- Memory quality improves over time
- Retrieval performance stays fast
- Agent proactively uses memory

### Phase 4: Local Model Integration
**Goals:**
- Test with local models (Llama, Mistral, etc.)
- Compare memory usage patterns
- Evaluate if local models follow instructions
- Optimize prompts for local models

**Success criteria:**
- Local models use memory tools consistently
- Quality comparable to Claude
- Performance acceptable on available hardware

## Future Enhancements

### Short-term (Weeks)

1. **Enhanced Project Detection:**
   - Train classifier on project names
   - User-configurable path → project mappings
   - Workspace/folder-based project groups

2. **Proactive Memory Enforcement:**
   - Wrapper script that auto-calls memory at session start
   - Verification that memory was used
   - Metrics dashboard for memory usage

3. **Entity Management Tools:**
   - Entity merge tool (consolidate duplicates)
   - Entity browser/editor UI
   - Bulk operations (rename, delete, merge)
   - Entity relationship visualization

4. **Improved Relations:**
   - Automatic relation suggestions based on co-occurrence
   - Relation strength scoring
   - Transitive relation inference (A→B, B→C implies A→C)

5. **Memory Quality Tools:**
   - Memory browser/search UI
   - Fact correction interface
   - Memory importance scoring
   - Duplicate detection

### Medium-term (Months)

1. **Advanced Context Loading:**
   - Time-weighted relevance (recent memories prioritized)
   - Conversation threading (related discussions)
   - Attention-based memory selection
   - Context budget management (token limits)

2. **Semantic Entity Matching:**
   - Embedding-based entity similarity
   - Automatic entity canonicalization
   - Entity alias system ("Tim" = "user" = "me")

3. **Task Management:**
   - Task lifecycle (created → active → completed → archived)
   - Task dependencies
   - Priority scoring
   - Deadline tracking

4. **Memory Consolidation:**
   - Summarize old episodic memories
   - Extract facts from conversations automatically
   - Compress redundant information
   - Archive low-importance memories

5. **Cross-Project Learning:**
   - Pattern recognition across projects
   - Generalized best practices from project-specific learnings
   - Transfer learning between similar projects

### Long-term (Future)

1. **Multi-User Support:**
   - Separate memory spaces per user
   - Shared project memories
   - Permission-based access control

2. **Federated Memory:**
   - Sync memories across devices
   - Backup and restore
   - Import/export memory sets
   - Collaborative memory spaces

3. **Active Memory Management:**
   - Proactive recall ("Did you remember to...")
   - Suggestion system based on patterns
   - Memory-based automation triggers

4. **Learned Behaviors:**
   - Procedural memory (how user solves problems)
   - Workflow pattern recognition
   - Personalized suggestions
   - Adaptive context loading strategies

5. **Memory Analytics:**
   - Memory usage patterns
   - Knowledge graph visualization
   - Project evolution timeline
   - Memory quality metrics

## Alternative Architectures Considered

### SQL + Vector Dual Storage
**Approach:** SQLite for structured facts, Qdrant for interactions

**Pros:**
- Faster exact lookups
- Better for analytical queries
- Lower storage overhead per fact

**Cons:**
- More complex (two storage systems)
- Dual-write complexity
- Entity fragmentation across systems
- Harder to do unified retrieval

**Decision:** Rejected in favor of vector-only for simplicity

### Graph Database (Neo4j)
**Approach:** Store memories and relations in graph DB

**Pros:**
- Natural fit for explicit relations
- Powerful graph queries
- Relationship traversal built-in

**Cons:**
- No semantic search (would need separate vector DB anyway)
- More complex setup and maintenance
- Overkill for single-user system
- Higher resource requirements

**Decision:** Rejected; explicit relations work fine in Qdrant metadata

### Cloud-Based Vector DB (Pinecone)
**Approach:** Use hosted vector database

**Pros:**
- No local infrastructure
- Managed scaling
- Professional support

**Cons:**
- Requires internet connection
- Privacy concerns (memories leave device)
- Ongoing costs
- Defeats "local AI" goal

**Decision:** Rejected; local-first aligns with project philosophy

### Hybrid: Qdrant + PostgreSQL
**Approach:** Qdrant for vectors, PostgreSQL for structured data

**Pros:**
- Best of both worlds (vector + relational)
- PostgreSQL has better tooling than SQLite
- Can do complex analytical queries

**Cons:**
- Even more complex than SQLite + Qdrant
- Multiple services to manage
- Higher resource requirements
- Unnecessary for single-user scale

**Decision:** Rejected; Qdrant metadata sufficient for filtering needs

## Implementation Checklist

### Core MCP Server
- [ ] Basic MCP server setup with stdio transport
- [ ] Qdrant client initialization and collection creation
- [ ] Sentence-transformers embedding model loading
- [ ] Tool registration (get_context_info, store_memory, retrieve_context, etc.)
- [ ] Environment detection logic (pwd, git, conversation title)
- [ ] Project detection algorithm
- [ ] Entity registry and normalization
- [ ] Memory relation management
- [ ] Hierarchical context loading

### MCP Tools
- [ ] `get_context_info()` - environment detection
- [ ] `store_memory()` - hierarchical storage with relations
- [ ] `retrieve_context()` - scoped retrieval with filters
- [ ] `set_project()` - explicit project selection
- [ ] `link_memories()` - create explicit relations
- [ ] `list_entities()` - entity discovery
- [ ] `search_entities()` - fuzzy entity matching

### Configuration
- [ ] Claude Desktop config file setup
- [ ] Data directory structure (~/.local/share/mcp-memory/)
- [ ] Context files (.clinerules, INSTRUCTIONS.md)
- [ ] Environment variable handling
- [ ] Git integration for repo detection

### Testing
- [ ] Unit tests for core functions
- [ ] Integration tests for MCP tools
- [ ] Project detection accuracy testing
- [ ] Entity normalization testing
- [ ] Relation traversal testing
- [ ] Memory retrieval quality evaluation
- [ ] Cross-session persistence verification

### Documentation
- [ ] Setup instructions
- [ ] Tool usage examples
- [ ] Agent instruction templates
- [ ] Troubleshooting guide
- [ ] Architecture diagrams

### User Interface (Optional)
- [ ] Memory browser web UI
- [ ] Entity management interface
- [ ] Relation visualization
- [ ] Memory search and filter
- [ ] Bulk operations tools

## Appendix: Key Design Decisions

### Why Three-Tier Hierarchy?
**Problem:** Flat memory retrieval returns irrelevant context

**Solution:** 
- **Global:** Universal facts (always relevant)
- **Project:** Context-specific (relevant to current work)
- **Task:** Objective-specific (relevant to current goal)

This mirrors human memory organization and prevents context pollution.

### Why Vector-Only?
**Alternatives considered:** SQL for facts, hybrid storage

**Rationale:**
- Simpler implementation (one storage system)
- Natural language queries work naturally
- Metadata filtering sufficient for scoping
- Storage overhead negligible at personal scale
- Semantic search handles entity variations

**Trade-off:** Slightly slower for exact lookups, but difference is imperceptible (milliseconds vs microseconds)

### Why Explicit Relations?
**Alternative:** Automatic relation inference from co-occurrence

**Rationale:**
- More accurate (intentional relationships)
- Avoids spurious correlations
- Agent can explain why memories are linked
- User can correct incorrect relations

**Trade-off:** Requires explicit action, but leads to higher quality knowledge graph

### Why Automatic Project Detection?
**Alternative:** User always specifies project explicitly

**Rationale:**
- Reduces friction (one less thing to remember)
- Works naturally with Claude Code (pwd-based)
- Graceful fallback to confirmation/manual entry
- Better user experience

**Trade-off:** Detection not 100% accurate, but high-confidence auto-detection + user confirmation covers most cases

### Why MCP?
**Alternatives:** Custom API, direct database access

**Rationale:**
- **Standardized protocol** for AI-tool communication
- **Platform agnostic** - works with Claude Code, Desktop, local models
- **Tool paradigm** - AI decides when to use memory
- **Growing ecosystem** - future integrations possible
- **Portable** - memory system can be reused across AI assistants

**Trade-off:** Requires MCP client support, but that's increasingly common

### Why Local-First?
**Alternative:** Cloud-hosted memory service

**Rationale:**
- **Privacy:** Sensitive memories stay on device
- **Ownership:** User owns their data completely
- **Offline:** Works without internet
- **Cost:** No ongoing service fees
- **Control:** Full customization possible

**Trade-off:** User manages infrastructure, but for personal use this is minimal (install + configure once)

### Why Sentence-Transformers?
**Alternatives:** OpenAI embeddings, Cohere, local LLMs

**Rationale:**
- **Open source:** No API dependencies
- **Local:** Runs on device
- **Fast:** CPU inference acceptable
- **Quality:** Good enough for conversational similarity
- **Size:** ~100MB is manageable

**Trade-off:** Lower quality than frontier embedding models, but sufficient for personal memory

## Conclusion

This MCP-based hierarchical memory system provides a practical, scalable solution for persistent AI memory. The three-tier architecture (global/project/task) prevents context pollution while ensuring relevant information is always available. Vector-only storage with metadata filtering balances simplicity with functionality.

Key innovations:
- **Automatic project detection** reduces friction
- **Explicit relations** build high-quality knowledge graphs
- **Hierarchical context loading** prevents information overload
- **Single storage backend** simplifies implementation
- **Platform agnostic** works across Claude Code, Desktop, and future local models

The system is designed for incremental adoption: start with basic storage/retrieval, add features as needed. The architecture supports future enhancements (entity deduplication, task management, memory consolidation) without requiring fundamental changes.

By starting with Claude Code for validation, we can test the memory architecture with a frontier model before investing in local model infrastructure. The same MCP server will work with local models when ready, providing a smooth migration path.

---

**Document Version:** 2.0  
**Last Updated:** October 8, 2025  
**Status:** Design complete, ready for implementation