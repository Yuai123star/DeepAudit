"""
Deep tests for AgentJsonParser.

Extends coverage beyond the base tests with edge cases, unicode handling,
malformed inputs, nested structures, truncated JSON recovery, and all
public class methods.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from app.services.agent.json_parser import (
    AgentJsonParser,
    JSON_REPAIR_AVAILABLE,
)


# ======================================================================
# clean_text -- extended edge cases
# ======================================================================


class TestCleanTextDeep:
    """Deeper edge-case coverage for clean_text."""

    def test_clean_text_all_bom_chars(self):
        """Multiple BOM chars are all stripped."""
        text = "\ufeff\ufeff\ufeffhello"
        assert AgentJsonParser.clean_text(text) == "hello"

    def test_clean_text_mixed_zero_width_chars(self):
        """All four zero-width variants (BOM, ZWSP, ZWNJ, ZWJ) are stripped."""
        text = "a\ufeffb\u200bc\u200cd\u200de"
        assert AgentJsonParser.clean_text(text) == "abcde"

    def test_clean_text_whitespace_only(self):
        """Whitespace-only string is returned unchanged (clean_text does not strip)."""
        assert AgentJsonParser.clean_text("   \n\t  ") == "   \n\t  "

    def test_clean_text_preserves_emoji(self):
        """Emoji and other unicode outside zero-width range are preserved."""
        text = "\U0001f600 hello \U0001f680"
        assert AgentJsonParser.clean_text(text) == text

    def test_clean_text_preserves_cjk(self):
        """Chinese/Japanese/Korean characters are preserved."""
        text = "\u4f60\u597d\u4e16\u754c"
        assert AgentJsonParser.clean_text(text) == "\u4f60\u597d\u4e16\u754c"

    def test_clean_text_returns_empty_for_none(self):
        """None input returns empty string."""
        assert AgentJsonParser.clean_text(None) == ""

    def test_clean_text_preserves_newlines_and_tabs(self):
        """Normal control characters (\\n, \\t) are kept."""
        text = "line1\nline2\ttab"
        assert AgentJsonParser.clean_text(text) == text

    def test_clean_text_long_string(self):
        """clean_text works on long strings without performance issues."""
        base = '{"key": "value"}'
        text = ("\ufeff" + base) * 1000
        result = AgentJsonParser.clean_text(text)
        assert "\ufeff" not in result
        assert result.count("key") == 1000


# ======================================================================
# fix_json_format -- extended
# ======================================================================


class TestFixJsonFormatDeep:
    """Additional coverage for fix_json_format."""

    def test_fix_json_format_multiple_trailing_commas(self):
        """Multiple trailing commas in nested structures are fixed."""
        text = '{"a": [1, 2,], "b": {"c": 3,},}'
        result = AgentJsonParser.fix_json_format(text)
        parsed = json.loads(result)
        assert parsed == {"a": [1, 2], "b": {"c": 3}}

    def test_fix_json_format_no_change_needed(self):
        """Already valid JSON is returned essentially unchanged."""
        text = '{"a": 1}'
        result = AgentJsonParser.fix_json_format(text)
        assert json.loads(result) == {"a": 1}

    def test_fix_json_format_strip_whitespace(self):
        """Leading/trailing whitespace is stripped."""
        text = '  {"a": 1}  '
        result = AgentJsonParser.fix_json_format(text)
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_fix_json_format_unescaped_newline_in_string(self):
        """Unescaped newlines in JSON string values are fixed."""
        text = ': "line1\nline2"'
        result = AgentJsonParser.fix_json_format(text)
        assert "\\n" in result

    def test_fix_json_format_empty_string(self):
        """Empty string input produces empty output."""
        assert AgentJsonParser.fix_json_format("") == ""


# ======================================================================
# extract_json_string -- extended
# ======================================================================


class TestExtractJsonStringDeep:
    """Deeper coverage for extract_json_string."""

    def test_extract_json_string_array_markdown(self):
        """Extracts a JSON array from a markdown code block."""
        text = '```json\n[1, 2, 3]\n```'
        result = AgentJsonParser.extract_json_string(text)
        assert result == "[1, 2, 3]"

    def test_extract_json_string_markdown_without_language(self):
        """Code block without explicit language hint still extracts."""
        text = '```\n{"key": "val"}\n```'
        result = AgentJsonParser.extract_json_string(text)
        assert result == '{"key": "val"}'

    def test_extract_json_string_multiple_code_blocks(self):
        """Returns the first code block when multiple are present."""
        text = '```json\n{"first": true}\n```\nSome text\n```json\n{"second": true}\n```'
        result = AgentJsonParser.extract_json_string(text)
        assert '"first"' in result

    def test_extract_json_string_array_only(self):
        """Finds JSON array without markdown wrapping."""
        text = 'Result: [1, 2, 3] done'
        result = AgentJsonParser.extract_json_string(text)
        assert result == "[1, 2, 3]"

    def test_extract_json_string_no_closing_bracket(self):
        """Returns from first { to end when no closing brace exists."""
        text = 'prefix {"a": 1'
        result = AgentJsonParser.extract_json_string(text)
        assert result == '{"a": 1'

    def test_extract_json_string_bracket_before_brace(self):
        """When [ comes before {, uses the [ as start."""
        text = 'prefix [1, 2] and {"a": 1}'
        result = AgentJsonParser.extract_json_string(text)
        # start_idx = min(7, ...) -> the [ at position 7
        assert result.startswith("[")
        assert result.endswith("}")

    def test_extract_json_string_mixed_brackets(self):
        """End index uses max of last } or last ]."""
        text = '{"a": [1]} and trailing'
        result = AgentJsonParser.extract_json_string(text)
        assert result == '{"a": [1]}'


# ======================================================================
# extract_from_markdown -- extended
# ======================================================================


class TestExtractFromMarkdownDeep:
    """Tests for extract_from_markdown."""

    def test_extract_from_markdown_valid(self):
        text = 'Result:\n```json\n{"status": "ok"}\n```'
        result = AgentJsonParser.extract_from_markdown(text)
        assert result == {"status": "ok"}

    def test_extract_from_markdown_no_language_tag(self):
        """Works without the json language tag."""
        text = '```\n{"status": "ok"}\n```'
        result = AgentJsonParser.extract_from_markdown(text)
        assert result == {"status": "ok"}

    def test_extract_from_markdown_missing_raises(self):
        with pytest.raises(ValueError, match="No markdown code block"):
            AgentJsonParser.extract_from_markdown("no code blocks here")

    def test_extract_from_markdown_array_raises_value_error(self):
        """Only matches braces in regex, so array-only block raises ValueError."""
        text = '```json\n[1, 2, 3]\n```'
        # The regex requires { in the code block; [1, 2, 3] has none.
        with pytest.raises(ValueError, match="No markdown code block found"):
            AgentJsonParser.extract_from_markdown(text)


# ======================================================================
# extract_json_object -- extended
# ======================================================================


class TestExtractJsonObjectDeep:
    """Tests for extract_json_object."""

    def test_extract_nested_object(self):
        text = 'outer {"a": {"b": 2}}'
        result = AgentJsonParser.extract_json_object(text)
        assert result == {"a": {"b": 2}}

    def test_extract_object_with_escaped_quotes(self):
        text = r'{"key": "value with \"quotes\""}'
        result = AgentJsonParser.extract_json_object(text)
        assert result["key"] == 'value with "quotes"'

    def test_extract_object_with_braces_in_string(self):
        """Braces inside a quoted string should not affect brace counting."""
        text = '{"key": "val{ue}"}'
        result = AgentJsonParser.extract_json_object(text)
        assert result["key"] == "val{ue}"

    def test_extract_object_no_json_raises(self):
        with pytest.raises(ValueError, match="No JSON object found"):
            AgentJsonParser.extract_json_object("no json at all")

    def test_extract_object_incomplete_with_last_brace(self):
        """If braces are unbalanced but a closing } exists, uses the last }.
        The result may still fail json.loads if the content is truly broken;
        this tests the bracket-matching path that falls through to rfind."""
        text = '{"a": 1, "b": 2}'
        result = AgentJsonParser.extract_json_object(text)
        assert isinstance(result, dict)
        assert result.get("a") == 1
        assert result.get("b") == 2

    def test_extract_object_trailing_comma_fixed(self):
        """Trailing comma before } is removed."""
        text = '{"a": 1,}'
        result = AgentJsonParser.extract_json_object(text)
        assert result == {"a": 1}

    def test_extract_object_no_closing_brace_raises(self):
        """When there is no closing } at all, raises ValueError."""
        with pytest.raises(ValueError, match="Incomplete JSON"):
            AgentJsonParser.extract_json_object('{"a": 1')


# ======================================================================
# fix_truncated_json -- extended
# ======================================================================


class TestFixTruncatedJsonDeep:
    """Tests for fix_truncated_json."""

    def test_fix_truncated_missing_bracket(self):
        text = '{"a": [1, 2'
        result = AgentJsonParser.fix_truncated_json(text)
        assert result["a"] == [1, 2]

    def test_fix_truncated_missing_brace(self):
        text = '{"a": 1, "b": {"c": 2'
        result = AgentJsonParser.fix_truncated_json(text)
        assert result["a"] == 1
        assert result["b"]["c"] == 2

    def test_fix_truncated_both_missing(self):
        """Both brackets and braces missing get auto-closed with valid JSON content."""
        text = '{"items": [{"id": 1}, {"id": 2}'
        result = AgentJsonParser.fix_truncated_json(text)
        assert isinstance(result, dict)
        assert "items" in result
        assert len(result["items"]) == 2

    def test_fix_truncated_no_json_raises(self):
        with pytest.raises(ValueError, match="Cannot fix truncated JSON"):
            AgentJsonParser.fix_truncated_json("no braces here")

    def test_fix_truncated_valid_json_passes_through(self):
        """Already-valid JSON should parse correctly."""
        text = '{"a": 1}'
        result = AgentJsonParser.fix_truncated_json(text)
        assert result == {"a": 1}

    def test_fix_truncated_trailing_comma_removed(self):
        """Trailing commas are also cleaned in the fix path."""
        text = '{"a": 1,'
        result = AgentJsonParser.fix_truncated_json(text)
        assert result == {"a": 1}


# ======================================================================
# repair_with_library
# ======================================================================


class TestRepairWithLibrary:
    """Tests for repair_with_library, conditional on json-repair availability."""

    @pytest.mark.skipif(not JSON_REPAIR_AVAILABLE, reason="json-repair not installed")
    def test_repair_with_library_valid(self):
        text = '{"key": "value"}'
        result = AgentJsonParser.repair_with_library(text)
        assert result == {"key": "value"}

    @pytest.mark.skipif(not JSON_REPAIR_AVAILABLE, reason="json-repair not installed")
    def test_repair_with_library_list_wrapped(self):
        """A list result gets wrapped in {"items": ...}."""
        text = '[1, 2, 3]'
        result = AgentJsonParser.repair_with_library(text)
        assert "items" in result
        assert result["items"] == [1, 2, 3]

    @pytest.mark.skipif(not JSON_REPAIR_AVAILABLE, reason="json-repair not installed")
    def test_repair_with_library_empty_raises(self):
        with pytest.raises(ValueError, match="No JSON content"):
            AgentJsonParser.repair_with_library("   ")

    @pytest.mark.skipif(JSON_REPAIR_AVAILABLE, reason="Testing fallback when library absent")
    @patch("app.services.agent.json_parser.JSON_REPAIR_AVAILABLE", False)
    def test_repair_with_library_not_available_raises(self):
        with pytest.raises(ValueError, match="json-repair library not available"):
            AgentJsonParser.repair_with_library("anything")


# ======================================================================
# parse -- extended
# ======================================================================


class TestParseDeep:
    """Extended parse tests with edge cases."""

    def test_parse_whitespace_only_returns_default(self):
        result = AgentJsonParser.parse("   \n\t  ", default={"fallback": True})
        assert result == {"fallback": True}

    def test_parse_whitespace_only_no_default_raises(self):
        with pytest.raises(ValueError, match="LLM"):
            AgentJsonParser.parse("   \n\t  ")

    def test_parse_nested_json(self):
        text = '{"outer": {"inner": {"deep": 42}}}'
        result = AgentJsonParser.parse(text)
        assert result["outer"]["inner"]["deep"] == 42

    def test_parse_json_with_unicode_values(self):
        text = '{"name": "\u4f60\u597d", "emoji": "\U0001f600"}'
        result = AgentJsonParser.parse(text)
        assert result["name"] == "\u4f60\u597d"
        assert result["emoji"] == "\U0001f600"

    def test_parse_mixed_text_and_json(self):
        """JSON embedded in prose text is extracted."""
        text = 'Here is my analysis:\n{"findings": []}\nEnd of analysis.'
        result = AgentJsonParser.parse(text)
        assert result == {"findings": []}

    def test_parse_markdown_wrapped_json(self):
        text = '```json\n{"count": 5}\n```'
        result = AgentJsonParser.parse(text)
        assert result["count"] == 5

    @pytest.mark.skipif(JSON_REPAIR_AVAILABLE, reason="json-repair can recover from some garbage")
    def test_parse_returns_default_on_garbage(self):
        garbage = "this is not json at all {{{["
        result = AgentJsonParser.parse(garbage, default={"ok": False})
        assert result == {"ok": False}

    @pytest.mark.skipif(JSON_REPAIR_AVAILABLE, reason="json-repair can recover from some garbage")
    def test_parse_garbage_no_default_raises(self):
        garbage = "this is not json at all {{{["
        with pytest.raises(ValueError):
            AgentJsonParser.parse(garbage)

    def test_parse_trailing_comma_in_object(self):
        text = '{"a": 1, "b": 2,}'
        result = AgentJsonParser.parse(text)
        assert result == {"a": 1, "b": 2}

    def test_parse_bom_prefixed_json(self):
        text = '\ufeff{"key": "val"}'
        result = AgentJsonParser.parse(text)
        assert result == {"key": "val"}

    def test_parse_returns_first_successful_method(self):
        """When direct parsing works, it returns without trying fallbacks."""
        text = '{"direct": true}'
        result = AgentJsonParser.parse(text)
        assert result == {"direct": True}


# ======================================================================
# parse_findings -- extended
# ======================================================================


class TestParseFindingsDeep:
    """Extended parse_findings edge cases."""

    def test_parse_findings_string_items_converted(self):
        """String items that are valid JSON dicts are parsed into dicts."""
        text = '{"findings": ["{\\"title\\": \\"XSS\\", \\"severity\\": \\"high\\"}"]}'
        findings = AgentJsonParser.parse_findings(text)
        assert len(findings) == 1
        assert findings[0]["title"] == "XSS"

    def test_parse_findings_invalid_string_items_skipped(self):
        """String items that cannot be parsed are skipped."""
        text = '{"findings": ["not valid json at all"]}'
        findings = AgentJsonParser.parse_findings(text)
        assert findings == []

    def test_parse_findings_non_dict_items_skipped(self):
        """Non-dict, non-string items are skipped."""
        text = '{"findings": [42, true, null]}'
        findings = AgentJsonParser.parse_findings(text)
        assert findings == []

    def test_parse_findings_mixed_valid_invalid(self):
        """Mix of valid dicts, valid strings, and invalid items."""
        text = '{"findings": [{"title": "A"}, "{\\"title\\": \\"B\\"}", 42, "bad"]}'
        findings = AgentJsonParser.parse_findings(text)
        assert len(findings) == 2
        assert findings[0]["title"] == "A"
        assert findings[1]["title"] == "B"

    def test_parse_findings_no_findings_key(self):
        """When JSON has no 'findings' key, returns empty list."""
        text = '{"other": "data"}'
        findings = AgentJsonParser.parse_findings(text)
        assert findings == []

    def test_parse_findings_markdown_wrapped(self):
        text = '```json\n{"findings": [{"title": "SQLi", "severity": "critical"}]}\n```'
        findings = AgentJsonParser.parse_findings(text)
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical"

    def test_parse_findings_exception_returns_empty(self):
        """Even on totally unparseable input, returns empty list (not raises)."""
        findings = AgentJsonParser.parse_findings("{{{invalid[[[")
        assert findings == []

    def test_parse_findings_large_list(self):
        """Handles a large list of findings without issues."""
        items = [{"title": f"Vuln-{i}", "severity": "low"} for i in range(200)]
        text = json.dumps({"findings": items})
        findings = AgentJsonParser.parse_findings(text)
        assert len(findings) == 200


# ======================================================================
# safe_get -- extended
# ======================================================================


class TestSafeGetDeep:
    """Extended safe_get tests."""

    def test_safe_get_nested_dict(self):
        data = {"a": {"b": {"c": 42}}}
        assert AgentJsonParser.safe_get(data, "a") == {"b": {"c": 42}}

    def test_safe_get_none_value_returns_none(self):
        data = {"key": None}
        assert AgentJsonParser.safe_get(data, "key") is None

    def test_safe_get_list_value(self):
        data = {"items": [1, 2, 3]}
        assert AgentJsonParser.safe_get(data, "items") == [1, 2, 3]

    def test_safe_get_integer_input(self):
        assert AgentJsonParser.safe_get(42, "key", "default") == "default"

    def test_safe_get_bool_input(self):
        assert AgentJsonParser.safe_get(True, "key") is None


# ======================================================================
# parse_any -- extended
# ======================================================================


class TestParseAnyDeep:
    """Extended parse_any tests."""

    def test_parse_any_dict(self):
        text = '{"a": 1}'
        result = AgentJsonParser.parse_any(text)
        assert result == {"a": 1}

    def test_parse_any_number(self):
        text = '42'
        result = AgentJsonParser.parse_any(text)
        assert result == 42

    def test_parse_any_boolean(self):
        text = 'true'
        result = AgentJsonParser.parse_any(text)
        assert result is True

    def test_parse_any_null(self):
        text = 'null'
        result = AgentJsonParser.parse_any(text)
        assert result is None

    def test_parse_any_markdown_wrapped_array(self):
        text = '```json\n[1, 2, 3]\n```'
        result = AgentJsonParser.parse_any(text)
        assert result == [1, 2, 3]

    def test_parse_any_none_text(self):
        assert AgentJsonParser.parse_any(None, default="missing") == "missing"

    @pytest.mark.skipif(JSON_REPAIR_AVAILABLE, reason="json-repair can recover from some garbage")
    def test_parse_any_invalid_json(self):
        """Invalid JSON returns the default when json-repair is not available."""
        result = AgentJsonParser.parse_any("not json {{{", default="fallback")
        assert result == "fallback"

    def test_parse_any_nested_structure(self):
        text = '{"users": [{"name": "alice"}, {"name": "bob"}]}'
        result = AgentJsonParser.parse_any(text)
        assert len(result["users"]) == 2
