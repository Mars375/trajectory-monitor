"""Tests for tools/analyze_openclaw.py — Forge report generator."""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure src is importable
REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import the module by exec'ing it (since it's in tools/)
_TOOL_PATH = REPO_ROOT / "tools" / "analyze_openclaw.py"
_mod_ns: dict = {}
exec(open(_TOOL_PATH).read(), _mod_ns)

filter_forge_jobs = _mod_ns["filter_forge_jobs"]
generate_forge_report = _mod_ns["generate_forge_report"]
_find_openclaw_paths = _mod_ns["_find_openclaw_paths"]
_fmt_duration = _mod_ns["_fmt_duration"]
_fmt_tokens = _mod_ns["_fmt_tokens"]

from trajectory_monitor.parser import JobState, RunEntry
from trajectory_monitor.scorer import score_all
from trajectory_monitor.signals import analyze_all


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def sample_jobs():
    """Create sample jobs including forge and non-forge."""
    return [
        JobState(
            job_id="forge-imagine-001",
            name="forge-imagine",
            enabled=True,
            consecutive_errors=2,
            last_run_status="error",
            last_duration_ms=290000,
            runs=[
                RunEntry(ts=1000, job_id="forge-imagine-001", action="finished",
                         status="error", duration_ms=290000,
                         error="Timeout exceeded", summary="",
                         input_tokens=1000, output_tokens=500, total_tokens=1500),
                RunEntry(ts=2000, job_id="forge-imagine-001", action="finished",
                         status="error", duration_ms=300000,
                         error="Timeout exceeded", summary="",
                         input_tokens=1100, output_tokens=600, total_tokens=1700),
            ],
        ),
        JobState(
            job_id="forge-chantier-memos-002",
            name="forge-chantier-memos",
            enabled=True,
            consecutive_errors=0,
            last_run_status="ok",
            last_duration_ms=900000,
            runs=[
                RunEntry(ts=1000, job_id="forge-chantier-memos-002", action="finished",
                         status="ok", duration_ms=900000,
                         summary="Added recall filters and validated with tests",
                         input_tokens=2000, output_tokens=1500, total_tokens=3500),
                RunEntry(ts=2000, job_id="forge-chantier-memos-002", action="finished",
                         status="ok", duration_ms=870000,
                         summary="Implemented tag deduplication, verified",
                         input_tokens=2100, output_tokens=1400, total_tokens=3500),
            ],
        ),
        JobState(
            job_id="other-job-003",
            name="some-other-cron",
            enabled=True,
            consecutive_errors=0,
            last_run_status="ok",
            last_duration_ms=50000,
            runs=[
                RunEntry(ts=1000, job_id="other-job-003", action="finished",
                         status="ok", duration_ms=50000,
                         summary="Ran cleanup successfully",
                         input_tokens=500, output_tokens=200, total_tokens=700),
            ],
        ),
    ]


# ── Filter tests ──────────────────────────────────────────────────


class TestFilterForgeJobs:
    def test_filters_forge_jobs(self, sample_jobs):
        result = filter_forge_jobs(sample_jobs)
        names = [j.name for j in result]
        assert "forge-imagine" in names
        assert "forge-chantier-memos" in names
        assert "some-other-cron" not in names

    def test_empty_list(self):
        assert filter_forge_jobs([]) == []

    def test_no_forge_jobs(self):
        jobs = [JobState(job_id="x", name="other-job")]
        assert filter_forge_jobs(jobs) == []


# ── Report generation tests ──────────────────────────────────────


class TestGenerateForgeReport:
    def test_generates_report(self, sample_jobs):
        signals = analyze_all(sample_jobs)
        scores = score_all(sample_jobs)
        report = generate_forge_report(sample_jobs, filter_forge_jobs(sample_jobs), signals, scores)

        assert "# 🔍 Forge Trajectory Report" in report
        assert "forge-imagine" in report
        assert "forge-chantier-memos" in report
        # Non-forge job should appear in context section
        assert "Non-Forge" in report

    def test_report_has_summary(self, sample_jobs):
        signals = analyze_all(sample_jobs)
        scores = score_all(sample_jobs)
        report = generate_forge_report(sample_jobs, filter_forge_jobs(sample_jobs), signals, scores)

        assert "📊 Summary" in report
        assert "Average quality score" in report

    def test_report_has_score_table(self, sample_jobs):
        signals = analyze_all(sample_jobs)
        scores = score_all(sample_jobs)
        report = generate_forge_report(sample_jobs, filter_forge_jobs(sample_jobs), signals, scores)

        assert "🏆 Job Scores" in report
        assert "| Job |" in report

    def test_report_has_recommendations(self, sample_jobs):
        signals = analyze_all(sample_jobs)
        scores = score_all(sample_jobs)
        report = generate_forge_report(sample_jobs, filter_forge_jobs(sample_jobs), signals, scores)

        # forge-imagine should be failing → recommendations section
        assert "💡 Recommendations" in report
        assert "forge-imagine" in report

    def test_report_has_run_details(self, sample_jobs):
        signals = analyze_all(sample_jobs)
        scores = score_all(sample_jobs)
        report = generate_forge_report(sample_jobs, filter_forge_jobs(sample_jobs), signals, scores)

        assert "📋 Run Details" in report

    def test_empty_jobs(self):
        report = generate_forge_report([], [], {}, [])
        assert "Forge Trajectory Report" in report

    def test_no_forge_jobs_report(self):
        jobs = [JobState(job_id="x", name="other")]
        signals = analyze_all(jobs)
        scores = score_all(jobs)
        report = generate_forge_report(jobs, [], signals, scores)
        # Should still generate a valid report, just no forge jobs
        assert "Forge Trajectory Report" in report


