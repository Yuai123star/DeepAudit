"""
Tests for app.services.llm.tokenizer module.

Covers:
- TokenEstimator.count_tokens with tiktoken (mocked) and heuristic fallback
- _heuristic_estimate for ASCII, CJK, mixed, empty, single-char inputs
- estimate_messages_tokens for single/multiple/multimodal messages
- Module-level state reset between tests
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.llm.tokenizer import (
    TokenEstimator,
    _check_tiktoken_availability,
)


# Shortcut for readability
_heuristic_estimate = TokenEstimator._heuristic_estimate


# ---------------------------------------------------------------------------
# Fixtures – reset module-level state between tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_module_state():
    """Reset module-level globals so tests don't leak state."""
    import app.services.llm.tokenizer as mod

    original_available = mod._tiktoken_available
    original_logged = mod._logged_method
    original_encoders = mod._encoders.copy()

    yield

    mod._tiktoken_available = original_available
    mod._logged_method = original_logged
    mod._encoders.clear()
    mod._encoders.update(original_encoders)


@pytest.fixture()
def force_tiktoken_unavailable():
    """Force the heuristic path by marking tiktoken as unavailable and patching _get_tiktoken_encoder."""
    import app.services.llm.tokenizer as mod

    mod._tiktoken_available = False
    mod._logged_method = True
    mod._encoders.clear()
    with patch("app.services.llm.tokenizer._get_tiktoken_encoder", return_value=None):
        yield


@pytest.fixture()
def force_tiktoken_available():
    """Force tiktoken path with a mocked encoder."""
    import app.services.llm.tokenizer as mod

    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = list(range(7))  # 7 tokens

    mod._tiktoken_available = True
    mod._logged_method = True
    mod._encoders["gpt-4"] = mock_encoder
    yield mock_encoder


# ---------------------------------------------------------------------------
# _heuristic_estimate
# ---------------------------------------------------------------------------

class TestHeuristicEstimate:
    """Tests for the pure heuristic estimation function."""

    def test_empty_string(self):
        assert _heuristic_estimate("") == 0

    def test_single_ascii_char(self):
        # 1 ascii char / 4 = 0.25, rounded up to at least 1
        assert _heuristic_estimate("a") == 1

    def test_pure_ascii_text(self):
        # "Hello World" = 11 ascii chars => 11/4 = 2.75 => int(2.75+0.5)=3
        text = "Hello World"
        result = _heuristic_estimate(text)
        expected_tokens = max(1, int(len(text) / 4.0 + 0.5))
        assert result == expected_tokens

    def test_pure_cjk_text(self):
        # 6 CJK characters => 6/1.5 = 4.0 => int(4.0+0.5)=4
        text = "\u4f60\u597d\u4e16\u754c\u4f60\u597d"  # 你好世界你好
        result = _heuristic_estimate(text)
        expected_tokens = max(1, int(len(text) / 1.5 + 0.5))
        assert result == expected_tokens

    def test_mixed_ascii_and_cjk(self):
        # "Hello你好" = 5 ascii + 2 CJK => 5/4 + 2/1.5 = 1.25 + 1.33 = 2.58 => int(3.08)=3
        text = "Hello\u4f60\u597d"
        result = _heuristic_estimate(text)
        ascii_count = 5
        cjk_count = 2
        tokens = ascii_count / 4.0 + cjk_count / 1.5
        assert result == max(1, int(tokens + 0.5))

    def test_cjk_punctuation_counted_as_cjk(self):
        # CJK punctuation range 0x3000-0x303F should be counted as CJK
        text = "\u3001\u3002"  # 、。
        result = _heuristic_estimate(text)
        assert result == max(1, int(2 / 1.5 + 0.5))

    def test_fullwidth_chars_counted_as_cjk(self):
        # Fullwidth range 0xFF00-0xFFEF
        text = "\uff01\uff1f"  # ！？
        result = _heuristic_estimate(text)
        assert result == max(1, int(2 / 1.5 + 0.5))

    def test_other_unicode(self):
        # Emoji / other unicode falls into "other" bucket => chars/2
        text = "\U0001f600\U0001f601"  # 2 emoji
        result = _heuristic_estimate(text)
        assert result == max(1, int(2 / 2.0 + 0.5))


# ---------------------------------------------------------------------------
# TokenEstimator.count_tokens
# ---------------------------------------------------------------------------

