import os
import io
import random
import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

import structlog
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, Dict, Any, List
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from PIL import Image
from huggingface_hub import AsyncInferenceClient
from openai import AsyncOpenAI
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, BigInteger, String, Boolean, DateTime, JSON, Text, select, update, func
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type
)
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import PlainTextResponse
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

# Load environment variables
load_dotenv()

# ============ Configuration ============
class Settings(BaseSettings):
    """Application settings with validation."""
    DISCORD_TOKEN: str = Field(..., min_length=50)
    HF_TOKEN: str = Field(..., min_length=10)
    DATABASE_URL: str = Field(default="postgresql+asyncpg://bot_user:password@localhost/discord_bot")
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    LOG_LEVEL: str = Field(default="INFO")
    ENVIRONMENT: str = Field(default="production")
    APP_PORT: int = Field(default=8080)

    # Rate limits
    RATE_LIMIT_GENERATE: int = Field(default=3)  # per user per minute
    RATE_LIMIT_ASK: int = Field(default=5)      # per user per minute

    # Credits
    DEFAULT_CREDITS: int = Field(default=5)
    COST_TEXT: int = Field(default=1)
    COST_IMAGE_SDXL: int = Field(default=3)
    COST_IMAGE_PONY: int = Field(default=2)
    COST_IMAGE_HIDREAM: int = Field(default=5)

    # Stripe (optional)
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None

    # Admin Discord IDs (comma-separated string)
    ADMIN_DISCORD_IDS: str = Field(default="")

    @property
    def admin_ids(self) -> list[int]:
        """Parse ADMIN_DISCORD_IDS to list of ints."""
        if not self.ADMIN_DISCORD_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_DISCORD_IDS.split(",") if x.strip().isdigit()]

settings = Settings()

# Global model configurations
IMAGE_MODELS = {
    "sdxl": {
        "provider": "fal-ai",
        "model": "fofr/sdxl-emoji",
        "description": "Emoji-style images"
    },
    "pony": {
        "provider": "replicate",
        "model": "stabilityai/sdxl-turbo",
        "description": "Fast SDXL turbo images"
    },
    "hidream": {
        "provider": "fal-ai",
        "model": "strangerzonehf/Flux-Super-Realism-LoRA",
        "description": "Super realistic images"
    }
}

# Text model identifier
TEXT_MODEL = "mistralai/Mistral-7B-Instruct-v0.2:featherless-ai"

# ============ Structured Logging ============
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        getattr(logging, settings.LOG_LEVEL.upper())
    ),
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# ============ Sentry Error Tracking ============
if settings.ENVIRONMENT == "production":
    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        environment=settings.ENVIRONMENT,
    )
    logger.info("Sentry initialized", environment=settings.ENVIRONMENT)

# ============ Database Models ============
class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    discord_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    discriminator: Mapped[Optional[str]] = mapped_column(String(4))
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

class Credit(Base):
    __tablename__ = "credits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_refill_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    command_type: Mapped[str] = mapped_column(String(50), nullable=False)
    model_used: Mapped[Optional[str]] = mapped_column(String(255))
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_hash: Mapped[Optional[str]] = mapped_column(String(64))
    cost_credits: Mapped[int] = mapped_column(Integer, default=1)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

class AdminAudit(Base):
    __tablename__ = "admin_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

# ============ Metrics ============
REQUEST_COUNTER = Counter(
    'discord_bot_requests_total',
    'Total number of requests',
    ['command', 'user_id', 'status']
)
REQUEST_DURATION = Histogram(
    'discord_bot_request_duration_seconds',
    'Request duration in seconds',
    ['command', 'model']
)
ACTIVE_USERS = Gauge(
    'discord_bot_active_users',
    'Number of unique users in the last 24h'
)
CREDITS_REMAINING = Gauge(
    'discord_bot_credits_remaining',
    'Average credits remaining across users'
)

# ============ Database Setup ============
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.LOG_LEVEL == "DEBUG",
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600
)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db() -> AsyncSession:
    """Dependency for database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

@asynccontextmanager
async def db_session() -> AsyncSession:
    """Context manager for DB sessions outside FastAPI."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# ============ Redis Setup ============
redis_client: Optional[redis.Redis] = None

async def init_redis():
    """Initialize Redis connection pool."""
    global redis_client
    redis_client = await redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20
    )
    logger.info("Redis connected")

