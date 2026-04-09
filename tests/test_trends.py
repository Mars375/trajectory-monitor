"""Trend analysis tests for trajectory-monitor."""

from __future__ import annotations

import json

from trajectory_monitor.mcp_server import analyze_session, check_job, get_score
from trajectory_monitor.parser import JobState, RunEntry
from trajectory_monitor.report import generate_json_report
from trajectory_monitor.scorer import analyze_trend


def _run(ts: int, status: str, summary: str = "", error: str = "", duration_ms: int = 10000, total_tokens: int = 500) -> RunEntry:
    return RunEntry(
        ts=ts,
        job_id="job-1",
        action="finished",
        status=status,
        duration_ms=duration_ms,
        summary=summary,
        error=error,
        total_tokens=total_tokens,
        output_tokens=max(total_tokens // 2, 1),
        input_tokens=max(total_tokens // 2, 1),
    )


def test_analyze_trend_improving():
    job = JobState(
        job_id="job-1",
        name="trend-improving",
        consecutive_errors=0,
        last_run_status="ok",
        last_duration_ms=9000,
        runs=[
            _run(1000, "error", error="Write to /tmp/a failed: permission denied", duration_ms=7000, total_tokens=300),
            _run(2000, "error", error="Write to /tmp/b failed: permission denied", duration_ms=7200, total_tokens=320),
            _run(3000, "ok", summary="Validated parser with pytest", duration_ms=9000, total_tokens=450),
            _run(4000, "ok", summary="Validated scoring and generated report", duration_ms=9500, total_tokens=470),
        ],
    )

    trend = analyze_trend(job)
    assert trend.direction == "improving"
    assert trend.score_delta > 0
    assert trend.previous_score is not None
    assert trend.recent_score is not None


def test_analyze_trend_regressing():
    job = JobState(
        job_id="job-1",
        name="trend-regressing",
        consecutive_errors=2,
        last_run_status="error",
        last_duration_ms=7000,
        runs=[
            _run(1000, "ok", summary="Validated parser with pytest", duration_ms=9000, total_tokens=450),
            _run(2000, "ok", summary="Validated scoring and generated report", duration_ms=9500, total_tokens=470),
            _run(3000, "error", error="Write to /tmp/a failed: permission denied", duration_ms=7000, total_tokens=300),
            _run(4000, "error", error="Write to /tmp/b failed: permission denied", duration_ms=7200, total_tokens=320),
        ],
    )

    trend = analyze_trend(job)
    assert trend.direction == "regressing"
    assert trend.score_delta < 0


def test_analyze_trend_insufficient_data():
    job = JobState(
        job_id="job-1",
        name="trend-short",
        runs=[
            _run(1000, "ok", summary="Run 1"),
            _run(2000, "ok", summary="Run 2"),
            _run(3000, "ok", summary="Run 3"),
        ],
    )

    trend = analyze_trend(job)
    assert trend.direction == "insufficient_data"
    assert trend.previous_score is None
    assert trend.recent_score is None


def test_generate_json_report_includes_trend_summary():
    job = JobState(
        job_id="job-1",
        name="trend-json",
        runs=[
            _run(1000, "error", error="Write to /tmp/a failed: permission denied"),
            _run(2000, "error", error="Write to /tmp/b failed: permission denied"),
            _run(3000, "ok", summary="Validated parser with pytest"),
            _run(4000, "ok", summary="Validated scoring and generated report"),
        ],
    )

    report = json.loads(generate_json_report([job]))
    assert "trend_counts" in report["summary"]
    assert report["jobs"][0]["trend"]["direction"] == "improving"


def test_mcp_tools_include_trend(tmp_path):
    jobs_json = tmp_path / "jobs.json"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    jobs_json.write_text(json.dumps({
        "version": 1,
        "jobs": [
            {
                "id": "job-1",
                "name": "trend-job",
                "enabled": True,
                "state": {
                    "consecutiveErrors": 0,
                    "lastRunStatus": "ok",
                    "lastDurationMs": 9500,
                },
            }
        ],
    }))

    entries = [
        {"ts": 1000, "jobId": "job-1", "action": "finished", "status": "error", "durationMs": 7000, "error": "Write to /tmp/a failed: permission denied", "usage": {"input_tokens": 150, "output_tokens": 150, "total_tokens": 300}},
        {"ts": 2000, "jobId": "job-1", "action": "finished", "status": "error", "durationMs": 7200, "error": "Write to /tmp/b failed: permission denied", "usage": {"input_tokens": 160, "output_tokens": 160, "total_tokens": 320}},
        {"ts": 3000, "jobId": "job-1", "action": "finished", "status": "ok", "durationMs": 9000, "summary": "Validated parser with pytest", "usage": {"input_tokens": 225, "output_tokens": 225, "total_tokens": 450}},
        {"ts": 4000, "jobId": "job-1", "action": "finished", "status": "ok", "durationMs": 9500, "summary": "Validated scoring and generated report", "usage": {"input_tokens": 235, "output_tokens": 235, "total_tokens": 470}},
    ]
    (runs_dir / "runs.jsonl").write_text("\n".join(json.dumps(entry) for entry in entries))

    check_data = json.loads(check_job("trend-job", str(jobs_json), str(runs_dir)))
    score_data = json.loads(get_score("trend-job", str(jobs_json), str(runs_dir)))

    assert check_data["trend"]["direction"] == "improving"
    assert score_data["trend"]["direction"] == "improving"


def test_analyze_session_includes_trend():
    transcript = "\n".join([
        json.dumps({"ts": 1000, "jobId": "test", "action": "finished", "status": "error", "durationMs": 7000, "error": "Write to /tmp/a failed: permission denied", "usage": {"input_tokens": 150, "output_tokens": 150, "total_tokens": 300}}),
        json.dumps({"ts": 2000, "jobId": "test", "action": "finished", "status": "error", "durationMs": 7200, "error": "Write to /tmp/b failed: permission denied", "usage": {"input_tokens": 160, "output_tokens": 160, "total_tokens": 320}}),
        json.dumps({"ts": 3000, "jobId": "test", "action": "finished", "status": "ok", "durationMs": 9000, "summary": "Validated parser with pytest", "usage": {"input_tokens": 225, "output_tokens": 225, "total_tokens": 450}}),
        json.dumps({"ts": 4000, "jobId": "test", "action": "finished", "status": "ok", "durationMs": 9500, "summary": "Validated scoring and generated report", "usage": {"input_tokens": 235, "output_tokens": 235, "total_tokens": 470}}),
    ])

    data = json.loads(analyze_session(transcript, job_name="trend-session"))
    assert data["trend"]["direction"] == "improving"