class TestCountTokens:

    def test_empty_text_returns_zero(self, force_tiktoken_available):
        result = TokenEstimator.count_tokens("", model="gpt-4")
        assert result == 0

    def test_tiktoken_path(self, force_tiktoken_available):
        """When tiktoken is available and encoder exists, use it."""
        result = TokenEstimator.count_tokens("Hello world", model="gpt-4")
        force_tiktoken_available.encode.assert_called_once_with("Hello world")
        assert result == 7  # mocked to return list of length 7

    def test_heuristic_fallback_when_unavailable(self, force_tiktoken_unavailable):
        """When tiktoken is unavailable, falls back to heuristic."""
        text = "Hello World"
        result = TokenEstimator.count_tokens(text, model="gpt-4")
        expected = _heuristic_estimate(text)
        assert result == expected

    def test_heuristic_fallback_on_encode_failure(self):
        """When tiktoken encoder exists but encode() throws, fall back to heuristic."""
        import app.services.llm.tokenizer as mod

        mock_encoder = MagicMock()
        mock_encoder.encode.side_effect = RuntimeError("encode failure")
        mod._tiktoken_available = True
        mod._logged_method = True
        mod._encoders["gpt-4"] = mock_encoder

        text = "Some text"
        result = TokenEstimator.count_tokens(text, model="gpt-4")
        assert result == _heuristic_estimate(text)

    def test_encoder_caching(self):
        """Verify encoder is cached after first retrieval."""
        import app.services.llm.tokenizer as mod

        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1, 2, 3]
        mod._tiktoken_available = True
        mod._logged_method = True
        mod._encoders.clear()

        with patch("app.services.llm.tokenizer._get_tiktoken_encoder", return_value=mock_encoder) as mock_get:
            TokenEstimator.count_tokens("test", model="gpt-4-new")
            TokenEstimator.count_tokens("test again", model="gpt-4-new")
            # _get_tiktoken_encoder is called twice (no caching at this level;
            # caching happens inside _get_tiktoken_encoder via _encoders dict)
            assert mock_get.call_count == 2


# ---------------------------------------------------------------------------
# TokenEstimator.estimate_messages_tokens
# ---------------------------------------------------------------------------

class TestEstimateMessagesTokens:

    def test_empty_list(self, force_tiktoken_unavailable):
        """Empty message list should return just the overhead (3 tokens)."""
        result = TokenEstimator.estimate_messages_tokens([])
        assert result == 3  # only overhead

    def test_single_message(self, force_tiktoken_unavailable):
        """Single message = 4 (per-msg overhead) + token count of content + 3 (list overhead)."""
        text = "Hello"
        messages = [{"role": "user", "content": text}]
        result = TokenEstimator.estimate_messages_tokens(messages)
        expected = 4 + _heuristic_estimate(text) + 3
        assert result == expected

    def test_multiple_messages(self, force_tiktoken_unavailable):
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        result = TokenEstimator.estimate_messages_tokens(messages)
        expected = (
            4 + _heuristic_estimate("You are helpful.")
            + 4 + _heuristic_estimate("Hi")
            + 3
        )
        assert result == expected

    def test_multimodal_content_blocks(self, force_tiktoken_unavailable):
        """Messages with list content (multimodal) should only count text parts."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image", "url": "https://example.com/img.png"},
                ],
            }
        ]
        result = TokenEstimator.estimate_messages_tokens(messages)
        # Only the text block is counted
        expected = 4 + _heuristic_estimate("Describe this image") + 3
        assert result == expected

    def test_message_with_empty_content(self, force_tiktoken_unavailable):
        messages = [{"role": "user", "content": ""}]
        result = TokenEstimator.estimate_messages_tokens(messages)
        # "" returns 0 tokens from count_tokens
        expected = 4 + 0 + 3
        assert result == expected


# ---------------------------------------------------------------------------
# _check_tiktoken_availability
# ---------------------------------------------------------------------------

class TestCheckTiktokenAvailability:

    def test_returns_cached_true(self):
        import app.services.llm.tokenizer as mod
        mod._tiktoken_available = True
        assert _check_tiktoken_availability() is True

    def test_returns_cached_false(self):
        import app.services.llm.tokenizer as mod
        mod._tiktoken_available = False
        assert _check_tiktoken_availability() is False

    def test_detects_import_error(self):
        """When tiktoken import fails, availability should be False."""
        import app.services.llm.tokenizer as mod
        mod._tiktoken_available = None
        mod._logged_method = False

        with patch.dict("sys.modules", {"tiktoken": None}):
            # Force re-check by making tiktoken unavailable via import failure
            with patch("builtins.__import__", side_effect=ImportError("no tiktoken")):
                result = _check_tiktoken_availability(log_result=False)
        assert result is False
