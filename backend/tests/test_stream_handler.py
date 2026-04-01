"""
Tests for Stream Handler module.

Tests StreamEventType, StreamEvent, and StreamHandler at
app.services.agent.streaming.stream_handler.
"""

import json
from unittest.mock import patch

import pytest

from app.services.agent.streaming.stream_handler import (
    StreamEvent,
    StreamEventType,
    StreamHandler,
)


# ============ StreamEventType Tests ============


class TestStreamEventType:
    """Tests for StreamEventType enum."""

    def test_is_string_enum(self):
        assert isinstance(StreamEventType.LLM_START, str)
        assert StreamEventType.LLM_START == "llm_start"

    def test_all_event_type_values(self):
        expected = {
            "llm_start",
            "llm_thought",
            "llm_decision",
            "llm_action",
            "llm_observation",
            "llm_complete",
            "thinking_start",
            "thinking_token",
            "thinking_end",
            "tool_call_start",
            "tool_call_input",
            "tool_call_output",
            "tool_call_end",
            "tool_call_error",
            "node_start",
            "node_end",
            "phase_start",
            "phase_end",
            "finding_new",
            "finding_verified",
            "progress",
            "info",
            "warning",
            "error",
            "task_start",
            "task_complete",
            "task_error",
            "task_cancel",
            "heartbeat",
        }
        actual = {member.value for member in StreamEventType}
        assert actual == expected

    def test_total_member_count(self):
        assert len(StreamEventType) == 29


# ============ StreamEvent Tests ============


class TestStreamEvent:
    """Tests for StreamEvent dataclass."""

    def test_defaults(self):
        evt = StreamEvent(event_type=StreamEventType.HEARTBEAT)
        assert evt.event_type == StreamEventType.HEARTBEAT
        assert evt.data == {}
        assert evt.sequence == 0
        assert evt.node_name is None
        assert evt.phase is None
        assert evt.tool_name is None

    def test_to_dict_returns_expected_keys(self):
        evt = StreamEvent(
            event_type=StreamEventType.PROGRESS,
            data={"current": 5, "total": 10},
            sequence=42,
        )
        result = evt.to_dict()
        assert result["event_type"] == "progress"
        assert result["data"] == {"current": 5, "total": 10}
        assert result["sequence"] == 42
        assert result["node_name"] is None
        assert result["phase"] is None
        assert result["tool_name"] is None

    def test_to_dict_with_all_optional_fields(self):
        evt = StreamEvent(
            event_type=StreamEventType.TOOL_CALL_START,
            data={"tool_name": "semgrep"},
            sequence=7,
            node_name="AnalysisNode",
            phase="analysis",
            tool_name="semgrep",
        )
        result = evt.to_dict()
        assert result["node_name"] == "AnalysisNode"
        assert result["phase"] == "analysis"
        assert result["tool_name"] == "semgrep"

    def test_to_sse_format(self):
        evt = StreamEvent(
            event_type=StreamEventType.HEARTBEAT,
            data={"msg": "ping"},
            sequence=1,
        )
        sse = evt.to_sse()
        assert sse.startswith("event: heartbeat\ndata: ")
        assert sse.endswith("\n\n")
        payload_str = sse.split("data: ", 1)[1].rstrip("\n")
        payload = json.loads(payload_str)
        assert payload["type"] == "heartbeat"
        assert payload["sequence"] == 1
        assert payload["data"] == {"msg": "ping"}

    def test_to_sse_includes_optional_node(self):
        evt = StreamEvent(
            event_type=StreamEventType.NODE_START,
            data={},
            sequence=3,
            node_name="ReconNode",
            phase="reconnaissance",
        )
        sse = evt.to_sse()
        payload_str = sse.split("data: ", 1)[1].rstrip("\n")
        payload = json.loads(payload_str)
        assert payload["node"] == "ReconNode"
        assert payload["phase"] == "reconnaissance"

    def test_to_sse_omits_optional_when_none(self):
        evt = StreamEvent(event_type=StreamEventType.INFO, data={}, sequence=0)
        sse = evt.to_sse()
        payload_str = sse.split("data: ", 1)[1].rstrip("\n")
        payload = json.loads(payload_str)
        assert "node" not in payload
        assert "phase" not in payload
        assert "tool" not in payload

    def test_to_sse_includes_tool(self):
        evt = StreamEvent(
            event_type=StreamEventType.TOOL_CALL_END,
            data={},
            sequence=5,
            tool_name="bandit",
        )
        sse = evt.to_sse()
        payload_str = sse.split("data: ", 1)[1].rstrip("\n")
        payload = json.loads(payload_str)
        assert payload["tool"] == "bandit"

    def test_to_sse_unicode_safe(self):
        evt = StreamEvent(
            event_type=StreamEventType.INFO,
            data={"message": "发现漏洞"},
            sequence=1,
        )
        sse = evt.to_sse()
        assert "发现漏洞" in sse


