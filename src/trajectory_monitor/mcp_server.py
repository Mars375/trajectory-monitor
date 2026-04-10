"""MCP server for trajectory-monitor, agents can self-inspect.

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
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .parser import JobState, build_job_states, parse_transcript_file, parse_transcript_text
from .recommendations import generate_recommendations
from .report import generate_json_report
from .scorer import (
    action_policy_to_dict,
    analyze_trend,
    build_action_policy,
    policy_thresholds_to_dict,
    resolve_policy_thresholds,
    score_job,
    trend_to_dict,
)
from .signals import DETECTORS, analyze_job, check_file_existence

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


def _path_exists(value: str) -> bool:
    if not value or "\n" in value or "\r" in value:
        return False
    try:
        return Path(value).exists()
    except OSError:
        return False


def _load_policy_thresholds(policy_config: str = ""):
    try:
        return resolve_policy_thresholds(policy_config)
    except ValueError as exc:
        raise ValueError(f"Invalid policy_config: {exc}") from exc


def _trailing_error_streak(runs) -> int:
    streak = 0
    for run in reversed(runs):
        if run.is_error:
            streak += 1
        else:
            break
    return streak


mcp = FastMCP(
    "trajectory-monitor",
    instructions="Analyze agent trajectories, detect anomalies, score quality.",
)


@mcp.tool()
def analyze_jobs(jobs_json_path: str = "", runs_dir: str = "", policy_config: str = "") -> str:
    """Full analysis of all cron jobs. Returns JSON report with scores and signals.

    Args:
        jobs_json_path: Path to jobs.json (auto-detected if omitted)
        runs_dir: Path to runs/ directory (auto-detected if omitted)
        policy_config: Optional JSON string or file path overriding action policy thresholds
    """
    try:
        policy_thresholds = _load_policy_thresholds(policy_config)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    jp = _find_jobs_json(jobs_json_path or None)
    rd = _find_runs_dir(runs_dir or None)
    if not jp or not Path(jp).exists():
        return json.dumps({"error": f"jobs.json not found at {jp}"})
    jobs = build_job_states(jp, rd)
    return generate_json_report(jobs, policy_thresholds=policy_thresholds)


@mcp.tool()
def check_job(job_name: str, jobs_json_path: str = "", runs_dir: str = "", policy_config: str = "") -> str:
    """Analyze a specific cron job by name. Returns signals and quality score.

    Args:
        job_name: Name of the job to analyze
        jobs_json_path: Path to jobs.json (auto-detected if omitted)
        runs_dir: Path to runs/ directory (auto-detected if omitted)
        policy_config: Optional JSON string or file path overriding action policy thresholds
    """
    try:
        policy_thresholds = _load_policy_thresholds(policy_config)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    jp = _find_jobs_json(jobs_json_path or None)
    rd = _find_runs_dir(runs_dir or None)
    if not jp or not Path(jp).exists():
        return json.dumps({"error": f"jobs.json not found at {jp}"})

    jobs = build_job_states(jp, rd)
    for job in jobs:
        if job.name == job_name:
            signals = analyze_job(job)
            score = score_job(job)
            trend = analyze_trend(job)
            policy = build_action_policy(
                job,
                score=score,
                signals=signals,
                trend=trend,
                thresholds=policy_thresholds,
            )
            return json.dumps(
                {
                    "job": job_name,
                    "score": score.score,
                    "grade": score.grade,
                    "trend": trend_to_dict(trend),
                    "policy_thresholds": policy_thresholds_to_dict(policy_thresholds),
                    "action_policy": action_policy_to_dict(policy),
                    "total_runs": job.total_runs,
                    "error_rate": round(job.error_rate, 2),
                    "consecutive_errors": job.consecutive_errors,
                    "signals": [_signal_payload(s) for s in signals],
                    "breakdown": score.breakdown,
                    "signal_penalties": {k: round(v, 1) for k, v in score.signal_penalties.items()},
                },
                indent=2,
                ensure_ascii=False,
            )
    return json.dumps({"error": f"Job '{job_name}' not found"})


@mcp.tool()
def get_score(job_name: str, jobs_json_path: str = "", runs_dir: str = "", policy_config: str = "") -> str:
    """Get quality score for a specific job. Returns score (0-100), grade, and breakdown.

    Args:
        job_name: Name of the job to score
        jobs_json_path: Path to jobs.json (auto-detected if omitted)
        runs_dir: Path to runs/ directory (auto-detected if omitted)
        policy_config: Optional JSON string or file path overriding action policy thresholds
    """
    try:
        policy_thresholds = _load_policy_thresholds(policy_config)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    jp = _find_jobs_json(jobs_json_path or None)
    rd = _find_runs_dir(runs_dir or None)
    if not jp or not Path(jp).exists():
        return json.dumps({"error": f"jobs.json not found at {jp}"})

    jobs = build_job_states(jp, rd)
    for job in jobs:
        if job.name == job_name:
            score = score_job(job)
            trend = analyze_trend(job)
            policy = build_action_policy(job, score=score, trend=trend, thresholds=policy_thresholds)
            return json.dumps(
                {
                    "job": job_name,
                    "score": score.score,
                    "grade": score.grade,
                    "trend": trend_to_dict(trend),
                    "policy_thresholds": policy_thresholds_to_dict(policy_thresholds),
                    "action_policy": action_policy_to_dict(policy),
                    "breakdown": {k: round(v, 1) for k, v in score.breakdown.items()},
                    "signal_penalties": {k: round(v, 1) for k, v in score.signal_penalties.items()},
                },
                indent=2,
            )
    return json.dumps({"error": f"Job '{job_name}' not found"})


@mcp.tool()
def get_recommendations(
    job_name: str = "",
    jobs_json_path: str = "",
    runs_dir: str = "",
    policy_config: str = "",
) -> str:
    """Get actionable recommendations for one job or all jobs with issues.

    Args:
        job_name: Optional specific job to inspect. If omitted, returns all jobs with recommendations.
        jobs_json_path: Path to jobs.json (auto-detected if omitted)
        runs_dir: Path to runs/ directory (auto-detected if omitted)
        policy_config: Optional JSON string or file path overriding action policy thresholds
    """
    try:
        policy_thresholds = _load_policy_thresholds(policy_config)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

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
                trend = analyze_trend(job)
                policy = build_action_policy(
                    job,
                    score=score,
                    signals=signals,
                    trend=trend,
                    thresholds=policy_thresholds,
                )
                return json.dumps(
                    {
                        "job": job_name,
                        "score": score.score,
                        "grade": score.grade,
                        "trend": trend_to_dict(trend),
                        "policy_thresholds": policy_thresholds_to_dict(policy_thresholds),
                        "action_policy": action_policy_to_dict(policy),
                        "signals": [_signal_payload(s) for s in signals],
                        "recommendations": [_recommendation_payload(r) for r in recommendations],
                    },
                    indent=2,
                    ensure_ascii=False,
                )
        return json.dumps({"error": f"Job '{job_name}' not found"})

    jobs_with_recommendations: dict[str, dict[str, object]] = {}
    for job in jobs:
        signals = analyze_job(job)
        recommendations = generate_recommendations(signals)
        if not recommendations:
            continue
        score = score_job(job)
        trend = analyze_trend(job)
        policy = build_action_policy(
            job,
            score=score,
            signals=signals,
            trend=trend,
            thresholds=policy_thresholds,
        )
        jobs_with_recommendations[job.name] = {
            "score": score.score,
            "grade": score.grade,
            "trend": trend_to_dict(trend),
            "action_policy": action_policy_to_dict(policy),
            "signal_count": len(signals),
            "recommendations": [_recommendation_payload(r) for r in recommendations],
        }

    return json.dumps(
        {
            "policy_thresholds": policy_thresholds_to_dict(policy_thresholds),
            "jobs": jobs_with_recommendations,
            "count": len(jobs_with_recommendations),
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def analyze_session(
    transcript: str,
    job_name: str = "session",
    workspace_path: str = "",
    policy_config: str = "",
) -> str:
    """Analyze a session transcript (JSONL, markdown, or transcript file) for anomalies.

    Parses OpenClaw JSONL or markdown/text action logs and runs all signal detectors.
    If workspace_path is provided, also checks whether referenced files
    actually exist on disk.

    Args:
        transcript: Session transcript, raw JSONL, markdown/text, or a path to a transcript file
        job_name: Name for this session (default: "session")
        workspace_path: Optional workspace root for filesystem-aware hallucination checks
        policy_config: Optional JSON string or file path overriding action policy thresholds
    """
    try:
        policy_thresholds = _load_policy_thresholds(policy_config)
    except ValueError as exc:
        return json.dumps({"error": str(exc)})

    source = transcript.strip()
    workspace = workspace_path.strip()

    if not source:
        runs = []
    elif _path_exists(source):
        runs = parse_transcript_file(source)
    else:
        runs = parse_transcript_text(source, default_job_id=job_name)

    if not runs:
        return json.dumps(
            {
                "error": "No valid transcript entries found",
                "hint": "Provide OpenClaw JSONL finished entries or markdown/text action lines",
            }
        )

    job = JobState(
        job_id=job_name,
        name=job_name,
        consecutive_errors=_trailing_error_streak(runs),
        last_run_status=runs[-1].status if runs else "",
        last_duration_ms=runs[-1].duration_ms if runs else 0,
        runs=runs,
    )

    signals = analyze_job(job)
    extra_signals = []
    workspace_check = {
        "enabled": bool(workspace),
        "path": workspace,
        "exists": bool(workspace) and Path(workspace).exists(),
    }
    if workspace_check["exists"]:
        disk_signal = check_file_existence(job, workspace)
        if disk_signal is not None:
            extra_signals.append(disk_signal)
            signals.append(disk_signal)

    recommendations = generate_recommendations(signals)
    score = score_job(job, extra_signals=extra_signals)
    trend = analyze_trend(job)
    policy = build_action_policy(
        job,
        score=score,
        signals=signals,
        trend=trend,
        thresholds=policy_thresholds,
    )

    return json.dumps(
        {
            "session": job_name,
            "runs_analyzed": len(runs),
            "errors": len(job.error_runs),
            "score": score.score,
            "grade": score.grade,
            "trend": trend_to_dict(trend),
            "policy_thresholds": policy_thresholds_to_dict(policy_thresholds),
            "action_policy": action_policy_to_dict(policy),
            "workspace_check": workspace_check,
            "signal_penalties": {k: round(v, 1) for k, v in score.signal_penalties.items()},
            "signals": [_signal_payload(s) for s in signals],
            "recommendations": [_recommendation_payload(r) for r in recommendations],
        },
        indent=2,
        ensure_ascii=False,
    )


@mcp.tool()
def list_signals() -> str:
    """List all available signal detectors and their descriptions."""
    detector_info = []
    for det in DETECTORS:
        detector_info.append(
            {
                "name": det.__name__,
                "description": det.__doc__.strip().split("\n")[0] if det.__doc__ else "",
            }
        )
    return json.dumps(
        {
            "detectors": detector_info,
            "count": len(detector_info),
        },
        indent=2,
    )


def main_serve() -> None:
    """Entry point for `trajectory-monitor serve`."""
    mcp.run()


if __name__ == "__main__":
    main_serve()
