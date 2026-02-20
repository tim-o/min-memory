# src/tools.py

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
from .storage import qdrant, embedder, build_filter
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
                    "score_threshold": {"type": "number", "default": 0.0}
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
        if project and not explicit_scope:
            global_filter = build_filter(user=current_user, scope="global", memory_type=arguments.get("memory_type"), task_id=arguments.get("task_id"))
            project_filter = build_filter(user=current_user, project=project, memory_type=arguments.get("memory_type"), task_id=arguments.get("task_id"))
            global_response = qdrant.query_points(collection_name="memories", query=query_embedding, query_filter=global_filter, limit=limit // 2)
            project_response = qdrant.query_points(collection_name="memories", query=query_embedding, query_filter=project_filter, limit=limit // 2)
            results = sorted(global_response.points + project_response.points, key=lambda x: x.score, reverse=True)[:limit]
        else:
            query_filter = build_filter(user=current_user, scope=explicit_scope, project=project, memory_type=arguments.get("memory_type"), task_id=arguments.get("task_id"))
            results = qdrant.query_points(collection_name="memories", query=query_embedding, query_filter=query_filter, limit=limit).points
        score_threshold = arguments.get("score_threshold", 0.0)
        filtered_results = [r for r in results if r.score >= score_threshold]
        context = []
        for result in filtered_results:
            memory = {
                "id": result.id,
                "text": result.payload["text"],
                "memory_type": result.payload["memory_type"],
                "scope": result.payload["scope"],
                "entity": result.payload["entity"],
                "project": result.payload.get("project"),
                "score": result.score,
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

    return [TextContent(type="text", text="Unknown tool")]