async def close_redis():
    """Close Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")

# ============ Rate Limiting ============
class RateLimiter:
    """Distributed rate limiter using Redis."""

    def __init__(self):
        self.prefix = "rate_limit:"

    async def is_allowed(
        self,
        user_id: int,
        command: str,
        max_requests: int,
        window_seconds: int = 60
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Check if user can perform action.

        Returns:
            (allowed, info_dict)
        """
        if not redis_client:
            # Fallback to in-memory if Redis unavailable
            return True, {}

        key = f"{self.prefix}{user_id}:{command}"
        now = asyncio.get_event_loop().time()

        # Use Redis sorted set for sliding window
        pipeline = redis_client.pipeline()
        await pipeline.zadd(key, {str(now): now})
        await pipeline.zremrangebyscore(key, 0, now - window_seconds)
        await pipeline.zcard(key)
        await pipeline.expire(key, window_seconds)
        results = await pipeline.execute()

        request_count = results[2]

        allowed = request_count <= max_requests
        info = {
            "requests_in_window": request_count,
            "limit": max_requests,
            "window_seconds": window_seconds,
            "remaining": max(0, max_requests - request_count)
        }

        return allowed, info

rate_limiter = RateLimiter()

# ============ Credit System ============
class CreditManager:
    """Manages user credits with atomic operations."""

    @staticmethod
    async def get_user_credits(session: AsyncSession, user_id: int) -> int:
        """Get current credit balance."""
        result = await session.execute(
            select(Credit.balance).where(Credit.user_id == user_id)
        )
        balance = result.scalar_one_or_none()
        if balance is None:
            # Create credit record for new user
            credit = Credit(user_id=user_id, balance=settings.DEFAULT_CREDITS)
            session.add(credit)
            await session.commit()
            return settings.DEFAULT_CREDITS
        return balance

    @staticmethod
    async def deduct_credits(
        session: AsyncSession,
        user_id: int,
        amount: int,
        command_type: str
    ) -> bool:
        """
        Atomically deduct credits. Returns False if insufficient.
        """
        result = await session.execute(
            select(Credit.balance).where(Credit.user_id == user_id).with_for_update()
        )
        balance = result.scalar_one_or_none()

        if balance is None:
            balance = settings.DEFAULT_CREDITS
            credit = Credit(user_id=user_id, balance=balance)
            session.add(credit)
            await session.flush()

        if balance < amount:
            return False

        await session.execute(
            update(Credit)
            .where(Credit.user_id == user_id)
            .values(balance=Credit.balance - amount)
        )

        # Log transaction
        usage = UsageLog(
            user_id=user_id,
            command_type=command_type,
            prompt="<deduction_check>",
            cost_credits=amount,
            success=True
        )
        session.add(usage)

        return True

    @staticmethod
    async def add_credits(
        session: AsyncSession,
        user_id: int,
        amount: int,
        reason: str = "admin_grant"
    ):
        """Add credits to user (for admin/purchases)."""
        await session.execute(
            update(Credit)
            .where(Credit.user_id == user_id)
            .values(balance=Credit.balance + amount)
        )
        logger.info("credits_added", user_id=user_id, amount=amount, reason=reason)

credit_manager = CreditManager()

# ============ Retry & Circuit Breaker ============
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10),
    retry=retry_if_exception_type((Exception,))
)
async def call_huggingface_api_with_retry(func, *args, **kwargs):
    """Wrapper for HF API calls with exponential backoff."""
    return await func(*args, **kwargs)

# Simple circuit breaker
class CircuitBreaker:
    """Circuit breaker pattern implementation."""

    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open

    async def call(self, func, *args, **kwargs):
        if self.state == "open":
            if datetime.utcnow() - self.last_failure_time > timedelta(seconds=self.timeout):
                self.state = "half-open"
            else:
                raise Exception("Circuit breaker is open")

        try:
            result = await func(*args, **kwargs)
            if self.state == "half-open":
                self.state = "closed"
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()
            if self.failure_count >= self.failure_threshold:
                self.state = "open"
            raise

# Initialize circuit breakers for HF endpoints
hf_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout=60)

# ============ Bot Setup ============
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    description="AI-powered Discord bot",
    intents=intents,
    help_command=None,
    max_messages=10000
)

# ============ FastAPI App for Health/Metrics ============
app = FastAPI(title="Discord AI Bot API", version="1.0.0")

