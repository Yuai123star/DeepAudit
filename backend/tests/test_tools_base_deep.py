"""
Deep tests for Agent Tool base module.

Covers ToolResult (dataclass), AgentTool (ABC), execute with timing/error
handling, get_langchain_tool conversion, and tool stats tracking.
Uses a concrete subclass for testing the abstract base class.
"""

import asyncio
import json
import time
from typing import Optional, Type
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.services.agent.tools.base import AgentTool, ToolResult


# ======================================================================
# Concrete test tool implementation
# ======================================================================


class DummyArgsSchema(BaseModel):
    """Pydantic schema for tool args."""
    query: str
    limit: int = 10


class DummyTool(AgentTool):
    """Concrete tool for testing the abstract AgentTool."""

    def __init__(self, *, should_fail=False, result_data=None, delay=0):
        super().__init__()
        self._should_fail = should_fail
        self._result_data = result_data or {"ok": True}
        self._delay = delay

    @property
    def name(self) -> str:
        return "dummy_tool"

    @property
    def description(self) -> str:
        return "A dummy tool for testing purposes"

    @property
    def args_schema(self) -> Optional[Type[BaseModel]]:
        return DummyArgsSchema

    async def _execute(self, **kwargs) -> ToolResult:
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._should_fail:
            raise RuntimeError("Intentional failure")
        return ToolResult(success=True, data=self._result_data)


class MinimalTool(AgentTool):
    """Tool with no args_schema for testing the Tool path in get_langchain_tool."""

    @property
    def name(self) -> str:
        return "minimal_tool"

    @property
    def description(self) -> str:
        return "Minimal tool"

    @property
    def args_schema(self) -> Optional[Type[BaseModel]]:
        return None

    async def _execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, data="done")


