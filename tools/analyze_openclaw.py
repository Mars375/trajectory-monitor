#!/usr/bin/env python3
"""Analyze OpenClaw forge crons and produce a markdown report.

Designed for forge-meta-improve to consume. Analyzes all forge-* jobs,
detects anomalies, scores quality, and generates actionable recommendations.

Usage:
    python tools/analyze_openclaw.py [--jobs-json PATH] [--runs-dir PATH] [--output PATH]

If no paths given, auto-detects OpenClaw cron paths.
Output goes to stdout unless --output is specified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root or from tools/ dir
try:
    REPO_ROOT = Path(__file__).resolve().parent.parent
except NameError:
    # When exec'd without __file__
    REPO_ROOT = Path(os.getcwd())
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trajectory_monitor.parser import JobState, build_job_states
from trajectory_monitor.report import generate_json_report
from trajectory_monitor.scorer import QualityScore, analyze_trend, score_all
from trajectory_monitor.signals import Signal, Severity, analyze_all


# ── Constants ─────────────────────────────────────────────────────

FORGE_PREFIX = "forge-"
GRADE_ICONS = {"A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴"}
SEVERITY_ICONS = {"info": "💡", "warning": "⚠️", "critical": "🔴"}
TREND_ICONS = {
    "improving": "↗ improving",
    "stable": "→ stable",
    "regressing": "↘ regressing",
    "insufficient_data": "· n/a",
}

# Recommendations by signal kind
RECOMMENDATIONS = {
    "consecutive_errors": "Investigate the error cause. Check logs: `openclaw cron runs <job-id>`. Consider disabling if persistent.",
    "crash_repeat": "Same error repeating. Check file permissions, disk space, or API rate limits.",
    "loop": "Agent is stuck in a loop. Review the cron prompt for conflicting instructions.",
    "stagnation": "Job is enabled but never runs. Check schedule config and agent availability.",
    "duration_spike": "Last run was much slower than usual. May indicate resource contention or input bloat.",
    "token_bloat": "Output tokens are growing. May indicate prompt drift or context accumulation.",
    "feature_race": "Shipping features without validation. Add smoke tests or validation steps between runs.",
    "hallucination_pattern": "Agent references files that may not exist. Verify workspace state and check for re-created files across runs. May indicate hallucination or stale workspace assumptions.",
}


def _grade_icon(grade: str) -> str:
    return GRADE_ICONS.get(grade, "❓")


def _severity_icon(sev: Severity) -> str:
    return SEVERITY_ICONS.get(sev.value, "??")


def _fmt_duration(ms: int) -> str:
    """Format milliseconds to human-readable duration."""
    if ms <= 0:
        return "N/A"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.1f}min"
    hours = minutes / 60
    return f"{hours:.1f}h"


def _fmt_tokens(n: int) -> str:
    """Format token count."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def _find_openclaw_paths() -> tuple[str, str]:
    """Auto-detect OpenClaw cron paths."""
    candidates = [
        Path.home() / ".openclaw" / "cron",
        Path("/home/orion/.openclaw/cron"),
    ]
    for base in candidates:
        jobs = base / "jobs.json"
        runs = base / "runs"
        if jobs.exists():
            return str(jobs), str(runs)
    return "", ""


def filter_forge_jobs(jobs: list[JobState]) -> list[JobState]:
    """Filter to only forge-* jobs."""
    return [j for j in jobs if j.name.startswith(FORGE_PREFIX) or "forge" in j.job_id.lower()]


