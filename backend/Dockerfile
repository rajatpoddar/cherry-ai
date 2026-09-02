# 🌸 Cherry Backend Dockerfile
# FastAPI server for Cherry AI girlfriend + server assistant

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies.
# Cherry runs server queries (docker ps, df -h, free -h, uptime, nproc)
# from inside this container, so we need real Linux tools, not just
# python's stdlib. Also install docker CLI so we can talk to the host
# docker daemon via the mounted socket.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    procps \
    coreutils \
    util-linux \
    binutils \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

# Install Docker CLI (client only — we connect to the host daemon via socket)
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
       > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
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
