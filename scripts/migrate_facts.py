#!/usr/bin/env python3
"""One-time migration script to move facts from SQLite to Qdrant vector storage"""

import sqlite3
import sys
import pathlib
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from datetime import datetime
import hashlib

DATA_DIR = pathlib.Path.home() / ".local" / "share" / "mcp-memory"
SQLITE_DB = DATA_DIR / "memory.db"

def generate_memory_id(entity: str, timestamp: str) -> str:
    """Generate semantic ID: mem_{entity}_{timestamp_hash}"""
    ts_hash = hashlib.md5(timestamp.encode()).hexdigest()[:6]
    safe_entity = entity.lower().replace(" ", "_")[:30]
    return f"mem_{safe_entity}_{ts_hash}"

def migrate():
    print("Starting migration from SQLite to Qdrant...")

    # Check if SQLite DB exists
    if not SQLITE_DB.exists():
        print(f"SQLite database not found at {SQLITE_DB}")
        print("Nothing to migrate.")
        return

    # Connect to SQLite
    db = sqlite3.connect(str(SQLITE_DB))
    cursor = db.execute("SELECT entity, attribute, value, timestamp FROM facts")
    facts = cursor.fetchall()

    if not facts:
        print("No facts found in SQLite database")
        return

    print(f"Found {len(facts)} facts to migrate")

    # Initialize Qdrant and embedder
    qdrant = QdrantClient(path=str(DATA_DIR / "qdrant"))
    embedder = SentenceTransformer('all-MiniLM-L6-v2')

    # Migrate each fact
    migrated = 0
    for entity, attribute, value, timestamp in facts:
        # Determine scope and memory type
        if entity in ["user_preferences", "system", "technical"]:
            scope = "global"
            memory_type = "core_identity"
            project = None
        elif entity == "clarity":
            scope = "project"
            memory_type = "project_context"
            project = "clarity"
        else:
            # Default to global for unknown entities
            scope = "global"
            memory_type = "core_identity"
            project = None

        # Create memory text
        text = value  # Use the value as the primary text

        # Generate embedding
        embedding = embedder.encode(text).tolist()

        # Generate memory ID
        if not timestamp:
            timestamp = datetime.now().isoformat()
        memory_id = generate_memory_id(entity, timestamp)

        # Create payload
        payload = {
            "text": text,
            "memory_type": memory_type,
            "scope": scope,
            "entity": entity,
            "project": project,
            "task_id": None,
            "related_to": [],
            "relation_types": {},
            "tags": [attribute] if attribute else [],
            "created_at": timestamp,
            "updated_at": timestamp,
            "status": None,
            "priority": None
        }

        # Store in Qdrant
        from qdrant_client.models import PointStruct
        qdrant.upsert(
            collection_name="memories",
            points=[
                PointStruct(
                    id=memory_id,
                    vector=embedding,
                    payload=payload
                )
            ]
        )

        migrated += 1
        print(f"Migrated: {entity}.{attribute} → {memory_id}")

    print(f"\nMigration complete: {migrated} facts migrated to Qdrant")
    print(f"\nSQLite database preserved at: {SQLITE_DB}")
    print("You can delete it manually if migration looks good.")

    db.close()

if __name__ == "__main__":
    try:
        migrate()
    except Exception as e:
        print(f"Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
