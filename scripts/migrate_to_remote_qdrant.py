#!/usr/bin/env python3
"""Migrate data from embedded Qdrant (file-based) to standalone Qdrant (HTTP).

Usage:
    # Extract backup first:
    #   mkdir -p /tmp/qdrant-local && tar xzf backup/qdrant-backup-*.tar.gz -C /tmp/qdrant-local --strip-components=1
    #
    # Then run with standalone Qdrant already running:
    #   python scripts/migrate_to_remote_qdrant.py --source /tmp/qdrant-local --target http://localhost:6333

    python scripts/migrate_to_remote_qdrant.py --source <path-to-embedded-data> --target <qdrant-url>
"""

import argparse
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct


def migrate(source_path: str, target_url: str):
    print(f"Source (embedded): {source_path}")
    print(f"Target (remote):   {target_url}")

    src = QdrantClient(path=source_path)
    dst = QdrantClient(url=target_url, check_compatibility=False)

    # Get all collections from source
    collections = src.get_collections().collections
    print(f"\nFound {len(collections)} collections: {[c.name for c in collections]}")

    for col_info in collections:
        name = col_info.name
        col = src.get_collection(name)
        vectors_config = col.config.params.vectors
        print(f"\n--- Migrating collection '{name}' ---")
        print(f"  Vector size: {vectors_config.size}, distance: {vectors_config.distance}")
        print(f"  Points count: {col.points_count}")

        # Recreate collection on target
        try:
            dst.get_collection(name)
            print(f"  Collection '{name}' already exists on target, skipping creation")
        except Exception:
            dst.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=vectors_config.size,
                    distance=vectors_config.distance,
                ),
            )
            print(f"  Created collection '{name}' on target")

        # Scroll through all points and upsert in batches
        batch_size = 100
        offset = None
        total = 0

        while True:
            results, offset = src.scroll(
                collection_name=name,
                limit=batch_size,
                offset=offset,
                with_vectors=True,
                with_payload=True,
            )

            if not results:
                break

            points = [
                PointStruct(id=r.id, vector=r.vector, payload=r.payload)
                for r in results
            ]
            dst.upsert(collection_name=name, points=points)
            total += len(results)
            print(f"  Migrated {total} points...")

            if offset is None:
                break

        # Recreate payload indexes
        col_detail = src.get_collection(name)
        for field_name, field_index in (col_detail.payload_schema or {}).items():
            try:
                dst.create_payload_index(
                    collection_name=name,
                    field_name=field_name,
                    field_schema=field_index.data_type,
                )
                print(f"  Created index on '{field_name}'")
            except Exception as e:
                print(f"  Index on '{field_name}' skipped: {e}")

        # Verify
        dst_col = dst.get_collection(name)
        print(f"  Target now has {dst_col.points_count} points (source had {col.points_count})")
        if dst_col.points_count != col.points_count:
            print(f"  WARNING: Point count mismatch!")

    src.close()
    print("\nMigration complete!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate embedded Qdrant to standalone")
    parser.add_argument("--source", required=True, help="Path to embedded Qdrant data directory")
    parser.add_argument("--target", default="http://localhost:6333", help="Standalone Qdrant URL")
    args = parser.parse_args()
    migrate(args.source, args.target)
