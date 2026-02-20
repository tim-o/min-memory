# Agent Instructions for the Hierarchical Memory System

**Objective:** To use the provided tools to maintain persistent, hierarchical memory across sessions, ensuring continuity and context awareness.

**Compliance:** Memory usage is **MANDATORY**. Failure to follow these instructions will result in critical context loss.

## 1. The Three-Tier Context Hierarchy

You have access to three scopes of memory. Understanding them is critical for correct context retrieval.

1.  **Global (`scope="global"`):** Your core identity and the user's universal preferences. This context is **ALWAYS** relevant and must be loaded in every session.
    *   *Examples:* User's communication style, core values, cross-project technical preferences.

2.  **Project (`scope="project"`):** Context specific to a single project. This is loaded only when that project is active.
    *   *Examples:* A project's architecture, technical constraints, client requirements, voice and tone guidelines.

3.  **Task (`scope="task"`):** Specific instructions for a current objective within a project.
    *   *Examples:* "Refactor the auth module," "Debug the entity fragmentation issue," "Acceptance criteria: ..."

## 2. MANDATORY Session Start Pattern

Every session **MUST** begin with the following sequence to load the correct context.

**Step 1: Get Environment Information**

Call `get_context_info()` to understand the environment you are operating in.

```python
context_info = get_context_info()
```

**Step 2: Detect and Set the Project**

Use the information from `context_info` to determine the current project. This is a client-side responsibility. A typical logic flow is:
1.  Check for a git repository name.
2.  Check the current working directory.
3.  Perform a semantic search on the conversation title.
4.  If a project is identified with high confidence, set it automatically using `set_project("project-name")`.
5.  If uncertain, **you MUST ask the user for confirmation.** Example: `"It looks like we are working on the 'min-memory' project. Is that correct?"`

**Step 3: Load Hierarchical Context**

Once the project is set, retrieve the full hierarchical context using `retrieve_context`. The key is to query for memories relevant to the current conversation while also pulling in the project and global scopes.

```python
# Example of a comprehensive context loading call
context = retrieve_context(
    query=user_s_initial_message,
    project="min-memory", # The detected project
    # By not specifying a 'scope', you get both 'project' and 'global' memories
    # that are semantically relevant to the query.
    limit=20,
    include_related=True
)
```

After this sequence, you are properly oriented and ready to assist.

## 3. When to Store Memories

Store information immediately as it is revealed. Do not wait until the end of a conversation.

*   **Global Scope (Core Identity & User Preferences):**
    *   *Trigger:* User reveals a preference, a value, or a recurring pattern of behavior.
    *   *Example:*
        ```python
        store_memory(
            text="User prefers to use the `anyio` library for async tasks over `asyncio` directly.",
            memory_type="core_identity",
            scope="global",
            entity="user_preferences"
        )
        ```

*   **Project Scope (Project Context):**
    *   *Trigger:* A decision is made about a project's architecture, a new requirement is defined, or a technical constraint is identified.
    *   *Example:*
        ```python
        store_memory(
            text="The 'min-memory' project uses a soft-delete pattern for memories, flagging them with `deleted:True`.",
            memory_type="project_context",
            scope="project",
            project="min-memory",
            entity="min-memory-architecture"
        )
        ```

*   **Episodic (Conversational Events):**
    *   *Trigger:* An important decision is made during a conversation, or the user provides a critical clarification.
    *   *Example:*
        ```python
        store_memory(
            text="User confirmed that token efficiency is a primary concern, leading to the decision to create a `store_multi_entity_memory` tool.",
            memory_type="episodic",
            scope="project",
            project="min-memory",
            entity="design_decision"
        )
        ```

## 4. Preventing Entity Fragmentation

To keep the memory system organized, you **MUST** avoid creating duplicate or fragmented entities.

**Workflow:** Before storing a memory with a new entity name:
1.  Call `list_entities()` to review the existing, known entities.
2.  Call `search_entities(query="potential-new-entity")` to check for similarly named entities.
3.  If a similar entity exists, **use the existing, canonical name.**

*   **Example Scenario:**
    *   *User says:* "Tell me about my preferences for coding."
    *   *Your internal thought process:* The user mentioned "preferences for coding." Is that a new entity?
    *   *Action:* `search_entities(query="preferences")`
    *   *Result:* The tool returns a match for `"user_preferences"` with a high score.
    *   *Correct Action:* You use the existing entity `"user_preferences"` in your `retrieve_context` call instead of creating a new one.

## 5. Using Memory Relations

Explicitly link related memories to build a rich knowledge graph.

*   **Use Case:** A new decision supersedes an old one.
*   **Action:**
    ```python
    link_memories(
        memory_id="new_decision_id",
        related_id="old_decision_id", 
        relation_type="supersedes"
    )
    ```
*   **Key Relation Types:**
    *   `supersedes`: Replaces a previous fact or decision.
    -   `supports`: Reinforces or provides evidence for another memory.
    *   `implements`: A task or code change that enacts a design decision.
    *   `depends_on`: A memory that is a prerequisite for another.
    *   `refines`: Adds more detail to an existing memory.
