"""Tests for trajectory-monitor MCP server."""

import json
import tempfile
from pathlib import Path

import pytest

from trajectory_monitor.parser import JobState, RunEntry
from trajectory_monitor.mcp_server import (
    analyze_jobs,
    analyze_session,
    check_job,
    get_recommendations,
    get_score,
    list_signals,
)


@pytest.fixture
def tmp_workspace(tmp_path):
    """Create a temp workspace with jobs.json and runs."""
    jobs_json = tmp_path / "jobs.json"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    jobs_data = {
        "version": 1,
        "jobs": [
            {
                "id": "job-healthy-001",
                "name": "healthy-job",
                "description": "A healthy job",
                "enabled": True,
                "state": {
                    "consecutiveErrors": 0,
                    "lastRunStatus": "ok",
                    "lastDurationMs": 50000,
                },
            },
            {
                "id": "job-crashing-002",
                "name": "crashing-job",
                "description": "A crashing job",
                "enabled": True,
                "state": {
                    "consecutiveErrors": 3,
                    "lastRunStatus": "error",
                    "lastDurationMs": 10000,
                },
            },
        ],
    }
    jobs_json.write_text(json.dumps(jobs_data))

    run_data = [
        # Healthy: 3 OK runs
        {"ts": 1000, "jobId": "job-healthy-001", "action": "finished", "status": "ok",
         "durationMs": 50000, "model": "glm-5", "summary": "Analyzed dependency tree",
         "usage": {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500}},
        {"ts": 2000, "jobId": "job-healthy-001", "action": "finished", "status": "ok",
         "durationMs": 52000, "model": "glm-5", "summary": "Scanned codebase for vulnerabilities",
         "usage": {"input_tokens": 1100, "output_tokens": 550, "total_tokens": 1650}},
        {"ts": 3000, "jobId": "job-healthy-001", "action": "finished", "status": "ok",
         "durationMs": 48000, "model": "glm-5", "summary": "Generated documentation",
         "usage": {"input_tokens": 1050, "output_tokens": 520, "total_tokens": 1570}},
        # Crashing: 3 errors
        {"ts": 1000, "jobId": "job-crashing-002", "action": "finished", "status": "error",
         "durationMs": 10000, "error": "Write to /tmp/file.txt failed: permission denied",
         "usage": {"input_tokens": 500, "output_tokens": 200, "total_tokens": 700}},
        {"ts": 2000, "jobId": "job-crashing-002", "action": "finished", "status": "error",
         "durationMs": 12000, "error": "Write to /tmp/other.txt failed: permission denied",
         "usage": {"input_tokens": 600, "output_tokens": 250, "total_tokens": 850}},
        {"ts": 3000, "jobId": "job-crashing-002", "action": "finished", "status": "error",
         "durationMs": 11000, "error": "Write to /tmp/data.txt failed: permission denied",
         "usage": {"input_tokens": 550, "output_tokens": 230, "total_tokens": 780}},
    ]

    run_file = runs_dir / "test-runs.jsonl"
    with open(run_file, "w") as f:
        for entry in run_data:
            f.write(json.dumps(entry) + "\n")

    return tmp_path


# ── analyze_jobs ──────────────────────────────────────────────────


class TestAnalyzeJobs:
    def test_analyze_jobs_returns_json(self, tmp_workspace):
        result = analyze_jobs(
            jobs_json_path=str(tmp_workspace / "jobs.json"),
            runs_dir=str(tmp_workspace / "runs"),
        )
        data = json.loads(result)
        assert "summary" in data
        assert data["summary"]["jobs_analyzed"] == 2
        assert len(data["jobs"]) == 2

    def test_analyze_jobs_missing_path(self):
        result = analyze_jobs(jobs_json_path="/nonexistent/path.json")
        data = json.loads(result)
        assert "error" in data


# ── check_job ─────────────────────────────────────────────────────