# ============ StreamHandler.__init__ / sequence Tests ============


class TestStreamHandlerInit:
    """Tests for StreamHandler initialization and sequence numbering."""

    def test_initial_state(self):
        handler = StreamHandler(task_id="task-001")
        assert handler.task_id == "task-001"
        assert handler._sequence == 0
        assert handler._current_phase is None
        assert handler._current_node is None
        assert handler._thinking_buffer == []
        assert handler._tool_states == {}

    def test_next_sequence_increments(self):
        handler = StreamHandler(task_id="t1")
        assert handler._next_sequence() == 1
        assert handler._next_sequence() == 2
        assert handler._next_sequence() == 3


# ============ _is_node_event Tests ============


class TestIsNodeEvent:
    """Tests for StreamHandler._is_node_event."""

    def setup_method(self):
        self.handler = StreamHandler(task_id="t1")

    def test_exact_match_recon(self):
        assert self.handler._is_node_event("recon") is True

    def test_exact_match_AnalysisNode(self):
        assert self.handler._is_node_event("AnalysisNode") is True

    def test_case_insensitive(self):
        assert self.handler._is_node_event("RECON") is True
        assert self.handler._is_node_event("AnalysisNODE") is True

    def test_substring_match(self):
        assert self.handler._is_node_event("my_recon_node") is True
        assert self.handler._is_node_event("analysis_sub") is True

    def test_non_node_event(self):
        assert self.handler._is_node_event("ChatModel") is False
        assert self.handler._is_node_event("random_name") is False

    def test_empty_string(self):
        assert self.handler._is_node_event("") is False


# ============ _truncate_data Tests ============


class TestTruncateData:
    """Tests for StreamHandler._truncate_data."""

    def setup_method(self):
        self.handler = StreamHandler(task_id="t1")

    def test_short_string_unchanged(self):
        assert self.handler._truncate_data("hello", max_length=1000) == "hello"

    def test_long_string_truncated(self):
        long_str = "a" * 2000
        result = self.handler._truncate_data(long_str, max_length=1000)
        assert len(result) == 1003  # 1000 chars + "..."
        assert result.endswith("...")

    def test_dict_truncation_limits_items(self):
        big_dict = {f"k{i}": f"v{i}" for i in range(20)}
        result = self.handler._truncate_data(big_dict, max_length=100)
        assert len(result) <= 10  # DATA_DICT_ITEMS = 10

    def test_list_truncation_limits_items(self):
        big_list = [f"item{i}" for i in range(20)]
        result = self.handler._truncate_data(big_list, max_length=100)
        assert len(result) <= 10  # DATA_LIST_ITEMS = 10

    def test_non_string_type_converted(self):
        result = self.handler._truncate_data(12345, max_length=3)
        assert result == "123"

    def test_none_converted_to_string(self):
        result = self.handler._truncate_data(None, max_length=3)
        assert result == "Non"


# ============ create_progress_event Tests ============


