"""
Tests for Agent Event Manager module.

Tests AgentEventData, AgentEventEmitter, and EventManager at
app.services.agent.event_manager.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.event_manager import (
    AgentEventData,
    AgentEventEmitter,
    EventManager,
)


# ============ AgentEventData Tests ============


class TestAgentEventData:
    """Tests for AgentEventData dataclass."""

    def test_defaults(self):
        data = AgentEventData(event_type="test_event")
        assert data.event_type == "test_event"
        assert data.phase is None
        assert data.message is None
        assert data.tool_name is None
        assert data.tool_input is None
        assert data.tool_output is None
        assert data.tool_duration_ms is None
        assert data.finding_id is None
        assert data.tokens_used == 0
        assert data.metadata is None

    def test_with_all_fields(self):
        data = AgentEventData(
            event_type="tool_call",
            phase="analysis",
            message="Calling semgrep",
            tool_name="semgrep_scan",
            tool_input={"path": "/app"},
            tool_output={"results": []},
            tool_duration_ms=1500,
            finding_id="finding-123",
            tokens_used=50,
            metadata={"iteration": 3},
        )
        assert data.event_type == "tool_call"
        assert data.phase == "analysis"
        assert data.tool_name == "semgrep_scan"
        assert data.tool_duration_ms == 1500
        assert data.tokens_used == 50

    def test_to_dict(self):
        data = AgentEventData(
            event_type="thinking",
            message="Analyzing code",
            tokens_used=10,
        )
        d = data.to_dict()
        assert d["event_type"] == "thinking"
        assert d["message"] == "Analyzing code"
        assert d["tokens_used"] == 10
        assert d["phase"] is None
        assert d["tool_name"] is None
        assert d["metadata"] is None


# ============ AgentEventEmitter Tests ============


class TestAgentEventEmitterInit:
    """Tests for AgentEventEmitter initialization."""

    def test_initial_state(self):
        mock_manager = MagicMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)
        assert emitter.task_id == "task-1"
        assert emitter._sequence == 0
        assert emitter._current_phase is None


class TestAgentEventEmitterEmit:
    """Tests for the core emit method."""

    @pytest.mark.asyncio
    async def test_emit_increments_sequence(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        await emitter.emit(AgentEventData(event_type="test"))
        assert emitter._sequence == 1

        await emitter.emit(AgentEventData(event_type="test2"))
        assert emitter._sequence == 2

    @pytest.mark.asyncio
    async def test_emit_passes_correct_args(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-abc", event_manager=mock_manager)

        data = AgentEventData(event_type="thinking", message="hello")
        await emitter.emit(data)

        mock_manager.add_event.assert_called_once()
        call_kwargs = mock_manager.add_event.call_args
        assert call_kwargs.kwargs["task_id"] == "task-abc"
        assert call_kwargs.kwargs["sequence"] == 1
        assert call_kwargs.kwargs["event_type"] == "thinking"

    @pytest.mark.asyncio
    async def test_emit_sets_phase_from_current_phase(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        emitter._current_phase = "analysis"
        data = AgentEventData(event_type="thinking", message="hello")
        assert data.phase is None

        await emitter.emit(data)
        # The emit method sets phase from _current_phase if data.phase is None
        assert data.phase == "analysis"

    @pytest.mark.asyncio
    async def test_emit_does_not_override_explicit_phase(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        emitter._current_phase = "analysis"
        data = AgentEventData(event_type="test", phase="verification")
        await emitter.emit(data)
        assert data.phase == "verification"


class TestAgentEventEmitterPhaseMethods:
    """Tests for emit_phase_start and emit_phase_complete."""

    @pytest.mark.asyncio
    async def test_emit_phase_start_sets_current_phase(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        await emitter.emit_phase_start("reconnaissance", "Starting recon")
        assert emitter._current_phase == "reconnaissance"

        call_kwargs = mock_manager.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "phase_start"
        assert call_kwargs["phase"] == "reconnaissance"

    @pytest.mark.asyncio
    async def test_emit_phase_start_default_message(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        await emitter.emit_phase_start("analysis")
        call_kwargs = mock_manager.add_event.call_args.kwargs
        assert "analysis" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_emit_phase_complete(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        await emitter.emit_phase_complete("analysis", "Analysis done")
        call_kwargs = mock_manager.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "phase_complete"
        assert call_kwargs["phase"] == "analysis"
        assert call_kwargs["message"] == "Analysis done"


class TestAgentEventEmitterConvenience:
    """Tests for emit_thinking, emit_tool_call, emit_tool_result."""

    @pytest.mark.asyncio
    async def test_emit_thinking(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        await emitter.emit_thinking("I should check SQL injection", metadata={"step": 1})
        call_kwargs = mock_manager.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "thinking"
        assert call_kwargs["message"] == "I should check SQL injection"

    @pytest.mark.asyncio
    async def test_emit_tool_call(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        await emitter.emit_tool_call("semgrep_scan", {"path": "/app/src"})
        call_kwargs = mock_manager.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "tool_call"
        assert call_kwargs["tool_name"] == "semgrep_scan"

    @pytest.mark.asyncio
    async def test_emit_tool_result(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        await emitter.emit_tool_result("semgrep_scan", "scan output", 1500)
        call_kwargs = mock_manager.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "tool_result"
        assert call_kwargs["tool_name"] == "semgrep_scan"
        assert call_kwargs["tool_duration_ms"] == 1500

    @pytest.mark.asyncio
    async def test_emit_tool_result_string_output_serialized(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        await emitter.emit_tool_result("tool1", "plain text output", 100)
        call_kwargs = mock_manager.add_event.call_args.kwargs
        # String output should be wrapped in a dict
        assert isinstance(call_kwargs["tool_output"], dict)
        assert "result" in call_kwargs["tool_output"]


class TestAgentEventEmitterSequence:
    """Tests that sequence increments across different emit methods."""

    @pytest.mark.asyncio
    async def test_sequence_increments_across_methods(self):
        mock_manager = MagicMock()
        mock_manager.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="task-1", event_manager=mock_manager)

        await emitter.emit_thinking("step 1")
        assert emitter._sequence == 1

        await emitter.emit_tool_call("tool1", {})
        assert emitter._sequence == 2

        await emitter.emit_tool_result("tool1", "ok", 100)
        assert emitter._sequence == 3


# ============ EventManager Tests ============


class TestEventManager:
    """Tests for EventManager core functionality."""

    def test_create_queue(self):
        manager = EventManager()
        queue = manager.create_queue("task-1")
        assert isinstance(queue, asyncio.Queue)
        assert "task-1" in manager._event_queues

    def test_create_queue_idempotent(self):
        manager = EventManager()
        q1 = manager.create_queue("task-1")
        q2 = manager.create_queue("task-1")
        assert q1 is q2

    def test_remove_queue(self):
        manager = EventManager()
        manager.create_queue("task-1")
        manager.remove_queue("task-1")
        assert "task-1" not in manager._event_queues

    def test_remove_nonexistent_queue_no_error(self):
        manager = EventManager()
        # Should not raise
        manager.remove_queue("nonexistent")

    @pytest.mark.asyncio
    async def test_add_event_pushes_to_queue(self):
        manager = EventManager()
        queue = manager.create_queue("task-1")

        await manager.add_event(
            task_id="task-1",
            event_type="thinking",
            sequence=1,
            message="hello",
        )

        assert not queue.empty()
        event = queue.get_nowait()
        assert event["event_type"] == "thinking"
        assert event["message"] == "hello"

    @pytest.mark.asyncio
    async def test_add_event_without_queue_no_error(self):
        manager = EventManager()
        # No queue created for this task, should not raise
        event_id = await manager.add_event(
            task_id="task-no-queue",
            event_type="info",
            sequence=1,
        )
        assert event_id is not None

    @pytest.mark.asyncio
    async def test_add_event_calls_callback(self):
        manager = EventManager()
        callback = AsyncMock()
        manager.add_callback("task-1", callback)

        await manager.add_event(
            task_id="task-1",
            event_type="info",
            sequence=1,
            message="test",
        )

        callback.assert_called_once()
        event_data = callback.call_args.args[0]
        assert event_data["event_type"] == "info"
        assert event_data["message"] == "test"

    @pytest.mark.asyncio
    async def test_add_event_calls_sync_callback(self):
        manager = EventManager()
        sync_callback = MagicMock()
        manager.add_callback("task-1", sync_callback)

        await manager.add_event(
            task_id="task-1",
            event_type="info",
            sequence=1,
        )

        sync_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_emitter(self):
        manager = EventManager()
        emitter = manager.create_emitter("task-xyz")
        assert isinstance(emitter, AgentEventEmitter)
        assert emitter.task_id == "task-xyz"
        assert emitter.event_manager is manager

    def test_add_and_remove_callback(self):
        manager = EventManager()
        cb = MagicMock()
        manager.add_callback("task-1", cb)
        assert cb in manager._event_callbacks["task-1"]

        manager.remove_callback("task-1", cb)
        assert cb not in manager._event_callbacks["task-1"]

    @pytest.mark.asyncio
    async def test_close_clears_queues_and_callbacks(self):
        manager = EventManager()
        manager.create_queue("task-1")
        manager.create_queue("task-2")
        manager.add_callback("task-1", MagicMock())

        await manager.close()

        assert len(manager._event_queues) == 0
        assert len(manager._event_callbacks) == 0
