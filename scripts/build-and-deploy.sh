#!/bin/bash
set -e

echo "=== Building and Deploying MCP Memory Server ==="
echo ""

NO_CACHE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cache)
            NO_CACHE=1
            shift
            ;;
        *)
            echo "ERROR: Unknown argument: $1"
            echo "Usage: $0 [--no-cache]"
            exit 1
            ;;
    esac
done

# Check PROJECT_ID is set
if [ -z "$PROJECT_ID" ]; then
    echo "ERROR: PROJECT_ID environment variable not set"
    exit 1
fi

IMAGE="us-central1-docker.pkg.dev/$PROJECT_ID/mcp-memory/server:latest"

echo "Building image: $IMAGE"
if [ "$NO_CACHE" -eq 1 ]; then
    echo "  (docker build --no-cache)"
fi

BUILD_ARGS=()
if [ "$NO_CACHE" -eq 1 ]; then
    BUILD_ARGS+=(--no-cache)
fi

docker build "${BUILD_ARGS[@]}" -t "$IMAGE" .

echo ""
echo "Pushing to Artifact Registry..."
docker push "$IMAGE"

echo ""
echo "Image pushed successfully!"
echo ""
echo "Restarting GCP instance with 'gcloud compute instances reset mcp-memory-server'"
gcloud compute instances reset mcp-memory-server
echo ""
echo "Or SSH and restart manually:"
echo "  gcloud compute ssh mcp-memory-server-instance --zone=us-central1-a"
echo "  sudo docker pull $IMAGE"
echo "  sudo systemctl restart konlet-startup"
echo ""
