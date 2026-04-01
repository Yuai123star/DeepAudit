"""
Tests for app.services.llm.prompt_cache module.

Covers:
- CacheConfig defaults and custom values
- CacheStats properties (hit_rate, token_savings, division-by-zero guards)
- PromptCacheManager.supports_caching (Anthropic vs OpenAI vs unknown)
- PromptCacheManager.determine_strategy (NONE, SYSTEM_ONLY, SYSTEM_AND_EARLY, MULTI_POINT)
- PromptCacheManager.add_cache_markers_anthropic (system, early, multi-point marking)
- PromptCacheManager._add_cache_to_message (string->list, existing list mutation)
- PromptCacheManager.process_messages (end-to-end)
- PromptCacheManager.update_stats + get_stats_summary
"""

import pytest
from unittest.mock import patch

from app.services.llm.prompt_cache import (
    CacheConfig,
    CacheStrategy,
    CacheStats,
    PromptCacheManager,
)


# ---------------------------------------------------------------------------
# CacheConfig
# ---------------------------------------------------------------------------

class TestCacheConfig:

    def test_defaults(self):
        cfg = CacheConfig()
        assert cfg.enabled is True
        assert cfg.strategy == CacheStrategy.SYSTEM_AND_EARLY
        assert cfg.min_system_prompt_tokens == 1000
        assert cfg.early_messages_count == 5
        assert cfg.multi_point_interval == 10
        assert cfg.max_cache_points == 4

    def test_custom_values(self):
        cfg = CacheConfig(
            enabled=False,
            strategy=CacheStrategy.MULTI_POINT,
            min_system_prompt_tokens=500,
            early_messages_count=3,
            multi_point_interval=5,
            max_cache_points=2,
        )
        assert cfg.enabled is False
        assert cfg.strategy == CacheStrategy.MULTI_POINT
        assert cfg.min_system_prompt_tokens == 500
        assert cfg.early_messages_count == 3
        assert cfg.multi_point_interval == 5
        assert cfg.max_cache_points == 2


# ---------------------------------------------------------------------------
# CacheStats
# ---------------------------------------------------------------------------

