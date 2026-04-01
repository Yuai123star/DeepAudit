"""
Tests for Agent state persistence module.

Tests AgentStatePersistence and CheckpointManager at
app.services.agent.core.persistence.
"""

import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.agent.core.persistence import (
    AgentStatePersistence,
    CheckpointManager,
)
from app.services.agent.core.state import AgentState, AgentStatus


# ============ AgentStatePersistence Tests ============


class TestAgentStatePersistenceSaveLoad:
    """Tests for save_state and load_state."""

    def test_save_state_returns_filepath(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(agent_id="test_agent_1", status=AgentStatus.RUNNING)
        filepath = persistence.save_state(state)
        assert filepath.endswith(".json")
        assert "test_agent_1" in filepath
        assert os.path.exists(filepath)

    def test_save_state_with_checkpoint_name(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(agent_id="test_agent_2")
        filepath = persistence.save_state(state, checkpoint_name="milestone_1")
        assert "milestone_1" in filepath
        assert "test_agent_2" in filepath

    def test_save_state_creates_valid_json(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(
            agent_id="test_agent_3",
            agent_name="TestAgent",
            iteration=5,
            status=AgentStatus.RUNNING,
        )
        filepath = persistence.save_state(state)
        with open(filepath, "r") as f:
            data = json.load(f)
        assert data["version"] == "1.0"
        assert "serialized_at" in data
        assert "state" in data
        assert data["state"]["agent_id"] == "test_agent_3"
        assert data["state"]["iteration"] == 5

    def test_load_state_returns_agent_state(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        original = AgentState(
            agent_id="test_agent_4",
            agent_name="Loader",
            iteration=10,
            max_iterations=100,
            status=AgentStatus.COMPLETED,
        )
        filepath = persistence.save_state(original)
        loaded = persistence.load_state(filepath)
        assert loaded is not None
        assert loaded.agent_id == "test_agent_4"
        assert loaded.agent_name == "Loader"
        assert loaded.iteration == 10
        assert loaded.max_iterations == 100
        assert loaded.status == AgentStatus.COMPLETED.value

    def test_load_state_returns_none_on_bad_file(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        bad_path = os.path.join(temp_dir, "nonexistent.json")
        assert persistence.load_state(bad_path) is None

    def test_load_state_returns_none_on_invalid_json(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        bad_file = os.path.join(temp_dir, "bad.json")
        with open(bad_file, "w") as f:
            f.write("this is not json{{{")
        assert persistence.load_state(bad_file) is None

    def test_roundtrip_preserves_messages(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(agent_id="msg_agent")
        state.add_message("system", "You are a security auditor.")
        state.add_message("user", "Analyze this file.")
        state.add_message("assistant", "Found SQL injection.")
        filepath = persistence.save_state(state)
        loaded = persistence.load_state(filepath)
        assert loaded is not None
        assert len(loaded.messages) == 3
        assert loaded.messages[0]["role"] == "system"
        assert loaded.messages[1]["role"] == "user"
        assert loaded.messages[2]["content"] == "Found SQL injection."

    def test_roundtrip_preserves_findings(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(agent_id="finding_agent")
        state.add_finding({"type": "sql_injection", "severity": "high"})
        state.add_finding({"type": "xss", "severity": "medium"})
        filepath = persistence.save_state(state)
        loaded = persistence.load_state(filepath)
        assert loaded is not None
        assert len(loaded.findings) == 2
        assert loaded.findings[0]["type"] == "sql_injection"
        assert loaded.findings[1]["severity"] == "medium"


class TestAgentStatePersistenceLatestCheckpoint:
    """Tests for load_latest_checkpoint."""

    def test_load_latest_returns_none_when_no_checkpoints(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        result = persistence.load_latest_checkpoint("nonexistent_agent")
        assert result is None

    def test_load_latest_returns_most_recent(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        # Create multiple checkpoints with different iterations
        state1 = AgentState(agent_id="multi_agent", iteration=1)
        state2 = AgentState(agent_id="multi_agent", iteration=5)
        state3 = AgentState(agent_id="multi_agent", iteration=10)

        persistence.save_state(state1, checkpoint_name="cp1")
        persistence.save_state(state2, checkpoint_name="cp2")
        persistence.save_state(state3, checkpoint_name="cp3")

        loaded = persistence.load_latest_checkpoint("multi_agent")
        assert loaded is not None
        assert loaded.iteration == 10

    def test_load_latest_ignores_other_agents(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state_a = AgentState(agent_id="agent_a", iteration=1)
        state_b = AgentState(agent_id="agent_b", iteration=99)
        persistence.save_state(state_a, checkpoint_name="cp_a")
        persistence.save_state(state_b, checkpoint_name="cp_b")

        loaded = persistence.load_latest_checkpoint("agent_a")
        assert loaded is not None
        assert loaded.agent_id == "agent_a"
        assert loaded.iteration == 1


class TestAgentStatePersistenceListCheckpoints:
    """Tests for list_checkpoints."""

    def test_list_checkpoints_empty(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        result = persistence.list_checkpoints()
        assert result == []

    def test_list_all_checkpoints(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state_a = AgentState(agent_id="a")
        state_b = AgentState(agent_id="b")
        persistence.save_state(state_a, checkpoint_name="cp_a")
        persistence.save_state(state_b, checkpoint_name="cp_b")

        all_cps = persistence.list_checkpoints()
        assert len(all_cps) == 2
        for cp in all_cps:
            assert "filepath" in cp
            assert "filename" in cp
            assert "size_bytes" in cp
            assert "modified_at" in cp

    def test_list_checkpoints_filtered_by_agent(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state_a = AgentState(agent_id="filter_a")
        state_b = AgentState(agent_id="filter_b")
        persistence.save_state(state_a, checkpoint_name="cp_a1")
        persistence.save_state(state_a, checkpoint_name="cp_a2")
        persistence.save_state(state_b, checkpoint_name="cp_b1")

        filtered = persistence.list_checkpoints(agent_id="filter_a")
        assert len(filtered) == 2
        for cp in filtered:
            assert "filter_a" in cp["filename"]

    def test_list_checkpoints_sorted_by_modified_time_desc(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(agent_id="sort_agent")
        persistence.save_state(state, checkpoint_name="first")
        persistence.save_state(state, checkpoint_name="second")
        persistence.save_state(state, checkpoint_name="third")

        cps = persistence.list_checkpoints(agent_id="sort_agent")
        assert len(cps) == 3
        # Latest should be first
        assert "third" in cps[0]["filename"]


class TestAgentStatePersistenceDeleteCheckpoint:
    """Tests for delete_checkpoint."""

    def test_delete_checkpoint_removes_file(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(agent_id="del_agent")
        filepath = persistence.save_state(state, checkpoint_name="to_delete")
        assert os.path.exists(filepath)
        assert persistence.delete_checkpoint(filepath) is True
        assert not os.path.exists(filepath)

    def test_delete_nonexistent_checkpoint_returns_false(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        result = persistence.delete_checkpoint("/nonexistent/path/file.json")
        assert result is False


class TestAgentStatePersistenceCleanup:
    """Tests for cleanup_old_checkpoints."""

    def test_cleanup_removes_oldest(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(agent_id="cleanup_agent")
        # Create 7 checkpoints
        for i in range(7):
            persistence.save_state(state, checkpoint_name=f"cp_{i}")

        deleted = persistence.cleanup_old_checkpoints("cleanup_agent", keep_count=3)
        assert deleted == 4
        remaining = persistence.list_checkpoints(agent_id="cleanup_agent")
        assert len(remaining) == 3

    def test_cleanup_nothing_when_under_limit(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(agent_id="small_agent")
        persistence.save_state(state, checkpoint_name="cp1")
        persistence.save_state(state, checkpoint_name="cp2")

        deleted = persistence.cleanup_old_checkpoints("small_agent", keep_count=5)
        assert deleted == 0
        remaining = persistence.list_checkpoints(agent_id="small_agent")
        assert len(remaining) == 2


class TestAgentStatePersistenceSerialization:
    """Tests for _serialize_state and _deserialize_state."""

    def test_serialize_includes_version_and_timestamp(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        state = AgentState(agent_id="serial_agent")
        data = persistence._serialize_state(state)
        assert data["version"] == "1.0"
        assert "serialized_at" in data
        assert "state" in data

    def test_deserialize_from_raw_state_dict(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        data = {
            "version": "1.0",
            "serialized_at": "2025-01-01T00:00:00+00:00",
            "state": {
                "agent_id": "deser_agent",
                "agent_name": "Test",
                "iteration": 7,
            },
        }
        state = persistence._deserialize_state(data)
        assert state.agent_id == "deser_agent"
        assert state.iteration == 7

    def test_deserialize_handles_unknown_version(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        data = {
            "version": "99.0",
            "state": {
                "agent_id": "future_agent",
                "iteration": 0,
            },
        }
        state = persistence._deserialize_state(data)
        assert state.agent_id == "future_agent"


class TestAgentStatePersistenceInit:
    """Tests for constructor behavior."""

    def test_creates_directory_if_missing(self, temp_dir):
        nested = os.path.join(temp_dir, "a", "b", "c")
        persistence = AgentStatePersistence(persist_dir=nested)
        assert os.path.isdir(nested)

    def test_default_parameters(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        assert persistence.use_database is False
        assert persistence.db_session_factory is None


# ============ CheckpointManager Tests ============


class TestCheckpointManager:
    """Tests for CheckpointManager."""

    def test_should_checkpoint_initially_false_with_small_interval(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        manager = CheckpointManager(persistence, auto_checkpoint_interval=5)
        state = AgentState(agent_id="chk_agent", iteration=0)
        assert manager.should_checkpoint(state) is False

    def test_should_checkpoint_true_after_interval(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        manager = CheckpointManager(persistence, auto_checkpoint_interval=3)
        state = AgentState(agent_id="chk_agent2")
        state.iteration = 3
        assert manager.should_checkpoint(state) is True

    def test_should_checkpoint_false_before_interval(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        manager = CheckpointManager(persistence, auto_checkpoint_interval=10)
        state = AgentState(agent_id="chk_agent3")
        state.iteration = 5
        assert manager.should_checkpoint(state) is False

    def test_should_checkpoint_tracks_last_iteration(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        manager = CheckpointManager(persistence, auto_checkpoint_interval=5)
        state = AgentState(agent_id="chk_agent4")
        state.iteration = 5
        assert manager.should_checkpoint(state) is True
        # After creating checkpoint, should not trigger again immediately
        manager.create_checkpoint(state)
        state.iteration = 6
        assert manager.should_checkpoint(state) is False
        # Should trigger again at iteration 10
        state.iteration = 10
        assert manager.should_checkpoint(state) is True

    def test_create_checkpoint_saves_file(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        manager = CheckpointManager(persistence, auto_checkpoint_interval=5)
        state = AgentState(agent_id="create_agent", iteration=3)
        filepath = manager.create_checkpoint(state, checkpoint_name="manual_cp")
        assert os.path.exists(filepath)
        assert "manual_cp" in filepath

    def test_auto_checkpoint_creates_when_needed(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        manager = CheckpointManager(persistence, auto_checkpoint_interval=3)
        state = AgentState(agent_id="auto_agent")
        state.iteration = 3
        filepath = manager.auto_checkpoint(state)
        assert filepath is not None
        assert os.path.exists(filepath)

    def test_auto_checkpoint_returns_none_when_not_needed(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        manager = CheckpointManager(persistence, auto_checkpoint_interval=10)
        state = AgentState(agent_id="auto_agent2")
        state.iteration = 2
        result = manager.auto_checkpoint(state)
        assert result is None

    def test_restore_from_checkpoint_with_path(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        manager = CheckpointManager(persistence, auto_checkpoint_interval=5)
        original = AgentState(agent_id="restore_agent", iteration=42)
        filepath = manager.create_checkpoint(original, checkpoint_name="restore_me")

        restored = manager.restore_from_checkpoint("restore_agent", filepath)
        assert restored is not None
        assert restored.iteration == 42

    def test_restore_from_checkpoint_latest(self, temp_dir):
        persistence = AgentStatePersistence(persist_dir=temp_dir)
        manager = CheckpointManager(persistence, auto_checkpoint_interval=1)
        state = AgentState(agent_id="latest_agent")

        state.iteration = 1
        manager.create_checkpoint(state, checkpoint_name="cp1")
        state.iteration = 5
        manager.create_checkpoint(state, checkpoint_name="cp2")

        restored = manager.restore_from_checkpoint("latest_agent")
        assert restored is not None
        assert restored.iteration == 5
