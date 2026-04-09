"""Tests for trajectory-monitor."""

import json
import tempfile
from pathlib import Path

import pytest

from trajectory_monitor.parser import (
    JobState,
    RunEntry,
    build_job_states,
    parse_jobs_json,
    parse_run_jsonl,
    parse_run_jsonl_text,
)
from trajectory_monitor.scorer import score_job, score_all
from trajectory_monitor.signals import (
    Severity,
    analyze_all,
    analyze_job,
    detect_consecutive_errors,
    detect_crash_repeat,
    detect_duration_spike,
    detect_feature_race,
    detect_loop,
    detect_stagnation,
)


# ── Fixtures ──────────────────────────────────────────────────────


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
            {
                "id": "job-stagnant-003",
                "name": "stagnant-job",
                "description": "Never ran",
                "enabled": True,
                "state": {
                    "consecutiveErrors": 0,
                    "lastRunStatus": "",
                    "lastDurationMs": 0,
                },
            },
        ],
    }
    jobs_json.write_text(json.dumps(jobs_data))

    # Create run transcripts
    run_data = [
        # Healthy: 3 OK runs
        {"ts": 1000, "jobId": "job-healthy-001", "action": "finished", "status": "ok",
         "durationMs": 50000, "model": "glm-5", "summary": "Analyzed dependency tree and updated 3 packages",
         "usage": {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500}},
        {"ts": 2000, "jobId": "job-healthy-001", "action": "finished", "status": "ok",
         "durationMs": 52000, "model": "glm-5", "summary": "Scanned codebase for security vulnerabilities, found 0 issues",
         "usage": {"input_tokens": 1100, "output_tokens": 550, "total_tokens": 1650}},
        {"ts": 3000, "jobId": "job-healthy-001", "action": "finished", "status": "ok",
         "durationMs": 48000, "model": "glm-5", "summary": "Generated documentation for 12 API endpoints",
         "usage": {"input_tokens": 1050, "output_tokens": 520, "total_tokens": 1570}},
        # Crashing: 3 errors with same pattern
        {"ts": 1000, "jobId": "job-crashing-002", "action": "finished", "status": "error",
         "durationMs": 10000, "error": "Write to /tmp/file.txt failed: permission denied",
         "usage": {"input_tokens": 500, "output_tokens": 200, "total_tokens": 700}},
        {"ts": 2000, "jobId": "job-crashing-002", "action": "finished", "status": "error",
         "durationMs": 12000, "error": "Write to /tmp/other.txt failed: permission denied",
         "usage": {"input_tokens": 600, "output_tokens": 250, "total_tokens": 850}},
        {"ts": 3000, "jobId": "job-crashing-002", "action": "finished", "status": "error",
         "durationMs": 11000, "error": "Write to /tmp/data.txt failed: permission denied",
         "usage": {"input_tokens": 550, "output_tokens": 230, "total_tokens": 780}},
        # Skip entries (not "finished")
        {"ts": 500, "jobId": "job-healthy-001", "action": "started", "status": "ok"},
    ]

    run_file = runs_dir / "test-runs.jsonl"
    with open(run_file, "w") as f:
        for entry in run_data:
            f.write(json.dumps(entry) + "\n")

    return tmp_path


# ── Parser tests ──────────────────────────────────────────────────


class TestParser:
    def test_parse_jobs_json(self, tmp_workspace):
        jobs = parse_jobs_json(tmp_workspace / "jobs.json")
        assert len(jobs) == 3
        assert jobs[0].name == "healthy-job"
        assert jobs[1].name == "crashing-job"
        assert jobs[2].name == "stagnant-job"

    def test_parse_jobs_json_missing(self, tmp_path):
        jobs = parse_jobs_json(tmp_path / "nonexistent.json")
        assert jobs == []

    def test_parse_run_jsonl(self, tmp_workspace):
        runs_dir = tmp_workspace / "runs"
        run_file = runs_dir / "test-runs.jsonl"
        entries = parse_run_jsonl(run_file)
        # Should only get "finished" entries
        assert len(entries) == 6  # 3 healthy + 3 crashing

    def test_parse_run_jsonl_text_default_job_and_summary_fallback(self):
        text = "\n".join([
            json.dumps({
                "ts": 1000,
                "action": "finished",
                "status": "ok",
                "durationMs": 1000,
                "result": {"summary": "Fallback summary from result"},
            }),
            json.dumps({"ts": 2000, "action": "started", "status": "ok"}),
        ])
        entries = parse_run_jsonl_text(text, default_job_id="session-123")
        assert len(entries) == 1
        assert entries[0].job_id == "session-123"
        assert entries[0].summary == "Fallback summary from result"

    def test_build_job_states(self, tmp_workspace):
        jobs = build_job_states(
            tmp_workspace / "jobs.json",
            tmp_workspace / "runs",
        )
        assert len(jobs) >= 3

        healthy = next(j for j in jobs if j.name == "healthy-job")
        assert healthy.total_runs == 3
        assert len(healthy.ok_runs) == 3

        crashing = next(j for j in jobs if j.name == "crashing-job")
        assert crashing.total_runs == 3
        assert len(crashing.error_runs) == 3
        assert crashing.consecutive_errors == 3


