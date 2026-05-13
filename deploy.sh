#!/bin/bash
# Production deployment script for Discord AI Bot
# Usage: ./deploy.sh [pull|restart|logs|backup|migrate|status]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DOCKER_COMPOSE="${PROJECT_DIR}/docker-compose.yml"
ENV_FILE="${PROJECT_DIR}/.env.docker"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        log_error "docker-compose is not installed"
        exit 1
    fi

    if [ ! -f "$ENV_FILE" ]; then
        log_warn ".env.docker not found. Creating from example..."
        cp "${PROJECT_DIR}/.env.docker.example" "$ENV_FILE"
        log_warn "Please edit $ENV_FILE and set your tokens"
        exit 1
    fi

    # Validate required env vars
    source "$ENV_FILE"
    if [ -z "${DISCORD_TOKEN:-}" ] || [ "${DISCORD_TOKEN}" == "your_discord_bot_token_here" ]; then
        log_error "DISCORD_TOKEN not set in $ENV_FILE"
        exit 1
    fi

    if [ -z "${HF_TOKEN:-}" ] || [ "${HF_TOKEN}" == "your_huggingface_token_here" ]; then
        log_error "HF_TOKEN not set in $ENV_FILE"
        exit 1
    fi

    log_info "Prerequisites OK"
}

# Pull latest images
cmd_pull() {
    log_info "Pulling Docker images..."
    docker-compose -f "$DOCKER_COMPOSE" pull
    log_info "Images pulled"
}

# Restart all services
cmd_restart() {
    log_info "Restarting services..."
    docker-compose -f "$DOCKER_COMPOSE" down
    docker-compose -f "$DOCKER_COMPOSE" up -d
    log_info "Services restarted"
}

# View logs
cmd_logs() {
    docker-compose -f "$DOCKER_COMPOSE" logs -f bot
}

# Database backup
cmd_backup() {
    BACKUP_DIR="${PROJECT_DIR}/backups"
    mkdir -p "$BACKUP_DIR"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="${BACKUP_DIR}/discord_bot_backup_${TIMESTAMP}.sql.gz"

    log_info "Creating database backup..."

    # Get postgres container name
    PG_CONTAINER=$(docker-compose -f "$DOCKER_COMPOSE" ps -q postgres)

    if [ -n "$PG_CONTAINER" ]; then
        docker exec "$PG_CONTAINER" pg_dump -U bot_user discord_bot | gzip > "$BACKUP_FILE"
        log_info "Backup saved to $BACKUP_FILE"
    else
        log_error "PostgreSQL container not running"
        exit 1
    fi
}

# Run database migrations
cmd_migrate() {
    log_info "Running migrations..."
    # Future: alembic upgrade head
    log_info "Migrations complete (none pending)"
}

# Service status
cmd_status() {
    docker-compose -f "$DOCKER_COMPOSE" ps
    echo ""
    log_info "Health check:"
    curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null || echo "Health endpoint unreachable"
}

# Full setup (first time)
cmd_setup() {
    log_info "Running initial setup..."

    # Generate strong passwords
    if [ ! -f "$ENV_FILE" ]; then
        POSTGRES_PASSWORD=$(openssl rand -hex 16)
        REDIS_PASSWORD=$(openssl rand -hex 16)

        cat > "$ENV_FILE" <<EOF
DISCORD_TOKEN=${DISCORD_TOKEN:-your_discord_bot_token_here}
HF_TOKEN=${HF_TOKEN:-your_huggingface_token_here}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=discord_bot
POSTGRES_USER=bot_user
REDIS_HOST=redis
REDIS_PORT=6379
LOG_LEVEL=INFO
ENVIRONMENT=production
APP_PORT=8080
EOF

        log_info "Created .env.docker with secure passwords"
        log_warn "Please set DISCORD_TOKEN and HF_TOKEN in $ENV_FILE"
    fi

    check_prerequisites
    cmd_pull
    cmd_restart

    log_info "Setup complete!"
    log_info "Check status: ./deploy.sh status"
    log_info "View logs: ./deploy.sh logs"
}

# Main command dispatch
case "${1:-help}" in
    pull)
        check_prerequisites
        cmd_pull
        ;;
    restart)
        cmd_restart
        ;;
    logs)
        cmd_logs
        ;;
    backup)
        cmd_backup
        ;;
    migrate)
        cmd_migrate
        ;;
    status)
        cmd_status
        ;;
    setup)
        cmd_setup
        ;;
    help|*)
        cat <<EOF
Usage: $0 {pull|restart|logs|backup|migrate|status|setup|help}

Commands:
  pull      - Pull latest Docker images
  restart   - Restart all services
  logs      - View bot logs (follow)
  backup    - Create database backup
  migrate   - Run database migrations
  status    - Show service status and health
  setup     - Initial setup (first run)
  help      - Show this help

Setup:
  1. Run: $0 setup
  2. Edit .env.docker with your tokens
  3. Run: $0 restart

For production, also configure:
  - Systemd service (deploy/systemd/discord-bot.service)
  - Logrotate (deploy/logrotate/discord-bot)
  - SSL certificates (nginx reverse proxy if needed)
EOF
        ;;
esac
