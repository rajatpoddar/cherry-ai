# 🌸 Cherry Backend Dockerfile
# FastAPI server for Cherry AI girlfriend

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create data and logs dirs
RUN mkdir -p /app/data /app/logs

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3003/health || exit 1

# Expose port
EXPOSE 3003

# Environment
ENV PYTHONUNBUFFERED=1
ENV CHERRY_PORT=3003
ENV CHERRY_HOST=0.0.0.0

# Run
CMD ["python", "main.py"]