def generate_forge_report(
    all_jobs: list[JobState],
    forge_jobs: list[JobState],
    signals_by_job: dict[str, list[Signal]],
    scores: list[QualityScore],
) -> str:
    """Generate a forge-specific markdown report."""
    now = datetime.now(timezone.utc)
    lines: list[str] = []

    # Header
    lines.append("# 🔍 Forge Trajectory Report")
    lines.append("")
    lines.append(f"**Generated**: {now.strftime('%Y-%m-%d %H:%M')} UTC")
    lines.append(f"**Forge jobs**: {len(forge_jobs)} / {len(all_jobs)} total")
    lines.append("")

    # Score lookup
    score_by_name = {s.job_name: s for s in scores}
    forge_scores = [score_by_name[j.name] for j in forge_jobs if j.name in score_by_name]
    forge_scores.sort(key=lambda s: s.score)
    trends_by_name = {job.name: analyze_trend(job) for job in forge_jobs}

    # Summary metrics
    if forge_scores:
        avg = sum(s.score for s in forge_scores) / len(forge_scores)
        criticals = sum(s.critical_count for s in forge_scores)
        warnings = sum(s.warning_count for s in forge_scores)
        failing = sum(1 for s in forge_scores if s.score < 40)

        lines.append("## 📊 Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Average quality score | **{avg:.0f}/100** |")
        lines.append(f"| Total signals | {criticals} critical, {warnings} warnings |")
        lines.append(f"| Failing jobs (<40) | {failing} |")
        lines.append(f"| Healthy jobs (≥75) | {sum(1 for s in forge_scores if s.score >= 75)} |")
        lines.append(f"| Regressing jobs | {sum(1 for t in trends_by_name.values() if t.direction == 'regressing')} |")
        lines.append(f"| Improving jobs | {sum(1 for t in trends_by_name.values() if t.direction == 'improving')} |")
        lines.append("")

    # Score table
    lines.append("## 🏆 Job Scores")
    lines.append("")
    lines.append("| Job | Score | Grade | Trend | Runs | Errors | Signals |")
    lines.append("|-----|-------|-------|-------|------|--------|---------|")

    for s in forge_scores:
        job = next((j for j in forge_jobs if j.name == s.job_name), None)
        runs = job.total_runs if job else 0
        err_rate = f"{job.error_rate:.0%}" if job and runs > 0 else "N/A"
        sig_count = s.signals_count
        icon = _grade_icon(s.grade)
        trend = TREND_ICONS.get(trends_by_name[s.job_name].direction, "· n/a")
        lines.append(f"| `{s.job_name}` | {s.score} | {icon} {s.grade} | {trend} | {runs} | {err_rate} | {sig_count} |")
    lines.append("")

    # Signals detail
    forge_signals = {k: v for k, v in signals_by_job.items() if k.startswith(FORGE_PREFIX)}
    if forge_signals:
        lines.append("## 🚨 Signals Detected")
        lines.append("")

        for job_name, sigs in sorted(forge_signals.items()):
            lines.append(f"### `{job_name}`")
            lines.append("")
            for sig in sigs:
                icon = _severity_icon(sig.severity)
                lines.append(f"- {icon} **[{sig.kind}]** {sig.message}")
                if sig.details:
                    for k, v in sig.details.items():
                        if isinstance(v, list):
                            v = ", ".join(str(x)[:50] for x in v[:3])
                        lines.append(f"  - `{k}`: {v}")
            lines.append("")

    # Recommendations
    jobs_needing_attention = [s for s in forge_scores if s.score < 60]
    if jobs_needing_attention:
        lines.append("## 💡 Recommendations")
        lines.append("")

        for s in jobs_needing_attention:
            trend = trends_by_name[s.job_name]
            lines.append(f"### `{s.job_name}` — score {s.score}/100 ({TREND_ICONS.get(trend.direction, '· n/a')})")
            lines.append("")
            sigs = forge_signals.get(s.job_name, [])
            seen_kinds = set()
            for sig in sigs:
                if sig.kind not in seen_kinds:
                    seen_kinds.add(sig.kind)
                    rec = RECOMMENDATIONS.get(sig.kind, "Review the job configuration and recent runs.")
                    lines.append(f"- **{sig.kind}**: {rec}")
            if not sigs:
                lines.append("- Low score without specific signals. Check the score breakdown for weak components.")
            lines.append("")

    # Run details table
    lines.append("## 📋 Run Details")
    lines.append("")
    lines.append("| Job | Last Duration | Total Tokens | Last Status | Consec. Errors |")
    lines.append("|-----|--------------|-------------|-------------|----------------|")

    for s in forge_scores:
        job = next((j for j in forge_jobs if j.name == s.job_name), None)
        if not job:
            continue
        dur = _fmt_duration(job.last_duration_ms)
        tokens = _fmt_tokens(job.total_tokens)
        status = "✅ ok" if job.last_run_status == "ok" else "❌ error" if job.last_run_status == "error" else "—"
        consec = str(job.consecutive_errors) if job.consecutive_errors > 0 else "0"
        lines.append(f"| `{s.job_name}` | {dur} | {tokens} | {status} | {consec} |")
    lines.append("")

    # Comparison with non-forge
    non_forge_jobs = [j for j in all_jobs if j not in forge_jobs]
    if non_forge_jobs:
        nf_scores = [score_by_name[j.name] for j in non_forge_jobs if j.name in score_by_name]
        if nf_scores:
            nf_avg = sum(s.score for s in nf_scores) / len(nf_scores)
            nf_criticals = sum(1 for s in nf_scores if s.critical_count > 0)
            lines.append("## 📈 Context: Non-Forge Jobs")
            lines.append("")
            lines.append(f"- **{len(non_forge_jobs)}** non-forge jobs analyzed")
            lines.append(f"- Average score: **{nf_avg:.0f}/100**")
            lines.append(f"- Jobs with critical signals: {nf_criticals}")
            lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Report generated by trajectory-monitor on {now.strftime('%Y-%m-%d')}*")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze OpenClaw forge crons and produce a markdown report",
    )
    parser.add_argument(
        "--jobs-json",
        default=None,
        help="Path to jobs.json (auto-detected if omitted)",
    )
    parser.add_argument(
        "--runs-dir",
        default=None,
        help="Path to runs/ directory (auto-detected if omitted)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output full JSON report instead of forge-focused markdown",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include all jobs (not just forge-*)",
    )

    args = parser.parse_args()

    # Resolve paths
    if args.jobs_json:
        jobs_json = args.jobs_json
        runs_dir = args.runs_dir or ""
    else:
        jobs_json, runs_dir = _find_openclaw_paths()

    if not jobs_json or not Path(jobs_json).exists():
        print("Error: Cannot find jobs.json. Use --jobs-json PATH.", file=sys.stderr)
        return 1

    all_jobs = build_job_states(jobs_json, runs_dir)
    if not all_jobs:
        print("Error: No jobs found.", file=sys.stderr)
        return 1

    jobs = all_jobs if args.all else filter_forge_jobs(all_jobs)
    signals_by_job = analyze_all(jobs)
    scores = score_all(jobs)

    if args.json:
        output = generate_json_report(jobs)
    else:
        output = generate_forge_report(
            all_jobs=all_jobs,
            forge_jobs=jobs,
            signals_by_job=signals_by_job,
            scores=scores,
        )

    if args.output:
        Path(args.output).write_text(output)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
