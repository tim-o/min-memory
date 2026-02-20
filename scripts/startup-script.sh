#!/bin/bash
# GCE startup script - runs on every boot
# Starts Caddy reverse proxy for HTTPS termination

# Get static IP from instance metadata
STATIC_IP=$(curl -s "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip" -H "Metadata-Flavor: Google")

# Wait for docker to be ready
while ! docker info >/dev/null 2>&1; do
  echo "Waiting for docker..."
  sleep 2
done

# Create Caddyfile for IP-based HTTPS with self-signed cert
mkdir -p /mnt/stateful_partition/caddy
cat > /mnt/stateful_partition/caddy/Caddyfile <<'EOF'
{
  auto_https off
}

:443 {
  tls internal {
    on_demand
  }
  reverse_proxy localhost:8080 {
    header_up Accept "application/json, text/event-stream"
  }
}
EOF

# Check if caddy container already exists
if docker ps -a --format '{{.Names}}' | grep -q '^caddy$'; then
  echo "Caddy container exists, restarting with new config..."
  docker rm -f caddy
fi

echo "Creating caddy container..."
docker run -d \
  --name caddy \
  --restart=always \
  --network=host \
  -v /mnt/stateful_partition/caddy/Caddyfile:/etc/caddy/Caddyfile \
  -v /mnt/stateful_partition/caddy/data:/data \
  -v /mnt/stateful_partition/caddy/config:/config \
  caddy:2-alpine

echo "Startup script complete"
