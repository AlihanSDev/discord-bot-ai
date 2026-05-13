#!/bin/bash
# Pre-flight checks for Docker deployment
# Run this before starting the bot in production

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0
WARN=0

check_pass() {
    echo -e "${GREEN}[PASS]${NC} $1"
    ((PASS++))
}

check_fail() {
    echo -e "${RED}[FAIL]${NC} $1"
    ((FAIL++))
}

check_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    ((WARN++))
}

echo "=== Discord Bot Pre-flight Checks ==="
echo ""

# Check Docker
echo "1. Checking Docker..."
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version)
    check_pass "Docker installed: $DOCKER_VERSION"
else
    check_fail "Docker not found"
fi

# Check Docker Compose
echo "2. Checking Docker Compose..."
if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    COMPOSE_VERSION=$(docker-compose --version 2>/dev/null || docker compose version --short)
    check_pass "Docker Compose: $COMPOSE_VERSION"
else
    check_fail "Docker Compose not found"
fi

# Check env file
echo "3. Checking environment configuration..."
if [ ! -f .env.docker ]; then
    check_fail ".env.docker not found"
else
    check_pass ".env.docker exists"

    # Source and check required vars
    source .env.docker 2>/dev/null || true

    if [ -z "${DISCORD_TOKEN:-}" ] || [ "$DISCORD_TOKEN" = "your_discord_bot_token_here" ]; then
        check_fail "DISCORD_TOKEN not set or placeholder"
    else
        check_pass "DISCORD_TOKEN configured (length: ${#DISCORD_TOKEN})"
    fi

    if [ -z "${HF_TOKEN:-}" ] || [ "$HF_TOKEN" = "your_huggingface_token_here" ]; then
        check_fail "HF_TOKEN not set or placeholder"
    else
        check_pass "HF_TOKEN configured (length: ${#HF_TOKEN})"
    fi

    if [ -z "${POSTGRES_PASSWORD:-}" ] || [ "$POSTGRES_PASSWORD" = "ChangeMePostgresPassword123!" ]; then
        check_warn "POSTGRES_PASSWORD is default — change it!"
    else
        check_pass "POSTGRES_PASSWORD set (strong)"
    fi

    if [ -z "${REDIS_PASSWORD:-}" ] || [ "$REDIS_PASSWORD" = "ChangeMeRedisPassword123!" ]; then
        check_warn "REDIS_PASSWORD is default — change it!"
    else
        check_pass "REDIS_PASSWORD set"
    fi
fi

# Check ports
echo "4. Checking port availability..."
REQUIRED_PORTS=(8080 5432 6379)
for port in "${REQUIRED_PORTS[@]}"; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        check_warn "Port $port is already in use — will be occupied by Docker"
    else
        check_pass "Port $port is free"
    fi
done

# Check disk space
echo "5. Checking disk space..."
AVAIL=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$AVAIL" -lt 5 ]; then
    check_warn "Low disk space: ${AVAIL}GB available (recommend 10GB+)"
else
    check_pass "Disk space: ${AVAIL}GB available"
fi

# Check memory
echo "6. Checking system memory..."
if command -v free &> /dev/null; then
    TOTAL_MEM=$(free -g | awk '/^Mem:/{print $2}')
    if [ "$TOTAL_MEM" -lt 4 ]; then
        check_warn "Low memory: ${TOTAL_MEM}GB total (4GB+ recommended)"
    else
        check_pass "Memory: ${TOTAL_MEM}GB"
    fi
fi

# Check docker daemon
echo "7. Checking Docker daemon..."
if docker info &> /dev/null; then
    check_pass "Docker daemon running"
else
    check_fail "Docker daemon not accessible"
fi

# Check compose override
echo "8. Checking docker-compose override..."
if [ -f docker-compose.prod.yml ]; then
    check_pass "docker-compose.prod.yml exists (monitoring stack available)"
else
    check_warn "docker-compose.prod.yml not found (monitoring stack disabled)"
fi

# Check SSL certs (optional)
echo "9. Checking SSL certificates (optional)..."
if [ -d nginx/ssl ]; then
    if ls nginx/ssl/*.pem 1>/dev/null 2>&1; then
        check_pass "SSL certificates found in nginx/ssl/"
    else
        check_warn "nginx/ssl/ directory empty (HTTPS will need certificates)"
    fi
else
    check_warn "nginx/ssl/ directory not found (HTTPS config will need creation)"
fi

# Check systemd/supervisor dirs
echo "10. Checking process manager directories..."
if [ -d /etc/systemd/system ]; then
    check_pass "systemd available"
fi

if command -v supervisorctl &> /dev/null; then
    check_pass "supervisor installed"
fi

echo ""
echo "=== Summary ==="
echo -e "Passed:  $PASS"
echo -e "Failed:  $FAIL"
echo -e "Warnings: $WARN"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo -e "${GREEN}✓ Pre-flight checks passed${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Edit .env.docker — set real tokens"
    echo "  2. Run: ./deploy.sh setup"
    echo "  3. Run: ./deploy.sh status"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Pre-flight checks failed${NC}"
    echo "Please fix the above issues before deployment."
    exit 1
fi
