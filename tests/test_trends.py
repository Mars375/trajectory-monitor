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


# ── Regression-trend signal tests ──────────────────────────────

from trajectory_monitor.signals import detect_regression_trend, analyze_job


def test_regression_trend_signal_regressing():
    """A regressing job should emit a regression_trend signal."""
    job = JobState(
        job_id="job-1",
        name="regressing-job",
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
    signal = detect_regression_trend(job)
    assert signal is not None
    assert signal.kind == "regression_trend"
    assert signal.severity.value in ("warning", "critical")
    assert "Score dropping" in signal.message
    assert signal.details["score_delta"] < 0


def test_regression_trend_signal_improving_no_signal():
    """An improving job should NOT emit a regression_trend signal."""
    job = JobState(
        job_id="job-1",
        name="improving-job",
        consecutive_errors=0,
        last_run_status="ok",
        last_duration_ms=9000,
        runs=[
            _run(1000, "error", error="Write failed", duration_ms=7000, total_tokens=300),
            _run(2000, "error", error="Write failed", duration_ms=7200, total_tokens=320),
            _run(3000, "ok", summary="Validated parser with pytest", duration_ms=9000, total_tokens=450),
            _run(4000, "ok", summary="Validated scoring and generated report", duration_ms=9500, total_tokens=470),
        ],
    )
    signal = detect_regression_trend(job)
    assert signal is None


def test_regression_trend_signal_insufficient_data():
    """A job with too few runs should not emit a regression_trend signal."""
    job = JobState(
        job_id="job-1",
        name="short-job",
        runs=[
            _run(1000, "ok", summary="Run 1"),
            _run(2000, "ok", summary="Run 2"),
        ],
    )
    signal = detect_regression_trend(job)
    assert signal is None


def test_regression_trend_signal_severity_critical():
    """A sharp regression (score delta <= -20) should be CRITICAL."""
    job = JobState(
        job_id="job-1",
        name="crash-job",
        consecutive_errors=3,
        last_run_status="error",
        runs=[
            _run(1000, "ok", summary="All tests pass", duration_ms=5000, total_tokens=400),
            _run(2000, "ok", summary="Smoke test OK", duration_ms=5500, total_tokens=420),
            _run(3000, "ok", summary="Smoke test OK", duration_ms=5300, total_tokens=410),
            _run(4000, "error", error="fatal: out of memory", duration_ms=12000, total_tokens=800),
            _run(5000, "error", error="fatal: out of memory", duration_ms=15000, total_tokens=900),
            _run(6000, "error", error="fatal: out of memory", duration_ms=18000, total_tokens=1100),
        ],
    )
    signal = detect_regression_trend(job)
    assert signal is not None
    assert signal.kind == "regression_trend"
    assert signal.severity.value == "critical"


def test_regression_trend_in_analyze_job():
    """analyze_job should include regression_trend alongside other signals."""
    job = JobState(
        job_id="job-1",
        name="multi-signal-job",
        consecutive_errors=2,
        last_run_status="error",
        runs=[
            _run(1000, "ok", summary="All good", duration_ms=5000, total_tokens=400),
            _run(2000, "ok", summary="All good", duration_ms=5500, total_tokens=420),
            _run(3000, "error", error="Write to /tmp/a failed: permission denied", duration_ms=7000, total_tokens=300),
            _run(4000, "error", error="Write to /tmp/b failed: permission denied", duration_ms=7200, total_tokens=320),
        ],
    )
    signals = analyze_job(job)
    kinds = [s.kind for s in signals]
    assert "regression_trend" in kinds
    assert "consecutive_errors" in kinds


def test_regression_trend_recommendation():
    """A regression_trend signal should produce recommendations."""
    from trajectory_monitor.recommendations import generate_recommendations
    from trajectory_monitor.signals import Signal, Severity

    signal = Signal(
        kind="regression_trend",
        severity=Severity.WARNING,
        message="Score dropping: 65→50 (Δ-15)",
        job_name="test-job",
        details={"score_delta": -15, "previous_score": 65, "recent_score": 50, "window_size": 3},
    )
    recs = generate_recommendations([signal])
    assert len(recs) >= 1
    assert recs[0].signal_kind == "regression_trend"
    assert "delta=-15" in recs[0].action or "regressing" in recs[0].action.lower()


def test_build_action_policy_bugfix_only_for_crashing_job():
    from trajectory_monitor.scorer import build_action_policy, score_job

    job = JobState(
        job_id="job-1",
        name="policy-crash",
        consecutive_errors=3,
        last_run_status="error",
        runs=[
            _run(1000, "error", error="Write to /tmp/a failed: permission denied", duration_ms=7000, total_tokens=300),
            _run(2000, "error", error="Write to /tmp/b failed: permission denied", duration_ms=7200, total_tokens=320),
            _run(3000, "error", error="Write to /tmp/c failed: permission denied", duration_ms=7100, total_tokens=310),
        ],
    )

    score = score_job(job)
    policy = build_action_policy(job, score=score)

    assert policy.mode == "bugfix_only"
    assert policy.feature_delivery_allowed is False
    assert policy.should_alert is True
    assert any("consecutive errors" in reason for reason in policy.reasons)



def test_generate_json_report_includes_action_policy():
    job = JobState(
        job_id="job-1",
        name="policy-healthy",
        consecutive_errors=0,
        last_run_status="ok",
        runs=[
            _run(1000, "ok", summary="Validated parser with pytest", duration_ms=9000, total_tokens=450),
            _run(2000, "ok", summary="Validated scoring and generated report", duration_ms=9500, total_tokens=470),
            _run(3000, "ok", summary="Validated report formatting", duration_ms=9100, total_tokens=460),
            _run(4000, "ok", summary="Validated MCP payloads", duration_ms=9050, total_tokens=455),
        ],
    )

    report = json.loads(generate_json_report([job]))
    assert report["summary"]["policy_counts"]["normal"] == 1
    assert report["jobs"][0]["action_policy"]["mode"] == "normal"
    assert report["jobs"][0]["action_policy"]["feature_delivery_allowed"] is True