class TestCreateProgressEvent:
    """Tests for StreamHandler.create_progress_event."""

    def setup_method(self):
        self.handler = StreamHandler(task_id="t1")

    def test_percentage_calculation(self):
        evt = self.handler.create_progress_event(current=5, total=10)
        assert evt.data["percentage"] == 50.0
        assert evt.data["current"] == 5
        assert evt.data["total"] == 10

    def test_zero_total_gives_zero_percentage(self):
        evt = self.handler.create_progress_event(current=5, total=0)
        assert evt.data["percentage"] == 0

    def test_custom_message(self):
        evt = self.handler.create_progress_event(current=1, total=10, message="Scanning")
        assert evt.data["message"] == "Scanning"

    def test_default_message(self):
        evt = self.handler.create_progress_event(current=3, total=10)
        assert "3/10" in evt.data["message"]

    def test_sequence_increments(self):
        self.handler._sequence = 0
        evt = self.handler.create_progress_event(current=1, total=10)
        assert evt.sequence == 1

    def test_full_progress_is_100(self):
        evt = self.handler.create_progress_event(current=10, total=10)
        assert evt.data["percentage"] == 100.0


# ============ create_finding_event Tests ============


class TestCreateFindingEvent:
    """Tests for StreamHandler.create_finding_event."""

    def setup_method(self):
        self.handler = StreamHandler(task_id="t1")

    def test_new_finding_type(self):
        finding = {"title": "SQL Injection", "severity": "high", "vulnerability_type": "sql_injection"}
        evt = self.handler.create_finding_event(finding, is_verified=False)
        assert evt.event_type == StreamEventType.FINDING_NEW

    def test_verified_finding_type(self):
        finding = {"title": "XSS", "severity": "critical"}
        evt = self.handler.create_finding_event(finding, is_verified=True)
        assert evt.event_type == StreamEventType.FINDING_VERIFIED

    def test_finding_data_fields(self):
        finding = {
            "title": "SQL Injection",
            "severity": "high",
            "vulnerability_type": "sql_injection",
            "file_path": "/app/db.py",
            "line_start": 42,
        }
        evt = self.handler.create_finding_event(finding, is_verified=False)
        assert evt.data["title"] == "SQL Injection"
        assert evt.data["severity"] == "high"
        assert evt.data["file_path"] == "/app/db.py"
        assert evt.data["line_start"] == 42
        assert evt.data["is_verified"] is False

    def test_finding_defaults_for_missing_keys(self):
        evt = self.handler.create_finding_event({}, is_verified=False)
        assert evt.data["title"] == "Unknown"
        assert evt.data["severity"] == "medium"
        assert evt.data["vulnerability_type"] == "other"

    def test_verified_message_contains_checkmark(self):
        finding = {"title": "Test", "severity": "low"}
        evt = self.handler.create_finding_event(finding, is_verified=True)
        assert "已验证" in evt.data["message"]

    def test_new_finding_message_format(self):
        finding = {"title": "TestVuln", "severity": "high"}
        evt = self.handler.create_finding_event(finding, is_verified=False)
        assert "HIGH" in evt.data["message"]
        assert "TestVuln" in evt.data["message"]


# ============ create_heartbeat Tests ============


class TestCreateHeartbeat:
    """Tests for StreamHandler.create_heartbeat."""

    def test_heartbeat_does_not_increment_sequence(self):
        handler = StreamHandler(task_id="t1")
        handler._sequence = 5
        evt = handler.create_heartbeat()
        assert evt.sequence == 5
        assert handler._sequence == 5

    def test_heartbeat_event_type(self):
        handler = StreamHandler(task_id="t1")
        evt = handler.create_heartbeat()
        assert evt.event_type == StreamEventType.HEARTBEAT

    def test_heartbeat_data(self):
        handler = StreamHandler(task_id="t1")
        evt = handler.create_heartbeat()
        assert evt.data["message"] == "ping"


# ============ process_langgraph_event Tests ============


