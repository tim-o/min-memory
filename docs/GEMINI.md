# Critical Instructions

You have access to a persistent memory system via MCP tools. You MUST use these tools proactively to maintain continuity across sessions.

## Memory Architecture

The system uses **hierarchical scopes**:
- **global**: User preferences, core identity, system facts - available everywhere
- **project**: Project-specific context - only when working on that project
- **task**: Temporary task-specific info - scoped to a specific task

## When to Store Memories

Use `mcp__memory__store_memory()` with appropriate scope:

**Global scope** (scope="global") - Store when:
- User shares personal preferences or communication style
- Learning about user's technical knowledge or approaches
- System capabilities or constraints are discussed
- Core identity information is revealed

**Project scope** (scope="project") - Store when:
- Project goals or requirements are established
- Architecture decisions are made
- Project status updates occur
- Project-specific context changes

**Task scope** (scope="task") - Store when:
- Working on a specific, bounded task
- Task instructions or constraints are given
- Task status needs tracking

### Memory Types
Choose the right `memory_type`:
- `core_identity`: User preferences, values, communication style
- `project_context`: Project goals, architecture, status
- `task_instruction`: Specific task requirements
- `episodic`: Conversational interactions, decisions made

## When to Retrieve Memories

**At the START of every session:**
1. Call `mcp__memory__get_context_info()` to detect current directory/project
2. If in a project repo, call `mcp__memory__set_project(project="name")` to validate it exists
3. Call `mcp__memory__retrieve_context(query="relevant keywords", project="name")` for hierarchical retrieval
4. This automatically returns both global AND project memories

**During conversation:**
- Call `mcp__memory__list_entities()` to see what you know about
- Call `mcp__memory__search_entities(query="partial name")` to find similar entities
- Call `mcp__memory__retrieve_context()` with specific queries when user references past context

ALWAYS retrieve context before answering questions about:
- Previous conversations ("what did we discuss...")
- User preferences ("how do I like...")
- Project status ("where did we leave off...")
- Any entity you've stored memories about

## Memory Hygiene

- Store memories DURING the conversation, not just at the end
- Use accurate entity names (use `mcp__memory__search_entities()` to avoid duplicates)
- Be specific with text (include full context, not just values)
- Tag memories appropriately for easier retrieval
- Use `mcp__memory__link_memories()` to connect related memories
- Retrieve proactively, don't wait to be asked

## Available Tools

Core tools (auto-allowed):
- `mcp__memory__store_memory(text, memory_type, scope, entity, project?, tags?)`
- `mcp__memory__retrieve_context(query, project?, scope?, memory_type?, limit?)`
- `mcp__memory__set_project(project)`
- `mcp__memory__get_context_info()`
- `mcp__memory__list_entities(scope?, project?)`
- `mcp__memory__search_entities(query, scope?)`

Relationship tools (requires approval):
- `mcp__memory__link_memories(memory_id, related_id, relation_type)`

## Hierarchical Retrieval

When you call `retrieve_context(query="...", project="clarity")` WITHOUT specifying scope:
- Automatically retrieves BOTH global scope AND project scope memories
- Sorted by semantic relevance to your query
- This ensures user preferences and project context are both available

When you specify scope explicitly:
- `retrieve_context(query="...", scope="global")` - Only global memories
- `retrieve_context(query="...", scope="project", project="clarity")` - Only project memories

Remember: The user expects you to remember. Forgetting is a bug.
