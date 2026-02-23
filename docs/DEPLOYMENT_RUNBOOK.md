# GCP Deployment Runbook

This runbook deploys the MCP Memory Server on a GCE VM using docker-compose with three services: Qdrant (vector DB), MCP memory server, and Caddy (HTTPS reverse proxy).

## Prerequisites

- GCP project with billing enabled
- Static IP reserved (`gcloud compute addresses create mcp-memory-ip --region=us-central1`)
- DNS A record pointing your domain to the static IP
- gcloud CLI installed and authenticated

## Environment Variables

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export ZONE="us-central1-a"
export VM_NAME="mcp-memory-server"
```

## Step 1: Create VM with Persistent Disk (10 min)

```bash
# Create persistent disk for Qdrant data (survives VM deletion)
gcloud compute disks create mcp-memory-data \
  --zone=$ZONE --size=10GB --type=pd-standard

# Create VM with Ubuntu, attach data disk and static IP
gcloud compute instances create $VM_NAME \
  --zone=$ZONE \
  --machine-type=e2-small \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=20GB \
  --disk=name=mcp-memory-data,device-name=mcp-memory-data,mode=rw,auto-delete=no \
  --address=mcp-memory-ip \
  --tags=http-server,https-server \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

## Step 2: Configure Firewall (if not already done)

```bash
gcloud compute firewall-rules create allow-http-https \
  --project=$PROJECT_ID \
  --allow=tcp:80,tcp:443 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=http-server,https-server
```

## Step 3: Set Up VM (15 min)

```bash
gcloud compute ssh $VM_NAME --zone=$ZONE
```

On the VM:

```bash
# Format and mount persistent disk
sudo mkfs.ext4 -F /dev/disk/by-id/google-mcp-memory-data
sudo mkdir -p /mnt/data
sudo mount /dev/disk/by-id/google-mcp-memory-data /mnt/data
echo '/dev/disk/by-id/google-mcp-memory-data /mnt/data ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab

# Create Qdrant storage dir
sudo mkdir -p /mnt/data/qdrant
sudo chown -R 1000:1000 /mnt/data/qdrant

# Install Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Configure Docker for Artifact Registry
sudo gcloud auth configure-docker us-central1-docker.pkg.dev --quiet

# Clone repo
sudo git clone https://github.com/tim-o/min-memory.git /opt/mcp-memory
sudo chown -R $USER:$USER /opt/mcp-memory

# Create .env
cat > /opt/mcp-memory/.env <<EOF
AUTH0_DOMAIN=your-tenant.us.auth0.com
AUTH0_API_AUDIENCE=https://your-domain.com
TRUSTED_BACKEND_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
QDRANT_STORAGE_PATH=/mnt/data/qdrant
EOF

# Start services
cd /opt/mcp-memory
docker compose up -d
```

## Step 4: Verify Deployment

```bash
# Check all services are running
docker compose ps

# Test health endpoint
curl -sk https://your-domain.com/health

# Check Qdrant dashboard
curl -sk https://your-domain.com/qdrant/collections
```

## Updating the Application

CI/CD is handled by GitHub Actions (`.github/workflows/deploy.yml`). On push to `main`:

1. Builds and pushes Docker image to Artifact Registry
2. SSHs to the VM and runs `git pull && docker compose pull && docker compose up -d`

Manual update:

```bash
gcloud compute ssh $VM_NAME --zone=$ZONE -- \
  "cd /opt/mcp-memory && git pull origin main && docker compose pull && docker compose up -d"
```

## Data Migration (from embedded Qdrant)

If migrating from a file-based embedded Qdrant setup:

```bash
# 1. Back up embedded data from old VM
gcloud compute ssh OLD_VM --zone=$ZONE -- \
  "tar czf - -C /path/to qdrant" > backup/qdrant-backup.tar.gz

# 2. Extract locally
mkdir -p /tmp/qdrant-local
tar xzf backup/qdrant-backup.tar.gz -C /tmp/qdrant-local --strip-components=1

# 3. Run migration script (with standalone Qdrant already running)
python scripts/migrate_to_remote_qdrant.py \
  --source /tmp/qdrant-local \
  --target http://QDRANT_IP:6333
```

The migration script reads from the embedded SQLite format and writes to the standalone HTTP API.

## Troubleshooting

```bash
# View all logs
gcloud compute ssh $VM_NAME --zone=$ZONE -- \
  "cd /opt/mcp-memory && docker compose logs -f"

# View specific service logs
gcloud compute ssh $VM_NAME --zone=$ZONE -- \
  "cd /opt/mcp-memory && docker compose logs mcp-memory"

# Check disk usage
gcloud compute ssh $VM_NAME --zone=$ZONE -- \
  "df -h /mnt/data"

# Restart all services
gcloud compute ssh $VM_NAME --zone=$ZONE -- \
  "cd /opt/mcp-memory && docker compose restart"
```

## Cost Estimate

- **e2-small VM**: ~$13/month
- **20GB boot disk**: ~$1/month (pd-standard)
- **10GB data disk**: ~$0.50/month (pd-standard)
- **Static IP**: ~$3/month (while attached)
- **Artifact Registry**: ~$0.10/GB/month

**Total**: ~$18/month

## Rollback

```bash
# The persistent disk (mcp-memory-data) has auto-delete=no,
# so it survives VM deletion. To recreate:
gcloud compute instances delete $VM_NAME --zone=$ZONE
# Then follow Step 1 (skip disk creation) and Step 3.
```