# ======================================================================
# ToolResult tests
# ======================================================================


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_defaults(self):
        result = ToolResult(success=True)
        assert result.success is True
        assert result.data is None
        assert result.error is None
        assert result.duration_ms == 0
        assert result.metadata == {}

    def test_with_all_fields(self):
        result = ToolResult(
            success=False,
            data="error info",
            error="something went wrong",
            duration_ms=500,
            metadata={"retries": 3},
        )
        assert result.success is False
        assert result.data == "error info"
        assert result.error == "something went wrong"
        assert result.duration_ms == 500
        assert result.metadata["retries"] == 3

    def test_to_dict(self):
        result = ToolResult(
            success=True,
            data={"key": "val"},
            duration_ms=100,
            metadata={"source": "test"},
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["data"] == {"key": "val"}
        assert d["duration_ms"] == 100
        assert d["metadata"]["source"] == "test"
        assert d["error"] is None

    def test_to_string_success_string_data(self):
        result = ToolResult(success=True, data="hello world")
        assert result.to_string() == "hello world"

    def test_to_string_success_dict_data(self):
        result = ToolResult(success=True, data={"a": 1})
        s = result.to_string()
        parsed = json.loads(s)
        assert parsed == {"a": 1}

    def test_to_string_success_list_data(self):
        result = ToolResult(success=True, data=[1, 2, 3])
        s = result.to_string()
        parsed = json.loads(s)
        assert parsed == [1, 2, 3]

    def test_to_string_success_non_serializable(self):
        """Non-string, non-dict/list data uses str()."""
        result = ToolResult(success=True, data=42)
        assert result.to_string() == "42"

    def test_to_string_error(self):
        result = ToolResult(success=False, error="boom")
        assert result.to_string() == "Error: boom"

    def test_to_string_truncation(self):
        """Long output is truncated to max_length."""
        long_data = "x" * 10000
        result = ToolResult(success=True, data=long_data)
        output = result.to_string(max_length=100)
        assert len(output) < 200  # includes truncation suffix
        assert "truncated" in output

    def test_to_string_custom_max_length(self):
        result = ToolResult(success=True, data="x" * 5000)
        output = result.to_string(max_length=50)
        assert len(output) < 150
        assert "truncated" in output

    def test_to_string_unicode(self):
        result = ToolResult(success=True, data="\u4f60\u597d\u4e16\u754c")
        s = result.to_string()
        assert "\u4f60\u597d" in s


# ======================================================================
# AgentTool -- initialization
# ======================================================================


class TestAgentToolInit:
    """Tests for AgentTool initialization."""

    def test_initial_counters(self):
        tool = DummyTool()
        assert tool._call_count == 0
        assert tool._total_duration_ms == 0

    def test_name_property(self):
        tool = DummyTool()
        assert tool.name == "dummy_tool"

    def test_description_property(self):
        tool = DummyTool()
        assert tool.description == "A dummy tool for testing purposes"

    def test_args_schema_property(self):
        tool = DummyTool()
        assert tool.args_schema is DummyArgsSchema

    def test_args_schema_none(self):
        tool = MinimalTool()
        assert tool.args_schema is None


# ======================================================================
# AgentTool -- execute
# ======================================================================


class TestAgentToolExecute:
    """Tests for AgentTool.execute (timing, error handling, stats)."""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        tool = DummyTool(result_data={"count": 42})
        result = await tool.execute(query="test", limit=5)
        assert result.success is True
        assert result.data == {"count": 42}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_sets_duration(self):
        tool = DummyTool(delay=0.05)
        result = await tool.execute(query="test")
        assert result.duration_ms >= 40  # at least 50ms minus margin

    @pytest.mark.asyncio
    async def test_execute_updates_stats(self):
        tool = DummyTool()
        assert tool._call_count == 0

        await tool.execute(query="first")
        assert tool._call_count == 1

        await tool.execute(query="second")
        assert tool._call_count == 2

    @pytest.mark.asyncio
    async def test_execute_captures_exception(self):
        tool = DummyTool(should_fail=True)
        result = await tool.execute(query="test")
        assert result.success is False
        assert "Intentional failure" in result.error
        assert isinstance(result.duration_ms, int)

    @pytest.mark.asyncio
    async def test_execute_exception_still_updates_stats(self):
        """Even when _execute raises, call_count is incremented."""
        tool = DummyTool(should_fail=True)
        await tool.execute(query="test")
        assert tool._call_count == 1

    @pytest.mark.asyncio
    async def test_stats_property(self):
        tool = DummyTool()
        await tool.execute(query="test1")
        await tool.execute(query="test2")

        stats = tool.stats
        assert stats["name"] == "dummy_tool"
        assert stats["call_count"] == 2
        assert "total_duration_ms" in stats
        assert "avg_duration_ms" in stats

    @pytest.mark.asyncio
    async def test_stats_avg_duration_no_division_by_zero(self):
        """When no calls, avg_duration_ms should be 0 (not crash)."""
        tool = DummyTool()
        stats = tool.stats
        assert stats["avg_duration_ms"] == 0

    @pytest.mark.asyncio
    async def test_execute_no_args(self):
        """Execute with no arguments works if _execute doesn't need them."""
        tool = MinimalTool()
        result = await tool.execute()
        assert result.success is True
        assert result.data == "done"


# ======================================================================
# AgentTool -- get_langchain_tool
# ======================================================================


class TestAgentToolLangchain:
    """Tests for get_langchain_tool conversion.

    These tests are conditional on langchain.tools having the expected
    import path. If the langchain version changes, the source module's
    get_langchain_tool would need to change too.
    """

    def test_structured_tool_with_schema(self):
        """When args_schema is set, returns a StructuredTool."""
        tool = DummyTool()
        try:
            lc_tool = tool.get_langchain_tool()
        except ImportError:
            pytest.skip("langchain.tools.Tool/StructuredTool not importable")
        # StructuredTool has args_schema attribute
        assert hasattr(lc_tool, "args_schema")

    def test_tool_without_schema(self):
        """When args_schema is None, returns a basic Tool."""
        tool = MinimalTool()
        try:
            lc_tool = tool.get_langchain_tool()
        except ImportError:
            pytest.skip("langchain.tools.Tool not importable")
        assert lc_tool.name == "minimal_tool"
        assert lc_tool.description == "Minimal tool"

    def test_langchain_tool_name_matches(self):
        tool = DummyTool()
        try:
            lc_tool = tool.get_langchain_tool()
        except ImportError:
            pytest.skip("langchain.tools not importable")
        assert lc_tool.name == "dummy_tool"

    def test_langchain_tool_description_matches(self):
        tool = DummyTool()
        try:
            lc_tool = tool.get_langchain_tool()
        except ImportError:
            pytest.skip("langchain.tools not importable")
        assert lc_tool.description == "A dummy tool for testing purposes"


# ======================================================================
# AgentTool -- multiple executions and stats accumulation
# ======================================================================


class TestAgentToolMultipleExecutions:
    """Tests for accumulated stats over multiple executions."""

    @pytest.mark.asyncio
    async def test_total_duration_accumulates(self):
        tool = DummyTool(delay=0.01)
        await tool.execute(query="a")
        first_total = tool._total_duration_ms

        await tool.execute(query="b")
        assert tool._total_duration_ms >= first_total

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure_stats(self):
        tool = DummyTool()
        # Success
        await tool.execute(query="ok")
        # Failure
        fail_tool = DummyTool(should_fail=True)
        fail_tool._call_count = 0
        fail_tool._total_duration_ms = 0
        await fail_tool.execute(query="fail")

        assert tool._call_count == 1
        assert fail_tool._call_count == 1

    @pytest.mark.asyncio
    async def test_independent_tools_have_independent_stats(self):
        tool1 = DummyTool()
        tool2 = DummyTool()

        await tool1.execute(query="t1")
        await tool1.execute(query="t1")
        await tool2.execute(query="t2")

        assert tool1.stats["call_count"] == 2
        assert tool2.stats["call_count"] == 1