class TestProcessLanggraphEvent:
    """Tests for StreamHandler.process_langgraph_event dispatch."""

    @pytest.fixture
    def handler(self):
        return StreamHandler(task_id="t1")

    @pytest.mark.asyncio
    async def test_unknown_event_returns_none(self, handler):
        result = await handler.process_langgraph_event({"event": "unknown_kind", "name": "x"})
        assert result is None

    @pytest.mark.asyncio
    async def test_non_node_chain_start_returns_none(self, handler):
        result = await handler.process_langgraph_event({
            "event": "on_chain_start",
            "name": "SomeRandomRunnable",
            "data": {},
        })
        assert result is None

    @pytest.mark.asyncio
    async def test_non_node_chain_end_returns_none(self, handler):
        result = await handler.process_langgraph_event({
            "event": "on_chain_end",
            "name": "SomeOtherRunnable",
            "data": {},
        })
        assert result is None


# ============ _handle_llm_start / stream / end Tests ============


class TestHandleLlmEvents:
    """Tests for LLM start/stream/end handling."""

    @pytest.fixture
    def handler(self):
        return StreamHandler(task_id="t1")

    @pytest.mark.asyncio
    async def test_llm_start_clears_buffer(self, handler):
        handler._thinking_buffer = ["old data"]
        await handler._handle_llm_start({}, "ChatModel")
        assert handler._thinking_buffer == []

    @pytest.mark.asyncio
    async def test_llm_start_returns_thinking_start(self, handler):
        evt = await handler._handle_llm_start({}, "ChatModel")
        assert evt.event_type == StreamEventType.THINKING_START
        assert evt.data["model"] == "ChatModel"

    @pytest.mark.asyncio
    async def test_llm_stream_with_chunk_object(self, handler):
        class FakeChunk:
            content = "hello"

        evt = await handler._handle_llm_stream({"chunk": FakeChunk()}, "model")
        assert evt is not None
        assert evt.event_type == StreamEventType.THINKING_TOKEN
        assert evt.data["token"] == "hello"
        assert evt.data["accumulated"] == "hello"

    @pytest.mark.asyncio
    async def test_llm_stream_with_dict_chunk(self, handler):
        evt = await handler._handle_llm_stream({"chunk": {"content": "world"}}, "model")
        assert evt is not None
        assert evt.data["token"] == "world"

    @pytest.mark.asyncio
    async def test_llm_stream_accumulates(self, handler):
        handler._thinking_buffer = ["hello "]
        await handler._handle_llm_stream({"chunk": {"content": "world"}}, "model")
        assert handler._thinking_buffer == ["hello ", "world"]

    @pytest.mark.asyncio
    async def test_llm_stream_no_chunk_returns_none(self, handler):
        result = await handler._handle_llm_stream({}, "model")
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_stream_empty_content_returns_none(self, handler):
        result = await handler._handle_llm_stream({"chunk": {"content": ""}}, "model")
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_end_returns_thinking_end(self, handler):
        handler._thinking_buffer = ["full ", "response"]
        evt = await handler._handle_llm_end({}, "model")
        assert evt.event_type == StreamEventType.THINKING_END
        assert evt.data["response"] == "full response"

    @pytest.mark.asyncio
    async def test_llm_end_clears_buffer(self, handler):
        handler._thinking_buffer = ["data"]
        await handler._handle_llm_end({}, "model")
        assert handler._thinking_buffer == []

    @pytest.mark.asyncio
    async def test_llm_end_extracts_usage_metadata(self, handler):
        handler._thinking_buffer = ["resp"]

        class UsageMeta:
            input_tokens = 100
            output_tokens = 50

        class FakeOutput:
            usage_metadata = UsageMeta()

        evt = await handler._handle_llm_end({"output": FakeOutput()}, "model")
        assert evt.data["usage"]["input_tokens"] == 100
        assert evt.data["usage"]["output_tokens"] == 50

    @pytest.mark.asyncio
    async def test_full_llm_lifecycle_via_process(self, handler):
        """Integration: start -> stream tokens -> end via process_langgraph_event."""
        # Start
        start_evt = await handler.process_langgraph_event({
            "event": "on_chat_model_start",
            "name": "ChatModel",
            "data": {},
        })
        assert start_evt.event_type == StreamEventType.THINKING_START

        # Stream
        token_evt = await handler.process_langgraph_event({
            "event": "on_chat_model_stream",
            "name": "ChatModel",
            "data": {"chunk": {"content": "thinking..."}},
        })
        assert token_evt.event_type == StreamEventType.THINKING_TOKEN
        assert token_evt.data["token"] == "thinking..."

        # End
        end_evt = await handler.process_langgraph_event({
            "event": "on_chat_model_end",
            "name": "ChatModel",
            "data": {},
        })
        assert end_evt.event_type == StreamEventType.THINKING_END
        assert end_evt.data["response"] == "thinking..."


