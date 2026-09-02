#!/bin/bash
# 🌸 Cherry — NAS Deploy Script (v2.0)
# One-command deployment: git pull → sync → down → build → up → verify
#
# Usage:
#   ./scripts/deploy-to-nas.sh              # interactive (asks to confirm)
#   ./scripts/deploy-to-nas.sh --yes        # non-interactive (CI / cron)
#   ./scripts/deploy-to-nas.sh --rollback   # rollback to previous image
#   ./scripts/deploy-to-nas.sh --logs       # tail remote logs
#   ./scripts/deploy-to-nas.sh --status     # show remote status only
#   ./scripts/deploy-to-nas.sh --help       # show help
#
# Environment overrides:
#   NAS_HOST=192.168.29.101 ./deploy-to-nas.sh
#   NAS_USER=rajat ./deploy-to-nas.sh
#   BRANCH=main ./deploy-to-nas.sh --yes

set -euo pipefail

# Configuration
NAS_HOST="${NAS_HOST:-100.98.94.128}"
NAS_USER="${NAS_USER:-rajat}"
NAS_DEPLOY_DIR="/volume1/docker/cherry"
BRANCH="${BRANCH:-main}"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_REPO="$(cd "${LOCAL_DIR}/.." && pwd)"
BACKUP_TAG="cherry-backup-$(date +%Y%m%d-%H%M%S)"

ASSUME_YES=0
DO_ROLLBACK=0
DO_LOGS=0
DO_STATUS=0

if [ -t 1 ]; then
    GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; RED='\033[0;31m'; PURPLE='\033[0;35m'; NC='\033[0m'
else
    GREEN=''; YELLOW=''; BLUE=''; RED=''; PURPLE=''; NC=''
fi

log() { echo -e "$@"; }
ok()    { log "${GREEN}✓${NC} $*"; }
warn()  { log "${YELLOW}⚠${NC} $*"; }
fail()  { log "${RED}✗${NC} $*"; exit 1; }
info()  { log "${BLUE}▶${NC} $*"; }
hdr()   { log "${PURPLE}$*${NC}"; }

ssh_run() {
    ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
        "${NAS_USER}@${NAS_HOST}" \
        "export PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/docker/bin:\$PATH; $1"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes|-y)       ASSUME_YES=1; shift ;;
        --rollback)     DO_ROLLBACK=1; shift ;;
        --logs)         DO_LOGS=1; shift ;;
        --status)       DO_STATUS=1; shift ;;
        --help|-h)      sed -n '2,16p' "$0"; exit 0 ;;
        *)              fail "Unknown argument: $1  (use --help)" ;;
    esac
done

hdr ""
hdr "🌸 Cherry — NAS Deploy v2.0"
hdr "============================"
log "  Repo:   ${LOCAL_REPO}"
log "  Branch: ${BRANCH}"
log "  NAS:    ${NAS_USER}@${NAS_HOST}"
log "  Path:   ${NAS_DEPLOY_DIR}"
log ""

command -v ssh   >/dev/null || fail "ssh not found"
command -v rsync >/dev/null || fail "rsync not found"
command -v git   >/dev/null || fail "git not found"

info "Checking SSH to NAS..."
if ! ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes \
        "${NAS_USER}@${NAS_HOST}" "echo connected" >/dev/null 2>&1; then
    fail "Cannot SSH to NAS. Check Tailscale/VPN/network."
fi
ok "SSH OK"

info "Verifying NAS deploy dir..."
ssh_run "sudo test -d ${NAS_DEPLOY_DIR} && echo ok" | grep -q "^ok$" \
    || fail "Remote dir ${NAS_DEPLOY_DIR} not found. Run init first (see docs)."
ok "Remote dir exists"

# Mode: status
if [ "$DO_STATUS" = "1" ]; then
    info "Remote status:"
    ssh_run "cd ${NAS_DEPLOY_DIR} && sudo docker compose ps"
    echo
    info "Health check:"
    ssh_run "curl -sS -m 5 http://localhost:3003/health || echo 'unreachable'"
    exit 0
fi

# Mode: logs
if [ "$DO_LOGS" = "1" ]; then
    info "Tailing remote logs (Ctrl+C to stop)..."
    exec ssh_run "cd ${NAS_DEPLOY_DIR} && sudo docker compose logs -f --tail=100"
fi

