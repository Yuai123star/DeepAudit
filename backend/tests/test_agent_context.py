"""
Tests for app.services.agent.core.context

Covers:
- generate_correlation_id format
- set/get correlation_id, task_id, current_agent roundtrips
- get_correlation_id auto-generation when unset
- get_trace_path mutation safety
- push_trace / pop_trace stack operations
- ExecutionContext dataclass defaults, child_context, with_iteration,
  with_metadata, trace_string, span_id, to_dict, from_dict, to_log_dict
- ExecutionContextManager sync and async usage
- create_context helper
- get_current_context helper
- with_context and traced decorators
"""

import asyncio
import re

import pytest

from app.services.agent.core.context import (
    ExecutionContext,
    ExecutionContextManager,
    create_context,
    generate_correlation_id,
    get_correlation_id,
    get_current_agent,
    get_current_context,
    get_task_id,
    get_trace_path,
    pop_trace,
    push_trace,
    set_correlation_id,
    set_current_agent,
    set_task_id,
    traced,
    with_context,
    _correlation_id,
    _task_id,
    _current_agent,
    _trace_path,
)


# ============ Fixtures ============


@pytest.fixture(autouse=True)
def _reset_context_vars():
    """
    Reset all module-level contextvars to their defaults before each test
    so tests are isolated from one another.
    """
    _correlation_id.set("")
    _task_id.set("")
    _current_agent.set(None)
    _trace_path.set([])
    yield
    _correlation_id.set("")
    _task_id.set("")
    _current_agent.set(None)
    _trace_path.set([])


# ============ generate_correlation_id ============


class TestGenerateCorrelationId:
    """Tests for generate_correlation_id()."""

    def test_format_matches_cid_hex12(self):
        cid = generate_correlation_id()
        assert re.fullmatch(r"cid-[0-9a-f]{12}", cid), f"Unexpected format: {cid}"

    def test_prefix_is_cid_dash(self):
        cid = generate_correlation_id()
        assert cid.startswith("cid-")

    def test_unique_across_calls(self):
        ids = {generate_correlation_id() for _ in range(50)}
        assert len(ids) == 50, "Correlation IDs should be unique"


# ============ correlation_id get / set ============


class TestCorrelationId:
    """Tests for set_correlation_id / get_correlation_id."""

    def test_set_get_roundtrip(self):
        token = set_correlation_id("cid-abc123456789")
        assert get_correlation_id() == "cid-abc123456789"
        _correlation_id.reset(token)

    def test_get_auto_generates_when_unset(self):
        """When no correlation_id has been set, get_correlation_id generates one."""
        cid = get_correlation_id()
        assert cid.startswith("cid-")
        assert re.fullmatch(r"cid-[0-9a-f]{12}", cid)

    def test_get_auto_generates_stores_result(self):
        """The auto-generated id is stored so subsequent calls return the same value."""
        first = get_correlation_id()
        second = get_correlation_id()
        assert first == second


# ============ task_id get / set ============


class TestTaskId:
    """Tests for set_task_id / get_task_id."""

    def test_default_is_empty_string(self):
        assert get_task_id() == ""

    def test_set_get_roundtrip(self):
        token = set_task_id("task-42")
        assert get_task_id() == "task-42"
        _task_id.reset(token)


# ============ current_agent get / set ============


class TestCurrentAgent:
    """Tests for set_current_agent / get_current_agent."""

    def test_default_is_none(self):
        assert get_current_agent() is None

    def test_set_get_roundtrip(self):
        token = set_current_agent("orchestrator")
        assert get_current_agent() == "orchestrator"
        _current_agent.reset(token)


# ============ trace_path operations ============


class TestTracePath:
    """Tests for get_trace_path, push_trace, pop_trace."""

    def test_default_is_empty_list(self):
        assert get_trace_path() == []

    def test_get_returns_copy_mutation_safe(self):
        """Mutating the returned list should not affect the stored path."""
        push_trace("alpha")
        path = get_trace_path()
        path.append("MUTATED")
        assert get_trace_path() == ["alpha"], "get_trace_path must return a copy"

    def test_push_trace_appends(self):
        push_trace("recon")
        push_trace("analysis")
        assert get_trace_path() == ["recon", "analysis"]

    def test_pop_trace_returns_last_and_removes(self):
        push_trace("recon")
        push_trace("analysis")
        popped = pop_trace()
        assert popped == "analysis"
        assert get_trace_path() == ["recon"]

    def test_pop_trace_on_empty_returns_none(self):
        assert pop_trace() is None

    def test_push_pop_push_sequence(self):
        push_trace("a")
        pop_trace()
        push_trace("b")
        assert get_trace_path() == ["b"]


