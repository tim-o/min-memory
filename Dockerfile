# Use slim base image for minimal size
FROM python:3.12-slim

WORKDIR /app

# Install dependencies (fastembed uses ONNX, no PyTorch needed)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/


# Environment defaults
ENV MCP_DATA_DIR=/var/lib/data
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Create data directory
RUN mkdir -p /var/lib/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run the server
CMD ["python", "-m", "src.main"]
