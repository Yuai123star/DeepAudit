"""
Tests for the circuit breaker module (app.services.agent.core.circuit_breaker).

Covers CircuitState, CircuitBreakerConfig, CircuitStats, CircuitBreaker state
transitions (CLOSED->OPEN->HALF_OPEN->CLOSED), context manager, protect
decorator, get_status, and CircuitBreakerRegistry.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.core.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
    CircuitStats,
)
from app.services.agent.core.errors import CircuitOpenError


# ============ CircuitState ============


class TestCircuitState:
    def test_enum_values(self):
        assert CircuitState.CLOSED == "closed"
        assert CircuitState.OPEN == "open"
        assert CircuitState.HALF_OPEN == "half_open"

    def test_enum_members_count(self):
        assert len(CircuitState) == 3


# ============ CircuitStats ============


class TestCircuitStats:
    def test_initial_values(self):
        stats = CircuitStats()
        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        assert stats.rejected_calls == 0
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 0

    def test_record_success(self):
        stats = CircuitStats()
        stats.record_success()
        assert stats.total_calls == 1
        assert stats.successful_calls == 1
        assert stats.consecutive_successes == 1
        assert stats.consecutive_failures == 0

    def test_record_failure(self):
        stats = CircuitStats()
        stats.record_failure()
        assert stats.total_calls == 1
        assert stats.failed_calls == 1
        assert stats.consecutive_failures == 1
        assert stats.consecutive_successes == 0
        assert stats.last_failure_time is not None

    def test_record_rejection(self):
        stats = CircuitStats()
        stats.record_rejection()
        assert stats.rejected_calls == 1
        assert stats.total_calls == 0  # rejections don't count as total calls

    def test_failure_rate(self):
        stats = CircuitStats()
        assert stats.failure_rate == 0.0
        stats.record_success()
        stats.record_success()
        stats.record_failure()
        assert stats.failure_rate == pytest.approx(1.0 / 3.0)

    def test_failure_rate_zero_total(self):
        stats = CircuitStats()
        assert stats.failure_rate == 0.0

    def test_reset(self):
        stats = CircuitStats()
        stats.record_success()
        stats.record_failure()
        stats.record_rejection()
        stats.reset()
        assert stats.total_calls == 0
        assert stats.successful_calls == 0
        assert stats.failed_calls == 0
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 0

    def test_consecutive_resets_on_alternating(self):
        """Recording success resets consecutive_failures and vice versa."""
        stats = CircuitStats()
        stats.record_failure()
        stats.record_failure()
        assert stats.consecutive_failures == 2
        stats.record_success()
        assert stats.consecutive_failures == 0
        assert stats.consecutive_successes == 1
        stats.record_failure()
        assert stats.consecutive_successes == 0
        assert stats.consecutive_failures == 1


# ============ CircuitBreaker state transitions ============


class TestCircuitBreakerTransitions:
    """Tests for CircuitBreaker core state machine."""

    def test_starts_closed(self):
        cb = CircuitBreaker("test")
        assert cb.state == CircuitState.CLOSED
        assert cb.is_closed is True
        assert cb.is_open is False

    @pytest.mark.asyncio
    async def test_closed_to_open(self):
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config)
        for _ in range(3):
            try:
                await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
            except RuntimeError:
                pass
        assert cb.state == CircuitState.OPEN
        assert cb.stats.consecutive_failures == 3

    @pytest.mark.asyncio
    async def test_open_rejects_with_circuit_open_error(self):
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", config)
        # trip the breaker
        try:
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN
        with pytest.raises(CircuitOpenError):
            await cb.call(AsyncMock(return_value="ok"))

    @pytest.mark.asyncio
    async def test_open_to_half_open_after_recovery_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=10.0)
        cb = CircuitBreaker("test", config)
        # trip the breaker
        try:
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN

        # Advance time past recovery_timeout
        base_time = time.time()
        with patch(
            "app.services.agent.core.circuit_breaker.time.time",
            return_value=base_time + 20.0,
        ):
            result = await cb.call(AsyncMock(return_value="ok"))
        assert result == "ok"
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_to_closed_after_success_threshold(self):
        config = CircuitBreakerConfig(
            failure_threshold=1, success_threshold=2, recovery_timeout=0.0
        )
        cb = CircuitBreaker("test", config)
        # trip the breaker
        try:
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        except RuntimeError:
            pass

        # Move to HALF_OPEN by advancing time
        with patch(
            "app.services.agent.core.circuit_breaker.time.time",
            return_value=time.time() + 1.0,
        ):
            await cb.call(AsyncMock(return_value="ok1"))
        assert cb.state == CircuitState.HALF_OPEN

        # Need success_threshold consecutive successes to close
        with patch(
            "app.services.agent.core.circuit_breaker.time.time",
            return_value=time.time() + 2.0,
        ):
            await cb.call(AsyncMock(return_value="ok2"))
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_to_open_on_failure(self):
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.0)
        cb = CircuitBreaker("test", config)
        # trip the breaker
        try:
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        except RuntimeError:
            pass

        # Move to HALF_OPEN
        with patch(
            "app.services.agent.core.circuit_breaker.time.time",
            return_value=time.time() + 1.0,
        ):
            await cb.call(AsyncMock(return_value="probe"))
        assert cb.state == CircuitState.HALF_OPEN

        # A single failure in HALF_OPEN should re-open
        with patch(
            "app.services.agent.core.circuit_breaker.time.time",
            return_value=time.time() + 2.0,
        ):
            try:
                await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
            except RuntimeError:
                pass
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_limits_calls(self):
        config = CircuitBreakerConfig(
            failure_threshold=1, success_threshold=100, recovery_timeout=0.0,
            half_open_max_calls=2
        )
        cb = CircuitBreaker("test", config)
        # trip the breaker
        try:
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN

        # Directly transition to HALF_OPEN to avoid time patching issues
        async with cb._lock:
            await cb._transition_to(CircuitState.HALF_OPEN)

        # Use up the allowed calls
        await cb.call(AsyncMock(return_value="ok1"))
        await cb.call(AsyncMock(return_value="ok2"))
        # Third call should be rejected
        with pytest.raises(CircuitOpenError):
            await cb.call(AsyncMock(return_value="ok3"))


# ============ CircuitBreaker context manager ============


class TestCircuitBreakerContextManager:
    @pytest.mark.asyncio
    async def test_success_path(self):
        cb = CircuitBreaker("test")
        async with cb:
            pass  # no exception
        assert cb.stats.successful_calls == 1

    @pytest.mark.asyncio
    async def test_failure_path(self):
        config = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker("test", config)
        with pytest.raises(ValueError):
            async with cb:
                raise ValueError("oops")
        assert cb.stats.failed_calls == 1

    @pytest.mark.asyncio
    async def test_rejection_raises_circuit_open_error(self):
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", config)
        # trip the breaker
        try:
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        except RuntimeError:
            pass
        with pytest.raises(CircuitOpenError):
            async with cb:
                pass


# ============ CircuitBreaker.protect decorator ============


class TestCircuitBreakerProtect:
    @pytest.mark.asyncio
    async def test_protected_function_success(self):
        cb = CircuitBreaker("test")

        @cb.protect
        async def my_func():
            return "result"

        result = await my_func()
        assert result == "result"
        assert cb.stats.successful_calls == 1

    @pytest.mark.asyncio
    async def test_protected_function_failure(self):
        config = CircuitBreakerConfig(failure_threshold=5)
        cb = CircuitBreaker("test", config)

        @cb.protect
        async def my_func():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await my_func()
        assert cb.stats.failed_calls == 1


# ============ CircuitBreaker.get_status ============


class TestCircuitBreakerGetStatus:
    @pytest.mark.asyncio
    async def test_status_dict_structure(self):
        cb = CircuitBreaker("test_service")
        await cb.call(AsyncMock(return_value="ok"))
        status = cb.get_status()
        assert status["name"] == "test_service"
        assert status["state"] == "closed"
        assert "stats" in status
        assert status["stats"]["total_calls"] == 1
        assert status["stats"]["successful_calls"] == 1
        assert "time_in_state" in status


# ============ CircuitBreaker.reset ============


class TestCircuitBreakerReset:
    @pytest.mark.asyncio
    async def test_reset_returns_to_closed(self):
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", config)
        # trip the breaker
        try:
            await cb.call(AsyncMock(side_effect=RuntimeError("fail")))
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN

        await cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.stats.total_calls == 0


# ============ CircuitBreakerRegistry ============


class TestCircuitBreakerRegistry:
    def test_get_or_create_returns_same_instance(self):
        registry = CircuitBreakerRegistry()
        cb1 = registry.get_or_create("service_a")
        cb2 = registry.get_or_create("service_a")
        assert cb1 is cb2

    def test_get_or_create_different_names(self):
        registry = CircuitBreakerRegistry()
        cb_a = registry.get_or_create("a")
        cb_b = registry.get_or_create("b")
        assert cb_a is not cb_b

    def test_get_returns_none_for_unknown(self):
        registry = CircuitBreakerRegistry()
        assert registry.get("nonexistent") is None

    def test_get_returns_existing(self):
        registry = CircuitBreakerRegistry()
        cb = registry.get_or_create("svc")
        assert registry.get("svc") is cb

    @pytest.mark.asyncio
    async def test_reset_all(self):
        registry = CircuitBreakerRegistry()
        config = CircuitBreakerConfig(failure_threshold=1)
        cb1 = registry.get_or_create("a", config)
        cb2 = registry.get_or_create("b", config)
        # trip both
        try:
            await cb1.call(AsyncMock(side_effect=RuntimeError("x")))
        except RuntimeError:
            pass
        try:
            await cb2.call(AsyncMock(side_effect=RuntimeError("x")))
        except RuntimeError:
            pass
        assert cb1.state == CircuitState.OPEN
        assert cb2.state == CircuitState.OPEN

        await registry.reset_all()
        assert cb1.state == CircuitState.CLOSED
        assert cb2.state == CircuitState.CLOSED

    def test_get_all_status(self):
        registry = CircuitBreakerRegistry()
        registry.get_or_create("svc1")
        registry.get_or_create("svc2")
        statuses = registry.get_all_status()
        assert "svc1" in statuses
        assert "svc2" in statuses
        assert statuses["svc1"]["name"] == "svc1"
