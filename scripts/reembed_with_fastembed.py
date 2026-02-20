#!/usr/bin/env python3
"""
Re-embed all existing memories with FastEmbed (ONNX) instead of sentence-transformers (PyTorch)

This is necessary because FastEmbed and sentence-transformers use different models
with different vector dimensions, so existing embeddings won't work.
"""
from qdrant_client import QdrantClient
from fastembed import TextEmbedding
import pathlib
import os
import sys

def reembed_database(data_dir: str):
    """Re-embed all memories in the database"""
    print(f"Re-embedding database at: {data_dir}")

    # Initialize
    qdrant = QdrantClient(path=data_dir)
    embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

    # Get collection info
    try:
        collection_info = qdrant.get_collection("memories")
        print(f"Collection 'memories' found with {collection_info.points_count} points")
    except Exception as e:
        print(f"Error: Could not find collection 'memories': {e}")
        return False

    # Scroll through all points
    offset = None
    reembedded_count = 0
    batch = []

    print("\nRe-embedding memories...")

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
            text = point.payload.get("text", "")
            if not text:
                print(f"Warning: Memory {point.id} has no text, skipping")
                continue

            # Generate new embedding with FastEmbed
            embedding = list(embedder.embed([text]))[0].tolist()

            # Add to batch
            batch.append({
                "id": point.id,
                "vector": embedding,
                "payload": point.payload
            })

            reembedded_count += 1
            if reembedded_count % 10 == 0:
                print(f"  Re-embedded {reembedded_count} memories...")

        # Check if we're done
        if next_offset is None:
            break

        offset = next_offset

    # Update all points in batch
    if batch:
        print(f"\nUpdating {len(batch)} memories in Qdrant...")
        from qdrant_client.models import PointStruct

        points = [
            PointStruct(
                id=item["id"],
                vector=item["vector"],
                payload=item["payload"]
            )
            for item in batch
        ]

        qdrant.upsert(
            collection_name="memories",
            points=points
        )

        print(f"✓ Successfully re-embedded {reembedded_count} memories")
        return True
    else:
        print("No memories to re-embed")
        return True

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Re-embed memories with FastEmbed")
    parser.add_argument("--database", default="http", choices=["stdio", "http", "both"],
                       help="Which database to re-embed (default: http)")
    args = parser.parse_args()

    # Database paths
    data_dir_stdio = str(pathlib.Path.home() / ".local" / "share" / "mcp-memory" / "qdrant")
    data_dir_http = str(pathlib.Path.home() / ".local" / "share" / "mcp-memory-http" / "qdrant")

    print("=== MCP Memory Re-embedding: FastEmbed Migration ===\n")
    print("WARNING: This will replace all existing embeddings!")
    print("Make sure to stop all MCP servers before running this.\n")

    success = True

    if args.database in ["stdio", "both"]:
        print(f"Re-embedding stdio database: {data_dir_stdio}")
        if os.path.exists(data_dir_stdio):
            if reembed_database(data_dir_stdio):
                print("\n✓ Stdio database re-embedding successful\n")
            else:
                print("\n✗ Stdio database re-embedding failed\n")
                success = False
        else:
            print(f"Stdio database not found at {data_dir_stdio}, skipping\n")

    if args.database in ["http", "both"]:
        print(f"Re-embedding HTTP database: {data_dir_http}")
        if os.path.exists(data_dir_http):
            if reembed_database(data_dir_http):
                print("\n✓ HTTP database re-embedding successful\n")
            else:
                print("\n✗ HTTP database re-embedding failed\n")
                success = False
        else:
            print(f"HTTP database not found at {data_dir_http}, skipping\n")

    if success:
        print("=== All re-embedding complete ===")
        print("\nYou can now start your MCP servers with FastEmbed.")
    else:
        print("=== Re-embedding failed ===")
        sys.exit(1)