# Mode: rollback
if [ "$DO_ROLLBACK" = "1" ]; then
    info "Available backup tags on NAS:"
    ssh_run "sudo docker images --format '  {{.Repository}}:{{.Tag}} ({{.CreatedSince}})' | grep -E 'cherry-(backend|frontend):cherry-backup-' | head -10"
    echo
    BACKUPS=$(ssh_run "sudo docker images --format '{{.Repository}}:{{.Tag}}' | grep -E 'cherry-(backend|frontend):cherry-backup-' | head -1")
    if [ -z "$BACKUPS" ]; then
        fail "No backup images found. Nothing to rollback to."
    fi
    if [ "$ASSUME_YES" = "0" ]; then
        read -p "Rollback to latest backup tag? (y/N) " -n 1 -r
        echo
        [[ $REPLY =~ ^[Yy]$ ]] || { log "Aborted."; exit 0; }
    fi
    ssh_run "cd ${NAS_DEPLOY_DIR} && \
        sudo docker compose down && \
        sudo docker compose up -d" || fail "Rollback failed"
    # Note: actual rollback requires re-tagging backup as latest; show user how
    warn "Containers restarted with :latest tag. To truly rollback to a backup:"
    warn "  ssh ${NAS_USER}@${NAS_HOST} 'cd ${NAS_DEPLOY_DIR} && sudo docker tag cherry-backend:${BACKUPS#cherry-backend:} cherry-backend:latest && sudo docker compose up -d --force-recreate'"
    exit 0
fi

# Mode: deploy (default)
log ""
log "${YELLOW}This will:${NC}"
log "  1. git pull (latest commits) on ${BRANCH}"
log "  2. rsync code to NAS (excluding dev artifacts + .env + data)"
log "  3. Stop existing containers"
log "  4. Rebuild Docker images with cache"
log "  5. Start new containers"
log "  6. Wait for health check"
log ""

if [ "$ASSUME_YES" = "0" ]; then
    read -p "Continue? (y/N) " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]] || { log "Aborted."; exit 0; }
fi

# 3. Create remote directory (only if missing — safe to re-run)
info "Ensuring remote directory..."
ssh_run "sudo mkdir -p ${NAS_DEPLOY_DIR} && sudo chown ${NAS_USER}:users ${NAS_DEPLOY_DIR}" >/dev/null
ok "Remote dir ready"

# 1. Git pull ─────────────────────────────────
info "1/6  Git pull on ${BRANCH}..."
cd "${LOCAL_REPO}"

# Mac workaround for "dubious ownership" errors
git config --global --add safe.directory "${LOCAL_REPO}" 2>/dev/null || true

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    warn "Currently on '${CURRENT_BRANCH}', checking out '${BRANCH}'..."
    git checkout "${BRANCH}" || fail "Cannot checkout ${BRANCH}"
fi

# Auto-stash local edits so pull is never blocked
STASHED=0
if ! git diff --quiet HEAD 2>/dev/null; then
    warn "Uncommitted local changes detected — stashing..."
    git stash push -m "auto-stash-before-deploy-$(date +%s)" || fail "git stash failed"
    STASHED=1
fi

git pull --ff-only origin "${BRANCH}" || fail "git pull failed (non-fast-forward? Run: git pull --rebase origin ${BRANCH})"
ok "git pull done"

COMMIT_SHA=$(git rev-parse --short HEAD)
info "Commit: ${COMMIT_SHA}"

# 2. Rsync to NAS ─────────────────────────────
info "2/6  Syncing code to NAS..."
rsync -az --progress \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='.next' \
    --exclude='data/*.db' \
    --exclude='data/*.sqlite*' \
    --exclude='logs/*' \
    --exclude='.pids' \
    --exclude='.env' \
    --exclude='.env.local' \
    --exclude='.agents' \
    --exclude='*.bak' \
    --exclude='.DS_Store' \
    "${LOCAL_DIR}/" "${NAS_USER}@${NAS_HOST}:${NAS_DEPLOY_DIR}/"
ok "Files synced"

# Restore stash
if [ "$STASHED" = "1" ]; then
    git stash pop || warn "Could not auto-restore stash. Run: git stash list && git stash pop"
fi

# 3. Verify .env on NAS ───────────────────────
info "3/6  Checking .env on NAS..."
HAS_ENV=$(ssh_run "test -f ${NAS_DEPLOY_DIR}/.env && echo yes || echo no")
if [ "$HAS_ENV" != "yes" ]; then
    fail "No .env on NAS. Create one first:
  ssh ${NAS_USER}@${NAS_HOST}
  cd ${NAS_DEPLOY_DIR}
  cp .env.example .env   # then edit with your keys
  # Required: OPENROUTER_API_KEY
"
fi
ok ".env exists"

