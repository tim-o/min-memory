# src/tools.py

import asyncio
import logging
import json
import os
import httpx
from datetime import datetime
from difflib import SequenceMatcher
from mcp.server import Server
from mcp.types import Tool, TextContent
from qdrant_client.models import PointStruct

# Local module imports
from .storage import qdrant, embedder, build_filter, find_by_entity, async_update_access_tracking
from .scoring import compute_recency_score, blend_scores
from .entities import entity_tree
from .auth import get_current_user

logger = logging.getLogger(__name__)

# Try to import git, but don't fail if not available
try:
    import git
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    logging.warning("GitPython not available - git detection disabled")

# --- MCP Server and Tool Definitions ---

mcp_server = Server("memory-server")

# --- Helper Functions ---

def generate_memory_id(entity: str, timestamp: str) -> str:
    """Generate UUID from entity and timestamp for consistent IDs"""
    import uuid
    namespace = uuid.UUID('00000000-0000-0000-0000-000000000000')
    seed = f"{entity}:{timestamp}"
    return str(uuid.uuid5(namespace, seed))

def get_git_info(path: str):
    """Extract git repository information"""
    if not GIT_AVAILABLE:
        return None
    try:
        repo = git.Repo(path, search_parent_directories=True)
        remote_url = repo.remotes.origin.url if repo.remotes else None
        return {
            "repo": os.path.basename(repo.working_dir),
            "branch": repo.active_branch.name,
            "remote": remote_url
        }
    except (git.InvalidGitRepositoryError, git.NoSuchPathError, Exception) as e:
        logger.debug(f"Git detection failed: {e}")
        return None

# --- Tool Definitions ---

