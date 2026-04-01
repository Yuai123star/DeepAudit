"""
Tests for the rate limiter module (app.services.agent.core.rate_limiter).

Covers TokenBucketRateLimiter (try_acquire, acquire, available_tokens,
get_status), SlidingWindowRateLimiter (try_acquire, acquire), and
RateLimiterRegistry.
"""

import asyncio
import time

import pytest

from app.services.agent.core.rate_limiter import (
    RateLimiterRegistry,
    SlidingWindowRateLimiter,
    TokenBucketRateLimiter,
)


# ============ TokenBucketRateLimiter - try_acquire ============


class TestTokenBucketTryAcquire:
    """Tests for TokenBucketRateLimiter.try_acquire (non-blocking)."""

    @pytest.mark.asyncio
    async def test_acquire_from_full_bucket(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=5, name="test")
        assert await limiter.try_acquire() is True

    @pytest.mark.asyncio
    async def test_acquire_multiple_tokens(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=5, name="test")
        for _ in range(5):
            assert await limiter.try_acquire() is True

    @pytest.mark.asyncio
    async def test_acquire_rejected_when_empty(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=2, name="test")
        assert await limiter.try_acquire() is True
        assert await limiter.try_acquire() is True
        assert await limiter.try_acquire() is False

    @pytest.mark.asyncio
    async def test_acquire_multiple_tokens_at_once(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=5, name="test")
        assert await limiter.try_acquire(tokens=3) is True
        assert limiter.tokens == pytest.approx(2.0)
        assert await limiter.try_acquire(tokens=3) is False

    @pytest.mark.asyncio
    async def test_tokens_start_at_burst(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=10, name="test")
        assert limiter.tokens == 10.0


# ============ TokenBucketRateLimiter - acquire (blocking) ============


class TestTokenBucketAcquire:
    """Tests for TokenBucketRateLimiter.acquire (blocking with timeout)."""

    @pytest.mark.asyncio
    async def test_acquire_immediately_when_tokens_available(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=5, name="test")
        result = await limiter.acquire()
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_times_out(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=0, name="test")
        limiter.tokens = 0.0
        result = await limiter.acquire(tokens=1, timeout=0.05)
        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_succeeds_after_replenish(self):
        limiter = TokenBucketRateLimiter(rate=100.0, burst=1, name="test")
        # Consume the token
        assert await limiter.try_acquire() is True
        # With rate=100 tokens/sec and timeout, should replenish quickly
        result = await limiter.acquire(tokens=1, timeout=0.5)
        assert result is True


# ============ TokenBucketRateLimiter - available_tokens ============


class TestTokenBucketAvailableTokens:
    def test_initial_available_equals_burst(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=5, name="test")
        # available_tokens replenishes based on elapsed time, but right
        # after creation it should be close to burst
        assert limiter.available_tokens >= 5.0

    @pytest.mark.asyncio
    async def test_available_decreases_after_acquire(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=5, name="test")
        await limiter.try_acquire(tokens=3)
        # After deducting 3 from 5, tokens = 2
        assert limiter.tokens == pytest.approx(2.0)

    def test_available_capped_at_burst(self):
        limiter = TokenBucketRateLimiter(rate=1.0, burst=5, name="test")
        # Even if we manipulate tokens above burst, available is capped
        limiter.tokens = 100.0
        assert limiter.available_tokens == 5.0


# ============ TokenBucketRateLimiter - get_status ============


class TestTokenBucketGetStatus:
    def test_status_dict_keys(self):
        limiter = TokenBucketRateLimiter(rate=2.0, burst=10, name="svc")
        status = limiter.get_status()
        assert status["name"] == "svc"
        assert status["rate"] == 2.0
        assert status["burst"] == 10
        assert "available_tokens" in status


# ============ SlidingWindowRateLimiter - try_acquire ============


class TestSlidingWindowTryAcquire:
    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        limiter = SlidingWindowRateLimiter(
            max_requests=5, window_seconds=1.0, name="test"
        )
        for _ in range(5):
            assert await limiter.try_acquire() is True

    @pytest.mark.asyncio
    async def test_acquire_rejected_over_limit(self):
        limiter = SlidingWindowRateLimiter(
            max_requests=2, window_seconds=1.0, name="test"
        )
        assert await limiter.try_acquire() is True
        assert await limiter.try_acquire() is True
        assert await limiter.try_acquire() is False


# ============ SlidingWindowRateLimiter - acquire ============


class TestSlidingWindowAcquire:
    @pytest.mark.asyncio
    async def test_acquire_times_out(self):
        limiter = SlidingWindowRateLimiter(
            max_requests=1, window_seconds=10.0, name="test"
        )
        # Use up the single allowed request
        assert await limiter.try_acquire() is True
        # Next acquire should time out because window is 10 seconds
        result = await limiter.acquire(timeout=0.05)
        assert result is False

    @pytest.mark.asyncio
    async def test_acquire_succeeds_when_slot_available(self):
        limiter = SlidingWindowRateLimiter(
            max_requests=3, window_seconds=1.0, name="test"
        )
        result = await limiter.acquire()
        assert result is True


# ============ RateLimiterRegistry ============


class TestRateLimiterRegistry:
    def test_get_or_create_returns_same_instance(self):
        registry = RateLimiterRegistry()
        lim1 = registry.get_or_create("llm", rate=1.0, burst=5)
        lim2 = registry.get_or_create("llm", rate=2.0, burst=10)
        assert lim1 is lim2
        # First creation wins; rate should be from first call
        assert lim1.rate == 1.0

    def test_get_or_create_different_names(self):
        registry = RateLimiterRegistry()
        lim_a = registry.get_or_create("a")
        lim_b = registry.get_or_create("b")
        assert lim_a is not lim_b

    def test_get_returns_none_for_unknown(self):
        registry = RateLimiterRegistry()
        assert registry.get("nonexistent") is None

    def test_get_returns_existing(self):
        registry = RateLimiterRegistry()
        limiter = registry.get_or_create("svc")
        assert registry.get("svc") is limiter

    def test_get_all_status(self):
        registry = RateLimiterRegistry()
        registry.get_or_create("svc1", rate=1.0, burst=5)
        registry.get_or_create("svc2", rate=2.0, burst=10)
        statuses = registry.get_all_status()
        assert "svc1" in statuses
        assert "svc2" in statuses
        assert statuses["svc1"]["rate"] == 1.0
        assert statuses["svc2"]["burst"] == 10
