#!/usr/bin/env python3
"""
Health check and basic connectivity test.
Run: python test.py
"""

import asyncio
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_database_connection():
    """Test PostgreSQL connection."""
    print("Testing database connection...")
    try:
        from sqlalchemy import text
        from main import engine

        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
        print("  ✓ PostgreSQL connection OK")
        return True
    except Exception as e:
        print(f"  ✗ Database error: {e}")
        return False

async def test_redis_connection():
    """Test Redis connection."""
    print("Testing Redis connection...")
    try:
        from main import redis_client
        if redis_client is None:
            print("  ⚠ Redis not initialized (may be optional)")
            return True
        pong = await redis_client.ping()
        assert pong is True
        print("  ✓ Redis connection OK")
        return True
    except Exception as e:
        print(f"  ✗ Redis error: {e}")
        return False

async def test_environment():
    """Test environment configuration."""
    print("Testing environment...")
    from main import settings

    errors = []
    if not settings.DISCORD_TOKEN or len(settings.DISCORD_TOKEN) < 50:
        errors.append("DISCORD_TOKEN missing or too short")
    if not settings.HF_TOKEN or len(settings.HF_TOKEN) < 10:
        errors.append("HF_TOKEN missing or too short")

    if errors:
        for err in errors:
            print(f"  ✗ {err}")
        return False
    else:
        print("  ✓ Environment variables configured")
        return True

async def test_models():
    """Test model imports."""
    print("Testing model imports...")
    try:
        from main import IMAGE_MODELS, generate_image_bytes, generate_text_response
        assert isinstance(IMAGE_MODELS, dict)
        assert "sdxl" in IMAGE_MODELS
        assert "pony" in IMAGE_MODELS
        assert "hidream" in IMAGE_MODELS
        print(f"  ✓ {len(IMAGE_MODELS)} image models loaded")
        print(f"  ✓ Text generation function available")
        return True
    except Exception as e:
        print(f"  ✗ Model error: {e}")
        return False

async def test_rate_limiter():
    """Test rate limiter."""
    print("Testing rate limiter...")
    try:
        from main import rate_limiter
        allowed, info = await rate_limiter.is_allowed(999999, "test", 5)
        print(f"  ✓ Rate limiter works (allowed={allowed})")
        return True
    except Exception as e:
        print(f"  ✗ Rate limiter error: {e}")
        return False

async def run_all_tests():
    """Run all tests."""
    print("=" * 50)
    print("DISCORD BOT PRODUCTION READINESS TEST")
    print("=" * 50)
    print()

    results = []

    results.append(await test_environment())
    print()
    results.append(await test_models())
    print()
    results.append(await test_database_connection())
    print()
    results.append(await test_redis_connection())
    print()
    results.append(await test_rate_limiter())
    print()

    print("=" * 50)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    if all(results):
        print("✓ ALL CHECKS PASSED — Ready for production!")
        return 0
    else:
        print("✗ Some checks failed — review above")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