# ============ _handle_tool_start / end Tests ============


class TestHandleToolEvents:
    """Tests for tool start/end handling."""

    @pytest.fixture
    def handler(self):
        return StreamHandler(task_id="t1")

    @pytest.mark.asyncio
    async def test_tool_start_returns_tool_call_start(self, handler):
        evt = await handler._handle_tool_start("semgrep", {"input": {"path": "/app"}})
        assert evt.event_type == StreamEventType.TOOL_CALL_START
        assert evt.tool_name == "semgrep"
        assert evt.data["tool_name"] == "semgrep"

    @pytest.mark.asyncio
    async def test_tool_start_records_state(self, handler):
        await handler._handle_tool_start("bandit", {"input": {"path": "/src"}})
        assert "bandit" in handler._tool_states
        assert handler._tool_states["bandit"]["input"] == {"path": "/src"}

    @pytest.mark.asyncio
    async def test_tool_end_returns_tool_call_end(self, handler):
        handler._tool_states["semgrep"] = {"start_time": 0}
        evt = await handler._handle_tool_end("semgrep", {"output": "done"})
        assert evt.event_type == StreamEventType.TOOL_CALL_END
        assert evt.data["tool_name"] == "semgrep"

    @pytest.mark.asyncio
    async def test_tool_end_clears_state(self, handler):
        handler._tool_states["semgrep"] = {"start_time": 0}
        await handler._handle_tool_end("semgrep", {"output": "done"})
        assert "semgrep" not in handler._tool_states

    @pytest.mark.asyncio
    async def test_tool_end_with_unknown_tool_zero_duration(self, handler):
        evt = await handler._handle_tool_end("unknown_tool", {"output": "x"})
        assert evt.data["duration_ms"] == 0

    @pytest.mark.asyncio
    async def test_tool_end_extracts_content_from_output_object(self, handler):
        class FakeOutput:
            content = "result text"

        handler._tool_states["t"] = {"start_time": 0}
        evt = await handler._handle_tool_end("t", {"output": FakeOutput()})
        assert evt.data["output"] == "result text"

    @pytest.mark.asyncio
    async def test_full_tool_lifecycle_via_process(self, handler):
        """Integration: tool start -> end via process_langgraph_event."""
        start_evt = await handler.process_langgraph_event({
            "event": "on_tool_start",
            "name": "semgrep",
            "data": {"input": {"path": "/app"}},
        })
        assert start_evt.event_type == StreamEventType.TOOL_CALL_START

        end_evt = await handler.process_langgraph_event({
            "event": "on_tool_end",
            "name": "semgrep",
            "data": {"output": "3 findings"},
        })
        assert end_evt.event_type == StreamEventType.TOOL_CALL_END


# ============ _handle_node_start / end Tests ============


