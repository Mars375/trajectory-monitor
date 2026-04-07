"""CLI interface for trajectory-monitor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parser import build_job_states
from .report import generate_json_report, generate_terminal_report


def default_jobs_json() -> str:
    """Try to find jobs.json automatically."""
    candidates = [
        Path.home() / ".openclaw" / "cron" / "jobs.json",
        Path("/home/orion/.openclaw/cron/jobs.json"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return ""


def default_runs_dir() -> str:
    """Try to find runs directory automatically."""
    candidates = [
        Path.home() / ".openclaw" / "cron" / "runs",
        Path("/home/orion/.openclaw/cron/runs"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trajectory-monitor",
        description="Analyse les trajectoires d'exécution des agents LLM",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="analyze",
        choices=["analyze"],
        help="Command to run (default: analyze)",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Path to jobs.json (auto-detected if omitted)",
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Path to runs/ directory (auto-detected if omitted)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON instead of terminal report",
    )

    args = parser.parse_args(argv)

    jobs_json = args.target or default_jobs_json()
    runs_dir = args.runs_dir or default_runs_dir()

    if not jobs_json:
        print("Error: Cannot find jobs.json. Pass path as argument.", file=sys.stderr)
        return 1

    if not Path(jobs_json).exists():
        print(f"Error: {jobs_json} does not exist.", file=sys.stderr)
        return 1

    jobs = build_job_states(jobs_json, runs_dir)

    if not jobs:
        print("No jobs found.", file=sys.stderr)
        return 1

    if args.json:
        print(generate_json_report(jobs))
    else:
        print(generate_terminal_report(jobs))

    return 0


if __name__ == "__main__":
    sys.exit(main())
