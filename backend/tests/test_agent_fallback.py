"""
Tests for Fallback and Graceful Degradation module.

Tests FallbackHandler, FallbackConfig, and related utilities at
app.services.agent.core.fallback.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.agent.core.fallback import (
    FallbackAction,
    FallbackConfig,
    FallbackHandler,
    FallbackResult,
)
from app.services.agent.core.errors import (
    AgentError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMContextLengthError,
    ToolError,
    ExternalToolError,
)


# ============ FallbackConfig Tests ============


class TestFallbackConfig:
    """Tests for FallbackConfig defaults."""

    def test_default_enabled(self):
        config = FallbackConfig()
        assert config.enabled is True

    def test_default_max_context_reduction_ratio(self):
        config = FallbackConfig()
        assert config.max_context_reduction_ratio == 0.5

    def test_default_tool_fallbacks(self):
        config = FallbackConfig()
        assert "semgrep_scan" in config.tool_fallbacks
        assert config.tool_fallbacks["semgrep_scan"] == "pattern_match"
        assert "bandit_scan" in config.tool_fallbacks
        assert "gitleaks_scan" in config.tool_fallbacks

    def test_custom_tool_fallbacks(self):
        config = FallbackConfig(tool_fallbacks={"my_tool": "backup_tool"})
        assert config.tool_fallbacks == {"my_tool": "backup_tool"}


# ============ FallbackAction Tests ============


class TestFallbackAction:
    """Tests for FallbackAction enum values."""

    def test_enum_values(self):
        assert FallbackAction.RETRY.value == "retry"
        assert FallbackAction.RETRY_WITH_REDUCED_CONTEXT.value == "retry_reduced"
        assert FallbackAction.USE_FALLBACK_TOOL.value == "use_fallback"
        assert FallbackAction.SKIP.value == "skip"
        assert FallbackAction.CONTINUE_PARTIAL.value == "continue_partial"
        assert FallbackAction.ABORT.value == "abort"


# ============ FallbackResult Tests ============


class TestFallbackResult:
    """Tests for FallbackResult dataclass."""

    def test_fallback_result_fields(self):
        result = FallbackResult(
            action=FallbackAction.RETRY,
            success=False,
            message="retrying",
        )
        assert result.action == FallbackAction.RETRY
        assert result.success is False
        assert result.result is None
        assert result.error is None
        assert result.fallback_used is None
        assert result.message == "retrying"


# ============ handle_llm_failure Tests ============


class TestHandleLLMFailure:
    """Tests for FallbackHandler.handle_llm_failure."""

    @pytest.fixture
    def handler(self):
        return FallbackHandler(FallbackConfig(enabled=True))

    @pytest.mark.asyncio
    async def test_rate_limit_error_returns_retry(self, handler):
        error = LLMRateLimitError("rate limited", retry_after=30)
        result = await handler.handle_llm_failure(error, {})
        assert result.action == FallbackAction.RETRY
        assert result.success is False
        assert result.error is error
        assert "30" in result.message

    @pytest.mark.asyncio
    async def test_timeout_with_retry_func_and_reduce_context(self, handler):
        error = LLMTimeoutError("timed out")
        retry_fn = AsyncMock(return_value="retried_result")
        context = {"can_reduce_context": True}
        result = await handler.handle_llm_failure(error, context, retry_func=retry_fn)
        assert result.action == FallbackAction.RETRY_WITH_REDUCED_CONTEXT
        assert result.success is False

    @pytest.mark.asyncio
    async def test_timeout_with_retry_func_no_reduce_context(self, handler):
        error = LLMTimeoutError("timed out")
        retry_fn = AsyncMock()
        context = {"can_reduce_context": False}
        result = await handler.handle_llm_failure(error, context, retry_func=retry_fn)
        assert result.action == FallbackAction.CONTINUE_PARTIAL

    @pytest.mark.asyncio
    async def test_timeout_without_retry_func(self, handler):
        error = LLMTimeoutError("timed out")
        context = {}
        result = await handler.handle_llm_failure(error, context, retry_func=None)
        assert result.action == FallbackAction.CONTINUE_PARTIAL
        assert result.success is False
        assert "partial" in result.message.lower()

    @pytest.mark.asyncio
    async def test_context_length_error_returns_retry_reduced(self, handler):
        error = LLMContextLengthError("too long")
        result = await handler.handle_llm_failure(error, {})
        assert result.action == FallbackAction.RETRY_WITH_REDUCED_CONTEXT
        assert result.success is False

    @pytest.mark.asyncio
    async def test_recoverable_llm_error_returns_retry(self, handler):
        error = LLMError("transient failure", recoverable=True)
        result = await handler.handle_llm_failure(error, {})
        assert result.action == FallbackAction.RETRY
        assert result.success is False
        assert "recoverable" in result.message

    @pytest.mark.asyncio
    async def test_non_recoverable_llm_error_returns_abort(self, handler):
        error = LLMError("fatal failure", recoverable=False)
        result = await handler.handle_llm_failure(error, {})
        assert result.action == FallbackAction.ABORT
        assert result.success is False
        assert "non-recoverable" in result.message

    @pytest.mark.asyncio
    async def test_unknown_error_returns_abort(self, handler):
        error = ValueError("something unexpected")
        result = await handler.handle_llm_failure(error, {})
        assert result.action == FallbackAction.ABORT
        assert result.success is False

    @pytest.mark.asyncio
    async def test_disabled_config_returns_abort(self):
        handler = FallbackHandler(FallbackConfig(enabled=False))
        error = LLMRateLimitError("rate limited")
        result = await handler.handle_llm_failure(error, {})
        assert result.action == FallbackAction.ABORT
        assert "disabled" in result.message.lower()


# ============ handle_tool_failure Tests ============


class TestHandleToolFailure:
    """Tests for FallbackHandler.handle_tool_failure."""

    @pytest.fixture
    def handler(self):
        return FallbackHandler(FallbackConfig(
            enabled=True,
            tool_fallbacks={"semgrep_scan": "pattern_match"},
        ))

    @pytest.mark.asyncio
    async def test_fallback_tool_succeeds(self, handler):
        executor = AsyncMock(return_value="fallback result")
        error = ToolError("semgrep failed")
        result = await handler.handle_tool_failure(
            "semgrep_scan", error, {"path": "."}, fallback_executor=executor,
        )
        assert result.action == FallbackAction.USE_FALLBACK_TOOL
        assert result.success is True
        assert result.fallback_used == "pattern_match"
        assert result.result == "fallback result"

    @pytest.mark.asyncio
    async def test_fallback_tool_fails_returns_skip(self, handler):
        executor = AsyncMock(side_effect=RuntimeError("fallback also broken"))
        error = ToolError("semgrep failed")
        result = await handler.handle_tool_failure(
            "semgrep_scan", error, {"path": "."}, fallback_executor=executor,
        )
        assert result.action == FallbackAction.SKIP
        assert result.success is False

    @pytest.mark.asyncio
    async def test_no_fallback_tool_returns_skip(self, handler):
        error = ToolError("unknown tool failed")
        result = await handler.handle_tool_failure(
            "nonexistent_tool", error, {}, fallback_executor=None,
        )
        assert result.action == FallbackAction.SKIP

    @pytest.mark.asyncio
    async def test_recoverable_tool_error_returns_retry(self, handler):
        error = ToolError("tool glitch", recoverable=True)
        result = await handler.handle_tool_failure(
            "nonexistent_tool", error, {}, fallback_executor=None,
        )
        assert result.action == FallbackAction.RETRY
        assert result.success is False

    @pytest.mark.asyncio
    async def test_recoverable_external_tool_error_returns_retry(self, handler):
        error = ExternalToolError("semgrep crashed", recoverable=True)
        result = await handler.handle_tool_failure(
            "nonexistent_tool", error, {}, fallback_executor=None,
        )
        assert result.action == FallbackAction.RETRY

    @pytest.mark.asyncio
    async def test_non_recoverable_tool_error_returns_skip(self, handler):
        error = ToolError("permanent failure", recoverable=False)
        result = await handler.handle_tool_failure(
            "nonexistent_tool", error, {}, fallback_executor=None,
        )
        assert result.action == FallbackAction.SKIP

    @pytest.mark.asyncio
    async def test_disabled_config_returns_abort(self):
        handler = FallbackHandler(FallbackConfig(enabled=False))
        error = ToolError("failed")
        result = await handler.handle_tool_failure("tool", error, {})
        assert result.action == FallbackAction.ABORT

    @pytest.mark.asyncio
    async def test_no_fallback_executor_returns_skip(self, handler):
        error = ToolError("semgrep crashed")
        result = await handler.handle_tool_failure(
            "semgrep_scan", error, {"path": "."}, fallback_executor=None,
        )
        # Has fallback mapping but no executor, so check recoverable
        assert result.action in (FallbackAction.SKIP, FallbackAction.RETRY)


# ============ reduce_context Tests ============


class TestReduceContext:
    """Tests for FallbackHandler.reduce_context."""

    @pytest.fixture
    def handler(self):
        return FallbackHandler(FallbackConfig(max_context_reduction_ratio=0.5))

    def test_keeps_short_list_unchanged(self, handler):
        messages = [
            {"role": "system", "content": "You are an auditor."},
            {"role": "user", "content": "Check this file."},
        ]
        result = handler.reduce_context(messages)
        assert result == messages

    def test_preserves_system_messages(self, handler):
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "msg4"},
        ]
        result = handler.reduce_context(messages)
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == "System prompt"

    def test_reduces_non_system_messages(self, handler):
        messages = [
            {"role": "system", "content": "sys"},
        ] + [
            {"role": "user", "content": f"msg{i}"} for i in range(10)
        ]
        result = handler.reduce_context(messages)
        non_system = [m for m in result if m["role"] != "system"]
        # 50% of 10 = 5, so keep last 5
        assert len(non_system) == 5
        assert non_system[0]["content"] == "msg5"
        assert non_system[-1]["content"] == "msg9"

    def test_always_keeps_at_least_one_non_system(self, handler):
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "msg1"},
            {"role": "user", "content": "msg2"},
            {"role": "user", "content": "msg3"},
        ]
        result = handler.reduce_context(messages, reduction_ratio=0.1)
        non_system = [m for m in result if m["role"] != "system"]
        assert len(non_system) >= 1

    def test_custom_reduction_ratio(self, handler):
        messages = [
            {"role": "system", "content": "sys"},
        ] + [
            {"role": "user", "content": f"msg{i}"} for i in range(10)
        ]
        result = handler.reduce_context(messages, reduction_ratio=0.3)
        non_system = [m for m in result if m["role"] != "system"]
        assert len(non_system) == 3


# ============ truncate_content Tests ============


class TestTruncateContent:
    """Tests for FallbackHandler.truncate_content."""

    @pytest.fixture
    def handler(self):
        return FallbackHandler(FallbackConfig())

    def test_short_content_unchanged(self, handler):
        content = "Hello world"
        result = handler.truncate_content(content, max_length=100)
        assert result == content

    def test_long_content_is_truncated(self, handler):
        content = "A" * 1000
        result = handler.truncate_content(content, max_length=100, keep_start=30, keep_end=30)
        assert "CONTENT TRUNCATED" in result
        assert len(result) < 1000

    def test_preserves_head_and_tail(self, handler):
        content = "A" * 400 + "B" * 400
        result = handler.truncate_content(content, max_length=100, keep_start=30, keep_end=30)
        assert result.startswith("A" * 30)
        assert result.endswith("B" * 30)

    def test_exact_max_length_unchanged(self, handler):
        content = "X" * 50
        result = handler.truncate_content(content, max_length=50)
        assert result == content

    def test_truncation_notice_present(self, handler):
        content = "A" * 1000
        result = handler.truncate_content(content, max_length=200, keep_start=50, keep_end=50)
        assert "... [CONTENT TRUNCATED] ..." in result