class TestCacheStats:

    def test_hit_rate_with_hits(self):
        stats = CacheStats(cache_hits=8, cache_misses=2)
        assert stats.hit_rate == 0.8

    def test_hit_rate_zero_total(self):
        """Division by zero guard: no hits and no misses => 0.0."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_token_savings_with_tokens(self):
        stats = CacheStats(cached_tokens=500, total_tokens=1000)
        assert stats.token_savings == 0.5

    def test_token_savings_zero_total(self):
        """Division by zero guard: no total tokens => 0.0."""
        stats = CacheStats()
        assert stats.token_savings == 0.0


# ---------------------------------------------------------------------------
# PromptCacheManager.supports_caching
# ---------------------------------------------------------------------------

class TestSupportsCaching:

    def test_anthropic_claude_model(self):
        mgr = PromptCacheManager()
        assert mgr.supports_caching("claude-3-5-sonnet", "anthropic") is True

    def test_anthropic_provider_case_insensitive(self):
        mgr = PromptCacheManager()
        assert mgr.supports_caching("claude-3-opus", "Anthropic") is True
        assert mgr.supports_caching("claude-3-haiku", "Claude") is True

    def test_openai_model_not_supported(self):
        mgr = PromptCacheManager()
        assert mgr.supports_caching("gpt-4-turbo", "openai") is False

    def test_gpt4o_not_supported(self):
        mgr = PromptCacheManager()
        assert mgr.supports_caching("gpt-4o", "openai") is False

    def test_unknown_model_returns_false(self):
        mgr = PromptCacheManager()
        assert mgr.supports_caching("some-random-model", "anthropic") is False

    def test_disabled_config_returns_false(self):
        mgr = PromptCacheManager(config=CacheConfig(enabled=False))
        assert mgr.supports_caching("claude-3-5-sonnet", "anthropic") is False


# ---------------------------------------------------------------------------
# PromptCacheManager.determine_strategy
# ---------------------------------------------------------------------------

class TestDetermineStrategy:

    def test_disabled_returns_none(self):
        mgr = PromptCacheManager(config=CacheConfig(enabled=False))
        assert mgr.determine_strategy([], system_prompt_tokens=5000) == CacheStrategy.NONE

    def test_low_system_tokens_returns_none(self):
        """system_prompt_tokens < min_system_prompt_tokens (1000) => NONE."""
        mgr = PromptCacheManager()
        assert mgr.determine_strategy([], system_prompt_tokens=500) == CacheStrategy.NONE

    def test_short_conversation_system_only(self):
        """< 10 messages => SYSTEM_ONLY."""
        mgr = PromptCacheManager()
        msgs = [{"role": "user", "content": "hi"}] * 5
        assert mgr.determine_strategy(msgs, system_prompt_tokens=1500) == CacheStrategy.SYSTEM_ONLY

    def test_medium_conversation_system_and_early(self):
        """10-29 messages => SYSTEM_AND_EARLY."""
        mgr = PromptCacheManager()
        msgs = [{"role": "user", "content": "hi"}] * 15
        assert mgr.determine_strategy(msgs, system_prompt_tokens=1500) == CacheStrategy.SYSTEM_AND_EARLY

    def test_long_conversation_multi_point(self):
        """>= 30 messages => MULTI_POINT."""
        mgr = PromptCacheManager()
        msgs = [{"role": "user", "content": "hi"}] * 30
        assert mgr.determine_strategy(msgs, system_prompt_tokens=1500) == CacheStrategy.MULTI_POINT

    def test_exact_boundary_10_messages(self):
        """Exactly 10 messages => SYSTEM_AND_EARLY."""
        mgr = PromptCacheManager()
        msgs = [{"role": "user", "content": "hi"}] * 10
        assert mgr.determine_strategy(msgs, system_prompt_tokens=1500) == CacheStrategy.SYSTEM_AND_EARLY

    def test_exact_boundary_30_messages(self):
        """Exactly 30 messages => MULTI_POINT."""
        mgr = PromptCacheManager()
        msgs = [{"role": "user", "content": "hi"}] * 30
        assert mgr.determine_strategy(msgs, system_prompt_tokens=1500) == CacheStrategy.MULTI_POINT


# ---------------------------------------------------------------------------
# PromptCacheManager._add_cache_to_message
# ---------------------------------------------------------------------------

class TestAddCacheToMessage:

    def test_string_content_converted_to_list(self):
        mgr = PromptCacheManager()
        msg = {"role": "system", "content": "You are helpful."}
        result = mgr._add_cache_to_message(msg)
        assert isinstance(result["content"], list)
        assert len(result["content"]) == 1
        block = result["content"][0]
        assert block["type"] == "text"
        assert block["text"] == "You are helpful."
        assert block["cache_control"] == {"type": "ephemeral"}

    def test_existing_list_content_last_block_mutated(self):
        mgr = PromptCacheManager()
        msg = {
            "role": "system",
            "content": [
                {"type": "text", "text": "Part 1"},
                {"type": "text", "text": "Part 2"},
            ],
        }
        result = mgr._add_cache_to_message(msg)
        assert len(result["content"]) == 2
        # Last block gets cache_control
        assert result["content"][-1]["cache_control"] == {"type": "ephemeral"}
        # First block should NOT have cache_control
        assert "cache_control" not in result["content"][0]

    def test_empty_list_content_no_crash(self):
        mgr = PromptCacheManager()
        msg = {"role": "system", "content": []}
        result = mgr._add_cache_to_message(msg)
        assert result["content"] == []


# ---------------------------------------------------------------------------
# PromptCacheManager.add_cache_markers_anthropic
# ---------------------------------------------------------------------------

class TestAddCacheMarkersAnthropic:

    def test_none_strategy_returns_original(self):
        mgr = PromptCacheManager()
        msgs = [{"role": "user", "content": "hi"}]
        result = mgr.add_cache_markers_anthropic(msgs, CacheStrategy.NONE)
        assert result == msgs

    def test_system_only_marks_system_message(self):
        mgr = PromptCacheManager()
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        result = mgr.add_cache_markers_anthropic(msgs, CacheStrategy.SYSTEM_ONLY)
        # Only the system message should have cache_control
        assert isinstance(result[0]["content"], list)  # system msg converted
        assert result[0]["content"][0]["cache_control"] == {"type": "ephemeral"}
        # User and assistant messages should remain strings
        assert isinstance(result[1]["content"], str)
        assert isinstance(result[2]["content"], str)

    def test_system_and_early_marks_early_messages(self):
        mgr = PromptCacheManager(config=CacheConfig(early_messages_count=2))
        msgs = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
            {"role": "user", "content": "msg3"},
        ]
        result = mgr.add_cache_markers_anthropic(msgs, CacheStrategy.SYSTEM_AND_EARLY)
        # system (index 0), user (index 1), assistant (index 2) should be marked
        # msg at index 3 should NOT be marked (i > early_messages_count=2)
        for i in range(3):
            content = result[i]["content"]
            if isinstance(content, list):
                assert content[0].get("cache_control") is not None or content[-1].get("cache_control") is not None
        # Index 3 should be unmodified (string)
        assert isinstance(result[3]["content"], str)

    def test_multi_point_adds_interval_markers(self):
        mgr = PromptCacheManager(config=CacheConfig(
            early_messages_count=1,
            multi_point_interval=2,
            max_cache_points=4,
        ))
        # Build 10 messages
        msgs = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = mgr.add_cache_markers_anthropic(msgs, CacheStrategy.MULTI_POINT)
        # At index 2,4,6,8 => multi-point markers (i % interval == 0)
        # At index 0,1 => early message markers (i <= early_messages_count)
        marked_indices = set()
        for i, m in enumerate(result):
            content = m["content"]
            if isinstance(content, list):
                if isinstance(content[-1], dict) and "cache_control" in content[-1]:
                    marked_indices.add(i)
                elif isinstance(content[0], dict) and "cache_control" in content[0]:
                    marked_indices.add(i)
        # Early: 0,1 and multi-point: 2,4,6,8 should be marked
        assert 0 in marked_indices
        assert 1 in marked_indices
        assert 2 in marked_indices
        assert 4 in marked_indices
        assert 8 in marked_indices


# ---------------------------------------------------------------------------
# PromptCacheManager.process_messages
# ---------------------------------------------------------------------------

class TestProcessMessages:

    def test_unsupported_model_returns_unmodified(self):
        mgr = PromptCacheManager()
        msgs = [{"role": "user", "content": "hi"}]
        result, cached = mgr.process_messages(msgs, "gpt-4o", "openai", system_prompt_tokens=1500)
        assert result == msgs
        assert cached is False

    def test_anthropic_model_with_caching(self):
        mgr = PromptCacheManager()
        msgs = [
            {"role": "system", "content": "A" * 2000},
            {"role": "user", "content": "Hello"},
        ]
        result, cached = mgr.process_messages(msgs, "claude-3-5-sonnet", "anthropic", system_prompt_tokens=2000)
        assert cached is True
        assert isinstance(result[0]["content"], list)

    def test_low_tokens_returns_false(self):
        mgr = PromptCacheManager()
        msgs = [{"role": "system", "content": "short"}]
        result, cached = mgr.process_messages(msgs, "claude-3-5-sonnet", "anthropic", system_prompt_tokens=100)
        assert cached is False
        assert result == msgs


# ---------------------------------------------------------------------------
# PromptCacheManager.update_stats + get_stats_summary
# ---------------------------------------------------------------------------

class TestStats:

    def test_cache_hit(self):
        mgr = PromptCacheManager()
        mgr.update_stats(cache_read_input_tokens=500, total_input_tokens=1000)
        assert mgr.stats.cache_hits == 1
        assert mgr.stats.cached_tokens == 500
        assert mgr.stats.total_tokens == 1000

    def test_cache_miss(self):
        mgr = PromptCacheManager()
        mgr.update_stats(total_input_tokens=800)
        assert mgr.stats.cache_misses == 1
        assert mgr.stats.cache_hits == 0

    def test_mixed_hits_and_misses(self):
        mgr = PromptCacheManager()
        mgr.update_stats(cache_read_input_tokens=500, total_input_tokens=1000)
        mgr.update_stats(total_input_tokens=800)
        mgr.update_stats(cache_read_input_tokens=200, total_input_tokens=400)
        assert mgr.stats.cache_hits == 2
        assert mgr.stats.cache_misses == 1
        assert mgr.stats.cached_tokens == 700
        assert mgr.stats.total_tokens == 2200

    def test_get_stats_summary(self):
        mgr = PromptCacheManager()
        mgr.update_stats(cache_read_input_tokens=500, total_input_tokens=1000)
        summary = mgr.get_stats_summary()
        assert summary["cache_hits"] == 1
        assert summary["cache_misses"] == 0
        assert summary["hit_rate"] == "100.00%"
        assert summary["cached_tokens"] == 500
        assert summary["total_tokens"] == 1000
        assert summary["token_savings"] == "50.00%"

    def test_get_stats_summary_no_data(self):
        mgr = PromptCacheManager()
        summary = mgr.get_stats_summary()
        assert summary["hit_rate"] == "0.00%"
        assert summary["token_savings"] == "0.00%"
