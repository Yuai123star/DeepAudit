"""
Tests for AgentState.

Covers lifecycle transitions, iteration tracking, stop conditions,
message/finding management, waiting state, and execution summaries.
"""

import pytest
from unittest.mock import patch

from app.services.agent.core.state import AgentState, AgentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(max_iterations: int = 20, **kwargs) -> AgentState:
    """Create an AgentState with explicit max_iterations, bypassing config lookup."""
    defaults = {
        "agent_id": "test_agent_001",
        "agent_name": "Test Agent",
        "max_iterations": max_iterations,
    }
    defaults.update(kwargs)
    return AgentState(**defaults)


# ---------------------------------------------------------------------------
# Default state
# ---------------------------------------------------------------------------

class TestDefaultState:
    def test_default_state_created(self):
        state = make_state()
        assert state.status == AgentStatus.CREATED
        assert state.iteration == 0
        assert state.stop_requested is False
        assert state.errors == []
        assert state.findings == []
        assert state.messages == []


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------

class TestLifecycleTransitions:
    def test_start_transitions_to_running(self):
        state = make_state()
        state.start()
        assert state.status == AgentStatus.RUNNING
        assert state.started_at is not None

    def test_set_completed(self):
        state = make_state()
        state.start()
        state.set_completed(final_result={"status": "done"})
        assert state.status == AgentStatus.COMPLETED
        assert state.final_result == {"status": "done"}
        assert state.finished_at is not None

    def test_set_failed(self):
        state = make_state()
        state.start()
        state.set_failed("something broke")
        assert state.status == AgentStatus.FAILED
        assert any("something broke" in e for e in state.errors)
        assert state.finished_at is not None

    def test_request_stop(self):
        state = make_state()
        state.start()
        state.request_stop()
        assert state.stop_requested is True
        assert state.status == AgentStatus.STOPPING

    def test_set_stopped(self):
        state = make_state()
        state.start()
        state.request_stop()
        state.set_stopped()
        assert state.status == AgentStatus.STOPPED
        assert state.finished_at is not None


# ---------------------------------------------------------------------------
# Iteration tracking
# ---------------------------------------------------------------------------

class TestIterationTracking:
    def test_increment_iteration(self):
        state = make_state()
        assert state.iteration == 0
        state.increment_iteration()
        assert state.iteration == 1
        state.increment_iteration()
        state.increment_iteration()
        assert state.iteration == 3


# ---------------------------------------------------------------------------
# should_stop
# ---------------------------------------------------------------------------

class TestShouldStop:
    def test_should_stop_when_stop_requested(self):
        state = make_state()
        state.request_stop()
        assert state.should_stop() is True

    def test_should_stop_when_completed(self):
        state = make_state()
        state.set_completed()
        assert state.should_stop() is True

    def test_should_stop_at_max_iterations(self):
        state = make_state(max_iterations=5)
        state.start()
        for _ in range(5):
            state.increment_iteration()
        assert state.should_stop() is True

    def test_should_not_stop_during_normal_run(self):
        state = make_state(max_iterations=20)
        state.start()
        state.increment_iteration()
        assert state.should_stop() is False


# ---------------------------------------------------------------------------
# Max iterations helpers
# ---------------------------------------------------------------------------

class TestMaxIterationsHelpers:
    def test_has_reached_max_iterations(self):
        state = make_state(max_iterations=3)
        assert state.has_reached_max_iterations() is False
        state.increment_iteration()
        state.increment_iteration()
        assert state.has_reached_max_iterations() is False
        state.increment_iteration()
        assert state.has_reached_max_iterations() is True

    def test_is_approaching_max_iterations(self):
        state = make_state(max_iterations=100)
        # 85% of 100 = 85
        for _ in range(84):
            state.increment_iteration()
        assert state.is_approaching_max_iterations() is False
        state.increment_iteration()  # iteration = 85
        assert state.is_approaching_max_iterations() is True


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class TestMessages:
    def test_add_message_and_get_history(self):
        state = make_state()
        state.add_message("user", "hello")
        state.add_message("assistant", "hi there")

        history = state.get_conversation_history()
        assert len(history) == 2
        assert history[0] == {"role": "user", "content": "hello"}
        assert history[1] == {"role": "assistant", "content": "hi there"}

        # Original messages still have timestamps
        for msg in state.messages:
            assert "timestamp" in msg


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

class TestFindings:
    def test_add_finding(self):
        state = make_state()
        finding = {"title": "SQL Injection", "severity": "high"}
        state.add_finding(finding)

        assert len(state.findings) == 1
        saved = state.findings[0]
        assert saved["title"] == "SQL Injection"
        assert "discovered_at" in saved
        assert saved["discovered_by"] == state.agent_id


# ---------------------------------------------------------------------------
# Execution summary
# ---------------------------------------------------------------------------

class TestExecutionSummary:
    def test_get_execution_summary(self):
        state = make_state()
        state.start()
        state.increment_iteration()

        summary = state.get_execution_summary()
        expected_keys = {
            "agent_id", "agent_name", "agent_type", "parent_id",
            "task", "status", "iteration", "max_iterations",
            "total_tokens", "tool_calls", "findings_count", "errors_count",
            "created_at", "started_at", "finished_at", "duration_seconds",
            "knowledge_modules",
        }
        assert expected_keys.issubset(summary.keys())
        assert summary["iteration"] == 1
        assert summary["findings_count"] == 0


# ---------------------------------------------------------------------------
# Waiting state
# ---------------------------------------------------------------------------

class TestWaitingState:
    def test_enter_waiting_state(self):
        state = make_state()
        state.start()
        state.enter_waiting_state(reason="waiting for sub-agent")
        assert state.status == AgentStatus.WAITING
        assert state.waiting_for_input is True
        assert state.waiting_reason == "waiting for sub-agent"
        assert state.waiting_start_time is not None

    def test_resume_from_waiting(self):
        state = make_state()
        state.start()
        state.enter_waiting_state(reason="paused")
        state.resume_from_waiting(new_task="new task description")

        assert state.status == AgentStatus.RUNNING
        assert state.waiting_for_input is False
        assert state.waiting_start_time is None
        assert state.waiting_reason == ""
        assert state.task == "new task description"

    def test_has_waiting_timeout_false_by_default(self):
        state = make_state()
        assert state.has_waiting_timeout() is False
