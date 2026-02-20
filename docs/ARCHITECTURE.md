# Min-Memory System Architecture

**Document Version:** 3.0  
**Last Updated:** 2025-10-12  
**Status:** Active

## 1. Executive Summary

This document outlines the technical architecture for a persistent, hierarchical memory system. The system is exposed as an HTTP service, secured by OAuth 2.0, and provides tools for AI agents to manage long-term memory. The core of the system is a vector-only storage backend that uses metadata for scoping, enabling a three-tier memory hierarchy (global, project, task).

## 2. System Overview

### 2.1. Core Concept

The system enables AI agents to remember conversations, facts, and context across sessions by exposing memory operations as a set of tools via an HTTP API. The service is designed to be called by any authorized client, including other MCP servers, local scripts, or web applications.

### 2.2. Architecture Diagram

```
┌──────────────────────────────────┐
│    AI Client (Agent, Web App)    │
│ - Authenticates via OAuth 2.0    │
│ - Calls HTTP endpoints for tools │
└────────────────┬─────────────────┘
                 │
                 │ HTTPS (JSON)
                 ↓
┌──────────────────────────────────┐
│      Min-Memory HTTP Server      │
│                                  │
│  - Starlette Application         │
│  - MCP Auth Middleware (OAuth 2) │
│  - Tool Endpoint (/mcp)          │
│                                  │
│  Components:                     │
│  • FastEmbed (Embeddings)        │
│  • Qdrant (Vector Storage)       │
└──────────────────────────────────┘
                 │
                 ↓
        ┌────────────────┐
        │  Qdrant DB     │
        │ (local file)   │
        └────────────────┘
```

## 3. Technical Implementation

### 3.1. Service Layer

*   **Framework:** The server is built using the **Starlette** ASGI framework, making it a lightweight and high-performance HTTP service.
*   **Transport:** Communication is done over HTTPS, with request and response bodies formatted as JSON.
*   **Hosting:** The application is designed to be containerized with Docker and run as a standard web service.

### 3.2. Authentication

*   **Protocol:** The API is secured using **OAuth 2.0 Bearer Tokens**.
*   **Library:** Authentication and token validation are handled by the **`mcpauth`** library, which simplifies integration with OIDC providers like Auth0.
*   **Flow:**
    1.  Clients obtain a JWT access token from the configured Auth0 tenant.
    2.  Clients include this token in the `Authorization: Bearer <token>` header for all API requests.
    3.  The `AuthGuardMiddleware` in the Starlette application intercepts requests, validates the JWT, and extracts the user's identity (`subject`).
    4.  All database operations are strictly partitioned by the authenticated user ID, ensuring data isolation.
*   **Configuration:** The system is configured via environment variables: `AUTH0_DOMAIN` and `AUTH0_API_AUDIENCE`.

### 3.3. Storage Layer

*   **Database:** **Qdrant** is used as the vector database. It is run in a local, file-based mode, persisting data to the directory specified by the `MCP_DATA_DIR` environment variable.
*   **Collection:** A single Qdrant collection named `memories` stores all memory records for all users.
*   **Data Model:** The architecture is **vector-only**. All information, including structured metadata, is stored in the payload of each point in the vector collection. There is no separate relational database.
*   **Indexing:** To ensure fast and efficient filtering, payload indexes are created on the following fields: `user`, `scope`, `project`, `memory_type`, `entity`, and `deleted`.

### 3.4. Embeddings

*   **Library:** Text embeddings are generated using the **`fastembed`** library.
*   **Model:** The specific model used is **`BAAI/bge-small-en-v1.5`**.
*   **Dimensions:** This model produces vectors with **384 dimensions**.

### 3.5. Core Features

*   **Soft Deletion:** The system uses a soft-delete pattern. When `delete_memory` is called, the memory's `deleted` flag is set to `True` and a `deleted_at` timestamp is added. By default, all retrieval queries are filtered to exclude records where `deleted: True`.
*   **User Isolation:** All database queries (`search`, `retrieve`, `scroll`) are automatically and mandatorily filtered by the authenticated `user` ID. This is a critical security measure to ensure users can only access their own memories.

## 4. API & Tool Definitions

The server exposes its functionality via a single primary endpoint, `/mcp`, which accepts tool calls. The schemas below reflect the current implementation.

*   `store_memory(text, memory_type, scope, entity, project?, task_id?, related_to?, relation_types?, tags?, status?, priority?)`
*   `retrieve_context(query, scope?, memory_type?, project?, task_id?, include_related?, limit?, score_threshold?)`
*   `set_project(project)`
*   `get_context_info()`
*   `link_memories(memory_id, related_id, relation_type)`
*   `list_entities(scope?, project?, memory_type?)`
*   `search_entities(query, scope?, limit?)`
*   `delete_memory(memory_id)`
*   `search(query)`
*   `fetch(id)`

*(Note: For full, detailed schemas, refer to the `list_tools` function in the implementation.)*

## 5. Key Design Decisions

*   **HTTP over Stdio:** An HTTP server is more flexible and standard than a stdio-based MCP server, allowing it to be called by a wider range of clients (web apps, scripts, other backend services) and deployed using standard web hosting practices.
*   **Standard OAuth 2.0:** Using a standard, library-driven (`mcpauth`) authentication flow is more secure, robust, and maintainable than a custom solution.
*   **Vector-Only Storage:** Simplifies the architecture by using a single data store. Qdrant's metadata filtering is powerful enough to handle the required scoping and querying without needing a separate relational database.
*   **Client-Side Project Detection:** The server provides the necessary information (`get_context_info`), but the complex logic for *detecting* the current project is the responsibility of the client agent. This keeps the server stateless and focused on its core task of memory management.