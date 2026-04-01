"""
Deep tests for Agent Event Manager.

Extends coverage of AgentEventData, AgentEventEmitter, and EventManager
with additional edge cases: phase tracking, LLM thought/decision/action
events, finding events, progress events, stream_events, DB persistence,
and error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.event_manager import (
    AgentEventData,
    AgentEventEmitter,
    EventManager,
)


# ======================================================================
# AgentEventData -- extended
# ======================================================================


class TestAgentEventDataDeep:
    """Extended AgentEventData tests."""

    def test_to_dict_all_fields_none(self):
        """to_dict works when all optional fields are None."""
        data = AgentEventData(event_type="test")
        d = data.to_dict()
        assert d["phase"] is None
        assert d["message"] is None
        assert d["tool_name"] is None
        assert d["tool_input"] is None
        assert d["tool_output"] is None
        assert d["tool_duration_ms"] is None
        assert d["finding_id"] is None
        assert d["tokens_used"] == 0
        assert d["metadata"] is None

    def test_to_dict_preserves_complex_metadata(self):
        data = AgentEventData(
            event_type="test",
            metadata={"nested": {"deep": [1, 2, 3]}, "flag": True},
        )
        d = data.to_dict()
        assert d["metadata"]["nested"]["deep"] == [1, 2, 3]
        assert d["metadata"]["flag"] is True

    def test_to_dict_preserves_tool_input(self):
        data = AgentEventData(
            event_type="tool_call",
            tool_input={"path": "/app/src", "recursive": True},
        )
        d = data.to_dict()
        assert d["tool_input"]["path"] == "/app/src"


# ======================================================================
# AgentEventEmitter -- phase tracking
# ======================================================================


class TestAgentEventEmitterPhaseTracking:
    """Tests for phase tracking through emit methods."""

    @pytest.mark.asyncio
    async def test_phase_start_updates_current_phase(self):
        """emit_phase_start updates _current_phase."""
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        assert emitter._current_phase is None
        await emitter.emit_phase_start("reconnaissance")
        assert emitter._current_phase == "reconnaissance"

    @pytest.mark.asyncio
    async def test_subsequent_emits_inherit_phase(self):
        """Events after phase_start inherit the current phase."""
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_phase_start("analysis")
        await emitter.emit_thinking("thinking...")

        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["phase"] == "analysis"

    @pytest.mark.asyncio
    async def test_phase_transitions(self):
        """Multiple phase_start calls update _current_phase each time."""
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        phases = ["reconnaissance", "analysis", "verification", "reporting"]
        for phase in phases:
            await emitter.emit_phase_start(phase)
            assert emitter._current_phase == phase

    @pytest.mark.asyncio
    async def test_phase_complete_default_message(self):
        """emit_phase_complete uses default message when none given."""
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_phase_complete("analysis")
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert "analysis" in call_kwargs["message"]


# ======================================================================
# AgentEventEmitter -- LLM thought/decision/action events
# ======================================================================


class TestAgentEventEmitterLLMEvents:
    """Tests for LLM-specific event methods."""

    @pytest.mark.asyncio
    async def test_emit_llm_thought_short(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_llm_thought("Short thought", iteration=5)
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "llm_thought"
        assert "Short thought" in call_kwargs["message"]
        assert call_kwargs["metadata"]["iteration"] == 5

    @pytest.mark.asyncio
    async def test_emit_llm_thought_long_truncated(self):
        """Long thoughts are truncated in the display message."""
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        long_thought = "x" * 1000
        await emitter.emit_llm_thought(long_thought)
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        # Display message should contain truncation marker
        assert "..." in call_kwargs["message"]
        # Full thought preserved in metadata
        assert call_kwargs["metadata"]["thought"] == long_thought

    @pytest.mark.asyncio
    async def test_emit_llm_decision_with_reason(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_llm_decision("scan_file", "found suspicious pattern")
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "llm_decision"
        assert "scan_file" in call_kwargs["message"]
        assert "found suspicious pattern" in call_kwargs["message"]
        assert call_kwargs["metadata"]["decision"] == "scan_file"
        assert call_kwargs["metadata"]["reason"] == "found suspicious pattern"

    @pytest.mark.asyncio
    async def test_emit_llm_decision_without_reason(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_llm_decision("proceed")
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert "(" not in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_emit_llm_action(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        action_input = {"path": "/src/app.py", "recursive": True}
        await emitter.emit_llm_action("read_file", action_input)
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "llm_action"
        assert "read_file" in call_kwargs["message"]
        assert call_kwargs["metadata"]["action"] == "read_file"
        assert call_kwargs["metadata"]["action_input"] == action_input


# ======================================================================
# AgentEventEmitter -- finding events
# ======================================================================


class TestAgentEventEmitterFindings:
    """Tests for finding-related events."""

    @pytest.mark.asyncio
    async def test_emit_finding_new(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_finding(
            finding_id="f-001",
            title="SQL Injection",
            severity="high",
            vulnerability_type="sql_injection",
        )
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "finding_new"
        assert call_kwargs["finding_id"] == "f-001"
        assert "HIGH" in call_kwargs["message"]
        assert "SQL Injection" in call_kwargs["message"]
        assert call_kwargs["metadata"]["is_verified"] is False

    @pytest.mark.asyncio
    async def test_emit_finding_verified(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_finding(
            finding_id="f-002",
            title="XSS",
            severity="critical",
            vulnerability_type="xss",
            is_verified=True,
        )
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "finding_verified"
        assert call_kwargs["metadata"]["is_verified"] is True

    @pytest.mark.asyncio
    async def test_emit_finding_metadata_has_id_field(self):
        """Metadata includes 'id' field for frontend use."""
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_finding("f-003", "Info Leak", "low", "sensitive_data_exposure")
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["metadata"]["id"] == "f-003"


# ======================================================================
# AgentEventEmitter -- info/warning/error/progress/task events
# ======================================================================


class TestAgentEventEmitterMiscEvents:
    """Tests for info, warning, error, progress, and task events."""

    @pytest.mark.asyncio
    async def test_emit_info(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_info("Starting scan", metadata={"files": 10})
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "info"
        assert call_kwargs["message"] == "Starting scan"

    @pytest.mark.asyncio
    async def test_emit_warning(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_warning("Rate limit approaching")
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "warning"

    @pytest.mark.asyncio
    async def test_emit_error(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_error("Connection timeout", metadata={"retry": 3})
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "error"
        assert call_kwargs["metadata"]["retry"] == 3

    @pytest.mark.asyncio
    async def test_emit_progress(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_progress(5, 10, "Halfway there")
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "progress"
        assert call_kwargs["metadata"]["current"] == 5
        assert call_kwargs["metadata"]["total"] == 10
        assert call_kwargs["metadata"]["percentage"] == 50.0
        assert call_kwargs["message"] == "Halfway there"

    @pytest.mark.asyncio
    async def test_emit_progress_default_message(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_progress(3, 10)
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert "3/10" in call_kwargs["message"]

    @pytest.mark.asyncio
    async def test_emit_progress_zero_total(self):
        """When total=0, percentage should be 0 (no division by zero)."""
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_progress(0, 0)
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["metadata"]["percentage"] == 0

    @pytest.mark.asyncio
    async def test_emit_task_complete(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_task_complete(findings_count=5, duration_ms=12345)
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "task_complete"
        assert call_kwargs["metadata"]["findings_count"] == 5
        assert call_kwargs["metadata"]["duration_ms"] == 12345

    @pytest.mark.asyncio
    async def test_emit_task_error(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_task_error("Timeout", message="Task timed out")
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "task_error"
        assert call_kwargs["metadata"]["error"] == "Timeout"

    @pytest.mark.asyncio
    async def test_emit_task_cancelled(self):
        mock_mgr = MagicMock()
        mock_mgr.add_event = AsyncMock()
        emitter = AgentEventEmitter(task_id="t1", event_manager=mock_mgr)

        await emitter.emit_task_cancelled()
        call_kwargs = mock_mgr.add_event.call_args.kwargs
        assert call_kwargs["event_type"] == "task_cancel"


# ======================================================================
# EventManager -- add_event edge cases
# ======================================================================


class TestEventManagerAddEventDeep:
    """Extended add_event tests."""

    @pytest.mark.asyncio
    async def test_add_event_returns_uuid(self):
        """add_event returns a valid UUID string."""
        manager = EventManager()
        event_id = await manager.add_event(
            task_id="t1", event_type="info", sequence=1
        )
        assert isinstance(event_id, str)
        assert len(event_id) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_add_event_includes_timestamp(self):
        """Events have an ISO-format timestamp."""
        manager = EventManager()
        manager.create_queue("t1")

        await manager.add_event(task_id="t1", event_type="info", sequence=1)
        queue = manager._event_queues["t1"]
        event = queue.get_nowait()
        assert "timestamp" in event
        assert "T" in event["timestamp"]  # ISO format

    @pytest.mark.asyncio
    async def test_add_event_skips_db_for_thinking_token(self):
        """thinking_token events are not persisted to DB."""
        mock_session_factory = MagicMock()
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        manager = EventManager(db_session_factory=mock_session_factory)
        await manager.add_event(
            task_id="t1", event_type="thinking_token", sequence=1
        )
        # DB session should not have been used
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_event_persists_to_db(self):
        """Non-skipped events are saved to the database."""
        mock_session = AsyncMock()
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory = MagicMock(return_value=mock_cm)

        manager = EventManager(db_session_factory=mock_session_factory)
        await manager.add_event(
            task_id="t1", event_type="info", sequence=1, message="hello"
        )
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_event_db_error_does_not_raise(self):
        """DB save failure is logged but does not propagate."""
        mock_session = AsyncMock()
        mock_session.add.side_effect = RuntimeError("DB down")
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)
        mock_session_factory = MagicMock(return_value=mock_cm)

        manager = EventManager(db_session_factory=mock_session_factory)
        # Should not raise
        event_id = await manager.add_event(
            task_id="t1", event_type="info", sequence=1
        )
        assert event_id is not None

    @pytest.mark.asyncio
    async def test_add_event_callback_error_does_not_propagate(self):
        """A failing callback should not prevent other callbacks or add_event."""
        manager = EventManager()
        bad_callback = AsyncMock(side_effect=RuntimeError("callback boom"))
        good_callback = AsyncMock()
        manager.add_callback("t1", bad_callback)
        manager.add_callback("t1", good_callback)

        await manager.add_event(task_id="t1", event_type="info", sequence=1)
        bad_callback.assert_called_once()
        good_callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_event_full_queue_drops_event(self):
        """When queue is full, the event is dropped (logged) but no error raised."""
        manager = EventManager()
        queue = manager.create_queue("t1")
        # Fill the queue to capacity
        maxsize = queue.maxsize
        for i in range(maxsize):
            queue.put_nowait({"seq": i})

        # This should not raise despite full queue
        await manager.add_event(task_id="t1", event_type="info", sequence=999)


# ======================================================================
# EventManager -- stream_events
# ======================================================================


class TestEventManagerStreamEvents:
    """Tests for the stream_events async generator."""

    @pytest.mark.asyncio
    async def test_stream_yields_buffered_events(self):
        """stream_events first drains already-buffered events."""
        manager = EventManager()
        manager.create_queue("t1")

        # Use add_event to put events with proper format
        for i in range(3):
            await manager.add_event(
                task_id="t1", event_type="info", sequence=i + 1
            )

        events = []
        async for event in manager.stream_events("t1", after_sequence=0):
            events.append(event)
            if len(events) >= 3:
                break

        assert len(events) == 3

    @pytest.mark.asyncio
    async def test_stream_filters_by_sequence(self):
        """Events with sequence <= after_sequence are skipped."""
        manager = EventManager()
        manager.create_queue("t1")

        # Use add_event so events have proper format with "sequence" key
        for i in range(5):
            await manager.add_event(
                task_id="t1", event_type="info", sequence=i + 1
            )

        events = []
        with patch(
            "app.services.agent.event_manager.get_agent_config"
        ) as mock_cfg:
            mock_cfg.return_value.sse_heartbeat_interval_seconds = 0.01
            async for event in manager.stream_events("t1", after_sequence=3):
                # Heartbeats don't have sequence, skip them
                if event.get("event_type") == "heartbeat":
                    break
                events.append(event)

        # Only sequences 4 and 5 should pass
        assert len(events) == 2
        for e in events:
            assert e["sequence"] > 3

    @pytest.mark.asyncio
    async def test_stream_stops_on_task_complete(self):
        """Streaming stops when task_complete event is encountered in buffered events."""
        manager = EventManager()
        manager.create_queue("t1")

        await manager.add_event(task_id="t1", event_type="info", sequence=1)
        await manager.add_event(task_id="t1", event_type="task_complete", sequence=2)

        events = []
        async for event in manager.stream_events("t1"):
            events.append(event)

        assert len(events) == 2
        assert events[-1]["event_type"] == "task_complete"

    @pytest.mark.asyncio
    async def test_stream_creates_queue_if_missing(self):
        """When no queue exists, a new one is created (fallback)."""
        manager = EventManager()
        events = []
        # This will create a queue but the stream will hit timeout immediately
        # because no events are added. We use a short timeout.
        with patch(
            "app.services.agent.event_manager.get_agent_config"
        ) as mock_cfg:
            mock_cfg.return_value.sse_heartbeat_interval_seconds = 0.01
            async for event in manager.stream_events("t-missing"):
                events.append(event)
                break  # Only need to verify it yields at least a heartbeat

        # Either got a heartbeat or timed out -- either way, no crash
        if events:
            assert events[0]["event_type"] == "heartbeat"


# ======================================================================
# EventManager -- close
# ======================================================================


class TestEventManagerCloseDeep:
    """Extended close tests."""

    @pytest.mark.asyncio
    async def test_close_with_multiple_queues_and_callbacks(self):
        manager = EventManager()
        manager.create_queue("t1")
        manager.create_queue("t2")
        manager.create_queue("t3")
        manager.add_callback("t1", MagicMock())
        manager.add_callback("t2", AsyncMock())

        await manager.close()

        assert len(manager._event_queues) == 0
        assert len(manager._event_callbacks) == 0

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Calling close twice does not raise."""
        manager = EventManager()
        await manager.close()
        await manager.close()
        assert len(manager._event_queues) == 0