class TestHandleNodeEvents:
    """Tests for node start/end handling."""

    @pytest.fixture
    def handler(self):
        return StreamHandler(task_id="t1")

    @pytest.mark.asyncio
    async def test_node_start_updates_current_node(self, handler):
        await handler._handle_node_start("ReconNode", {})
        assert handler._current_node == "ReconNode"

    @pytest.mark.asyncio
    async def test_node_start_maps_phase(self, handler):
        await handler._handle_node_start("AnalysisNode", {})
        assert handler._current_phase == "analysis"

    @pytest.mark.asyncio
    async def test_node_start_returns_node_start_event(self, handler):
        evt = await handler._handle_node_start("ReconNode", {})
        assert evt.event_type == StreamEventType.NODE_START
        assert evt.data["node"] == "ReconNode"
        assert evt.data["phase"] == "reconnaissance"

    @pytest.mark.asyncio
    async def test_node_end_extracts_findings_count(self, handler):
        output = {
            "findings": [{"id": 1}, {"id": 2}, {"id": 3}],
            "entry_points": ["/a", "/b"],
            "high_risk_areas": ["zone1"],
        }
        evt = await handler._handle_node_end("AnalysisNode", {"output": output})
        assert evt.event_type == StreamEventType.NODE_END
        assert evt.data["summary"]["findings_count"] == 3
        assert evt.data["summary"]["entry_points_count"] == 2
        assert evt.data["summary"]["high_risk_areas_count"] == 1

    @pytest.mark.asyncio
    async def test_node_end_extracts_verified_count(self, handler):
        output = {"verified_findings": [{"id": 1}, {"id": 2}]}
        evt = await handler._handle_node_end("VerificationNode", {"output": output})
        assert evt.data["summary"]["verified_count"] == 2

    @pytest.mark.asyncio
    async def test_node_end_empty_output_gives_empty_summary(self, handler):
        evt = await handler._handle_node_end("ReconNode", {"output": {}})
        assert evt.data["summary"] == {}

    @pytest.mark.asyncio
    async def test_node_end_non_dict_output_gives_empty_summary(self, handler):
        evt = await handler._handle_node_end("ReconNode", {"output": "string_output"})
        assert evt.data["summary"] == {}

    @pytest.mark.asyncio
    async def test_node_lifecycle_via_process(self, handler):
        """Integration: node start -> end via process_langgraph_event."""
        start_evt = await handler.process_langgraph_event({
            "event": "on_chain_start",
            "name": "ReconNode",
            "data": {},
        })
        assert start_evt.event_type == StreamEventType.NODE_START
        assert handler._current_node == "ReconNode"
        assert handler._current_phase == "reconnaissance"

        end_evt = await handler.process_langgraph_event({
            "event": "on_chain_end",
            "name": "ReconNode",
            "data": {"output": {"findings": []}},
        })
        assert end_evt.event_type == StreamEventType.NODE_END


# ============ _handle_custom_event Tests ============


class TestHandleCustomEvent:
    """Tests for custom event handling."""

    @pytest.fixture
    def handler(self):
        return StreamHandler(task_id="t1")

    @pytest.mark.asyncio
    async def test_finding_maps_to_finding_new(self, handler):
        evt = await handler._handle_custom_event("finding", {"title": "XSS"})
        assert evt.event_type == StreamEventType.FINDING_NEW

    @pytest.mark.asyncio
    async def test_finding_verified_maps(self, handler):
        evt = await handler._handle_custom_event("finding_verified", {"title": "SQLi"})
        assert evt.event_type == StreamEventType.FINDING_VERIFIED

    @pytest.mark.asyncio
    async def test_progress_maps(self, handler):
        evt = await handler._handle_custom_event("progress", {"pct": 50})
        assert evt.event_type == StreamEventType.PROGRESS

    @pytest.mark.asyncio
    async def test_warning_maps(self, handler):
        evt = await handler._handle_custom_event("warning", {"msg": "slow"})
        assert evt.event_type == StreamEventType.WARNING

    @pytest.mark.asyncio
    async def test_error_maps(self, handler):
        evt = await handler._handle_custom_event("error", {"msg": "fail"})
        assert evt.event_type == StreamEventType.ERROR

    @pytest.mark.asyncio
    async def test_unknown_name_maps_to_info(self, handler):
        evt = await handler._handle_custom_event("something_else", {"val": 1})
        assert evt.event_type == StreamEventType.INFO

    @pytest.mark.asyncio
    async def test_custom_event_via_process(self, handler):
        evt = await handler.process_langgraph_event({
            "event": "on_custom_event",
            "name": "progress",
            "data": {"current": 3},
        })
        assert evt.event_type == StreamEventType.PROGRESS
        assert evt.data["current"] == 3