class TestCheckJob:
    def test_check_existing_job(self, tmp_workspace):
        result = check_job(
            job_name="crashing-job",
            jobs_json_path=str(tmp_workspace / "jobs.json"),
            runs_dir=str(tmp_workspace / "runs"),
        )
        data = json.loads(result)
        assert data["job"] == "crashing-job"
        assert data["score"] < 50
        assert len(data["signals"]) >= 1

    def test_check_healthy_job(self, tmp_workspace):
        result = check_job(
            job_name="healthy-job",
            jobs_json_path=str(tmp_workspace / "jobs.json"),
            runs_dir=str(tmp_workspace / "runs"),
        )
        data = json.loads(result)
        assert data["job"] == "healthy-job"
        assert data["score"] >= 60

    def test_check_nonexistent_job(self, tmp_workspace):
        result = check_job(
            job_name="nonexistent",
            jobs_json_path=str(tmp_workspace / "jobs.json"),
        )
        data = json.loads(result)
        assert "error" in data


# ── get_score ─────────────────────────────────────────────────────


class TestGetScore:
    def test_get_score_existing(self, tmp_workspace):
        result = get_score(
            job_name="healthy-job",
            jobs_json_path=str(tmp_workspace / "jobs.json"),
            runs_dir=str(tmp_workspace / "runs"),
        )
        data = json.loads(result)
        assert "score" in data
        assert "grade" in data
        assert "breakdown" in data
        assert "signal_penalties" in data
        assert data["job"] == "healthy-job"

    def test_get_score_nonexistent(self, tmp_workspace):
        result = get_score(
            job_name="ghost-job",
            jobs_json_path=str(tmp_workspace / "jobs.json"),
        )
        data = json.loads(result)
        assert "error" in data


# ── get_recommendations ──────────────────────────────────────────


class TestGetRecommendations:
    def test_get_recommendations_existing_job(self, tmp_workspace):
        result = get_recommendations(
            job_name="crashing-job",
            jobs_json_path=str(tmp_workspace / "jobs.json"),
            runs_dir=str(tmp_workspace / "runs"),
        )
        data = json.loads(result)
        assert data["job"] == "crashing-job"
        assert data["score"] < 50
        assert len(data["recommendations"]) >= 1
        assert any(r["signal_kind"] == "crash_repeat" for r in data["recommendations"])

    def test_get_recommendations_all_jobs(self, tmp_workspace):
        result = get_recommendations(
            jobs_json_path=str(tmp_workspace / "jobs.json"),
            runs_dir=str(tmp_workspace / "runs"),
        )
        data = json.loads(result)
        assert data["count"] >= 1
        assert "crashing-job" in data["jobs"]
        assert "healthy-job" not in data["jobs"]

    def test_get_recommendations_nonexistent_job(self, tmp_workspace):
        result = get_recommendations(
            job_name="ghost-job",
            jobs_json_path=str(tmp_workspace / "jobs.json"),
        )
        data = json.loads(result)
        assert "error" in data


# ── analyze_session ───────────────────────────────────────────────