# ======================================================================
# EventManager -- callback management
# ======================================================================


class TestEventManagerCallbacks:
    """Tests for callback add/remove/list."""

    def test_add_callback_creates_list(self):
        manager = EventManager()
        cb = MagicMock()
        manager.add_callback("t1", cb)
        assert "t1" in manager._event_callbacks
        assert cb in manager._event_callbacks["t1"]

    def test_add_multiple_callbacks(self):
        manager = EventManager()
        cb1 = MagicMock()
        cb2 = AsyncMock()
        manager.add_callback("t1", cb1)
        manager.add_callback("t1", cb2)
        assert len(manager._event_callbacks["t1"]) == 2

    def test_remove_nonexistent_callback_no_error(self):
        manager = EventManager()
        cb = MagicMock()
        # Removing a callback that was never added should not raise
        manager.remove_callback("t1", cb)

    def test_remove_callback_from_missing_task_no_error(self):
        manager = EventManager()
        manager.remove_callback("nonexistent-task", MagicMock())


# ======================================================================
# EventManager -- create_emitter
# ======================================================================


class TestEventManagerCreateEmitter:
    """Tests for create_emitter."""

    def test_create_emitter_returns_correct_type(self):
        manager = EventManager()
        emitter = manager.create_emitter("task-123")
        assert isinstance(emitter, AgentEventEmitter)
        assert emitter.task_id == "task-123"
        assert emitter.event_manager is manager

    def test_create_emitter_independent_instances(self):
        """Each call creates a new emitter instance."""
        manager = EventManager()
        e1 = manager.create_emitter("t1")
        e2 = manager.create_emitter("t2")
        assert e1 is not e2
        assert e1.task_id != e2.task_id
