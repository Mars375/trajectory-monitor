"""MCP server for trajectory-monitor — agents can self-inspect.

Provides tools:
- analyze_jobs: Full analysis of all cron jobs
- check_job: Analyze a specific job by name
- get_score: Get quality score for a job
- get_recommendations: Get actionable fix suggestions for one or many jobs
- analyze_session: Analyze a session transcript (text or path) for anomalies
- list_signals: List all available signal detectors

Run: python -m trajectory_monitor.mcp_server
    or: trajectory-monitor serve
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .parser import JobState, build_job_states
from .recommendations import generate_recommendations
from .report import generate_json_report
from .scorer import score_job
from .signals import DETECTORS, analyze_job

# ── Auto-detect paths ─────────────────────────────────────────────

_DEFAULT_PATHS = [
    Path.home() / ".openclaw" / "cron" / "jobs.json",
    Path("/home/orion/.openclaw/cron/jobs.json"),
]

_DEFAULT_RUNS = [
    Path.home() / ".openclaw" / "cron" / "runs",
    Path("/home/orion/.openclaw/cron/runs"),
]


def _find_jobs_json(path: str | None = None) -> str:
    if path:
        return path
    for p in _DEFAULT_PATHS:
        if p.exists():
            return str(p)
    return ""


def _find_runs_dir(path: str | None = None) -> str:
    if path:
        return path
    for p in _DEFAULT_RUNS:
        if p.exists():
            return str(p)
    return ""


def _signal_payload(signal) -> dict[str, object]:
    return {
        "kind": signal.kind,
        "severity": signal.severity.value,
        "message": signal.message,
        "details": signal.details,
    }


def _recommendation_payload(rec) -> dict[str, str]:
    return {
        "priority": rec.priority,
        "signal_kind": rec.signal_kind,
        "action": rec.action,
        "details": rec.details,
    }


# ── MCP Server ────────────────────────────────────────────────────

mcp = FastMCP(
    "trajectory-monitor",
    instructions="Analyze agent trajectories, detect anomalies, score quality.",
)


@mcp.tool()
def analyze_jobs(jobs_json_path: str = "", runs_dir: str = "") -> str:
    """Full analysis of all cron jobs. Returns JSON report with scores and signals.

    Args:
        jobs_json_path: Path to jobs.json (auto-detected if omitted)
        runs_dir: Path to runs/ directory (auto-detected if omitted)
    """
    jp = _find_jobs_json(jobs_json_path or None)
    rd = _find_runs_dir(runs_dir or None)
    if not jp or not Path(jp).exists():
        return json.dumps({"error": f"jobs.json not found at {jp}"})
    jobs = build_job_states(jp, rd)
    return generate_json_report(jobs)


@mcp.tool()
def check_job(job_name: str, jobs_json_path: str = "", runs_dir: str = "") -> str:
    """Analyze a specific cron job by name. Returns signals and quality score.

    Args:
        job_name: Name of the job to analyze
        jobs_json_path: Path to jobs.json (auto-detected if omitted)
        runs_dir: Path to runs/ directory (auto-detected if omitted)
    """
    jp = _find_jobs_json(jobs_json_path or None)
    rd = _find_runs_dir(runs_dir or None)
    if not jp or not Path(jp).exists():
        return json.dumps({"error": f"jobs.json not found at {jp}"})

    jobs = build_job_states(jp, rd)
    for job in jobs:
        if job.name == job_name:
            signals = analyze_job(job)
            score = score_job(job)
            return json.dumps({
                "job": job_name,
                "score": score.score,
                "grade": score.grade,
                "total_runs": job.total_runs,
                "error_rate": round(job.error_rate, 2),
                "consecutive_errors": job.consecutive_errors,
                "signals": [_signal_payload(s) for s in signals],
                "breakdown": score.breakdown,
            }, indent=2, ensure_ascii=False)
    return json.dumps({"error": f"Job '{job_name}' not found"})


@mcp.tool()
def get_score(job_name: str, jobs_json_path: str = "", runs_dir: str = "") -> str:
    """Get quality score for a specific job. Returns score (0-100), grade, and breakdown.

    Args:
        job_name: Name of the job to score
        jobs_json_path: Path to jobs.json (auto-detected if omitted)
        runs_dir: Path to runs/ directory (auto-detected if omitted)
    """
    jp = _find_jobs_json(jobs_json_path or None)
    rd = _find_runs_dir(runs_dir or None)
    if not jp or not Path(jp).exists():
        return json.dumps({"error": f"jobs.json not found at {jp}"})

    jobs = build_job_states(jp, rd)
    for job in jobs:
        if job.name == job_name:
            score = score_job(job)
            return json.dumps({
                "job": job_name,
                "score": score.score,
                "grade": score.grade,
                "breakdown": {k: round(v, 1) for k, v in score.breakdown.items()},
            }, indent=2)
    return json.dumps({"error": f"Job '{job_name}' not found"})


@mcp.tool()
def get_recommendations(job_name: str = "", jobs_json_path: str = "", runs_dir: str = "") -> str:
    """Get actionable recommendations for one job or all jobs with issues.

    Args:
        job_name: Optional specific job to inspect. If omitted, returns all jobs with recommendations.
        jobs_json_path: Path to jobs.json (auto-detected if omitted)
        runs_dir: Path to runs/ directory (auto-detected if omitted)
    """
    jp = _find_jobs_json(jobs_json_path or None)
    rd = _find_runs_dir(runs_dir or None)
    if not jp or not Path(jp).exists():
        return json.dumps({"error": f"jobs.json not found at {jp}"})

    jobs = build_job_states(jp, rd)

    if job_name:
        for job in jobs:
            if job.name == job_name:
                signals = analyze_job(job)
                recommendations = generate_recommendations(signals)
                score = score_job(job)
                return json.dumps({
                    "job": job_name,
                    "score": score.score,
                    "grade": score.grade,
                    "signals": [_signal_payload(s) for s in signals],
                    "recommendations": [_recommendation_payload(r) for r in recommendations],
                }, indent=2, ensure_ascii=False)
        return json.dumps({"error": f"Job '{job_name}' not found"})

    jobs_with_recommendations: dict[str, dict[str, object]] = {}
    for job in jobs:
        signals = analyze_job(job)
        recommendations = generate_recommendations(signals)
        if not recommendations:
            continue
        score = score_job(job)
        jobs_with_recommendations[job.name] = {
            "score": score.score,
            "grade": score.grade,
            "signal_count": len(signals),
            "recommendations": [_recommendation_payload(r) for r in recommendations],
        }

    return json.dumps({
        "jobs": jobs_with_recommendations,
        "count": len(jobs_with_recommendations),
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def analyze_session(transcript: str, job_name: str = "session") -> str:
    """Analyze a session transcript (text) for anomalies. Agents can self-inspect.

    Parses the transcript as JSONL run data and runs all signal detectors.
    Useful for checking your own trajectory mid-session.

    Args:
        transcript: Session transcript — either a file path ending in .jsonl, or raw JSONL text (one JSON object per line)
        job_name: Name for this session (default: "session")
    """
    entries_text = transcript.strip()

    # If it looks like a file path, read it
    if not entries_text.startswith("{") and Path(entries_text).exists():
        p = Path(entries_text)
        if p.suffix == ".jsonl":
            entries_text = p.read_text()
        else:
            return json.dumps({"error": f"File must be .jsonl, got {p.suffix}"})

    # Parse JSONL lines into RunEntry-like data
    from .parser import RunEntry

    runs: list[RunEntry] = []
    for line in entries_text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        if obj.get("action") != "finished":
            continue

        usage = obj.get("usage", {})
        runs.append(RunEntry(
            ts=obj.get("ts", 0),
            job_id=obj.get("jobId", job_name),
            action=obj.get("action", ""),
            status=obj.get("status", "unknown"),
            duration_ms=obj.get("durationMs", 0),
            model=obj.get("model", ""),
            provider=obj.get("provider", ""),
            error=obj.get("error", ""),
            summary=obj.get("summary", ""),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
            session_id=obj.get("sessionId", ""),
        ))

    if not runs:
        return json.dumps({
            "error": "No valid run entries found in transcript",
            "hint": "Provide JSONL with action=finished entries",
        })

    # Build a synthetic JobState and analyze
    job = JobState(
        job_id=job_name,
        name=job_name,
        runs=runs,
    )

    signals = analyze_job(job)
    recommendations = generate_recommendations(signals)
    score = score_job(job)

    return json.dumps({
        "session": job_name,
        "runs_analyzed": len(runs),
        "errors": len(job.error_runs),
        "score": score.score,
        "grade": score.grade,
        "signals": [_signal_payload(s) for s in signals],
        "recommendations": [_recommendation_payload(r) for r in recommendations],
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def list_signals() -> str:
    """List all available signal detectors and their descriptions."""
    detector_info = []
    for det in DETECTORS:
        detector_info.append({
            "name": det.__name__,
            "description": det.__doc__.strip().split("\n")[0] if det.__doc__ else "",
        })
    return json.dumps({
        "detectors": detector_info,
        "count": len(detector_info),
    }, indent=2)


def main_serve() -> None:
    """Entry point for `trajectory-monitor serve`."""
    mcp.run()


if __name__ == "__main__":
    main_serve()