# ============ ExecutionContext dataclass ============


class TestExecutionContextDefaults:
    """Tests for ExecutionContext default field values."""

    def test_correlation_id_auto_generated(self):
        ctx = ExecutionContext()
        assert re.fullmatch(r"cid-[0-9a-f]{12}", ctx.correlation_id)

    def test_task_id_default_empty(self):
        assert ExecutionContext().task_id == ""

    def test_trace_path_default_empty(self):
        assert ExecutionContext().trace_path == []

    def test_iteration_default_zero(self):
        assert ExecutionContext().iteration == 0

    def test_depth_default_zero(self):
        assert ExecutionContext().depth == 0

    def test_metadata_default_empty_dict(self):
        assert ExecutionContext().metadata == {}

    def test_current_agent_name_default_none(self):
        assert ExecutionContext().current_agent_name is None

    def test_created_at_is_iso_string(self):
        ctx = ExecutionContext()
        # Should be parseable as an ISO datetime
        from datetime import datetime
        datetime.fromisoformat(ctx.created_at)


class TestExecutionContextChildContext:
    """Tests for ExecutionContext.child_context()."""

    def _make_parent(self):
        return ExecutionContext(
            correlation_id="cid-parent12345",
            task_id="task-99",
            current_agent_id="parent-agent",
            current_agent_name="orchestrator",
            trace_path=["orchestrator"],
            iteration=3,
            depth=1,
            metadata={"env": "test"},
        )

    def test_increments_depth(self):
        parent = self._make_parent()
        child = parent.child_context(agent_id="child-agent", agent_name="analysis")
        assert child.depth == parent.depth + 1

    def test_resets_iteration_to_zero(self):
        parent = self._make_parent()
        child = parent.child_context(agent_id="child-agent", agent_name="analysis")
        assert child.iteration == 0

    def test_extends_trace_path(self):
        parent = self._make_parent()
        child = parent.child_context(agent_id="child-agent", agent_name="analysis")
        assert child.trace_path == ["orchestrator", "analysis"]
        # Parent should not be mutated
        assert parent.trace_path == ["orchestrator"]

    def test_sets_parent_agent_id(self):
        parent = self._make_parent()
        child = parent.child_context(agent_id="child-agent", agent_name="analysis")
        assert child.parent_agent_id == "parent-agent"

    def test_copies_metadata(self):
        parent = self._make_parent()
        child = parent.child_context(agent_id="child-agent", agent_name="analysis")
        assert child.metadata == {"env": "test"}
        # Mutating child metadata should not affect parent
        child.metadata["extra"] = True
        assert "extra" not in parent.metadata


class TestExecutionContextWithIteration:
    """Tests for ExecutionContext.with_iteration()."""

    def test_creates_copy_with_new_iteration(self):
        original = ExecutionContext(iteration=2, correlation_id="cid-aaa")
        updated = original.with_iteration(5)
        assert updated.iteration == 5
        assert original.iteration == 2, "Original must not be mutated"

    def test_preserves_other_fields(self):
        original = ExecutionContext(
            correlation_id="cid-xyz",
            task_id="task-1",
            depth=3,
            trace_path=["a", "b"],
        )
        updated = original.with_iteration(10)
        assert updated.correlation_id == "cid-xyz"
        assert updated.task_id == "task-1"
        assert updated.depth == 3
        assert updated.trace_path == ["a", "b"]


class TestExecutionContextWithMetadata:
    """Tests for ExecutionContext.with_metadata()."""

    def test_merges_new_metadata(self):
        original = ExecutionContext(metadata={"a": 1, "b": 2})
        updated = original.with_metadata(b=99, c=3)
        assert updated.metadata == {"a": 1, "b": 99, "c": 3}
        # Original unchanged
        assert original.metadata == {"a": 1, "b": 2}

    def test_adds_metadata_to_empty(self):
        original = ExecutionContext()
        updated = original.with_metadata(key="value")
        assert updated.metadata == {"key": "value"}


