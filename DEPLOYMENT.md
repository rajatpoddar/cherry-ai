# 🐳 Deployment Guide

> How to deploy Cherry to production (NAS).

## 🏠 Deployment Options

| Option | Pros | Cons | Best for |
|--------|------|------|----------|
| **Laptop (current)** | Easy dev, full NAS access via Tailscale | Must be on for Cherry | Personal use |
| **NAS Docker** | Always on, fast Ollama, no Tailscale needed | Uses NAS resources | Production |
| **VPS (future)** | Public access, Cloudflare tunnel | Cost, maintenance | Multi-device |

Currently: **Laptop for dev, NAS planned for prod.**

---

## 📦 NAS Docker Deployment (Recommended)

### Prerequisites
- SSH access to NAS: `ssh rajat@100.98.94.128`
- Docker + Docker Compose on NAS
- `/volume1/docker/` mounted and writable

### Step 1: Create cherry directory
```bash
ssh rajat@100.98.94.128
sudo mkdir -p /volume1/docker/cherry
sudo chown rajat:users /volume1/docker/cherry
cd /volume1/docker/cherry
```

### Step 2: Copy files from laptop
```bash
# On laptop
cd /Users/rajatpoddar/Developer/development/mybuffy
rsync -avz --exclude '__pycache__' --exclude 'data/*.db' cherry/ rajat@100.98.94.128:/volume1/docker/cherry/
```

### Step 3: Create docker-compose.yml
```yaml
version: '3.8'

services:
  cherry-backend:
    build: ./backend
    container_name: cherry-backend
    restart: unless-stopped
    ports:
      - "3003:3003"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - OLLAMA_HOST=http://host.docker.internal:11434
      - CHERRY_LOCAL=1
      - CHERRY_PORT=3003
    extra_hosts:
      - "host.docker.internal:host-gateway"

  # Optional: nginx for HTTPS
  nginx:
    image: nginx:alpine
    container_name: cherry-nginx
    restart: unless-stopped
    ports:
      - "3004:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - cherry-backend
```

### Step 4: Create Dockerfile in backend/
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 3003

CMD ["python", "main.py"]
```

### Step 5: Build and run
```bash
cd /volume1/docker/cherry
docker-compose up -d
docker-compose logs -f cherry-backend
```

### Step 6: Test
```bash
curl http://localhost:3003/health
```

### Step 7: Cloudflare tunnel (external access)
In Cloudflare tunnel config:
```yaml
- hostname: cherry.yourdomain.com
  service: http://localhost:3003
```

---

## 🔧 Configuration (.env)

Create `.env` in cherry root:

```bash
# Ollama
OLLAMA_HOST=http://100.98.94.128:11434  # Use NAS Ollama
# OLLAMA_HOST=http://host.docker.internal:11434  # If Ollama in different container

# Models
CHERRY_MODEL=qwen2.5:3b
CHERRY_CODER_MODEL=qwen2.5:3b

# Server
NAS_HOST=100.98.94.128
NAS_USER=rajat
CHERRY_LOCAL=0  # 0 = SSH to NAS, 1 = run locally

# Cherry server
CHERRY_PORT=3003
CHERRY_HOST=0.0.0.0

# Optional: Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## 🔄 Updating Cherry

```bash
# On laptop, make changes
cd /Users/rajatpoddar/Developer/development/mybuffy
rsync -avz cherry/ rajat@100.98.94.128:/volume1/docker/cherry/

# On NAS
ssh rajat@100.98.94.128
cd /volume1/docker/cherry
docker-compose restart cherry-backend
docker-compose logs -f cherry-backend
```

---

## 💾 Backup

Cherry's data lives in `/volume1/docker/cherry/data/`. Backup script:

```bash
#!/bin/bash
# /volume1/docker/cherry/backup.sh
BACKUP_DIR=/volume1/backups/cherry/$(date +%Y-%m-%d)
mkdir -p $BACKUP_DIR
cp -r /volume1/docker/cherry/data $BACKUP_DIR/
echo "Backed up to $BACKUP_DIR"
```

Add to cron:
```bash
0 2 * * * /volume1/docker/cherry/backup.sh
```

---

## 🩺 Health Monitoring

Cherry exposes `/health` endpoint. Add to Uptime Kuma or similar:
- URL: `http://100.98.94.128:3003/health`
- Check: `status == "healthy"`
- Interval: 60s

---

## 🐛 Troubleshooting

### Cherry not starting:
```bash
docker logs cherry-backend
# Common: missing .env, port conflict, ollama not reachable
```

### Ollama not reachable from Cherry container:
- Use `host.docker.internal:11434` (Docker Desktop)
- Or run Cherry in `--network host` mode
- Or use NAS internal IP

### Database issues:
```bash
docker exec -it cherry-backend python3 -c "import memory; print(memory.get_stats())"
```

### Reset everything:
```bash
docker-compose down
rm -rf data/cherry_memory.db logs/*
docker-compose up -d
```

---

## 📋 Production Checklist

Before going live:
- [ ] All endpoints tested with curl
- [ ] CORS restricted to your domain
- [ ] HTTPS via Cloudflare tunnel
- [ ] Backup cron running
- [ ] Health monitoring active
- [ ] Logs rotated (logrotate or similar)
- [ ] No `0.0.0.0` exposure beyond intended
- [ ] Strong SSH key (not password)
- [ ] Tailscale ACL restricts Cherry to Rajjoo only

---

*Last updated: 2026-09-02*