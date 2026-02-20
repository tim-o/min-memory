# Proposal: Multi-Entity Memory Storage

**Date:** 2025-10-12

**Status:** Proposed

## 1. Summary

This proposal recommends associating a single piece of text with multiple subjects (entities) by creating a separate, explicit memory record for each entity. This will be enabled by a new, token-efficient MCP tool for storing memories.

## 2. Problem

A single memory or piece of information often pertains to multiple subjects. For example, the text "Meeting with Sarah from Acme Corp about the min-memory project" is about three distinct entities: "Sarah," "Acme Corp," and "min-memory."

The current `store_memory` tool only allows for a single string `entity` per memory record. This forces the agent to either:
1.  Store the memory with only one of the entities, losing the connection to the others.
2.  Store the memory with a vague, composite entity like "sarah-acme-min-memory," which is not discoverable.
3.  Make multiple, separate calls to `store_memory`, which is highly inefficient for the frontier model's output tokens.

## 3. Proposed Solution

### 3.1. New MCP Tool

A new tool, `store_multi_entity_memory`, will be added to the memory server.

**Schema:**
```json
{
  "name": "store_multi_entity_memory",
  "description": "Stores a single piece of text as multiple memories, one for each provided entity.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "text": { "type": "string" },
      "entities": {
        "type": "array",
        "items": { "type": "string" }
      },
      "memory_type": { "type": "string" },
      "scope": { "type": "string" }
      // ... other relevant parameters like project, tags, etc.
    },
    "required": ["text", "entities", "memory_type", "scope"]
  }
}
```

### 3.2. Server-Side Implementation

The `memory_mcp_server` will be responsible for the logic. When it receives a call to this new tool, it will:
1.  Generate a single vector embedding for the `text`.
2.  Loop through the `entities` list provided in the tool call.
3.  For each entity in the list, it will create a new point in Qdrant. Each point will have the **same text and vector** but a **different `entity`** in its payload.

### 3.3. Agent Workflow

The agent workflow for storing a memory becomes:
1.  Identify a piece of text to remember.
2.  (Optional, but recommended) Call a local model to perform entity extraction on the text.
3.  Make a **single** call to `store_multi_entity_memory` with the text and the list of extracted entities.

## 4. Rationale and Benefits

The primary benefit is a significant improvement in **retrieval precision and context quality**.

When a memory is explicitly stored with the entity "Sarah," a future query for "Sarah" will retrieve that memory unambiguously. The agent receives the text along with the metadata confirming *why* it was retrieved. This reduces the cognitive load on the LLM, as it doesn't have to re-parse a longer, more ambiguous text to find the relevant information.

This moves the system from a "text-centric" model to a more powerful "entity-centric" model, creating a more structured and granular knowledge base.

## 5. Costs and Trade-offs

*   **Storage Cost:** This approach intentionally duplicates the text and its vector embedding, leading to higher storage usage in the Qdrant database.
*   **Justification:** The cost is justified by the immense gain in retrieval quality. For a personal-scale memory system, storage is cheap, whereas the quality of the context provided to the LLM is the single most important factor for performance.

## 6. Token Efficiency

This design is highly token-efficient for the frontier model. By making a single tool call with a list of entities, we avoid the scenario where the LLM has to generate multiple, verbose `store_memory` calls, thereby saving output tokens. This was a key insight raised during the design discussion.