class TestAnalyzeSession:
    def test_analyze_session_from_text(self):
        transcript = "\n".join([
            json.dumps({"ts": 1000, "jobId": "test", "action": "finished", "status": "ok",
                        "durationMs": 30000, "summary": "Added feature A",
                        "usage": {"input_tokens": 500, "output_tokens": 300, "total_tokens": 800}}),
            json.dumps({"ts": 2000, "jobId": "test", "action": "finished", "status": "ok",
                        "durationMs": 32000, "summary": "Implemented feature B",
                        "usage": {"input_tokens": 550, "output_tokens": 320, "total_tokens": 870}}),
            json.dumps({"ts": 3000, "jobId": "test", "action": "finished", "status": "ok",
                        "durationMs": 28000, "summary": "Created feature C",
                        "usage": {"input_tokens": 520, "output_tokens": 310, "total_tokens": 830}}),
        ])
        result = analyze_session(transcript, job_name="test-session")
        data = json.loads(result)
        assert data["session"] == "test-session"
        assert data["runs_analyzed"] == 3
        assert "score" in data
        assert "signals" in data
        assert "recommendations" in data
        # Should detect feature_race with 3 consecutive feature adds
        signal_kinds = [s["kind"] for s in data["signals"]]
        recommendation_kinds = [r["signal_kind"] for r in data["recommendations"]]
        assert "feature_race" in signal_kinds
        assert "feature_race" in recommendation_kinds

    def test_analyze_session_from_file(self, tmp_path):
        jsonl_file = tmp_path / "session.jsonl"
        entries = [
            {"ts": i * 1000, "jobId": "file-test", "action": "finished", "status": "ok",
             "durationMs": 30000, "summary": f"Run {i}",
             "usage": {"input_tokens": 500, "output_tokens": 300, "total_tokens": 800}}
            for i in range(4)
        ]
        jsonl_file.write_text("\n".join(json.dumps(e) for e in entries))

        result = analyze_session(str(jsonl_file), job_name="file-session")
        data = json.loads(result)
        assert data["runs_analyzed"] == 4
        assert data["session"] == "file-session"

    def test_analyze_session_with_workspace_check(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        transcript = "\n".join([
            json.dumps({
                "ts": 1000,
                "jobId": "ws",
                "action": "finished",
                "status": "ok",
                "durationMs": 20000,
                "summary": "Created src/parser.py, docs/guide.md and tests/test_parser.py",
                "usage": {"input_tokens": 400, "output_tokens": 200, "total_tokens": 600},
            }),
            json.dumps({
                "ts": 2000,
                "jobId": "ws",
                "action": "finished",
                "status": "ok",
                "durationMs": 18000,
                "summary": "Validated parser behavior with pytest",
                "usage": {"input_tokens": 420, "output_tokens": 210, "total_tokens": 630},
            }),
        ])

        result = analyze_session(
            transcript,
            job_name="workspace-session",
            workspace_path=str(workspace),
        )
        data = json.loads(result)
        assert data["workspace_check"]["enabled"] is True
        assert data["workspace_check"]["exists"] is True
        missing_on_disk = [
            s for s in data["signals"]
            if s["kind"] == "hallucination_pattern" and s["details"].get("type") == "missing_on_disk"
        ]
        assert len(missing_on_disk) == 1
        assert data["score"] < 75

    def test_analyze_session_empty(self):
        result = analyze_session("", job_name="empty")
        data = json.loads(result)
        assert "error" in data

    def test_analyze_session_with_errors(self):
        transcript = "\n".join([
            json.dumps({"ts": 1000, "jobId": "err", "action": "finished", "status": "error",
                        "durationMs": 5000, "error": "Failed: timeout exceeded at step 100",
                        "usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}}),
            json.dumps({"ts": 2000, "jobId": "err", "action": "finished", "status": "error",
                        "durationMs": 6000, "error": "Failed: timeout exceeded at step 200",
                        "usage": {"input_tokens": 120, "output_tokens": 60, "total_tokens": 180}}),
            json.dumps({"ts": 3000, "jobId": "err", "action": "finished", "status": "error",
                        "durationMs": 5500, "error": "Failed: timeout exceeded at step 300",
                        "usage": {"input_tokens": 110, "output_tokens": 55, "total_tokens": 165}}),
        ])
        result = analyze_session(transcript, job_name="error-session")
        data = json.loads(result)
        assert data["errors"] == 3
        signal_kinds = [s["kind"] for s in data["signals"]]
        recommendation_kinds = [r["signal_kind"] for r in data["recommendations"]]
        assert "crash_repeat" in signal_kinds
        assert "crash_repeat" in recommendation_kinds


# ── list_signals ──────────────────────────────────────────────────


class TestListSignals:
    def test_list_signals(self):
        result = list_signals()
        data = json.loads(result)
        assert "detectors" in data
        assert data["count"] >= 8  # 8 detectors
        names = [d["name"] for d in data["detectors"]]
        assert "detect_crash_repeat" in names
        assert "detect_feature_race" in names
        assert "detect_hallucination_pattern" in names
        assert "detect_loop" in names
