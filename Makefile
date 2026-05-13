.PHONY: help build test lint format deploy deploy-prod clean logs shell db-backup db-restore monitor

# Project configuration
PROJECT := discord-bot-ai
DOCKER_COMPOSE := docker-compose -f docker-compose.yml
DOCKER_COMPOSE_PROD := docker-compose -f docker-compose.yml -f docker-compose.prod.yml

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build Docker image
	$(DOCKER_COMPOSE) build

up: ## Start all services
	$(DOCKER_COMPOSE) up -d

down: ## Stop all services
	$(DOCKER_COMPOSE) down

logs: ## Show bot logs
	$(DOCKER_COMPOSE) logs -f bot

logs-bot: ## Show bot logs (shortcut)
	$(DOCKER_COMPOSE) logs -f bot

logs-postgres: ## Show PostgreSQL logs
	$(DOCKER_COMPOSE) logs -f postgres

logs-redis: ## Show Redis logs
	$(DOCKER_COMPOSE) logs -f redis

restart: ## Restart bot service only
	$(DOCKER_COMPOSE) restart bot

restart-all: ## Restart all services
	$(DOCKER_COMPOSE) restart

shell: ## Open shell in bot container
	$(DOCKER_COMPOSE) exec bot bash

shell-db: ## Open shell in PostgreSQL container
	$(DOCKER_COMPOSE) exec postgres psql -U bot_user -d discord_bot

db-backup: ## Create database backup
	@mkdir -p backups
	@POSTGRES_CONTAINER=$$(docker-compose ps -q postgres); \
	if [ -n "$$POSTGRES_CONTAINER" ]; then \
		docker exec $$POSTGRES_CONTAINER pg_dump -U bot_user discord_bot | gzip > "backups/backup_$$(date +%Y%m%d_%H%M%S).sql.gz"; \
		echo "Backup created: backups/backup_$$(date +%Y%m%d_%H%M%S).sql.gz"; \
	else \
		echo "PostgreSQL container not running"; \
		exit 1; \
	fi

db-restore: ## Restore database from backup (set BACKUP_FILE=path/to/backup.sql.gz)
	@if [ -z "$(BACKUP_FILE)" ]; then echo "Usage: make db-restore BACKUP_FILE=backups/XXX.sql.gz"; exit 1; fi
	@POSTGRES_CONTAINER=$$(docker-compose ps -q postgres); \
	if [ -n "$$POSTGRES_CONTAINER" ]; then \
		gunzip -c "$(BACKUP_FILE)" | docker exec -i $$POSTGRES_CONTAINER psql -U bot_user -d discord_bot; \
		echo "Restore complete"; \
	else \
		echo "PostgreSQL container not running"; \
		exit 1; \
	fi

ps: ## Show container status
	$(DOCKER_COMPOSE) ps

health: ## Check health endpoint
	@curl -s http://localhost:8080/health | python3 -m json.tool 2>/dev/null || echo "Health check failed"

test: ## Run tests
	$(DOCKER_COMPOSE) exec bot pytest tests/ -v --cov=.

lint: ## Run linters
	$(DOCKER_COMPOSE) exec bot black --check .
	$(DOCKER_COMPOSE) exec bot ruff check .

format: ## Format code
	$(DOCKER_COMPOSE) exec bot black .
	$(DOCKER_COMPOSE) exec bot ruff check --fix .

clean: ## Remove containers, volumes, and build cache
	$(DOCKER_COMPOSE) down -v
	docker system prune -f

clean-all: ## Full clean including images
	$(DOCKER_COMPOSE) down -v --rmi all
	docker system prune -a -f

deploy-prod: ## Deploy to production (requires prod compose override)
	@echo "Deploying to production..."
	$(DOCKER_COMPOSE_PROD) pull
	$(DOCKER_COMPOSE_PROD) up -d
	@echo "Deployment complete. Check: make health"

monitor: ## Start monitoring stack (Prometheus + Grafana)
	$(DOCKER_COMPOSE_PROD) --profile monitoring up -d
	@echo "Monitoring available:"
	@echo "  Grafana: http://localhost:3000 (admin/admin)"
	@echo "  Prometheus: http://localhost:9090"

stop-monitor: ## Stop monitoring stack
	$(DOCKER_COMPOSE_PROD) --profile monitoring down

scale-bot: ## Scale bot instances (requires swarm mode)
	# docker service scale discord-bot-ai_bot=3

migrate: ## Run database migrations
	$(DOCKER_COMPOSE) exec bot alembic upgrade head

shell-postgres: ## Connect to PostgreSQL
	$(DOCKER_COMPOSE) exec postgres psql -U bot_user -d discord_bot

# Local development (without Docker)
install: ## Install dependencies locally
	pip install -r requirements.txt

run: ## Run bot locally
	python main.py

dev: ## Run in development mode
	LOG_LEVEL=DEBUG python main.py

# Security
audit: ## Scan dependencies for vulnerabilities
	$(DOCKER_COMPOSE) exec bot pip-audit

security-check: ## Run security checks
	$(DOCKER_COMPOSE) exec bot safety check --full-report

# Backup
backup-all: ## Backup database and logs
	$(MAKE) db-backup
	@tar -czf backups/logs_$$(date +%Y%m%d_%H%M%S).tar.gz logs/ 2>/dev/null || true
	@echo "All backups created"

# Reset (danger!)
reset-db: ## WARNING: Delete all data and recreate
	@echo "WARNING: This will delete ALL data. Are you sure? (yes/no)"
	@read ans; if [ "$$ans" = "yes" ]; then \
		$(DOCKER_COMPOSE) down -v; \
		$(DOCKER_COMPOSE) up -d; \
		echo "Database reset"; \
	else \
		echo "Aborted"; \
	fi

.DEFAULT_GOAL := help