class TestExecutionContextTraceString:
    """Tests for ExecutionContext.trace_string property."""

    def test_empty_path_returns_root(self):
        ctx = ExecutionContext(trace_path=[])
        assert ctx.trace_string == "root"

    def test_single_element(self):
        ctx = ExecutionContext(trace_path=["orchestrator"])
        assert ctx.trace_string == "orchestrator"

    def test_joins_with_arrow(self):
        ctx = ExecutionContext(trace_path=["orchestrator", "analysis", "verification"])
        assert ctx.trace_string == "orchestrator > analysis > verification"


class TestExecutionContextSpanId:
    """Tests for ExecutionContext.span_id property."""

    def test_format_with_agent_id(self):
        ctx = ExecutionContext(
            correlation_id="cid-abc123456789",
            current_agent_id="agent-42",
            iteration=7,
        )
        assert ctx.span_id == "cid-abc123456789:agent-42:7"

    def test_format_without_agent_id_uses_unknown(self):
        ctx = ExecutionContext(
            correlation_id="cid-abc123456789",
            current_agent_id=None,
            iteration=0,
        )
        assert ctx.span_id == "cid-abc123456789:unknown:0"


class TestExecutionContextSerialization:
    """Tests for ExecutionContext.to_dict / from_dict roundtrip."""

    def test_to_dict_keys(self):
        ctx = ExecutionContext(
            correlation_id="cid-roundtrip123",
            task_id="task-5",
            current_agent_name="recon",
            trace_path=["recon"],
            iteration=1,
            depth=2,
            metadata={"x": 1},
        )
        d = ctx.to_dict()
        assert d["correlation_id"] == "cid-roundtrip123"
        assert d["task_id"] == "task-5"
        assert d["current_agent_name"] == "recon"
        assert d["trace_path"] == ["recon"]
        assert d["trace_string"] == "recon"
        assert d["iteration"] == 1
        assert d["depth"] == 2
        assert d["metadata"] == {"x": 1}

    def test_from_dict_roundtrip(self):
        original = ExecutionContext(
            correlation_id="cid-fromdict1234",
            task_id="task-10",
            parent_agent_id="p-1",
            current_agent_id="c-1",
            current_agent_name="verification",
            trace_path=["orch", "verify"],
            iteration=4,
            depth=2,
            metadata={"env": "prod"},
        )
        data = original.to_dict()
        restored = ExecutionContext.from_dict(data)
        assert restored.correlation_id == original.correlation_id
        assert restored.task_id == original.task_id
        assert restored.parent_agent_id == original.parent_agent_id
        assert restored.current_agent_id == original.current_agent_id
        assert restored.current_agent_name == original.current_agent_name
        assert restored.trace_path == original.trace_path
        assert restored.iteration == original.iteration
        assert restored.depth == original.depth
        assert restored.metadata == original.metadata

    def test_from_dict_missing_fields_use_defaults(self):
        restored = ExecutionContext.from_dict({})
        assert re.fullmatch(r"cid-[0-9a-f]{12}", restored.correlation_id)
        assert restored.task_id == ""
        assert restored.trace_path == []
        assert restored.iteration == 0
        assert restored.depth == 0
        assert restored.metadata == {}


class TestExecutionContextToLogDict:
    """Tests for ExecutionContext.to_log_dict()."""

    def test_minimal_fields(self):
        ctx = ExecutionContext(
            correlation_id="cid-logtest1234",
            task_id="task-1",
            current_agent_id="agent-7",
            current_agent_name="analysis",
            trace_path=["analysis"],
            iteration=2,
        )
        log = ctx.to_log_dict()
        assert log == {
            "correlation_id": "cid-logtest1234",
            "task_id": "task-1",
            "agent_id": "agent-7",
            "agent_name": "analysis",
            "trace": "analysis",
            "iteration": 2,
        }

    def test_does_not_include_metadata_or_depth(self):
        ctx = ExecutionContext(metadata={"secret": True}, depth=5)
        log = ctx.to_log_dict()
        assert "metadata" not in log
        assert "depth" not in log


# ============ ExecutionContextManager ============


