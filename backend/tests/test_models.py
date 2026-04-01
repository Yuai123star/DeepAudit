"""
Tests for SQLAlchemy model computed properties.

Covers:
- AgentTask.progress_percentage: phase-weighted progress with edge cases
- AgentFinding.generate_fingerprint: deterministic SHA-256 fingerprint generation
"""

import hashlib

import pytest

from app.models.agent_task import (
    AgentFinding,
    AgentTask,
    AgentTaskPhase,
    AgentTaskStatus,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_task(
    status: str = AgentTaskStatus.RUNNING,
    current_phase: str | None = None,
    total_files: int = 0,
    indexed_files: int = 0,
    analyzed_files: int = 0,
) -> AgentTask:
    """Build an AgentTask instance with only the fields we need for progress tests."""
    return AgentTask(
        status=status,
        current_phase=current_phase,
        total_files=total_files,
        indexed_files=indexed_files,
        analyzed_files=analyzed_files,
    )


def _make_finding(
    vulnerability_type: str = "sql_injection",
    file_path: str | None = None,
    line_start: int | None = None,
    function_name: str | None = None,
    code_snippet: str | None = None,
) -> AgentFinding:
    """Build an AgentFinding instance without needing a database session."""
    return AgentFinding(
        vulnerability_type=vulnerability_type,
        file_path=file_path,
        line_start=line_start,
        function_name=function_name,
        code_snippet=code_snippet,
    )


# ===================================================================
# AgentTask.progress_percentage
# ===================================================================


class TestProgressPercentage:
    """Tests for AgentTask.progress_percentage computed property."""

    # -- Terminal states ---------------------------------------------------

    def test_completed_returns_100(self):
        task = _make_task(status=AgentTaskStatus.COMPLETED)
        assert task.progress_percentage == 100.0

    def test_failed_returns_0(self):
        task = _make_task(status=AgentTaskStatus.FAILED)
        assert task.progress_percentage == 0.0

    def test_cancelled_returns_0(self):
        task = _make_task(status=AgentTaskStatus.CANCELLED)
        assert task.progress_percentage == 0.0

    # -- No phase set (no phase matches, all weights accumulate) -----------

    def test_no_phase_accumulates_all_weights(self):
        """When current_phase is None the for-loop never breaks,
        so all 6 phase weights are summed: 5+15+10+50+15+5 = 100,
        then clamped to 99.0."""
        task = _make_task(
            status=AgentTaskStatus.RUNNING,
            current_phase=None,
        )
        assert task.progress_percentage == 99.0

    # -- Each individual phase (generic 0.5 branch) ------------------------

    def test_planning_phase_half_progress(self):
        # Planning is first phase, weight=5, gets 5*0.5 = 2.5%
        task = _make_task(
            current_phase=AgentTaskPhase.PLANNING,
        )
        assert task.progress_percentage == pytest.approx(2.5)

    def test_reconnaissance_phase(self):
        # planning(5) + indexing(15) done = 20, then recon(10)*0.5 = 5, total 25.0
        task = _make_task(
            current_phase=AgentTaskPhase.RECONNAISSANCE,
        )
        assert task.progress_percentage == pytest.approx(25.0)

    def test_verification_phase(self):
        # planning(5)+indexing(15)+recon(10)+analysis(50) done = 80, then 15*0.5
        task = _make_task(
            current_phase=AgentTaskPhase.VERIFICATION,
        )
        assert task.progress_percentage == pytest.approx(87.5)

    def test_reporting_phase(self):
        # All prior done: 5+15+10+50+15 = 95, then 5*0.5
        task = _make_task(
            current_phase=AgentTaskPhase.REPORTING,
        )
        assert task.progress_percentage == pytest.approx(97.5)

    # -- INDEXING phase: uses indexed_files / total_files ------------------

    def test_indexing_phase_with_files(self):
        # planning(5) done, indexing 50%: 5 + 15*0.5 = 12.5
        task = _make_task(
            current_phase=AgentTaskPhase.INDEXING,
            total_files=100,
            indexed_files=50,
        )
        assert task.progress_percentage == pytest.approx(12.5)

    def test_indexing_phase_zero_files(self):
        """total_files=0 falls into the generic 0.5 branch (avoids ZeroDivisionError)."""
        task = _make_task(
            current_phase=AgentTaskPhase.INDEXING,
            total_files=0,
            indexed_files=0,
        )
        # 5 + 15*0.5 = 12.5
        assert task.progress_percentage == pytest.approx(12.5)

    def test_indexing_phase_all_indexed(self):
        # planning(5) + indexing fully done: 5 + 15*1.0 = 20.0
        task = _make_task(
            current_phase=AgentTaskPhase.INDEXING,
            total_files=200,
            indexed_files=200,
        )
        assert task.progress_percentage == pytest.approx(20.0)

    # -- ANALYSIS phase: uses analyzed_files / total_files -----------------

    def test_analysis_phase_with_files(self):
        # planning(5)+indexing(15)+recon(10) = 30 done, analysis 60%: 30 + 50*0.6 = 60.0
        task = _make_task(
            current_phase=AgentTaskPhase.ANALYSIS,
            total_files=100,
            analyzed_files=60,
        )
        assert task.progress_percentage == pytest.approx(60.0)

    def test_analysis_phase_zero_files(self):
        """total_files=0 falls into the generic 0.5 branch."""
        task = _make_task(
            current_phase=AgentTaskPhase.ANALYSIS,
            total_files=0,
            analyzed_files=0,
        )
        # 30 + 50*0.5 = 55.0
        assert task.progress_percentage == pytest.approx(55.0)

    # -- Cap at 99.0 -------------------------------------------------------

    def test_never_exceeds_99(self):
        """Even if computed weight > 99, the result is clamped."""
        task = _make_task(
            current_phase=None,  # accumulates all weights = 100, clamped to 99
        )
        assert task.progress_percentage == 99.0


# ===================================================================
# AgentFinding.generate_fingerprint
# ===================================================================


class TestGenerateFingerprint:
    """Tests for AgentFinding.generate_fingerprint deterministic hash."""

    def _expected_hash(self, vuln_type, file_path, line_start, func_name, snippet):
        components = [
            vuln_type or "",
            file_path or "",
            str(line_start or 0),
            func_name or "",
            (snippet or "")[:200],
        ]
        content = "|".join(components)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def test_basic_fingerprint(self):
        f = _make_finding(
            vulnerability_type="sql_injection",
            file_path="app/api/auth.py",
            line_start=42,
            function_name="login",
            code_snippet="query = f'SELECT * FROM users WHERE id={user_id}'",
        )
        expected = self._expected_hash("sql_injection", "app/api/auth.py", 42, "login",
                                       "query = f'SELECT * FROM users WHERE id={user_id}'")
        assert f.generate_fingerprint() == expected

    def test_deterministic(self):
        """Same inputs always produce the same fingerprint."""
        kwargs = dict(
            vulnerability_type="xss",
            file_path="views.py",
            line_start=10,
            function_name="render",
            code_snippet="<div>{{ user_input }}</div>",
        )
        f1 = _make_finding(**kwargs)
        f2 = _make_finding(**kwargs)
        assert f1.generate_fingerprint() == f2.generate_fingerprint()

    def test_different_vuln_type_different_fingerprint(self):
        base = dict(file_path="a.py", line_start=1, function_name="f", code_snippet="x")
        f1 = _make_finding(vulnerability_type="sql_injection", **base)
        f2 = _make_finding(vulnerability_type="xss", **base)
        assert f1.generate_fingerprint() != f2.generate_fingerprint()

    def test_different_file_path_different_fingerprint(self):
        base = dict(vulnerability_type="xss", line_start=1, function_name="f", code_snippet="x")
        f1 = _make_finding(file_path="a.py", **base)
        f2 = _make_finding(file_path="b.py", **base)
        assert f1.generate_fingerprint() != f2.generate_fingerprint()

    def test_different_line_start_different_fingerprint(self):
        base = dict(vulnerability_type="xss", file_path="a.py", function_name="f", code_snippet="x")
        f1 = _make_finding(line_start=10, **base)
        f2 = _make_finding(line_start=20, **base)
        assert f1.generate_fingerprint() != f2.generate_fingerprint()

    def test_none_fields_use_defaults(self):
        """None fields resolve to empty string / 0."""
        f = _make_finding(
            vulnerability_type="command_injection",
            file_path=None,
            line_start=None,
            function_name=None,
            code_snippet=None,
        )
        expected = self._expected_hash("command_injection", None, None, None, None)
        assert f.generate_fingerprint() == expected

    def test_long_snippet_truncated_to_200(self):
        """Code snippets longer than 200 chars are truncated before hashing."""
        long_snippet = "A" * 300
        f = _make_finding(
            vulnerability_type="rce",
            file_path="run.py",
            line_start=1,
            function_name="exec_cmd",
            code_snippet=long_snippet,
        )
        expected = self._expected_hash("rce", "run.py", 1, "exec_cmd", long_snippet)
        assert f.generate_fingerprint() == expected
        # Also verify the truncation matters: a 201-char snippet differs from 200
        f_short = _make_finding(
            vulnerability_type="rce",
            file_path="run.py",
            line_start=1,
            function_name="exec_cmd",
            code_snippet="A" * 200,
        )
        assert f.generate_fingerprint() == f_short.generate_fingerprint()

    def test_fingerprint_length_is_16(self):
        f = _make_finding(vulnerability_type="xss", file_path="a.py")
        assert len(f.generate_fingerprint()) == 16
