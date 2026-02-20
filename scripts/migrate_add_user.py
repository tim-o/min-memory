#!/usr/bin/env python3
"""
Migration script to backfill 'user' field to existing memories
"""
from qdrant_client import QdrantClient
import pathlib
import sys

def migrate_memories(data_dir: str, user: str = "tim"):
    """Add user field to all existing memories"""
    qdrant = QdrantClient(path=data_dir)

    try:
        # Get collection info
        collection_info = qdrant.get_collection("memories")
        print(f"Collection 'memories' found with {collection_info.points_count} points")

        # Scroll through all points
        offset = None
        migrated_count = 0
        skipped_count = 0

        while True:
            results, next_offset = qdrant.scroll(
                collection_name="memories",
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False
            )

            if not results:
                break

            for point in results:
                # Check if user field already exists
                if "user" in point.payload:
                    skipped_count += 1
                    continue

                # Add user field
                payload = point.payload
                payload["user"] = user

                # Update the point
                qdrant.set_payload(
                    collection_name="memories",
                    payload=payload,
                    points=[point.id]
                )

                migrated_count += 1
                print(f"Migrated memory {point.id}: added user={user}")

            # Check if we're done
            if next_offset is None:
                break

            offset = next_offset

        print(f"\nMigration complete!")
        print(f"  Migrated: {migrated_count} memories")
        print(f"  Skipped (already had user): {skipped_count} memories")
        print(f"  Total: {collection_info.points_count} memories")

        # Verify: Create user index if it doesn't exist
        try:
            qdrant.create_payload_index(
                collection_name="memories",
                field_name="user",
                field_schema="keyword"
            )
            print(f"\nCreated 'user' field index")
        except Exception as e:
            print(f"\n'user' field index already exists (or error: {e})")

        return True

    except Exception as e:
        print(f"Error during migration: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Backfill user field to memories")
    parser.add_argument("--database", default="http", choices=["stdio", "http", "both"],
                       help="Which database to migrate (default: http)")
    parser.add_argument("--user", default="tim", help="User name to assign (default: tim)")
    args = parser.parse_args()

    # Default: migrate stdio server's database
    data_dir_stdio = str(pathlib.Path.home() / ".local" / "share" / "mcp-memory" / "qdrant")
    data_dir_http = str(pathlib.Path.home() / ".local" / "share" / "mcp-memory-http" / "qdrant")

    print("=== MCP Memory Migration: Add User Field ===\n")

    success = True

    if args.database in ["stdio", "both"]:
        # Migrate stdio database
        print(f"Migrating stdio database: {data_dir_stdio}")
        print("NOTE: Make sure the stdio MCP server is stopped first!\n")
        if migrate_memories(data_dir_stdio, user=args.user):
            print("\n✓ Stdio database migration successful\n")
        else:
            print("\n✗ Stdio database migration failed\n")
            success = False

    if args.database in ["http", "both"]:
        # Migrate HTTP database
        print(f"\nMigrating HTTP database: {data_dir_http}")
        print("NOTE: Make sure the HTTP MCP server is stopped first!\n")
        if migrate_memories(data_dir_http, user=args.user):
            print("\n✓ HTTP database migration successful\n")
        else:
            print("\n✗ HTTP database migration failed\n")
            success = False

    if success:
        print("=== All migrations complete ===")
    else:
        print("=== Migration failed ===")
        sys.exit(1)