# ── Formatting helpers ───────────────────────────────────────────


class TestFormatting:
    def test_fmt_duration_seconds(self):
        assert _fmt_duration(30000) == "30s"

    def test_fmt_duration_minutes(self):
        assert _fmt_duration(120000) == "2.0min"

    def test_fmt_duration_hours(self):
        assert _fmt_duration(3600000) == "1.0h"

    def test_fmt_duration_zero(self):
        assert _fmt_duration(0) == "N/A"

    def test_fmt_tokens_small(self):
        assert _fmt_tokens(500) == "500"

    def test_fmt_tokens_k(self):
        assert _fmt_tokens(1500) == "1.5k"

    def test_fmt_tokens_m(self):
        assert _fmt_tokens(1500000) == "1.5M"


# ── CLI integration test ────────────────────────────────────────


class TestCLIIntegration:
    def test_main_with_explicit_paths(self, tmp_path):
        """Test the CLI main() function with a temp workspace."""
        jobs_json = tmp_path / "jobs.json"
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        output_file = tmp_path / "report.md"

        jobs_data = {
            "version": 1,
            "jobs": [
                {
                    "id": "forge-test-001",
                    "name": "forge-test-cron",
                    "enabled": True,
                    "state": {
                        "consecutiveErrors": 0,
                        "lastRunStatus": "ok",
                        "lastDurationMs": 50000,
                    },
                },
            ],
        }
        jobs_json.write_text(json.dumps(jobs_data))

        # Create a run transcript
        run_file = runs_dir / "test.jsonl"
        run_file.write_text(json.dumps({
            "ts": 1000, "jobId": "forge-test-001", "action": "finished",
            "status": "ok", "durationMs": 50000, "summary": "Test run OK",
            "usage": {"input_tokens": 500, "output_tokens": 200, "total_tokens": 700},
        }) + "\n")

        # Simulate CLI
        old_argv = sys.argv
        try:
            sys.argv = [
                "analyze_openclaw.py",
                "--jobs-json", str(jobs_json),
                "--runs-dir", str(runs_dir),
                "--output", str(output_file),
            ]
            result = _mod_ns["main"]()
        finally:
            sys.argv = old_argv

        assert result == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "forge-test-cron" in content
        assert "Forge Trajectory Report" in content

    def test_main_json_mode(self, tmp_path):
        """Test JSON output mode."""
        jobs_json = tmp_path / "jobs.json"
        runs_dir = tmp_path / "runs"
        runs_dir.mkdir()
        output_file = tmp_path / "report.json"

        jobs_data = {
            "version": 1,
            "jobs": [
                {
                    "id": "forge-test-002",
                    "name": "forge-json-test",
                    "enabled": True,
                    "state": {"consecutiveErrors": 0, "lastRunStatus": "ok", "lastDurationMs": 30000},
                },
            ],
        }
        jobs_json.write_text(json.dumps(jobs_data))

        old_argv = sys.argv
        try:
            sys.argv = [
                "analyze_openclaw.py",
                "--jobs-json", str(jobs_json),
                "--runs-dir", str(runs_dir),
                "--json",
                "--output", str(output_file),
            ]
            result = _mod_ns["main"]()
        finally:
            sys.argv = old_argv

        assert result == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert "summary" in data
        assert "jobs" in data

    def test_main_missing_jobs_json(self):
        """Test error when jobs.json doesn't exist."""
        old_argv = sys.argv
        try:
            sys.argv = ["analyze_openclaw.py", "--jobs-json", "/nonexistent/jobs.json"]
            result = _mod_ns["main"]()
        finally:
            sys.argv = old_argv

        assert result == 1