# ── Signal tests ──────────────────────────────────────────────────


class TestSignals:
    def test_detect_crash_repeat(self, tmp_workspace):
        jobs = build_job_states(tmp_workspace / "jobs.json", tmp_workspace / "runs")
        crashing = next(j for j in jobs if j.name == "crashing-job")
        signal = detect_crash_repeat(crashing)
        assert signal is not None
        assert signal.kind == "crash_repeat"
        assert signal.severity == Severity.CRITICAL  # 3x streak

    def test_detect_stagnation(self, tmp_workspace):
        jobs = build_job_states(tmp_workspace / "jobs.json", tmp_workspace / "runs")
        stagnant = next(j for j in jobs if j.name == "stagnant-job")
        signal = detect_stagnation(stagnant)
        assert signal is not None
        assert signal.kind == "stagnation"

    def test_detect_consecutive_errors(self, tmp_workspace):
        jobs = build_job_states(tmp_workspace / "jobs.json", tmp_workspace / "runs")
        crashing = next(j for j in jobs if j.name == "crashing-job")
        signal = detect_consecutive_errors(crashing)
        assert signal is not None
        assert signal.kind == "consecutive_errors"
        assert signal.severity == Severity.CRITICAL

    def test_healthy_no_signals(self, tmp_workspace):
        jobs = build_job_states(tmp_workspace / "jobs.json", tmp_workspace / "runs")
        healthy = next(j for j in jobs if j.name == "healthy-job")
        signals = analyze_job(healthy)
        # Healthy job should have no critical/warning signals
        assert all(s.severity == Severity.INFO for s in signals) or len(signals) == 0

    def test_analyze_all(self, tmp_workspace):
        jobs = build_job_states(tmp_workspace / "jobs.json", tmp_workspace / "runs")
        results = analyze_all(jobs)
        assert "crashing-job" in results
        assert len(results["crashing-job"]) >= 1

    def test_detect_feature_race_triggers(self):
        """3+ consecutive feature-add summaries without validation → signal."""
        job = JobState(
            job_id="race-001",
            name="forge-chantier-memos",
            runs=[
                RunEntry(ts=1000, job_id="race-001", action="finished", status="ok",
                         duration_ms=30000, summary="Added recall filters for date range",
                         input_tokens=500, output_tokens=300, total_tokens=800),
                RunEntry(ts=2000, job_id="race-001", action="finished", status="ok",
                         duration_ms=32000, summary="Implemented tag-based deduplication",
                         input_tokens=550, output_tokens=320, total_tokens=870),
                RunEntry(ts=3000, job_id="race-001", action="finished", status="ok",
                         duration_ms=28000, summary="Created export feature for markdown",
                         input_tokens=520, output_tokens=310, total_tokens=830),
                RunEntry(ts=4000, job_id="race-001", action="finished", status="ok",
                         duration_ms=35000, summary="Built semantic clustering pipeline",
                         input_tokens=600, output_tokens=400, total_tokens=1000),
            ],
        )
        signal = detect_feature_race(job)
        assert signal is not None
        assert signal.kind == "feature_race"
        assert signal.severity == Severity.WARNING  # streak=4 (< 5)
        assert signal.details["streak"] == 4

    def test_detect_feature_race_critical(self):
        """5+ feature-add runs → CRITICAL severity."""
        job = JobState(
            job_id="race-002",
            name="forge-chantier-chaos",
            runs=[
                RunEntry(ts=i * 1000, job_id="race-002", action="finished", status="ok",
                         duration_ms=30000, summary=f"Added feature {i}",
                         input_tokens=500, output_tokens=300, total_tokens=800)
                for i in range(6)
            ],
        )
        signal = detect_feature_race(job)
        assert signal is not None
        assert signal.severity == Severity.CRITICAL  # streak=6 (>= 5)

    def test_detect_feature_race_no_signal_with_validation(self):
        """Feature runs interspersed with validation → no signal."""
        job = JobState(
            job_id="safe-001",
            name="forge-chantier-safe",
            runs=[
                RunEntry(ts=1000, job_id="safe-001", action="finished", status="ok",
                         duration_ms=30000, summary="Added recall filters for date range",
                         input_tokens=500, output_tokens=300, total_tokens=800),
                RunEntry(ts=2000, job_id="safe-001", action="finished", status="ok",
                         duration_ms=32000, summary="Implemented tag-based deduplication",
                         input_tokens=550, output_tokens=320, total_tokens=870),
                RunEntry(ts=3000, job_id="safe-001", action="finished", status="ok",
                         duration_ms=28000, summary="Validated all filters with pytest",
                         input_tokens=520, output_tokens=310, total_tokens=830),
                RunEntry(ts=4000, job_id="safe-001", action="finished", status="ok",
                         duration_ms=35000, summary="Created export feature for markdown",
                         input_tokens=600, output_tokens=400, total_tokens=1000),
            ],
        )
        signal = detect_feature_race(job)
        # Validation run breaks the streak at 2, which is < 3
        assert signal is None

    def test_detect_feature_race_no_signal_too_few(self):
        """Fewer than 3 feature runs → no signal."""
        job = JobState(
            job_id="short-001",
            name="forge-chantier-short",
            runs=[
                RunEntry(ts=1000, job_id="short-001", action="finished", status="ok",
                         duration_ms=30000, summary="Added feature A",
                         input_tokens=500, output_tokens=300, total_tokens=800),
                RunEntry(ts=2000, job_id="short-001", action="finished", status="ok",
                         duration_ms=32000, summary="Implemented feature B",
                         input_tokens=550, output_tokens=320, total_tokens=870),
            ],
        )
        signal = detect_feature_race(job)
        assert signal is None

    def test_detect_feature_race_french_keywords(self):
        """French feature keywords (ajouté, implémenté) are detected."""
        job = JobState(
            job_id="fr-001",
            name="forge-chantier-fr",
            runs=[
                RunEntry(ts=1000, job_id="fr-001", action="finished", status="ok",
                         duration_ms=30000, summary="Ajouté filtres de recherche avancée",
                         input_tokens=500, output_tokens=300, total_tokens=800),
                RunEntry(ts=2000, job_id="fr-001", action="finished", status="ok",
                         duration_ms=32000, summary="Implémenté déduplication par tags",
                         input_tokens=550, output_tokens=320, total_tokens=870),
                RunEntry(ts=3000, job_id="fr-001", action="finished", status="ok",
                         duration_ms=28000, summary="Créé export markdown des résultats",
                         input_tokens=520, output_tokens=310, total_tokens=830),
            ],
        )
        signal = detect_feature_race(job)
        assert signal is not None
        assert signal.kind == "feature_race"


