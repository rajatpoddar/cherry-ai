#!/bin/bash
# 🌸 Cherry — NAS Deploy Script
# Deploys Cherry to Synology NAS via Tailscale
# Usage: ./scripts/deploy-to-nas.sh

set -e

# Configuration
NAS_HOST="${NAS_HOST:-100.98.94.128}"
NAS_USER="${NAS_USER:-rajat}"
NAS_DEPLOY_DIR="/volume1/docker/cherry"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🌸 Cherry — NAS Deploy${NC}"
echo "================================"
echo -e "NAS: ${NAS_USER}@${NAS_HOST}"
echo -e "Local: ${LOCAL_DIR}"
echo -e "Remote: ${NAS_DEPLOY_DIR}"
echo ""

# 1. Check prerequisites
echo -e "${BLUE}▶ Checking prerequisites...${NC}"
if ! command -v ssh &> /dev/null; then
    echo -e "${RED}✗ ssh not found${NC}"
    exit 1
fi
if ! command -v rsync &> /dev/null; then
    echo -e "${RED}✗ rsync not found${NC}"
    exit 1
fi

# Test SSH connection
if ! ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "${NAS_USER}@${NAS_HOST}" "echo connected" &> /dev/null; then
    echo -e "${RED}✗ Cannot SSH to NAS. Check Tailscale/VPN.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ SSH OK${NC}"

# 2. Confirm deploy
echo ""
echo -e "${YELLOW}This will:${NC}"
echo "  1. Sync cherry/ to ${NAS_DEPLOY_DIR}"
echo "  2. Build Docker images on NAS"
echo "  3. Restart Cherry services"
echo "  4. Cherry will be available on http://${NAS_HOST}:3003"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# 3. Create remote directory
echo ""
echo -e "${BLUE}▶ Creating remote directory...${NC}"
ssh "${NAS_USER}@${NAS_HOST}" "sudo mkdir -p ${NAS_DEPLOY_DIR} && sudo chown ${NAS_USER}:users ${NAS_DEPLOY_DIR}"
echo -e "${GREEN}✓ Remote dir ready${NC}"

# 4. Sync files (excluding dev artifacts)
echo ""
echo -e "${BLUE}▶ Syncing files...${NC}"
rsync -avz --progress \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.next' \
    --exclude='data/*.db' \
    --exclude='logs/*' \
    --exclude='.pids' \
    --exclude='.env.local' \
    "${LOCAL_DIR}/" "${NAS_USER}@${NAS_HOST}:${NAS_DEPLOY_DIR}/"
echo -e "${GREEN}✓ Files synced${NC}"

# 5. Setup .env on remote (copy if not exists, or warn)
echo ""
echo -e "${BLUE}▶ Setting up .env on remote...${NC}"
ssh "${NAS_USER}@${NAS_HOST}" "
    cd ${NAS_DEPLOY_DIR}
    if [ ! -f .env ]; then
        echo 'Creating .env from template (edit after deploy!)'
        cat > .env << 'REMOTE_ENV'
# Cherry Configuration — EDIT THIS ON NAS
OPENROUTER_API_KEY=sk-or-v1-PUT-YOUR-KEY-HERE
CHERRY_MODEL=minimax/minimax-m3:free
OLLAMA_HOST=http://localhost:11434
NAS_HOST=100.98.94.128
NAS_USER=rajat
CHERRY_LOCAL=1
CHERRY_PORT=3003
REMOTE_ENV
    else
        echo '.env already exists, leaving untouched'
    fi
"

# 6. Build Docker images on NAS
echo ""
echo -e "${BLUE}▶ Building Docker images on NAS...${NC}"
ssh "${NAS_USER}@${NAS_HOST}" "cd ${NAS_DEPLOY_DIR} && export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$PATH && sudo docker compose build"
echo -e "${GREEN}✓ Build complete${NC}"

# 7. Stop existing services (if any)
echo ""
echo -e "${BLUE}▶ Stopping existing services...${NC}"
ssh "${NAS_USER}@${NAS_HOST}" "cd ${NAS_DEPLOY_DIR} && export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$PATH && sudo docker compose down 2>/dev/null || true"

# 8. Start services
echo ""
echo -e "${BLUE}▶ Starting Cherry services...${NC}"
ssh "${NAS_USER}@${NAS_HOST}" "cd ${NAS_DEPLOY_DIR} && export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$PATH && sudo docker compose up -d"
echo -e "${GREEN}✓ Services started${NC}"

# 9. Wait and verify
echo ""
echo -e "${BLUE}▶ Waiting for Cherry to be healthy...${NC}"
sleep 10
ssh "${NAS_USER}@${NAS_HOST}" "cd ${NAS_DEPLOY_DIR} && export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:\$PATH && sudo docker compose ps"

# 10. Health check
echo ""
echo -e "${BLUE}▶ Health check...${NC}"
HEALTH=$(ssh "${NAS_USER}@${NAS_HOST}" "curl -s http://localhost:3003/health" 2>/dev/null || echo "failed")
if echo "$HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}✓ Cherry is healthy!${NC}"
    echo ""
    echo -e "${BLUE}Endpoints:${NC}"
    echo "  Backend:  http://${NAS_HOST}:3003"
    echo "  Frontend: http://${NAS_HOST}:3000"
    echo "  API Docs: http://${NAS_HOST}:3003/docs"
    echo ""
    echo -e "${YELLOW}⚠ Don't forget to:${NC}"
    echo "  1. Edit ${NAS_DEPLOY_DIR}/.env on NAS and add OPENROUTER_API_KEY"
    echo "  2. Restart: ssh ${NAS_USER}@${NAS_HOST} 'cd ${NAS_DEPLOY_DIR} && sudo docker compose restart'"
else
    echo -e "${RED}✗ Health check failed${NC}"
    echo "Check logs: ssh ${NAS_USER}@${NAS_HOST} 'cd ${NAS_DEPLOY_DIR} && sudo docker compose logs'"
fi
