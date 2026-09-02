#!/bin/bash
# Cherry - Local Start Script (Robust + Force-kill)
# Usage:
#   ./start.sh                      -> start all (skip if already running)
#   ./start.sh backend              -> start backend only
#   ./start.sh frontend             -> start frontend only
#   ./start.sh stop                 -> stop all
#   ./start.sh restart              -> stop + start all
#   ./start.sh restart backend      -> restart backend only
#   ./start.sh status               -> show status
#   ./start.sh logs [backend|frontend]
#
# Flags (must come FIRST, e.g. ./start.sh --force backend):
#   --force, -f   Kill existing process before starting (always restarts)
#   --quiet, -q   Reduce output

set -e

CHERRY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$CHERRY_DIR/backend"
FRONTEND_DIR="$CHERRY_DIR/frontend"
LOG_DIR="$CHERRY_DIR/logs"
PID_DIR="$CHERRY_DIR/.pids"

BACKEND_PORT="${CHERRY_PORT:-3003}"
FRONTEND_PORT="${CHERRY_FRONTEND_PORT:-3000}"

mkdir -p "$LOG_DIR" "$PID_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

FORCE=0
QUIET=0

log() {
    [ "$QUIET" = "1" ] && return
    echo -e "$@"
}

print_banner() {
    log "${PURPLE}"
    log "  Cherry - Personal AI Girlfriend & Server Assistant"
    log "  ==================================================="
    log "${NC}"
}

print_usage() {
    echo "Usage: $0 [--force|-f] [--quiet|-q] <command> [target]"
    echo ""
    echo "Commands:"
    echo "  all                   Start backend + frontend (default)"
    echo "  backend               Start backend only"
    echo "  frontend              Start frontend only"
    echo "  stop [target]         Stop all or specific target"
    echo "  restart [target]      Stop + start all or specific target"
    echo "  status                Show process status"
    echo "  logs [target]         Tail logs (default backend)"
    echo ""
    echo "Flags:"
    echo "  --force, -f           Kill running process before start (always restart)"
    echo "  --quiet, -q           Minimal output"
    echo ""
    echo "Examples:"
    echo "  $0                              # Start everything (skip if running)"
    echo "  $0 --force                      # Kill existing + start fresh"
    echo "  $0 --force backend              # Kill existing backend + restart"
    echo "  $0 restart                      # Stop + start everything"
    echo "  $0 status                       # Show what's running"
    echo "  $0 logs backend                 # Tail backend logs"
}

