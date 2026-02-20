# GCP Container-Optimized Deployment Runbook

This runbook deploys the MCP Memory Server using GCP Container-Optimized OS with automatic container deployment.

## Prerequisites

- GCP project with billing enabled
- Static IP already reserved (let's call it `STATIC_IP`)
- Docker installed locally
- gcloud CLI installed and authenticated

## Environment Variables

Set these before starting:

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export ZONE="us-central1-a"
export STATIC_IP="your-static-ip"
export TIM_TOKEN=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Save token somewhere safe!
echo "TIM_TOKEN: $TIM_TOKEN"
```

## Step 1: Build and Push Docker Image (5 min)

```bash
# Authenticate Docker with GCR
gcloud auth configure-docker

# Enable artifact registry
gcloud services enable artifactregistry.googleapis.com --project=$PROJECT_ID

# Create a repository (one-time setup)
  gcloud artifacts repositories create mcp-memory \
      --repository-format=docker \
      --location=$REGION \
      --project=$PROJECT_ID \
      --description="MCP Memory Server"

# Build the image
cd /path/to/min-memory
docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/mcp-memory/server:latest .

# Push
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/mcp-memory/server:latest

Updated Image Path Format

Old (GCR): gcr.io/PROJECT_ID/mcp-memory:latest
New (Artifact Registry): REGION-docker.pkg.dev/PROJECT_ID/REPO_NAME/IMAGE_NAME:TAG

Example: us-central1-docker.pkg.dev/my-project/mcp-memory/server:latest

Update Your Deployment Command

In the runbook, replace the --container-image flag:

--container-image=${REGION}-docker.pkg.dev/${PROJECT_ID}/mcp-memory/server:latest
```

## Step 2: Provision GCE Instance with Container (10 min)

```bash
# Create the instance with container-optimized OS
gcloud compute instances create-with-container mcp-memory-server \
  --project=$PROJECT_ID \
  --zone=$ZONE \
  --machine-type=e2-small \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-ssd \
  --image-family=cos-stable \
  --image-project=cos-cloud \
  --container-image=${REGION}-docker.pkg.dev/${PROJECT_ID}/mcp-memory/server:latest \
  --container-restart-policy=always \
  --container-env=TIM_TOKEN=$TIM_TOKEN,MCP_DATA_DIR=/var/lib/data,PORT=8080 \
  --container-mount-host-path=mount-path=/var/lib/data,host-path=/mnt/stateful_partition/data,mode=rw \
  --address=$STATIC_IP \
  --tags=http-server,https-server \
  --scopes=cloud-platform

# Note: cos-stable uses /mnt/stateful_partition for persistent data across reboots
```

## Step 3: Configure Firewall (if not already done)

```bash
# Allow HTTP/HTTPS traffic
gcloud compute firewall-rules create allow-http-https \
  --project=$PROJECT_ID \
  --allow=tcp:80,tcp:443 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=http-server,https-server \
  --description="Allow HTTP and HTTPS traffic"
```

## Step 4: Set Up HTTPS with Caddy (10 min)

The MCP server is running, but we need HTTPS. We'll use Cloud Run for Caddy or run Caddy as a second container.

**Option A: Add Caddy to the same VM**

```bash
# SSH into instance
gcloud compute ssh mcp-memory-server --zone=$ZONE --project=$PROJECT_ID

# Install Caddy via docker (Container-Optimized OS doesn't have apt)
docker run -d \
  --name caddy \
  --restart=always \
  --network=host \
  -v /mnt/stateful_partition/caddy/data:/data \
  -v /mnt/stateful_partition/caddy/config:/config \
  -e STATIC_IP=$STATIC_IP \
  caddy:2-alpine \
  caddy reverse-proxy --from https://$STATIC_IP --to localhost:8080 --internal-certs

exit
```

**Option B: Use Cloud Run for Caddy (Simpler)**

Actually, for IP-based HTTPS without a domain, this gets messy. Let's use Option A.

## Step 5: Migrate Existing Data (Optional, 10 min)

If you have existing Qdrant data locally:

```bash
# Create temporary archive
cd ~/.local/share/mcp-memory-http
tar czf /tmp/qdrant-data.tar.gz qdrant/

# Copy to instance
gcloud compute scp /tmp/qdrant-data.tar.gz \
  mcp-memory-server:/tmp/ \
  --zone=$ZONE --project=$PROJECT_ID

# SSH and extract
gcloud compute ssh mcp-memory-server --zone=$ZONE --project=$PROJECT_ID

# Extract data
sudo mkdir -p /mnt/stateful_partition/data
sudo tar xzf /tmp/qdrant-data.tar.gz -C /mnt/stateful_partition/data
sudo chown -R chronos:chronos /mnt/stateful_partition/data
rm /tmp/qdrant-data.tar.gz

# Restart container to pick up data
docker restart $(docker ps -q --filter ancestor=gcr.io/$PROJECT_ID/mcp-memory:latest)

exit
```

## Step 6: Verify Deployment (5 min)

```bash
# Check container is running
gcloud compute ssh mcp-memory-server --zone=$ZONE --project=$PROJECT_ID -- \
  "docker ps"

# Check logs
gcloud compute ssh mcp-memory-server --zone=$ZONE --project=$PROJECT_ID -- \
  "docker logs \$(docker ps -q --filter ancestor=gcr.io/$PROJECT_ID/mcp-memory:latest)"

# Test health endpoint
curl -k https://$STATIC_IP/health

# Test with auth
curl -k -H "Authorization: Bearer $TIM_TOKEN" https://$STATIC_IP/mcp
```

## Step 7: Configure Claude Code Client

Update `~/.config/claude-code/mcp_config.json`:

```json
{
  "mcpServers": {
    "memory": {
      "url": "https://YOUR_STATIC_IP",
      "transport": "sse",
      "headers": {
        "Authorization": "Bearer YOUR_TIM_TOKEN"
      }
    }
  }
}
```

Restart Claude Code and test:
```bash
claude mcp  # Should show memory server connected
```

## Step 8: Set Up Backups (10 min)

Create a backup script that runs via Cloud Scheduler (or cron on the VM):

```bash
# SSH to instance
gcloud compute ssh mcp-memory-server --zone=$ZONE --project=$PROJECT_ID

# Create backup script
cat > /mnt/stateful_partition/backup.sh <<'SCRIPT'
#!/bin/bash
DATE=$(date +%Y%m%d-%H%M%S)
BACKUP_FILE="/tmp/qdrant-backup-$DATE.tar.gz"
BUCKET="gs://mcp-memory-backups-$PROJECT_ID"

# Backup
tar czf "$BACKUP_FILE" -C /mnt/stateful_partition data/

# Upload to GCS
docker run --rm \
  -v /tmp:/tmp:ro \
  -v /root/.config/gcloud:/root/.config/gcloud:ro \
  google/cloud-sdk:alpine \
  gsutil cp "$BACKUP_FILE" "$BUCKET/"

# Cleanup local
rm "$BACKUP_FILE"

# Retain last 7 backups
docker run --rm \
  -v /root/.config/gcloud:/root/.config/gcloud:ro \
  google/cloud-sdk:alpine \
  bash -c "gsutil ls '$BUCKET/' | sort | head -n -7 | xargs -r gsutil rm"
SCRIPT

chmod +x /mnt/stateful_partition/backup.sh

# Test backup
sudo /mnt/stateful_partition/backup.sh

exit
```

Create cron job via Cloud Scheduler (easier than cron on COS):

```bash
# Create GCS bucket
gsutil mb -l $REGION gs://mcp-memory-backups-$PROJECT_ID

# Create Cloud Scheduler job (requires Cloud Scheduler API enabled)
gcloud scheduler jobs create http mcp-memory-backup \
  --schedule="0 2 * * *" \
  --uri="https://www.googleapis.com/compute/v1/projects/$PROJECT_ID/zones/$ZONE/instances/mcp-memory-server/start" \
  --http-method=POST \
  --message-body='{"script":"/mnt/stateful_partition/backup.sh"}' \
  --description="Daily backup of MCP Memory data"

# Alternative: Use cron on the VM
gcloud compute ssh mcp-memory-server --zone=$ZONE --project=$PROJECT_ID -- \
  "echo '0 2 * * * /mnt/stateful_partition/backup.sh >> /var/log/backup.log 2>&1' | sudo crontab -"
```

## Updating the Application

```bash
# Build new image
cd /path/to/min-memory
docker build -t gcr.io/$PROJECT_ID/mcp-memory:latest .
docker push gcr.io/$PROJECT_ID/mcp-memory:latest

# Update instance (will pull new image and restart)
gcloud compute instances update-container mcp-memory-server \
  --zone=$ZONE \
  --project=$PROJECT_ID \
  --container-image=gcr.io/$PROJECT_ID/mcp-memory:latest
```

## Troubleshooting

```bash
# View container logs
gcloud compute ssh mcp-memory-server --zone=$ZONE -- \
  "docker logs -f \$(docker ps -q)"

# Check container status
gcloud compute ssh mcp-memory-server --zone=$ZONE -- \
  "docker ps -a"

# Check disk usage
gcloud compute ssh mcp-memory-server --zone=$ZONE -- \
  "df -h /mnt/stateful_partition"

# Restart container
gcloud compute ssh mcp-memory-server --zone=$ZONE -- \
  "docker restart \$(docker ps -q)"
```

## Cost Estimate

- **e2-small**: ~$13.21/month
- **20GB SSD**: ~$3.40/month
- **Static IP**: ~$3/month (if attached)
- **GCR storage**: ~$0.26/GB/month (first 0.5GB free)
- **Egress**: First 1GB free, then $0.12/GB

**Total**: ~$19.61/month after credits

## Rollback

```bash
# Stop and delete instance
gcloud compute instances delete mcp-memory-server \
  --zone=$ZONE --project=$PROJECT_ID

# Data is backed up in GCS, can restore anytime
```