# ── Scorer tests ──────────────────────────────────────────────────


class TestScorer:
    def test_healthy_score_high(self, tmp_workspace):
        jobs = build_job_states(tmp_workspace / "jobs.json", tmp_workspace / "runs")
        healthy = next(j for j in jobs if j.name == "healthy-job")
        score = score_job(healthy)
        assert score.score >= 60  # Healthy should score reasonably
        assert score.grade in ("A", "B", "C")

    def test_crashing_score_low(self, tmp_workspace):
        jobs = build_job_states(tmp_workspace / "jobs.json", tmp_workspace / "runs")
        crashing = next(j for j in jobs if j.name == "crashing-job")
        score = score_job(crashing)
        assert score.score < 50  # Crashing should score low

    def test_stagnant_score_medium(self, tmp_workspace):
        jobs = build_job_states(tmp_workspace / "jobs.json", tmp_workspace / "runs")
        stagnant = next(j for j in jobs if j.name == "stagnant-job")
        score = score_job(stagnant)
        assert 0 <= score.score <= 100

    def test_score_all_sorted(self, tmp_workspace):
        jobs = build_job_states(tmp_workspace / "jobs.json", tmp_workspace / "runs")
        scores = score_all(jobs)
        assert len(scores) == len(jobs)
        # Should be sorted ascending (worst first)
        for i in range(len(scores) - 1):
            assert scores[i].score <= scores[i + 1].score