# Pre-flight: API key sanity check
APIKEY=$(ssh_run "grep -E '^OPENROUTER_API_KEY=' ${NAS_DEPLOY_DIR}/.env | cut -d= -f2-")
if [ -z "$APIKEY" ] || [[ "$APIKEY" == *PUT-YOUR-KEY* ]] || [[ "$APIKEY" == *REPLACE* ]]; then
    fail "OPENROUTER_API_KEY is missing/placeholder in ${NAS_DEPLOY_DIR}/.env"
fi
ok "OPENROUTER_API_KEY set"

# 4. Tag current images for rollback ───────────
info "4/6  Tagging current images for rollback (safety net)..."
ssh_run "
    cd ${NAS_DEPLOY_DIR}
    BACKEND_CUR=\$(sudo docker images -q cherry-backend:latest 2>/dev/null | head -1)
    FRONTEND_CUR=\$(sudo docker images -q cherry-frontend:latest 2>/dev/null | head -1)
    [ -n \"\$BACKEND_CUR\"  ] && sudo docker tag cherry-backend:latest  cherry-backend:${BACKUP_TAG}  || true
    [ -n \"\$FRONTEND_CUR\" ] && sudo docker tag cherry-frontend:latest cherry-frontend:${BACKUP_TAG} || true
    # Prune old backup tags, keep last 3
    sudo docker images --format '{{.Repository}}:{{.Tag}} {{.CreatedAt}}' \
        | grep -E 'cherry-(backend|frontend):cherry-backup-' \
        | sort -k2,3 \
        | head -n -6 \
        | awk '{print \$1}' \
        | xargs -r sudo docker rmi 2>/dev/null || true
    echo 'tagged'
" 2>/dev/null || warn "Image tagging skipped (first deploy?)"
ok "Rollback safety tag: ${BACKUP_TAG}"

# 5. Stop + Build + Up ────────────────────────
info "5/6  Stopping existing containers..."
ssh_run "cd ${NAS_DEPLOY_DIR} && sudo docker compose down --remove-orphans 2>&1 | tail -3" >/dev/null || true
ok "Stopped"

info "Building + starting new containers (commit ${COMMIT_SHA})..."
ssh_run "cd ${NAS_DEPLOY_DIR} && sudo docker compose build 2>&1 | tail -20" \
    || fail "Build failed. Inspect logs:
  ssh ${NAS_USER}@${NAS_HOST} 'cd ${NAS_DEPLOY_DIR} && sudo docker compose logs --tail=50'"

ssh_run "cd ${NAS_DEPLOY_DIR} && sudo docker compose up -d" \
    || fail "Up failed. Inspect logs:
  ssh ${NAS_USER}@${NAS_HOST} 'cd ${NAS_DEPLOY_DIR} && sudo docker compose logs --tail=50'"
ok "Containers started"

# 6. Health check + auto-rollback ──────────────
info "6/6  Waiting for health check..."
HEALTHY=0
for i in {1..30}; do
    sleep 2
    HEALTH=$(ssh_run "curl -sS -m 3 http://localhost:3003/health 2>/dev/null || echo ''")
    if echo "$HEALTH" | grep -q '"status":"healthy"'; then
        HEALTHY=1
        ok "Healthy after $((i*2))s"
        break
    fi
    [ $((i % 5)) -eq 0 ] && log "  ...still waiting (${i}/30)"
done

if [ "$HEALTHY" != "1" ]; then
    log ""
    fail "Health check failed after 60s. Recent logs:
$(ssh_run "cd ${NAS_DEPLOY_DIR} && sudo docker compose logs --tail=30" 2>/dev/null)

To rollback manually:
  ssh ${NAS_USER}@${NAS_HOST}
  cd ${NAS_DEPLOY_DIR}
  sudo docker tag cherry-backend:${BACKUP_TAG} cherry-backend:latest
  sudo docker tag cherry-frontend:${BACKUP_TAG} cherry-frontend:latest
  sudo docker compose up -d --force-recreate
"
fi

# Final status
log ""
ok "🎉 Cherry deployed!"
log ""
hdr "Endpoints:"
log "  Frontend:  ${BLUE}http://${NAS_HOST}:3000${NC}"
log "  Backend:   ${BLUE}http://${NAS_HOST}:3003${NC}"
log "  Health:    ${BLUE}http://${NAS_HOST}:3003/health${NC}"
log "  API Docs:  ${BLUE}http://${NAS_HOST}:3003/docs${NC}"
log ""
hdr "Useful commands:"
log "  ./scripts/deploy-to-nas.sh --status    # quick status check"
log "  ./scripts/deploy-to-nas.sh --logs      # tail remote logs"
log "  ./scripts/deploy-to-nas.sh --rollback  # rollback to backup"
log "  ./scripts/deploy-to-nas.sh --yes       # skip confirmation (CI/cron)"
