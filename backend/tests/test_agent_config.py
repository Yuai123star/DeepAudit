"""
Tests for Agent configuration module.

Covers AgentConfig defaults, singleton caching, ToolConfig / AgentTypeConfig
lookups, configuration validation, and the testing preset.
"""

import os
import pytest
from unittest.mock import patch

from app.services.agent.config import (
    AgentConfig,
    ToolConfig,
    AgentTypeConfig,
    LogLevel,
    get_agent_config,
    get_tool_config,
    get_agent_type_config,
    validate_config,
    apply_testing_preset,
)


@pytest.fixture(autouse=True)
def reset_config():
    """Ensure lru_cache is cleared before and after each test."""
    get_agent_config.cache_clear()
    yield
    get_agent_config.cache_clear()


# ---------------------------------------------------------------------------
# AgentConfig defaults
# ---------------------------------------------------------------------------

class TestAgentConfigDefaults:
    def test_default_config_values(self):
        config = AgentConfig()
        assert config.llm_max_retries == 3
        assert config.llm_temperature == 0.1
        assert config.orchestrator_max_iterations == 20


# ---------------------------------------------------------------------------
# get_agent_config singleton / cache
# ---------------------------------------------------------------------------

class TestGetAgentConfig:
    def test_get_agent_config_returns_same_instance(self):
        a = get_agent_config()
        b = get_agent_config()
        assert a is b

    def test_get_agent_config_cache_clear_and_recreate(self):
        first = get_agent_config()
        get_agent_config.cache_clear()
        second = get_agent_config()
        assert first is not second


# ---------------------------------------------------------------------------
# ToolConfig lookups
# ---------------------------------------------------------------------------

class TestToolConfigLookup:
    def test_get_tool_config_known_tool(self):
        tc = get_tool_config("semgrep_scan")
        assert isinstance(tc, ToolConfig)
        assert tc.name == "semgrep_scan"
        assert tc.fallback_tool == "pattern_match"
        assert tc.timeout_seconds == 120

    def test_get_tool_config_unknown_tool(self):
        tc = get_tool_config("nonexistent_tool_xyz")
        assert isinstance(tc, ToolConfig)
        assert tc.name == "nonexistent_tool_xyz"
        assert tc.timeout_seconds == 60  # default tool_timeout_seconds
        assert tc.max_retries == 2       # default tool_max_retries


# ---------------------------------------------------------------------------
# AgentTypeConfig lookups
# ---------------------------------------------------------------------------

class TestAgentTypeConfigLookup:
    def test_get_agent_type_config_orchestrator(self):
        atc = get_agent_type_config("orchestrator")
        assert isinstance(atc, AgentTypeConfig)
        assert atc.agent_type == "orchestrator"
        assert atc.max_iterations == 20
        assert "think" in atc.tools
        assert "dispatch_agent" in atc.tools

    def test_get_agent_type_config_unknown(self):
        atc = get_agent_type_config("unknown_agent")
        assert isinstance(atc, AgentTypeConfig)
        assert atc.agent_type == "unknown_agent"
        # Fallback uses analysis_max_iterations = 30
        assert atc.max_iterations == 30


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    def test_validate_config_default_warnings(self):
        warnings = validate_config()
        # Default config should not produce high-retry or high-iteration warnings
        assert isinstance(warnings, list)
        # Default config has log_llm_prompts=False and log_llm_responses=False,
        # circuit breaker and checkpoint enabled, so warnings should be empty
        assert len(warnings) == 0

    def test_validate_config_high_retries_warning(self):
        config = AgentConfig(llm_max_retries=10)
        with patch("app.services.agent.config.get_agent_config", return_value=config):
            warnings = validate_config()
            assert any("llm_max_retries" in w for w in warnings)


# ---------------------------------------------------------------------------
# apply_testing_preset
# ---------------------------------------------------------------------------

class TestApplyTestingPreset:
    def test_apply_testing_preset(self):
        # Clear any pre-existing AGENT_ env vars to ensure setdefault applies
        env_vars_to_clean = [
            "AGENT_LLM_TIMEOUT_SECONDS",
            "AGENT_TOOL_TIMEOUT_SECONDS",
            "AGENT_ORCHESTRATOR_MAX_ITERATIONS",
            "AGENT_ANALYSIS_MAX_ITERATIONS",
            "AGENT_CIRCUIT_BREAKER_ENABLED",
        ]
        original_env = {}
        for var in env_vars_to_clean:
            if var in os.environ:
                original_env[var] = os.environ.pop(var)

        try:
            apply_testing_preset()
            config = get_agent_config()
            assert config.llm_timeout_seconds == 30
            assert config.tool_timeout_seconds == 10
            assert config.orchestrator_max_iterations == 5
            assert config.analysis_max_iterations == 10
            assert config.circuit_breaker_enabled is False
        finally:
            # Restore original env
            for var in env_vars_to_clean:
                if var in os.environ:
                    del os.environ[var]
            for var, val in original_env.items():
                os.environ[var] = val
            get_agent_config.cache_clear()
