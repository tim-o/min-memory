# src/storage.py

import asyncio
import logging
import os
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, Filter, FieldCondition, MatchValue, MatchAny
)
from fastembed import TextEmbedding

# --- Configuration ---
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Initialize Storage Clients ---
logger.info("Initializing storage...")
qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

# --- Helper Functions ---

def build_filter(user: str, scope=None, project=None, memory_type=None, task_id=None, entity=None, include_deleted=False):
    """Build Qdrant filter from parameters - always includes user filter and excludes deleted by default"""
    conditions = [
        FieldCondition(key="user", match=MatchValue(value=user))  # ALWAYS filter by user
    ]

    # Exclude soft-deleted memories unless explicitly requested
    if not include_deleted:
        conditions.append(FieldCondition(key="deleted", match=MatchValue(value=False)))

    if scope:
        conditions.append(FieldCondition(key="scope", match=MatchValue(value=scope)))
    if project:
        conditions.append(FieldCondition(key="project", match=MatchValue(value=project)))
    if memory_type:
        if isinstance(memory_type, list):
            conditions.append(FieldCondition(key="memory_type", match=MatchAny(any=memory_type)))
        else:
            conditions.append(FieldCondition(key="memory_type", match=MatchValue(value=memory_type)))
    if task_id:
        conditions.append(FieldCondition(key="task_id", match=MatchValue(value=task_id)))
    if entity:
        conditions.append(FieldCondition(key="entity", match=MatchValue(value=entity)))

    return Filter(must=conditions)

# --- Database Setup ---

def setup_qdrant():
    """Ensures the Qdrant collection and indexes exist."""
    try:
        qdrant.get_collection("memories")
        logger.info("Collection 'memories' already exists.")
    except Exception:
        logger.info("Creating Qdrant collection 'memories'...")
        qdrant.create_collection(
            collection_name="memories",
            vectors_config=VectorParams(size=384, distance=Distance.COSINE)
        )
        logger.info("Created collection 'memories'.")

        # Create payload indexes for fast filtering
        logger.info("Creating payload indexes...")
        for field in ["user", "scope", "project", "memory_type", "entity", "deleted"]:
            qdrant.create_payload_index(
                collection_name="memories",
                field_name=field,
                field_schema="keyword"
            )
        logger.info("Created payload indexes.")

def find_by_entity(user: str, entity: str, project: str | None = None,
                   memory_type: str | None = None) -> list:
    """Find memories matching exact entity + user + optional project/type.

    Returns points sorted by updated_at descending. Used for upsert logic.
    """
    scroll_filter = build_filter(
        user=user, entity=entity, project=project, memory_type=memory_type
    )
    results, _ = qdrant.scroll(
        collection_name="memories",
        scroll_filter=scroll_filter,
        limit=100,
        with_payload=True,
        with_vectors=False,
    )
    # Sort by updated_at descending (most recent first)
    results.sort(
        key=lambda p: p.payload.get("updated_at", ""),
        reverse=True,
    )
    return results


def update_access_tracking(memory_ids: list[str]) -> None:
    """Increment access_count and set last_accessed_at on returned memories.

    Fire-and-forget: errors are logged but do not propagate.
    Treats missing access_count as 0 (AC-20).
    """
    if not memory_ids:
        return

    now = datetime.now().isoformat()
    try:
        points = qdrant.retrieve(collection_name="memories", ids=memory_ids, with_payload=True)
        for point in points:
            current_count = point.payload.get("access_count", 0)
            qdrant.set_payload(
                collection_name="memories",
                payload={
                    "access_count": current_count + 1,
                    "last_accessed_at": now
                },
                points=[point.id]
            )
    except Exception as e:
        logger.warning(f"Failed to update access tracking for {len(memory_ids)} memories: {e}")


async def async_update_access_tracking(memory_ids: list[str]) -> None:
    """Async wrapper for access tracking updates (fire-and-forget)."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, update_access_tracking, memory_ids)


# Initialize the database on module import
setup_qdrant()