class TestExecutionContextManager:
    """Tests for ExecutionContextManager sync and async context manager."""

    def test_sync_sets_and_restores_context_vars(self):
        ctx = ExecutionContext(
            correlation_id="cid-mgr00000001",
            task_id="task-sync",
            current_agent_name="recon",
            trace_path=["recon"],
        )
        with ExecutionContextManager(ctx):
            assert get_correlation_id() == "cid-mgr00000001"
            assert get_task_id() == "task-sync"
            assert get_current_agent() == "recon"
            assert get_trace_path() == ["recon"]

        # After exiting, values should be restored to defaults
        # (but correlation_id may have been auto-generated; check the others)
        assert get_task_id() == ""
        assert get_current_agent() is None

    def test_sync_returns_context_object(self):
        ctx = ExecutionContext(correlation_id="cid-rettest")
        with ExecutionContextManager(ctx) as entered:
            assert entered is ctx

    @pytest.mark.asyncio
    async def test_async_sets_and_restores_context_vars(self):
        ctx = ExecutionContext(
            correlation_id="cid-async0000001",
            task_id="task-async",
            current_agent_name="analysis",
            trace_path=["analysis"],
        )
        async with ExecutionContextManager(ctx):
            assert get_correlation_id() == "cid-async0000001"
            assert get_task_id() == "task-async"
            assert get_current_agent() == "analysis"

        assert get_task_id() == ""
        assert get_current_agent() is None

    def test_does_not_set_agent_when_name_is_none(self):
        ctx = ExecutionContext(
            correlation_id="cid-noagent",
            current_agent_name=None,
        )
        with ExecutionContextManager(ctx):
            assert get_current_agent() is None


# ============ create_context ============


class TestCreateContext:
    """Tests for create_context() helper."""

    def test_with_explicit_correlation_id(self):
        ctx = create_context(task_id="task-1", correlation_id="cid-custom12345")
        assert ctx.task_id == "task-1"
        assert ctx.correlation_id == "cid-custom12345"

    def test_generates_correlation_id_when_none(self):
        ctx = create_context(task_id="task-2")
        assert ctx.task_id == "task-2"
        assert re.fullmatch(r"cid-[0-9a-f]{12}", ctx.correlation_id)

    def test_metadata_kwargs(self):
        ctx = create_context(task_id="task-3", env="staging", region="us")
        assert ctx.metadata == {"env": "staging", "region": "us"}


# ============ get_current_context ============


class TestGetCurrentContext:
    """Tests for get_current_context() helper."""

    def test_reflects_context_vars(self):
        set_correlation_id("cid-curctx00001")
        set_task_id("task-current")
        set_current_agent("verification")
        push_trace("verification")

        ctx = get_current_context()
        assert ctx.correlation_id == "cid-curctx00001"
        assert ctx.task_id == "task-current"
        assert ctx.current_agent_name == "verification"
        assert ctx.trace_path == ["verification"]


# ============ with_context decorator ============


class TestWithContextDecorator:
    """Tests for with_context() decorator."""

    @pytest.mark.asyncio
    async def test_sets_context_during_execution(self):
        ctx = ExecutionContext(
            correlation_id="cid-deco00000001",
            task_id="task-deco",
            current_agent_name="recon",
        )

        @with_context(ctx)
        async def check():
            return {
                "cid": get_correlation_id(),
                "tid": get_task_id(),
                "agent": get_current_agent(),
            }

        result = await check()
        assert result["cid"] == "cid-deco00000001"
        assert result["tid"] == "task-deco"
        assert result["agent"] == "recon"

    @pytest.mark.asyncio
    async def test_restores_after_execution(self):
        set_task_id("original-task")

        ctx = ExecutionContext(
            correlation_id="cid-rest00000001",
            task_id="task-temp",
        )

        @with_context(ctx)
        async def noop():
            pass

        await noop()
        assert get_task_id() == "original-task"


# ============ traced decorator ============


class TestTracedDecorator:
    """Tests for traced() decorator."""

    @pytest.mark.asyncio
    async def test_pushes_and_pops_trace(self):
        push_trace("orchestrator")

        @traced("analysis")
        async def run():
            return get_trace_path()

        result = await run()
        assert result == ["orchestrator", "analysis"]
        # After execution, "analysis" should be popped
        assert get_trace_path() == ["orchestrator"]

    @pytest.mark.asyncio
    async def test_pops_trace_on_exception(self):
        push_trace("orchestrator")

        @traced("failing_agent")
        async def boom():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await boom()

        # Trace should be restored even after exception
        assert get_trace_path() == ["orchestrator"]

    @pytest.mark.asyncio
    async def test_nested_traced_decorators(self):
        @traced("outer")
        @traced("inner")
        async def nested():
            return get_trace_path()

        result = await nested()
        assert result == ["outer", "inner"]
        assert get_trace_path() == []
