"""MCP server for trajectory-monitor — agents can self-inspect.

Provides tools:
- analyze_jobs: Full analysis of all cron jobs
- check_job: Analyze a specific job by name
- get_score: Get quality score for a job

Note: This is a placeholder for the MCP server. Full implementation
requires the `mcp` package. For now, the core logic is in
signals.py and scorer.py which can be called from any MCP server.
"""

from __future__ import annotations

from .parser import build_job_states
from .report import generate_json_report, generate_terminal_report
from .scorer import score_job
from .signals import analyze_job


def tool_analyze_jobs(jobs_json_path: str, runs_dir: str = "") -> str:
    """MCP tool: Full analysis of all cron jobs."""
    jobs = build_job_states(jobs_json_path, runs_dir)
    return generate_json_report(jobs)


def tool_check_job(jobs_json_path: str, job_name: str, runs_dir: str = "") -> str:
    """MCP tool: Analyze a specific job."""
    jobs = build_job_states(jobs_json_path, runs_dir)
    for job in jobs:
        if job.name == job_name:
            signals = analyze_job(job)
            score = score_job(job)
            return (
                f"Job: {job.name}\n"
                f"Score: {score.score}/100 (grade {score.grade})\n"
                f"Runs: {job.total_runs} (errors: {len(job.error_runs)})\n"
                f"Signals: {len(signals)}\n"
                + ("\n".join(f"  - [{s.severity.value}] {s.kind}: {s.message}" for s in signals))
            )
    return f"Job '{job_name}' not found."


def tool_get_score(jobs_json_path: str, job_name: str, runs_dir: str = "") -> str:
    """MCP tool: Get quality score for a job."""
    jobs = build_job_states(jobs_json_path, runs_dir)
    for job in jobs:
        if job.name == job_name:
            score = score_job(job)
            return f"{score.score}/100 (grade {score.grade})"
    return f"Job '{job_name}' not found."
