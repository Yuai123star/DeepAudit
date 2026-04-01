"""
Tests for AgentJsonParser.

Covers text cleaning, JSON format fixing, extraction from markdown/bare text,
multi-strategy parsing, findings parsing, safe_get, and parse_any.
"""

import pytest
from app.services.agent.json_parser import AgentJsonParser


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------

class TestCleanText:
    def test_clean_text_removes_bom(self):
        text = "\ufeff{\"key\": \"value\"}"
        result = AgentJsonParser.clean_text(text)
        assert "\ufeff" not in result
        assert result == '{"key": "value"}'

    def test_clean_text_removes_zero_width(self):
        text = "hello\u200bworld\u200ctest\u200d"
        result = AgentJsonParser.clean_text(text)
        assert result == "helloworldtest"

    def test_clean_text_empty_string(self):
        assert AgentJsonParser.clean_text("") == ""
        assert AgentJsonParser.clean_text(None) == ""


# ---------------------------------------------------------------------------
# fix_json_format
# ---------------------------------------------------------------------------

class TestFixJsonFormat:
    def test_fix_json_format_trailing_comma_object(self):
        text = '{"a": 1,}'
        result = AgentJsonParser.fix_json_format(text)
        import json
        parsed = json.loads(result)
        assert parsed == {"a": 1}

    def test_fix_json_format_trailing_comma_array(self):
        text = '[1, 2,]'
        result = AgentJsonParser.fix_json_format(text)
        import json
        parsed = json.loads(result)
        assert parsed == [1, 2]


# ---------------------------------------------------------------------------
# extract_json_string
# ---------------------------------------------------------------------------

class TestExtractJsonString:
    def test_extract_json_string_markdown_code_block(self):
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        result = AgentJsonParser.extract_json_string(text)
        assert result == '{"key": "value"}'

    def test_extract_json_string_bare_braces(self):
        text = 'Some preamble text {"key": "value"} trailing text'
        result = AgentJsonParser.extract_json_string(text)
        assert result == '{"key": "value"}'

    def test_extract_json_string_no_json(self):
        text = "no json here at all"
        result = AgentJsonParser.extract_json_string(text)
        assert result == text


# ---------------------------------------------------------------------------
# parse
# ---------------------------------------------------------------------------

class TestParse:
    def test_parse_valid_json(self):
        result = AgentJsonParser.parse('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_json_in_markdown(self):
        text = '```json\n{"status": "ok", "count": 42}\n```'
        result = AgentJsonParser.parse(text)
        assert result["status"] == "ok"
        assert result["count"] == 42

    def test_parse_empty_text_returns_default(self):
        result = AgentJsonParser.parse("", default={})
        assert result == {}

    def test_parse_empty_text_no_default_raises(self):
        with pytest.raises(ValueError):
            AgentJsonParser.parse("")

    def test_parse_truncated_json(self):
        # Truncated JSON: missing closing brackets and braces
        truncated = '{"a": 1, "b": [1, 2'
        result = AgentJsonParser.parse(truncated, default=None)
        assert isinstance(result, dict)
        assert result.get("a") == 1


# ---------------------------------------------------------------------------
# parse_findings
# ---------------------------------------------------------------------------

class TestParseFindings:
    def test_parse_findings_valid(self):
        text = '{"findings": [{"title": "SQL Injection", "severity": "high"}, {"title": "XSS", "severity": "medium"}]}'
        findings = AgentJsonParser.parse_findings(text)
        assert len(findings) == 2
        assert findings[0]["title"] == "SQL Injection"
        assert findings[1]["severity"] == "medium"

    def test_parse_findings_empty_returns_empty_list(self):
        findings = AgentJsonParser.parse_findings("")
        assert findings == []


# ---------------------------------------------------------------------------
# safe_get
# ---------------------------------------------------------------------------

class TestSafeGet:
    def test_safe_get_dict(self):
        data = {"key": "value", "num": 42}
        assert AgentJsonParser.safe_get(data, "key") == "value"
        assert AgentJsonParser.safe_get(data, "num") == 42
        assert AgentJsonParser.safe_get(data, "missing", "fallback") == "fallback"

    def test_safe_get_non_dict_returns_default(self):
        assert AgentJsonParser.safe_get("not a dict", "key") is None
        assert AgentJsonParser.safe_get([1, 2, 3], "key", "default") == "default"
        assert AgentJsonParser.safe_get(None, "key", 0) == 0


# ---------------------------------------------------------------------------
# parse_any
# ---------------------------------------------------------------------------

class TestParseAny:
    def test_parse_any_list(self):
        text = '[1, 2, 3]'
        result = AgentJsonParser.parse_any(text)
        assert result == [1, 2, 3]

    def test_parse_any_empty_returns_default(self):
        assert AgentJsonParser.parse_any("", default="nothing") == "nothing"

    def test_parse_any_string_value(self):
        text = '"hello"'
        result = AgentJsonParser.parse_any(text)
        assert result == "hello"
