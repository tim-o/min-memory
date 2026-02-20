# src/storage.py

import logging
import os
import pathlib
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, Filter, FieldCondition, MatchValue, MatchAny
)
from fastembed import TextEmbedding

# --- Configuration ---
DATA_DIR = pathlib.Path(os.getenv("MCP_DATA_DIR", pathlib.Path.home() / ".local" / "share" / "mcp-memory-http"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Initialize Storage Clients ---
logger.info("Initializing storage...")
qdrant = QdrantClient(path=str(DATA_DIR / "qdrant"))
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

# Initialize the database on module import
setup_qdrant()