is_tracked_running() {
    local pidfile="$1"
    [ -f "$pidfile" ] || return 1
    local pid=$(cat "$pidfile" 2>/dev/null)
    [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

get_port_pids() {
    local port="$1"
    lsof -ti:"$port" 2>/dev/null || true
}

get_orphans() {
    local port="$1"
    local pidfile="$2"
    local tracked_pid=""
    [ -f "$pidfile" ] && tracked_pid=$(cat "$pidfile" 2>/dev/null)

    local port_pids=$(get_port_pids "$port")
    local orphans=""
    for p in $port_pids; do
        if [ "$p" != "$tracked_pid" ]; then
            orphans="$orphans $p"
        fi
    done
    echo "$orphans" | xargs
}

kill_pid() {
    local pid="$1"
    local name="${2:-process}"
    [ -z "$pid" ] && return 0
    kill -0 "$pid" 2>/dev/null || return 0

    log "  ${YELLOW}> Stopping $name (PID $pid)...${NC}"
    kill -TERM "$pid" 2>/dev/null || true
    local waited=0
    while kill -0 "$pid" 2>/dev/null && [ $waited -lt 4 ]; do
        sleep 1
        waited=$((waited + 1))
    done
    if kill -0 "$pid" 2>/dev/null; then
        log "  ${YELLOW}> Force-killing $name (PID $pid)...${NC}"
        kill -KILL "$pid" 2>/dev/null || true
    fi
    sleep 1
}

check_deps() {
    if ! python3 -c "import fastapi" 2>/dev/null; then
        log "${YELLOW}! Installing backend dependencies...${NC}"
        pip3 install -q -r "$BACKEND_DIR/requirements.txt"
    fi

    if [ ! -f "$CHERRY_DIR/.env" ]; then
        log "${RED}X .env file not found!${NC}"
        log "${YELLOW}Creating template...${NC}"
        cat > "$CHERRY_DIR/.env" << 'EOF'
# Cherry Configuration
OPENROUTER_API_KEY=sk-or-v1-PUT-YOUR-KEY-HERE
CHERRY_MODEL=minimax/minimax-m3:free
OLLAMA_HOST=http://100.98.94.128:11434
NAS_HOST=100.98.94.128
NAS_USER=rajat
CHERRY_LOCAL=0
CHERRY_PORT=3003
EOF
        log "${YELLOW}  Please edit .env and add your OPENROUTER_API_KEY${NC}"
    fi

    if [ -d "$FRONTEND_DIR" ] && [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        log "${YELLOW}! Installing frontend dependencies...${NC}"
        (cd "$FRONTEND_DIR" && npm install --silent)
    fi
}

ensure_stopped() {
    local name="$1"
    local pidfile="$PID_DIR/$name.pid"
    local port=""
    [ "$name" = "backend" ] && port=$BACKEND_PORT
    [ "$name" = "frontend" ] && port=$FRONTEND_PORT

    if is_tracked_running "$pidfile"; then
        local pid=$(cat "$pidfile")
        kill_pid "$pid" "$name"
        rm -f "$pidfile"
    fi

    if [ -n "$port" ]; then
        local orphans=$(get_orphans "$port" "$pidfile")
        if [ -n "$orphans" ]; then
            log "  ${YELLOW}> Cleaning orphan(s) on port $port: $orphans${NC}"
            for p in $orphans; do
                kill_pid "$p" "orphan-$name"
            done
        fi
    fi

    if [ -n "$port" ]; then
        local remaining=$(get_port_pids "$port")
        if [ -n "$remaining" ]; then
            log "  ${RED}X Port $port still occupied by: $remaining${NC}"
            return 1
        fi
    fi
    log "  ${GREEN}v Port clean${NC}"
    return 0
}

start_backend() {
    local pidfile="$PID_DIR/backend.pid"
    local port=$BACKEND_PORT

    log "${BLUE}> Starting backend on port $port...${NC}"
    cd "$BACKEND_DIR"

    nohup python3 main.py > "$LOG_DIR/backend.log" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$pidfile"

    local waited=0
    while [ $waited -lt 15 ]; do
        if [ -n "$(get_port_pids "$port")" ]; then
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done

    if is_tracked_running "$pidfile" && [ -n "$(get_port_pids "$port")" ]; then
        log "${GREEN}v Backend started (PID: $new_pid)${NC}"
        log "  ${BLUE}-> http://localhost:$port${NC}"
        log "  ${BLUE}-> API docs: http://localhost:$port/docs${NC}"
    else
        log "${RED}X Backend failed to start. Last log lines:${NC}"
        tail -10 "$LOG_DIR/backend.log" 2>/dev/null | sed 's/^/    /'
        rm -f "$pidfile"
        return 1
    fi
}

start_frontend() {
    local pidfile="$PID_DIR/frontend.pid"
    local port=$FRONTEND_PORT

    if [ ! -d "$FRONTEND_DIR" ]; then
        log "${YELLOW}! Frontend directory not found, skipping${NC}"
        return 0
    fi

    log "${BLUE}> Starting frontend on port $port...${NC}"
    cd "$FRONTEND_DIR"

    nohup npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$pidfile"

    local waited=0
    while [ $waited -lt 15 ]; do
        if [ -n "$(get_port_pids "$port")" ]; then
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done

    if is_tracked_running "$pidfile" && [ -n "$(get_port_pids "$port")" ]; then
        log "${GREEN}v Frontend started (PID: $new_pid)${NC}"
        log "  ${BLUE}-> http://localhost:$port${NC}"
    else
        log "${RED}X Frontend failed. Last log lines:${NC}"
        tail -10 "$LOG_DIR/frontend.log" 2>/dev/null | sed 's/^/    /'
        rm -f "$pidfile"
        return 1
    fi
}

start_service() {
    local name="$1"

    if [ "$FORCE" = "1" ]; then
        log "${CYAN}! --force: killing existing $name first${NC}"
        ensure_stopped "$name" || return 1
    fi

    local pidfile="$PID_DIR/$name.pid"
    local port=""
    [ "$name" = "backend" ] && port=$BACKEND_PORT
    [ "$name" = "frontend" ] && port=$FRONTEND_PORT

    local already_up=0
    if is_tracked_running "$pidfile"; then
        local tracked_pid=$(cat "$pidfile")
        local on_port=$(get_port_pids "$port")
        if echo "$on_port" | grep -q "$tracked_pid"; then
            already_up=1
        fi
    fi

    if [ "$already_up" = "1" ]; then
        log "${YELLOW}! $name already running (PID: $(cat $pidfile))${NC}"
        log "  ${CYAN}Hint: use --force to restart${NC}"
        return 0
    fi

    if [ -n "$port" ] && [ -n "$(get_port_pids "$port")" ]; then
        log "${YELLOW}! Port $port occupied, cleaning...${NC}"
        ensure_stopped "$name" || return 1
    fi

    if [ -f "$pidfile" ] && ! is_tracked_running "$pidfile"; then
        log "${YELLOW}! Stale PID file, removing${NC}"
        rm -f "$pidfile"
    fi

    if [ "$name" = "backend" ]; then
        start_backend
    elif [ "$name" = "frontend" ]; then
        start_frontend
    fi
}

stop_service() {
    local name="$1"
    local pidfile="$PID_DIR/$name.pid"
    local port=""
    [ "$name" = "backend" ] && port=$BACKEND_PORT
    [ "$name" = "frontend" ] && port=$FRONTEND_PORT

    log "${YELLOW}> Stopping $name...${NC}"

    if is_tracked_running "$pidfile"; then
        kill_pid "$(cat "$pidfile")" "$name"
        rm -f "$pidfile"
    else
        log "  ${CYAN}No tracked PID (already stopped or stale PID file)${NC}"
        rm -f "$pidfile"
    fi

    if [ -n "$port" ]; then
        local orphans=$(get_port_pids "$port")
        if [ -n "$orphans" ]; then
            log "  ${YELLOW}> Killing port $port holders: $orphans${NC}"
            for p in $orphans; do
                kill_pid "$p" "orphan-$name"
            done
        fi
    fi

    if [ -n "$port" ] && [ -n "$(get_port_pids "$port")" ]; then
        log "${RED}X Port $port still in use!${NC}"
        return 1
    fi
    log "${GREEN}v $name stopped${NC}"
}

stop_all() {
    stop_service "frontend" || true
    stop_service "backend" || true
}

show_status() {
    log "${BLUE}=== Cherry Status ===${NC}"
    for svc in backend frontend; do
        local pidfile="$PID_DIR/$svc.pid"
        local port=""
        [ "$svc" = "backend" ] && port=$BACKEND_PORT
        [ "$svc" = "frontend" ] && port=$FRONTEND_PORT
        local on_port=$(get_port_pids "$port")

        if is_tracked_running "$pidfile"; then
            local pid=$(cat "$pidfile")
            local bound=""
            if echo "$on_port" | grep -q "$pid"; then
                bound=" ${GREEN}-> port $port${NC}"
            else
                bound=" ${YELLOW}(not bound to port)${NC}"
            fi
            log "  ${GREEN}* $svc${NC}: running (PID: $pid)$bound"
        elif [ -n "$on_port" ]; then
            log "  ${YELLOW}o $svc${NC}: port $port in use by orphan PID(s): $on_port"
        else
            log "  ${RED}o $svc${NC}: stopped"
        fi
    done
    log ""
    log "Endpoints:"
    log "  ${BLUE}Backend:  http://localhost:$BACKEND_PORT${NC}"
    log "  ${BLUE}Frontend: http://localhost:$FRONTEND_PORT${NC}"
}

show_logs() {
    local svc="${1:-backend}"
    if [ -f "$LOG_DIR/$svc.log" ]; then
        tail -f "$LOG_DIR/$svc.log"
    else
        echo "No log for $svc at $LOG_DIR/$svc.log"
        exit 1
    fi
}

# ============================================================
# COMMAND DISPATCH
# ============================================================
ARGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --force|-f)
            FORCE=1
            shift
            ;;
        --quiet|-q)
            QUIET=1
            shift
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

CMD="${ARGS[0]:-all}"
TARGET="${ARGS[1]:-}"

case "$CMD" in
    backend|frontend)
        print_banner
        check_deps
        start_service "$CMD"
        ;;
    all)
        print_banner
        check_deps
        start_service "backend"
        start_service "frontend"
        log ""
        show_status
        log ""
        log "${PURPLE}Cherry is ready!${NC}"
        log "Open ${BLUE}http://localhost:$FRONTEND_PORT${NC}"
        log "Run ${YELLOW}./start.sh logs${NC} for live logs"
        log "Run ${YELLOW}./start.sh stop${NC} to stop"
        ;;
    stop)
        if [ -n "$TARGET" ]; then
            stop_service "$TARGET"
        else
            stop_all
        fi
        ;;
    restart)
        print_banner
        if [ -n "$TARGET" ]; then
            FORCE=1
            stop_service "$TARGET"
            start_service "$TARGET"
        else
            FORCE=1
            stop_service "frontend" || true
            stop_service "backend" || true
            check_deps
            start_service "backend"
            start_service "frontend"
            log ""
            show_status
        fi
        ;;
    status)
        show_status
        ;;
    logs)
        show_logs "${TARGET:-backend}"
        ;;
    help|--help|-h)
        print_usage
        ;;
    *)
        print_usage
        exit 1
        ;;
esac