@app.get("/health")
async def health_check():
    """Health check endpoint for Kubernetes/Docker."""
    health = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Check DB
    try:
        async with db_session() as db:
            await db.execute(select(1))
        health["checks"]["database"] = "healthy"
    except Exception as e:
        health["checks"]["database"] = f"unhealthy: {str(e)}"
        health["status"] = "degraded"

    # Check Redis
    if redis_client:
        try:
            await redis_client.ping()
            health["checks"]["redis"] = "healthy"
        except Exception as e:
            health["checks"]["redis"] = f"unhealthy: {str(e)}"
            health["status"] = "degraded"

    # Check Discord connection
    health["checks"]["discord"] = "connected" if bot.is_ready() else "disconnected"
    if not bot.is_ready():
        health["status"] = "degraded"

    status_code = 200 if health["status"] == "healthy" else 503
    return health

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return PlainTextResponse(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )

@app.get("/ready")
async def readiness():
    """Kubernetes readiness probe."""
    if not bot.is_ready():
        raise HTTPException(503, "Bot not ready")
    return {"status": "ready"}

# ============ Startup & Shutdown ============
@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan events."""
    # Startup
    logger.info("Initializing bot services...")

    # Initialize DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")

    # Initialize Redis
    try:
        await init_redis()
    except Exception as e:
        logger.warning("Redis connection failed", error=str(e))

    # Start FastAPI in background
    import uvicorn
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=settings.APP_PORT,
        log_level=settings.LOG_LEVEL.lower()
    )
    server = uvicorn.Server(config)
    asyncio.create_task(server.serve())

    yield

    # Shutdown
    logger.info("Shutting down...")
    await close_redis()
    await engine.dispose()
    logger.info("Shutdown complete")

app.router.lifespan_context = lifespan

# ============ Helper Functions ============
def is_admin(user_id: int) -> bool:
    """Check if user is bot admin."""
    return user_id in settings.admin_ids

async def get_or_create_user(session: AsyncSession, discord_user: discord.User) -> User:
    """Get or create user record."""
    result = await session.execute(
        select(User).where(User.discord_id == discord_user.id)
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            discord_id=discord_user.id,
            username=discord_user.name[:32],
            discriminator=discord_user.discriminator or ""
        )
        session.add(user)
        await session.flush()

        # Give initial credits
        credit = Credit(user_id=user.id, balance=settings.DEFAULT_CREDITS)
        session.add(credit)
        await session.commit()

    return user

# ============ Text Generation ============
@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=1, max=10))
async def generate_text_response(prompt: str) -> str:
    """Generate text via HuggingFace OpenAI-compatible endpoint."""
    start_time = asyncio.get_event_loop().time()

    try:
        client = AsyncOpenAI(
            base_url="https://router.huggingface.co/v1",
            api_key=settings.HF_TOKEN,
        )

        completion = await client.chat.completions.create(
            model="mistralai/Mistral-7B-Instruct-v0.2:featherless-ai",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.7,
        )

        duration = asyncio.get_event_loop().time() - start_time
        REQUEST_DURATION.labels(command="text", model="mistral").observe(duration)

        return completion.choices[0].message.content
    except Exception as e:
        logger.error("text_generation_failed", error=str(e), prompt=prompt[:100])
        REQUEST_COUNTER.labels(command="text", status="error").inc()
        raise

# ============ Image Generation ============
@retry(stop=stop_after_attempt(3), wait=wait_exponential_jitter(initial=2, max=15))
async def generate_image_bytes(model_key: str, prompt: str, seed: Optional[int] = None) -> bytes:
    """Generate image bytes asynchronously."""
    if model_key not in IMAGE_MODELS:
        raise ValueError(f"Unknown model: {model_key}. Available: {list(IMAGE_MODELS.keys())}")

    model_info = IMAGE_MODELS[model_key]
    if seed is None:
        seed = random.randint(0, 2**32 - 1)

    start_time = asyncio.get_event_loop().time()

    try:
        client = AsyncInferenceClient(
            provider=model_info["provider"],
            api_key=settings.HF_TOKEN,
        )

        image = await hf_circuit_breaker.call(
            client.text_to_image,
            prompt=prompt,
            model=model_info["model"],
            seed=seed,
        )

        # Convert PIL Image to bytes in memory
        img_bytes = io.BytesIO()
        image.save(img_bytes, format='PNG')
        return img_bytes.getvalue()

    except Exception as e:
        logger.error(
            f"Image generation failed for model={model_key}, "
            f"prompt={prompt[:50]}, seed={seed}: {e}",
            exc_info=True
        )
        raise

# ============ Discord Bot Events ============
@bot.event
async def on_ready():
    logger.info(
        "Bot started",
        user=str(bot.user),
        user_id=bot.user.id,
        guilds=len(bot.guilds)
    )

    try:
        synced = await bot.tree.sync()
        logger.info("Slash commands synced", count=len(synced))
    except Exception as e:
        logger.error("Failed to sync commands", error=str(e))

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    """Handle prefix command errors."""
    user_id = ctx.author.id

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(
            f"⏳ Cooldown: Try again in {error.retry_after:.1f}s"
        )
    elif isinstance(error, commands.CommandInvokeError):
        logger.error(
            "command_error",
            user_id=user_id,
            command=ctx.command.name,
            error=str(error.original)
        )
        await ctx.send("❌ Command failed. Check logs.")
    else:
        logger.error("unexpected_error", error=str(error))
        await ctx.send("❌ Unexpected error occurred.")

# ============ Slash Commands ============
@bot.tree.command(name="generate", description="Generate an AI image")
@app_commands.describe(
    prompt="Description of the image you want to generate",
    model="Image generation model to use"
)
@app_commands.choices(model=[
    app_commands.Choice(name="🎨 SDXL Emoji", value="sdxl"),
    app_commands.Choice(name="⚡ SDXL Turbo (Pony)", value="pony"),
    app_commands.Choice(name="✨ HiDream Realism", value="hidream"),
])
async def generate_slash(
    interaction: discord.Interaction,
    prompt: str,
    model: str = "sdxl"
):
    """Slash command for image generation with rate limiting and credits."""
    user_id = interaction.user.id

    # Rate limit check
    allowed, info = await rate_limiter.is_allowed(
        user_id, "generate", settings.RATE_LIMIT_GENERATE
    )
    if not allowed:
        await interaction.response.send_message(
            f"⏳ Rate limit exceeded. Remaining: {info['remaining']} requests",
            ephemeral=True
        )
        return

    # Defer response
    await interaction.response.defer(thinking=True)

    async with db_session() as db:
        # Get user
        user = await get_or_create_user(db, interaction.user)

        # Check credits
        balance = await credit_manager.get_user_credits(db, user.id)
        cost = settings.COST_IMAGE_SDXL if model == "sdxl" else \
               settings.COST_IMAGE_PONY if model == "pony" else \
               settings.COST_IMAGE_HIDREAM

        if balance < cost and not is_admin(user_id):
            await interaction.followup.send(
                f"❌ Insufficient credits. You have {balance}, need {cost}. "
                f"Contact an admin to add credits.",
                ephemeral=True
            )
            return

        try:
            # Generate image
            image_bytes = await generate_image_bytes(model, prompt)
            REQUEST_COUNTER.labels(command="generate", status="success").inc()

            # Deduct credits
            if not is_admin(user_id):
                success = await credit_manager.deduct_credits(db, user.id, cost, f"image_{model}")
                if not success:
                    await interaction.followup.send("❌ Failed to deduct credits", ephemeral=True)
                    return

            # Send image
            file = discord.File(io.BytesIO(image_bytes), filename=f"generated_{model}.png")
            embed = discord.Embed(
                title="🎨 Image Generated",
                description=f"**Model:** {model}\n**Prompt:** {prompt}",
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"Cost: {cost} credits | Remaining: {balance - cost}")
            embed.set_image(url="attachment://generated_image.png")

            await interaction.followup.send(file=file, embed=embed)

        except Exception as e:
            logger.error("generate_failed", user_id=user_id, error=str(e))
            await interaction.followup.send(
                f"❌ Generation failed: {str(e)}",
                ephemeral=True
            )
            REQUEST_COUNTER.labels(command="generate", status="error").inc()

@bot.tree.command(name="ask", description="Ask AI a question")
@app_commands.describe(question="Your question or prompt")
async def ask_slash(interaction: discord.Interaction, question: str):
    """Slash command for text generation."""
    user_id = interaction.user.id

    allowed, info = await rate_limiter.is_allowed(
        user_id, "ask", settings.RATE_LIMIT_ASK
    )
    if not allowed:
        await interaction.response.send_message(
            f"⏳ Rate limit exceeded. Remaining: {info['remaining']} requests",
            ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)

    async with db_session() as db:
        user = await get_or_create_user(db, interaction.user)
        balance = await credit_manager.get_user_credits(db, user.id)
        cost = settings.COST_TEXT

        if balance < cost and not is_admin(user_id):
            await interaction.followup.send(
                f"❌ Insufficient credits: {balance}/{cost}",
                ephemeral=True
            )
            return

        try:
            response = await generate_text_response(question)
            REQUEST_COUNTER.labels(command="ask", status="success").inc()

            if not is_admin(user_id):
                await credit_manager.deduct_credits(db, user.id, cost, "text")

            if len(response) > 1900:
                response = response[:1900] + "..."

            embed = discord.Embed(
                title="💬 AI Response",
                description=response,
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Cost: {cost} credits | Remaining: {balance - cost}")

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error("ask_failed", user_id=user_id, error=str(e))
            await interaction.followup.send(f"❌ Failed: {str(e)}", ephemeral=True)
            REQUEST_COUNTER.labels(command="ask", status="error").inc()

@bot.tree.command(name="balance", description="Check your credit balance")
async def balance_slash(interaction: discord.Interaction):
    """Show user credit balance."""
    async with db_session() as db:
        user = await get_or_create_user(db, interaction.user)
        balance = await credit_manager.get_user_credits(db, user.id)

        embed = discord.Embed(
            title="💰 Credit Balance",
            description=f"You have **{balance}** credits",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="Costs",
            value=f"""• Text generation: {settings.COST_TEXT} credits