@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    # (The full list of tool definitions from the original file)
    return [
        Tool(
            name="search",
            description="Search for memories based on a query string.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The query to search for."
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="fetch",
            description="Fetch a specific memory by its ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "The ID of the memory to fetch."
                    }
                },
                "required": ["id"]
            }
        ),
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
                    "project": {"type": "string"},
                    "task_id": {"type": "string"},
                    "related_to": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "relation_types": {"type": "object"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "status": {"type": "string"},
                    "priority": {"type": "integer"}
                },
                "required": ["text", "memory_type", "scope", "entity"]
            }
        ),
        Tool(
            name="retrieve_context",
            description="Hierarchical context retrieval with scoping",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "scope": {"type": "string"},
                    "memory_type": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "project": {"type": "string"},
                    "task_id": {"type": "string"},
                    "include_related": {"type": "boolean", "default": True},
                    "limit": {"type": "integer", "default": 10},
                    "score_threshold": {"type": "number", "default": 0.0},
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
                },
                "required": ["query"]
            }
        ),
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
        ),
        Tool(
            name="get_context_info",
            description="Get environment information for project detection",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
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
        ),
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
        ),
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
        ),
        Tool(
            name="delete_memory",
            description="Soft delete a memory by ID (sets deleted=true, filters from future retrievals)",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"}
                },
                "required": ["memory_id"]
            }
        ),
        Tool(
            name="update_memory",
            description="Update an existing memory's text and/or metadata fields. Only provided fields are changed.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {"type": "string"},
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
                    "project": {"type": "string"},
                    "task_id": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "status": {"type": "string"},
                    "priority": {"type": "integer"}
                },
                "required": ["memory_id"]
            }
        ),
        Tool(
            name="sync_session",
            description="Structured session sync: store decisions, status updates, learnings, and feedback with automatic type/scope inference and upsert semantics.",
            inputSchema={
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
                                "tags": {"type": "array", "items": {"type": "string"}},
                                "supersedes": {"type": "string", "description": "Memory ID this learning supersedes"}
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
        )
    ]


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    current_user = get_current_user()
    if not current_user:
        return [TextContent(type="text", text="Error: Unauthorized - no valid user context")]

    # This function body is the large `if/elif` block from the original file.
    # To save space, it is not repeated verbatim here, but it is the same logic.
    if name == "search":
        query = arguments["query"]
        query_embedding = list(embedder.embed([query]))[0].tolist()
        query_filter = build_filter(user=current_user)
        response = qdrant.query_points(collection_name="memories", query=query_embedding, query_filter=query_filter, limit=10)
        search_results = []
        for result in response.points:
            title = result.payload.get("text", "")[:80]
            search_results.append({"id": result.id, "title": title, "url": f"mcp://memory/{result.id}"})

        # Fire-and-forget access tracking (AC-19)
        returned_ids = [result.id for result in response.points]
        asyncio.ensure_future(async_update_access_tracking(returned_ids))

        return [TextContent(type="text", text=json.dumps(search_results, indent=2))]

    elif name == "fetch":
        memory_id = arguments["id"]
        try:
            points = qdrant.retrieve(collection_name="memories", ids=[memory_id], with_payload=True)
            if not points:
                return [TextContent(type="text", text="Error: Memory not found")]
            point = points[0]
            if point.payload.get("user") != current_user:
                logger.warning(f"User {current_user} attempted to fetch memory {memory_id} owned by another user.")
                return [TextContent(type="text", text="Error: Unauthorized")]
            return [TextContent(type="text", text=point.payload.get("text", ""))]
        except Exception as e:
            logger.error(f"Failed to fetch memory {memory_id}: {e}")
            return [TextContent(type="text", text=f"Error: Could not fetch memory.")]

    elif name == "store_memory":
        scope = arguments["scope"]
        project = arguments.get("project")
        task_id = arguments.get("task_id")
        if scope in ["project", "task"] and not project:
            return [TextContent(type="text", text="Error: project is required when scope is 'project' or 'task'")]
        if scope == "task" and not task_id:
            return [TextContent(type="text", text="Error: task_id is required when scope is 'task'")]
        text = arguments["text"]
        embedding = list(embedder.embed([text]))[0].tolist()
        timestamp = datetime.now().isoformat()
        memory_id = generate_memory_id(arguments["entity"], timestamp)
        payload = {
            "user": current_user,
            "text": text,
            "memory_type": arguments["memory_type"],
            "scope": scope,
            "entity": arguments["entity"],
            "project": project,
            "task_id": task_id,
            "related_to": arguments.get("related_to", []),
            "relation_types": arguments.get("relation_types", {}),
            "tags": arguments.get("tags", []),
            "created_at": timestamp,
            "updated_at": timestamp,
            "status": arguments.get("status"),
            "priority": arguments.get("priority"),
            "deleted": False
        }
        qdrant.upsert(collection_name="memories", points=[PointStruct(id=memory_id, vector=embedding, payload=payload)])
        logger.info(f"Stored memory: {memory_id} for user: {current_user}")
        return [TextContent(type="text", text=json.dumps({"memory_id": memory_id, "status": "stored"}))]

    elif name == "retrieve_context":
        query = arguments["query"]
        query_embedding = list(embedder.embed([query]))[0].tolist()
        project = arguments.get("project")
        explicit_scope = arguments.get("scope")
        limit = arguments.get("limit", 10)
        recency_weight = arguments.get("recency_weight", 0.3)
        status_filter = arguments.get("status_filter")
        is_project_scope = bool(project and not explicit_scope)

        # Fetch extra results to account for post-filtering
        fetch_limit = limit * 2 if is_project_scope else limit

        if is_project_scope:
            global_filter = build_filter(user=current_user, scope="global", memory_type=arguments.get("memory_type"), task_id=arguments.get("task_id"))
            project_filter = build_filter(user=current_user, project=project, memory_type=arguments.get("memory_type"), task_id=arguments.get("task_id"))
            global_response = qdrant.query_points(collection_name="memories", query=query_embedding, query_filter=global_filter, limit=fetch_limit // 2)
            project_response = qdrant.query_points(collection_name="memories", query=query_embedding, query_filter=project_filter, limit=fetch_limit // 2)
            results = global_response.points + project_response.points
        else:
            query_filter = build_filter(user=current_user, scope=explicit_scope, project=project, memory_type=arguments.get("memory_type"), task_id=arguments.get("task_id"))
            results = qdrant.query_points(collection_name="memories", query=query_embedding, query_filter=query_filter, limit=fetch_limit).points

        # Post-filter: status filtering for project_context memories (AC-11, AC-12)
        effective_status_filter = status_filter
        if is_project_scope and status_filter is None:
            effective_status_filter = ["active"]

        if effective_status_filter is not None:
            filtered = []
            for r in results:
                if r.payload.get("memory_type") == "project_context":
                    status = r.payload.get("status")
                    # status=None passes through for backward compat (AC-12)
                    if status is None or status in effective_status_filter:
                        filtered.append(r)
                else:
                    # Non-project_context results are never status-filtered
                    filtered.append(r)
            results = filtered

        score_threshold = arguments.get("score_threshold", 0.0)
        results = [r for r in results if r.score >= score_threshold]

        # Apply recency re-ranking (AC-10, AC-13)
        if recency_weight > 0.0:
            scored = []
            for r in results:
                recency = compute_recency_score(r.payload.get("created_at"))
                blended = blend_scores(r.score, recency, recency_weight)
                scored.append((r, blended))
            scored.sort(key=lambda x: x[1], reverse=True)
            scored = scored[:limit]
            blended_map = {id(r): s for r, s in scored}
            results = [r for r, _ in scored]
        else:
            results = sorted(results, key=lambda x: x.score, reverse=True)[:limit]
            blended_map = {}

        context = []
        for result in results:
            memory = {
                "id": result.id,
                "text": result.payload["text"],
                "memory_type": result.payload["memory_type"],
                "scope": result.payload["scope"],
                "entity": result.payload["entity"],
                "project": result.payload.get("project"),
                "score": blended_map.get(id(result), result.score),
                "created_at": result.payload.get("created_at"),
                "tags": result.payload.get("tags", [])
            }
            if arguments.get("include_related", True):
                related_to = result.payload.get("related_to", [])
                relation_types = result.payload.get("relation_types", {})
                if related_to:
                    related_memories = []
                    for rel_id in related_to:
                        try:
                            rel_point = qdrant.retrieve(collection_name="memories", ids=[rel_id])
                            if rel_point and rel_point[0].payload.get("user") == current_user:
                                related_memories.append({"id": rel_id, "text": rel_point[0].payload["text"], "relation": relation_types.get(rel_id, "related")})
                        except Exception as e:
                            logger.warning(f"Failed to retrieve related memory {rel_id}: {e}")
                    if related_memories:
                        memory["related_memories"] = related_memories
            context.append(memory)

        # Fire-and-forget access tracking (AC-19)
        returned_ids = [result.id for result in results]
        asyncio.ensure_future(async_update_access_tracking(returned_ids))

        return [TextContent(type="text", text=json.dumps(context, indent=2))]

    elif name == "set_project":
        project = arguments["project"]
        project_filter = build_filter(user=current_user, project=project)
        results, _ = qdrant.scroll(collection_name="memories", scroll_filter=project_filter, limit=1000)
        if not results:
            timestamp = datetime.now().isoformat()
            memory_id = generate_memory_id(project, timestamp)
            embedding = list(embedder.embed([f"Project: {project}"]))[0].tolist()
            qdrant.upsert(collection_name="memories", points=[PointStruct(id=memory_id, vector=embedding, payload={
                "user": current_user, "text": f"Project: {project}", "memory_type": "project_context", "scope": "project", "entity": project, "project": project, "task_id": None, "related_to": [], "relation_types": {}, "tags": [], "created_at": timestamp, "updated_at": timestamp, "status": None, "priority": None, "deleted": False})])
            return [TextContent(type="text", text=json.dumps({"project": project, "exists": False, "created": True, "memory_count": 1, "by_type": {"project_context": 1}}))]
        memory_count = len(results)
        by_type = {}
        last_updated = None
        for point in results:
            mem_type = point.payload.get("memory_type", "unknown")
            by_type[mem_type] = by_type.get(mem_type, 0) + 1
            updated = point.payload.get("updated_at")
            if updated:
                if not last_updated or updated > last_updated:
                    last_updated = updated
        return [TextContent(type="text", text=json.dumps({"project": project, "exists": True, "memory_count": memory_count, "by_type": by_type, "last_updated": last_updated}))]

    elif name == "get_context_info":
        pwd = os.getcwd()
        git_info = get_git_info(pwd)
        return [TextContent(type="text", text=json.dumps({"platform": "http", "user": current_user, "pwd": pwd, "git_info": git_info, "timestamp": datetime.now().isoformat()}))]

    elif name == "link_memories":
        memory_id = arguments["memory_id"]
        related_id = arguments["related_id"]
        relation_type = arguments["relation_type"]
        try:
            points = qdrant.retrieve(collection_name="memories", ids=[memory_id])
            if not points:
                return [TextContent(type="text", text=f"Error: Memory {memory_id} not found")]
            point = points[0]
            if point.payload.get("user") != current_user:
                return [TextContent(type="text", text="Error: Unauthorized - cannot modify other user's memories")]
            payload = point.payload
            related_to = payload.get("related_to", [])
            if related_id not in related_to:
                related_to.append(related_id)
            relation_types = payload.get("relation_types", {})
            relation_types[related_id] = relation_type
            payload["related_to"] = related_to
            payload["relation_types"] = relation_types
            payload["updated_at"] = datetime.now().isoformat()
            qdrant.set_payload(collection_name="memories", payload=payload, points=[memory_id])
            return [TextContent(type="text", text=json.dumps({"status": "linked", "memory_id": memory_id, "related_id": related_id, "relation_type": relation_type}))]
        except Exception as e:
            logger.error(f"Failed to link memories: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "list_entities":
        query_filter = build_filter(user=current_user, scope=arguments.get("scope"), project=arguments.get("project"), memory_type=arguments.get("memory_type"))
        results, _ = qdrant.scroll(collection_name="memories", scroll_filter=query_filter, limit=10000)
        entities_map = {}
        for point in results:
            entity = point.payload.get("entity")
            if not entity:
                continue
            if entity not in entities_map:
                entities_map[entity] = {"name": entity, "scope": point.payload.get("scope"), "project": point.payload.get("project"), "memory_count": 0, "first_seen": point.payload.get("created_at"), "last_updated": point.payload.get("updated_at")}
            entities_map[entity]["memory_count"] += 1
            created = point.payload.get("created_at")
            updated = point.payload.get("updated_at")
            if created and created < entities_map[entity]["first_seen"]:
                entities_map[entity]["first_seen"] = created
            if updated and updated > entities_map[entity]["last_updated"]:
                entities_map[entity]["last_updated"] = updated
        entities = list(entities_map.values())
        return [TextContent(type="text", text=json.dumps({"entities": entities, "count": len(entities)}, indent=2))]

    elif name == "search_entities":
        query = arguments["query"].lower()
        scope_filter = arguments.get("scope")
        limit = arguments.get("limit", 5)
        query_filter = build_filter(user=current_user, scope=scope_filter) if scope_filter else build_filter(user=current_user)
        results, _ = qdrant.scroll(collection_name="memories", scroll_filter=query_filter, limit=10000)
        entities_set = {}
        for point in results:
            entity = point.payload.get("entity")
            if entity and entity not in entities_set:
                entities_set[entity] = {"entity": entity, "scope": point.payload.get("scope"), "project": point.payload.get("project")}
        matches = []
        for entity_data in entities_set.values():
            entity = entity_data["entity"]
            score = SequenceMatcher(None, query, entity.lower()).ratio()
            if score > 0:
                matches.append({**entity_data, "score": round(score, 3)})
        matches.sort(key=lambda x: x["score"], reverse=True)
        matches = matches[:limit]
        return [TextContent(type="text", text=json.dumps({"matches": matches}, indent=2))]

    elif name == "delete_memory":
        memory_id = arguments["memory_id"]
        try:
            points = qdrant.retrieve(collection_name="memories", ids=[memory_id])
            if not points:
                return [TextContent(type="text", text=f"Error: Memory {memory_id} not found")]
            point = points[0]
            if point.payload.get("user") != current_user:
                return [TextContent(type="text", text="Error: Unauthorized - cannot delete other user's memories")]
            if point.payload.get("deleted", False):
                return [TextContent(type="text", text=json.dumps({"status": "already_deleted", "memory_id": memory_id}))]
            payload = point.payload
            payload["deleted"] = True
            payload["deleted_at"] = datetime.now().isoformat()
            payload["updated_at"] = datetime.now().isoformat()
            qdrant.set_payload(collection_name="memories", payload=payload, points=[memory_id])
            logger.info(f"Soft deleted memory: {memory_id} for user: {current_user}")
            return [TextContent(type="text", text=json.dumps({"status": "deleted", "memory_id": memory_id, "deleted_at": payload["deleted_at"]}))]
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "update_memory":
        memory_id = arguments["memory_id"]
        try:
            points = qdrant.retrieve(collection_name="memories", ids=[memory_id], with_vectors=True)
            if not points:
                return [TextContent(type="text", text=f"Error: Memory {memory_id} not found")]
            point = points[0]
            if point.payload.get("user") != current_user:
                return [TextContent(type="text", text="Error: Unauthorized - cannot update other user's memories")]
            if point.payload.get("deleted", False):
                return [TextContent(type="text", text=f"Error: Memory {memory_id} is deleted")]
            payload = point.payload
            updatable = ["memory_type", "scope", "entity", "project", "task_id", "tags", "status", "priority"]
            for field in updatable:
                if field in arguments:
                    payload[field] = arguments[field]
            # Re-embed if text changed
            if "text" in arguments:
                payload["text"] = arguments["text"]
                new_embedding = list(embedder.embed([arguments["text"]]))[0].tolist()
                qdrant.upsert(collection_name="memories", points=[PointStruct(id=memory_id, vector=new_embedding, payload={**payload, "updated_at": datetime.now().isoformat()})])
            else:
                payload["updated_at"] = datetime.now().isoformat()
                qdrant.set_payload(collection_name="memories", payload=payload, points=[memory_id])
            logger.info(f"Updated memory: {memory_id} for user: {current_user}")
            return [TextContent(type="text", text=json.dumps({"status": "updated", "memory_id": memory_id}))]
        except Exception as e:
            logger.error(f"Failed to update memory: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

    elif name == "sync_session":
        project = arguments["project"]

        # AC-08: Validate project against entity tree
        project_error = entity_tree.validate_project(project)
        if project_error:
            return [TextContent(type="text", text=json.dumps({"error": project_error}))]

        warnings = []
        details = {"decisions": [], "status_updates": [], "learnings": [], "feedback": []}
        created_count = 0
        updated_count = 0

        scope = "global" if project == "global" else "project"

        # --- decisions: always append (new records) ---
        for item in arguments.get("decisions", []):
            entity = item["entity"]
            # AC-09: Validate entity
            entity_warning = entity_tree.validate_entity(entity)
            if entity_warning:
                warnings.append(entity_warning)

            text = item["text"]
            embedding = list(embedder.embed([text]))[0].tolist()
            timestamp = datetime.now().isoformat()
            memory_id = generate_memory_id(entity + ":decision", timestamp)
            payload = {
                "user": current_user,
                "text": text,
                "memory_type": "episodic",
                "scope": scope,
                "entity": entity,
                "project": project if project != "global" else None,
                "task_id": None,
                "related_to": [],
                "relation_types": {},
                "tags": item.get("tags", []),
                "created_at": timestamp,
                "updated_at": timestamp,
                "status": None,
                "priority": None,
                "deleted": False,
            }
            qdrant.upsert(collection_name="memories", points=[PointStruct(id=memory_id, vector=embedding, payload=payload)])
            created_count += 1
            detail = {"memory_id": memory_id, "action": "created"}

            # AC-06: Handle supersedes
            if item.get("supersedes"):
                superseded_id = item["supersedes"]
                try:
                    sup_points = qdrant.retrieve(collection_name="memories", ids=[superseded_id])
                    if sup_points and sup_points[0].payload.get("user") == current_user:
                        sup_payload = sup_points[0].payload
                        related_to = sup_payload.get("related_to", [])
                        if memory_id not in related_to:
                            related_to.append(memory_id)
                        relation_types = sup_payload.get("relation_types", {})
                        relation_types[memory_id] = "supersedes"
                        sup_payload["related_to"] = related_to
                        sup_payload["relation_types"] = relation_types
                        sup_payload["updated_at"] = datetime.now().isoformat()
                        qdrant.set_payload(collection_name="memories", payload=sup_payload, points=[superseded_id])
                        # Also add reverse link on the new memory
                        payload["related_to"] = [superseded_id]
                        payload["relation_types"] = {superseded_id: "supersedes"}
                        payload["updated_at"] = datetime.now().isoformat()
                        qdrant.set_payload(collection_name="memories", payload=payload, points=[memory_id])
                    else:
                        warnings.append(f"Supersedes target '{superseded_id}' not found or not owned by user")
                except Exception as e:
                    logger.warning(f"Failed to create supersedes link for {superseded_id}: {e}")
                    warnings.append(f"Failed to create supersedes link for '{superseded_id}'")

            details["decisions"].append(detail)

        # --- status_updates: upsert by (entity, user, project, memory_type="project_context") ---
        for item in arguments.get("status_updates", []):
            entity = item["entity"]
            entity_warning = entity_tree.validate_entity(entity)
            if entity_warning:
                warnings.append(entity_warning)

            text = item["text"]
            status = item["status"]
            embedding = list(embedder.embed([text]))[0].tolist()
            timestamp = datetime.now().isoformat()

            # Look for existing record to upsert
            existing = find_by_entity(
                user=current_user, entity=entity,
                project=project if project != "global" else None,
                memory_type="project_context"
            )

            if len(existing) > 1:
                warnings.append(f"Multiple existing records for entity '{entity}' - updating most recent")

            if existing:
                # Update existing record
                point = existing[0]
                memory_id = point.id
                old_payload = point.payload
                old_payload["text"] = text
                old_payload["status"] = status
                old_payload["updated_at"] = timestamp
                # Re-embed with new text
                qdrant.upsert(collection_name="memories", points=[PointStruct(id=memory_id, vector=embedding, payload=old_payload)])
                updated_count += 1
                details["status_updates"].append({"memory_id": memory_id, "action": "updated", "previous_id": memory_id})
            else:
                # Create new record
                memory_id = generate_memory_id(entity + ":status", timestamp)
                payload = {
                    "user": current_user,
                    "text": text,
                    "memory_type": "project_context",
                    "scope": scope,
                    "entity": entity,
                    "project": project if project != "global" else None,
                    "task_id": None,
                    "related_to": [],
                    "relation_types": {},
                    "tags": [],
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "status": status,
                    "priority": None,
                    "deleted": False,
                }
                qdrant.upsert(collection_name="memories", points=[PointStruct(id=memory_id, vector=embedding, payload=payload)])
                created_count += 1
                details["status_updates"].append({"memory_id": memory_id, "action": "created"})

        # --- learnings: always append (new records) ---
        for item in arguments.get("learnings", []):
            entity = item["entity"]
            entity_warning = entity_tree.validate_entity(entity)
            if entity_warning:
                warnings.append(entity_warning)

            text = item["text"]
            embedding = list(embedder.embed([text]))[0].tolist()
            timestamp = datetime.now().isoformat()
            memory_id = generate_memory_id(entity + ":learning", timestamp)
            payload = {
                "user": current_user,
                "text": text,
                "memory_type": "episodic",
                "scope": scope,
                "entity": entity,
                "project": project if project != "global" else None,
                "task_id": None,
                "related_to": [],
                "relation_types": {},
                "tags": item.get("tags", []),
                "created_at": timestamp,
                "updated_at": timestamp,
                "status": None,
                "priority": None,
                "deleted": False,
            }
            qdrant.upsert(collection_name="memories", points=[PointStruct(id=memory_id, vector=embedding, payload=payload)])
            created_count += 1
            detail = {"memory_id": memory_id, "action": "created"}

            # AC-06: Handle supersedes
            if item.get("supersedes"):
                superseded_id = item["supersedes"]
                try:
                    sup_points = qdrant.retrieve(collection_name="memories", ids=[superseded_id])
                    if sup_points and sup_points[0].payload.get("user") == current_user:
                        sup_payload = sup_points[0].payload
                        related_to = sup_payload.get("related_to", [])
                        if memory_id not in related_to:
                            related_to.append(memory_id)
                        relation_types = sup_payload.get("relation_types", {})
                        relation_types[memory_id] = "supersedes"
                        sup_payload["related_to"] = related_to
                        sup_payload["relation_types"] = relation_types
                        sup_payload["updated_at"] = datetime.now().isoformat()
                        qdrant.set_payload(collection_name="memories", payload=sup_payload, points=[superseded_id])
                        payload["related_to"] = [superseded_id]
                        payload["relation_types"] = {superseded_id: "supersedes"}
                        payload["updated_at"] = datetime.now().isoformat()
                        qdrant.set_payload(collection_name="memories", payload=payload, points=[memory_id])
                    else:
                        warnings.append(f"Supersedes target '{superseded_id}' not found or not owned by user")
                except Exception as e:
                    logger.warning(f"Failed to create supersedes link for {superseded_id}: {e}")
                    warnings.append(f"Failed to create supersedes link for '{superseded_id}'")

            details["learnings"].append(detail)

        # --- feedback: upsert by (entity, user, memory_type="core_identity") ---
        for item in arguments.get("feedback", []):
            entity = item["entity"]
            entity_warning = entity_tree.validate_entity(entity)
            if entity_warning:
                warnings.append(entity_warning)

            text = item["text"]
            embedding = list(embedder.embed([text]))[0].tolist()
            timestamp = datetime.now().isoformat()

            existing = find_by_entity(
                user=current_user, entity=entity,
                memory_type="core_identity"
            )

            if len(existing) > 1:
                warnings.append(f"Multiple existing feedback records for entity '{entity}' - updating most recent")

            if existing:
                point = existing[0]
                memory_id = point.id
                old_payload = point.payload
                old_payload["text"] = text
                old_payload["updated_at"] = timestamp
                qdrant.upsert(collection_name="memories", points=[PointStruct(id=memory_id, vector=embedding, payload=old_payload)])
                updated_count += 1
                details["feedback"].append({"memory_id": memory_id, "action": "updated", "previous_id": memory_id})
            else:
                memory_id = generate_memory_id(entity + ":feedback", timestamp)
                payload = {
                    "user": current_user,
                    "text": text,
                    "memory_type": "core_identity",
                    "scope": "global",
                    "entity": entity,
                    "project": None,
                    "task_id": None,
                    "related_to": [],
                    "relation_types": {},
                    "tags": [],
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "status": None,
                    "priority": None,
                    "deleted": False,
                }
                qdrant.upsert(collection_name="memories", points=[PointStruct(id=memory_id, vector=embedding, payload=payload)])
                created_count += 1
                details["feedback"].append({"memory_id": memory_id, "action": "created"})

        result = {
            "summary": {
                "created": created_count,
                "updated": updated_count,
                "warnings": warnings,
            },
            "details": details,
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return [TextContent(type="text", text="Unknown tool")]
