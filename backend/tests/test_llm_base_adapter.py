"""
Tests for app.services.llm.base_adapter.BaseLLMAdapter
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm.base_adapter import BaseLLMAdapter
from app.services.llm.types import LLMConfig, LLMError, LLMProvider, LLMRequest


# ---------------------------------------------------------------------------
# Concrete subclass so we can instantiate the abstract base
# ---------------------------------------------------------------------------

class ConcreteAdapter(BaseLLMAdapter):
    """Minimal concrete adapter used solely for testing."""

    async def complete(self, request: LLMRequest):
        return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> LLMConfig:
    return LLMConfig(
        provider=LLMProvider.OPENAI,
        api_key="sk-test-key",
        model="gpt-4",
    )


@pytest.fixture
def adapter(config: LLMConfig) -> ConcreteAdapter:
    return ConcreteAdapter(config)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestInit:
    def test_stores_config(self, config: LLMConfig):
        adapter = ConcreteAdapter(config)
        assert adapter.config is config

    def test_client_is_none_initially(self, adapter: ConcreteAdapter):
        assert adapter._client is None


# ---------------------------------------------------------------------------
# get_provider / get_model
# ---------------------------------------------------------------------------

class TestGetProviderModel:
    def test_get_provider_returns_config_provider(self, adapter: ConcreteAdapter):
        assert adapter.get_provider() == LLMProvider.OPENAI

    def test_get_model_returns_config_model(self, adapter: ConcreteAdapter):
        assert adapter.get_model() == "gpt-4"

    def test_get_provider_different_provider(self):
        cfg = LLMConfig(provider=LLMProvider.DEEPSEEK, api_key="key", model="deepseek-v3")
        adapter = ConcreteAdapter(cfg)
        assert adapter.get_provider() == LLMProvider.DEEPSEEK


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    async def test_returns_true_when_api_key_set(self, adapter: ConcreteAdapter):
        assert await adapter.validate_config() is True

    async def test_raises_when_api_key_empty(self):
        cfg = LLMConfig(provider=LLMProvider.OPENAI, api_key="", model="gpt-4")
        adapter = ConcreteAdapter(cfg)
        with pytest.raises(LLMError, match="API Key"):
            await adapter.validate_config()

    async def test_whitespace_api_key_accepted_as_truthy(self):
        """Whitespace-only api_key is truthy, so validate_config returns True."""
        cfg = LLMConfig(provider=LLMProvider.CLAUDE, api_key="   ", model="claude-3")
        adapter = ConcreteAdapter(cfg)
        # api_key="   " is truthy, so no error raised
        assert await adapter.validate_config() is True

    async def test_llm_error_contains_provider(self):
        cfg = LLMConfig(provider=LLMProvider.QWEN, api_key="", model="qwen-max")
        adapter = ConcreteAdapter(cfg)
        with pytest.raises(LLMError) as exc_info:
            await adapter.validate_config()
        assert exc_info.value.provider == LLMProvider.QWEN


# ---------------------------------------------------------------------------
# build_headers
# ---------------------------------------------------------------------------

class TestBuildHeaders:
    def test_default_headers(self, adapter: ConcreteAdapter):
        headers = adapter.build_headers()
        assert headers == {"Content-Type": "application/json"}

    def test_merges_additional_headers(self, adapter: ConcreteAdapter):
        headers = adapter.build_headers({"Authorization": "Bearer tok"})
        assert headers == {
            "Content-Type": "application/json",
            "Authorization": "Bearer tok",
        }

    def test_merges_custom_headers_from_config(self):
        cfg = LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="key",
            model="gpt-4",
            custom_headers={"X-Custom": "value"},
        )
        adapter = ConcreteAdapter(cfg)
        headers = adapter.build_headers()
        assert headers["X-Custom"] == "value"
        assert headers["Content-Type"] == "application/json"

    def test_additional_overrides_content_type(self, adapter: ConcreteAdapter):
        headers = adapter.build_headers({"Content-Type": "text/plain"})
        assert headers["Content-Type"] == "text/plain"

    def test_custom_headers_override_additional(self):
        cfg = LLMConfig(
            provider=LLMProvider.OPENAI,
            api_key="key",
            model="gpt-4",
            custom_headers={"X-Custom": "from-config"},
        )
        adapter = ConcreteAdapter(cfg)
        headers = adapter.build_headers({"X-Custom": "from-additional"})
        # custom_headers is applied last, so it wins
        assert headers["X-Custom"] == "from-config"

    def test_none_additional_headers(self, adapter: ConcreteAdapter):
        headers = adapter.build_headers(None)
        assert headers == {"Content-Type": "application/json"}


# ---------------------------------------------------------------------------
# handle_error
# ---------------------------------------------------------------------------

class TestHandleError:
    def test_timeout_error_chinese(self, adapter: ConcreteAdapter):
        with pytest.raises(LLMError, match="请求超时"):
            adapter.handle_error(Exception("连接超时"))

    def test_timeout_error_english(self, adapter: ConcreteAdapter):
        with pytest.raises(LLMError, match="请求超时"):
            adapter.handle_error(Exception("Connection timeout error"))

    def test_insufficient_balance_chinese(self, adapter: ConcreteAdapter):
        with pytest.raises(LLMError, match="余额不足"):
            adapter.handle_error(Exception("账户余额不足"))

    def test_insufficient_balance_english(self, adapter: ConcreteAdapter):
        with pytest.raises(LLMError, match="余额不足"):
            adapter.handle_error(Exception("insufficient quota"))

    def test_401_auth_failure(self, adapter: ConcreteAdapter):
        err = Exception("Unauthorized")
        err.status_code = 401  # type: ignore[attr-defined]
        with pytest.raises(LLMError, match="API认证失败"):
            adapter.handle_error(err)

    def test_403_auth_failure(self, adapter: ConcreteAdapter):
        err = Exception("Forbidden")
        err.status_code = 403  # type: ignore[attr-defined]
        with pytest.raises(LLMError, match="API认证失败"):
            adapter.handle_error(err)

    def test_429_rate_limit(self, adapter: ConcreteAdapter):
        err = Exception("Too Many Requests")
        err.status_code = 429  # type: ignore[attr-defined]
        with pytest.raises(LLMError, match="频率超限"):
            adapter.handle_error(err)

    def test_500_server_error(self, adapter: ConcreteAdapter):
        err = Exception("Internal Server Error")
        err.status_code = 500  # type: ignore[attr-defined]
        with pytest.raises(LLMError, match="API服务异常"):
            adapter.handle_error(err)

    def test_502_server_error(self, adapter: ConcreteAdapter):
        err = Exception("Bad Gateway")
        err.status_code = 502  # type: ignore[attr-defined]
        with pytest.raises(LLMError, match="API服务异常"):
            adapter.handle_error(err)

    def test_default_error_no_status_code(self, adapter: ConcreteAdapter):
        with pytest.raises(LLMError) as exc_info:
            adapter.handle_error(Exception("Something went wrong"))
        assert "Something went wrong" in str(exc_info.value)

    def test_context_prepended(self, adapter: ConcreteAdapter):
        with pytest.raises(LLMError, match="my context:"):
            adapter.handle_error(Exception("oops"), context="my context")

    def test_api_response_forwarded(self, adapter: ConcreteAdapter):
        with pytest.raises(LLMError) as exc_info:
            adapter.handle_error(
                Exception("err"),
                api_response="raw-body-here",
            )
        assert exc_info.value.api_response == "raw-body-here"

    def test_insufficient_balance_sets_status_402(self, adapter: ConcreteAdapter):
        with pytest.raises(LLMError) as exc_info:
            adapter.handle_error(Exception("insufficient balance"))
        assert exc_info.value.status_code == 402


# ---------------------------------------------------------------------------
# with_timeout
# ---------------------------------------------------------------------------

class TestWithTimeout:
    async def test_returns_result_on_success(self, adapter: ConcreteAdapter):
        async def coro():
            return 42

        result = await adapter.with_timeout(coro(), timeout_seconds=5)
        assert result == 42

    async def test_raises_llm_error_on_timeout(self, adapter: ConcreteAdapter):
        async def slow_coro():
            await asyncio.sleep(10)
            return "never"

        with pytest.raises(LLMError, match="请求超时"):
            await adapter.with_timeout(slow_coro(), timeout_seconds=1)

    async def test_uses_config_timeout_when_none_passed(self, adapter: ConcreteAdapter):
        # config.timeout is 150 by default -- use a very short override to prove the path
        async def coro():
            return "ok"

        result = await adapter.with_timeout(coro())
        assert result == "ok"


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------

class TestClose:
    async def test_close_does_nothing_when_no_client(self, adapter: ConcreteAdapter):
        # Should not raise
        await adapter.close()
        assert adapter._client is None

    async def test_close_closes_existing_client(self, adapter: ConcreteAdapter):
        mock_client = AsyncMock()
        adapter._client = mock_client
        await adapter.close()
        mock_client.aclose.assert_awaited_once()
        assert adapter._client is None