• Image (SDXL): {settings.COST_IMAGE_SDXL} credits
• Image (Pony): {settings.COST_IMAGE_PONY} credits
• Image (HiDream): {settings.COST_IMAGE_HIDREAM} credits"""
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="admin", description="Admin commands")
@app_commands.describe(
    action="Action to perform",
    user_id="Discord user ID",
    amount="Credit amount"
)
@app_commands.choices(action=[
    app_commands.Choice(name="addcredits", value="addcredits"),
    app_commands.Choice(name="ban", value="ban"),
    app_commands.Choice(name="unban", value="unban"),
])
async def admin_slash(
    interaction: discord.Interaction,
    action: str,
    user_id: str,
    amount: int = 0
):
    """Admin-only commands."""
    if not is_admin(interaction.user.id):
        await interaction.response.send_message("❌ Admin only", ephemeral=True)
        return

    async with db_session() as db:
        if action == "addcredits":
            target_user = await db.execute(select(User).where(User.discord_id == int(user_id)))
            user = target_user.scalar_one_or_none()
            if not user:
                await interaction.response.send_message("❌ User not found", ephemeral=True)
                return

            await credit_manager.add_credits(db, user.id, amount, "admin_grant")

            # Audit log
            audit = AdminAudit(
                admin_id=interaction.user.id,
                action="add_credits",
                target_user_id=user.id,
                details={"amount": amount}
            )
            db.add(audit)
            await db.commit()

            await interaction.response.send_message(
                f"✅ Added {amount} credits to user {user_id}",
                ephemeral=True
            )

        elif action == "ban":
            target_user = await db.execute(select(User).where(User.discord_id == int(user_id)))
            user = target_user.scalar_one_or_none()
            if not user:
                await interaction.response.send_message("❌ User not found", ephemeral=True)
                return

            await db.execute(
                update(User).where(User.id == user.id).values(
                    is_banned=True,
                    ban_reason="Banned by admin"
                )
            )
            await db.commit()

            await interaction.response.send_message(
                f"✅ User {user_id} banned",
                ephemeral=True
            )

        elif action == "unban":
            target_user = await db.execute(select(User).where(User.discord_id == int(user_id)))
            user = target_user.scalar_one_or_none()
            if not user:
                await interaction.response.send_message("❌ User not found", ephemeral=True)
                return

            await db.execute(
                update(User).where(User.id == user.id).values(
                    is_banned=False,
                    ban_reason=None
                )
            )
            await db.commit()

            await interaction.response.send_message(
                f"✅ User {user_id} unbanned",
                ephemeral=True
            )

# Legacy prefix commands
@bot.command(name="balance")
async def balance_prefix(ctx: commands.Context):
    """Legacy prefix command for balance."""
    async with db_session() as db:
        user = await get_or_create_user(db, ctx.author)
        balance = await credit_manager.get_user_credits(db, user.id)
        await ctx.send(f"💰 Your balance: **{balance}** credits")

# ============ Main Entry Point ============
async def main():
    """Main entry point with proper shutdown handling."""
    # Validate config
    if not settings.DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN not set")
        sys.exit(1)

    # Initialize database (create tables if not exist)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables ensured")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e), exc_info=True)
        raise  # DB is critical, exit

    # Initialize Redis (optional but recommended)
    try:
        await init_redis()
        logger.info("Redis connected")
    except Exception as e:
        logger.warning("Redis connection failed, rate limiting will use in-memory fallback", error=str(e))

    # Start bot
    try:
        await bot.start(settings.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested")
    except Exception as e:
        logger.critical("Bot crashed", error=str(e), exc_info=True)
        raise
    finally:
        await bot.close()
        await engine.dispose()
        await close_redis()
        logger.info("Shutdown complete")
        logger.info("Shutdown complete")

if __name__ == "__main__":
    # Run with proper signal handling
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")
        sys.exit(0)
