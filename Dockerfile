# Multi-stage production Dockerfile for Discord AI Bot
# Stage 1: Builder
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pip dependencies to system location
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Production runtime
FROM python:3.11-slim-bookworm AS production

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /app/logs /app/data \
    && chown -R app:app /app /home/app

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=app:app . .

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Set PATH for user-installed Python packages
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER app

# Health check endpoint will be exposed on port 8080
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run the bot
CMD ["python", "main.py"]

# Stage 3: Development
FROM production AS development

# Switch to root for dev tools
USER root

# Install dev dependencies
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    black \
    isort \
    ruff \
    pre-commit

USER app

# Override command for development (with hot reload would need additional setup)
CMD ["python", "main.py"]
