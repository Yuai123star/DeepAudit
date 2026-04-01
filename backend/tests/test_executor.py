"""
Tests for app.services.agent.core.executor

Covers:
- ExecutionMode enum
- ExecutionTask / ExecutionResult dataclass defaults
- DynamicAgentExecutor: constructor, cancel, is_cancelled, get_execution_summary
- SubAgentExecutor: constructor, get_child_results, get_all_findings
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.agent.core.executor import (
    DynamicAgentExecutor,
    ExecutionMode,
    ExecutionResult,
    ExecutionTask,
    SubAgentExecutor,
)


# ===================================================================
# ExecutionMode enum
# ===================================================================

class TestExecutionMode:
    def test_sequential_value(self):
        assert ExecutionMode.SEQUENTIAL == "sequential"
        assert ExecutionMode.SEQUENTIAL.value == "sequential"

    def test_parallel_value(self):
        assert ExecutionMode.PARALLEL == "parallel"

    def test_adaptive_value(self):
        assert ExecutionMode.ADAPTIVE == "adaptive"

    def test_is_str_enum(self):
        assert isinstance(ExecutionMode.SEQUENTIAL, str)


# ===================================================================
# ExecutionTask dataclass defaults
# ===================================================================

class TestExecutionTask:
    def test_required_fields(self):
        task = ExecutionTask(agent_id="a1", agent_type="analysis", task="scan code")
        assert task.agent_id == "a1"
        assert task.agent_type == "analysis"
        assert task.task == "scan code"

    def test_default_context(self):
        task = ExecutionTask(agent_id="a1", agent_type="recon", task="list")
        assert task.context == {}

    def test_default_priority(self):
        task = ExecutionTask(agent_id="a1", agent_type="recon", task="list")
        assert task.priority == 0

    def test_default_dependencies(self):
        task = ExecutionTask(agent_id="a1", agent_type="recon", task="list")
        assert task.dependencies == []

    def test_default_status(self):
        task = ExecutionTask(agent_id="a1", agent_type="recon", task="list")
        assert task.status == "pending"

    def test_optional_fields_default_none(self):
        task = ExecutionTask(agent_id="a1", agent_type="recon", task="list")
        assert task.result is None
        assert task.error is None
        assert task.started_at is None
        assert task.finished_at is None

    def test_custom_values(self):
        now = datetime.now(timezone.utc)
        task = ExecutionTask(
            agent_id="a2",
            agent_type="verification",
            task="verify poc",
            context={"key": "val"},
            priority=5,
            dependencies=["a1"],
            status="running",
            started_at=now,
        )
        assert task.priority == 5
        assert task.dependencies == ["a1"]
        assert task.status == "running"
        assert task.started_at is now

    def test_mutable_defaults_are_independent(self):
        t1 = ExecutionTask(agent_id="x", agent_type="recon", task="t")
        t2 = ExecutionTask(agent_id="y", agent_type="recon", task="t")
        t1.context["foo"] = "bar"
        assert "foo" not in t2.context


# ===================================================================
# ExecutionResult dataclass defaults
# ===================================================================

class TestExecutionResult:
    def test_required_success_field(self):
        result = ExecutionResult(success=True)
        assert result.success is True

    def test_default_counts(self):
        result = ExecutionResult(success=False)
        assert result.total_agents == 0
        assert result.completed_agents == 0
        assert result.failed_agents == 0

    def test_default_collections(self):
        result = ExecutionResult(success=True)
        assert result.all_findings == []
        assert result.agent_results == {}
        assert result.errors == []

    def test_default_statistics(self):
        result = ExecutionResult(success=True)
        assert result.total_duration_ms == 0
        assert result.total_tokens == 0
        assert result.total_tool_calls == 0


# ===================================================================
# DynamicAgentExecutor
# ===================================================================

class TestDynamicAgentExecutor:
    """Tests for DynamicAgentExecutor constructor and simple methods."""

    def test_constructor_with_explicit_timeout(self):
        executor = DynamicAgentExecutor(
            llm_service=None,
            tools={},
            event_emitter=None,
            max_parallel=3,
            default_timeout=120,
        )
        assert executor.llm_service is None
        assert executor.tools == {}
        assert executor.event_emitter is None
        assert executor.max_parallel == 3
        assert executor.default_timeout == 120
        assert executor._tasks == {}
        assert executor._cancelled is False

    def test_constructor_reads_config_when_timeout_is_none(self):
        mock_config = MagicMock()
        mock_config.sub_agent_timeout_seconds = 600

        with patch(
            "app.services.agent.core.executor.get_agent_config",
            return_value=mock_config,
        ):
            executor = DynamicAgentExecutor(
                llm_service=None,
                tools={},
                event_emitter=None,
                default_timeout=None,
            )
        assert executor.default_timeout == 600

    def test_constructor_default_max_parallel(self):
        executor = DynamicAgentExecutor(
            llm_service=None,
            tools={},
            default_timeout=30,
        )
        assert executor.max_parallel == 5

    # -- cancel / is_cancelled --

    def test_cancel_sets_flag(self):
        executor = DynamicAgentExecutor(
            llm_service=None, tools={}, default_timeout=30,
        )
        assert executor.is_cancelled is False
        executor.cancel()
        assert executor.is_cancelled is True

    def test_cancel_cancels_running_asyncio_tasks(self):
        executor = DynamicAgentExecutor(
            llm_service=None, tools={}, default_timeout=30,
        )

        # Simulate a running asyncio.Task in _running_tasks
        mock_task = MagicMock()
        mock_task.done.return_value = False
        executor._running_tasks["t1"] = mock_task

        executor.cancel()
        mock_task.cancel.assert_called_once()

    def test_cancel_skips_done_tasks(self):
        executor = DynamicAgentExecutor(
            llm_service=None, tools={}, default_timeout=30,
        )

        mock_task = MagicMock()
        mock_task.done.return_value = True
        executor._running_tasks["t1"] = mock_task

        executor.cancel()
        mock_task.cancel.assert_not_called()

    # -- get_execution_summary --

    def test_summary_empty_tasks(self):
        executor = DynamicAgentExecutor(
            llm_service=None, tools={}, default_timeout=30,
        )
        summary = executor.get_execution_summary()
        assert summary["total_tasks"] == 0
        assert summary["completed"] == 0
        assert summary["failed"] == 0
        assert summary["pending"] == 0
        assert summary["running"] == 0
        assert summary["tasks"] == {}

    def test_summary_counts_by_status(self):
        executor = DynamicAgentExecutor(
            llm_service=None, tools={}, default_timeout=30,
        )
        executor._tasks = {
            "a": ExecutionTask(
                agent_id="a", agent_type="recon", task="t", status="completed",
            ),
            "b": ExecutionTask(
                agent_id="b", agent_type="analysis", task="t", status="failed",
                error="boom",
            ),
            "c": ExecutionTask(
                agent_id="c", agent_type="recon", task="t", status="running",
            ),
            "d": ExecutionTask(
                agent_id="d", agent_type="recon", task="t", status="pending",
            ),
        }
        summary = executor.get_execution_summary()
        assert summary["total_tasks"] == 4
        assert summary["completed"] == 1
        assert summary["failed"] == 1
        assert summary["running"] == 1
        assert summary["pending"] == 1
        assert summary["tasks"]["b"]["error"] == "boom"
        assert summary["tasks"]["a"]["agent_type"] == "recon"


# ===================================================================
# SubAgentExecutor
# ===================================================================

class TestSubAgentExecutor:
    def _make_parent(self):
        parent = MagicMock()
        parent.agent_id = "parent-001"
        return parent

    def test_constructor_stores_params(self):
        parent = self._make_parent()
        executor = SubAgentExecutor(
            parent_agent=parent,
            llm_service="llm",
            tools={"tool1": True},
            event_emitter="emitter",
        )
        assert executor.parent_agent is parent
        assert executor.llm_service == "llm"
        assert executor.tools == {"tool1": True}
        assert executor.event_emitter == "emitter"
        assert executor._child_agents == {}

    def test_constructor_creates_internal_dynamic_executor(self):
        parent = self._make_parent()
        executor = SubAgentExecutor(
            parent_agent=parent,
            llm_service="llm",
            tools={},
        )
        assert isinstance(executor._executor, DynamicAgentExecutor)

    # -- get_child_results --

    def test_get_child_results_returns_empty_when_no_children(self):
        parent = self._make_parent()
        executor = SubAgentExecutor(parent_agent=parent, llm_service=None, tools={})
        assert executor.get_child_results() == {}

    def test_get_child_results_returns_shallow_copy(self):
        parent = self._make_parent()
        executor = SubAgentExecutor(parent_agent=parent, llm_service=None, tools={})
        executor._child_agents = {
            "child-1": {"success": True, "data": {}},
            "child-2": {"success": False, "error": "fail"},
        }
        results = executor.get_child_results()
        assert results == executor._child_agents
        # Verify it is a copy (different object)
        assert results is not executor._child_agents

    # -- get_all_findings --

    def test_get_all_findings_empty_when_no_children(self):
        parent = self._make_parent()
        executor = SubAgentExecutor(parent_agent=parent, llm_service=None, tools={})
        assert executor.get_all_findings() == []

    def test_get_all_findings_flattens_from_successful_children(self):
        parent = self._make_parent()
        executor = SubAgentExecutor(parent_agent=parent, llm_service=None, tools={})
        executor._child_agents = {
            "c1": {
                "success": True,
                "data": {"findings": [{"id": "f1"}, {"id": "f2"}]},
            },
            "c2": {
                "success": True,
                "data": {"findings": [{"id": "f3"}]},
            },
        }
        findings = executor.get_all_findings()
        assert len(findings) == 3
        assert findings[0]["id"] == "f1"
        assert findings[2]["id"] == "f3"

    def test_get_all_findings_skips_failed_children(self):
        parent = self._make_parent()
        executor = SubAgentExecutor(parent_agent=parent, llm_service=None, tools={})
        executor._child_agents = {
            "c1": {
                "success": True,
                "data": {"findings": [{"id": "f1"}]},
            },
            "c2": {
                "success": False,
                "data": {"findings": [{"id": "should-not-appear"}]},
            },
        }
        findings = executor.get_all_findings()
        assert len(findings) == 1
        assert findings[0]["id"] == "f1"

    def test_get_all_findings_skips_children_without_data(self):
        parent = self._make_parent()
        executor = SubAgentExecutor(parent_agent=parent, llm_service=None, tools={})
        executor._child_agents = {
            "c1": {"success": True},
            "c2": {"success": True, "data": {}},
            "c3": {"success": True, "data": {"findings": [{"id": "f1"}]}},
        }
        findings = executor.get_all_findings()
        assert len(findings) == 1
