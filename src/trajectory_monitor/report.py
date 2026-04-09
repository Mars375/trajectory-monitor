"""Report generator — terminal output + structured JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .parser import JobState
from .recommendations import format_recommendations_report, recommendations_to_json
from .scorer import QualityScore, analyze_trend, score_all, trend_to_dict
from .signals import Severity, analyze_all


def _severity_icon(sev: Severity) -> str:
    return {
        Severity.INFO: "💡",
        Severity.WARNING: "⚠️",
        Severity.CRITICAL: "🔴",
    }.get(sev, "??")


def _trend_icon(direction: str) -> str:
    return {
        "improving": "↗",
        "stable": "→",
        "regressing": "↘",
        "insufficient_data": "·",
    }.get(direction, "?")


def generate_terminal_report(jobs: list[JobState]) -> str:
    """Generate a human-readable terminal report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  TRAJECTORY MONITOR — Session Analysis Report")
    lines.append(f"  Generated: {datetime.now(timezone.utc).isoformat()[:19]}Z")
    lines.append("=" * 60)

    signals_by_job = analyze_all(jobs)
    scores = score_all(jobs)
    trends_by_job = {job.name: analyze_trend(job) for job in jobs}

    # Summary
    total_signals = sum(len(s) for s in signals_by_job.values())
    critical = sum(1 for sl in signals_by_job.values() for s in sl if s.severity == Severity.CRITICAL)
    warnings = sum(1 for sl in signals_by_job.values() for s in sl if s.severity == Severity.WARNING)
    avg_score = sum(s.score for s in scores) / len(scores) if scores else 0
    regressing = sum(1 for t in trends_by_job.values() if t.direction == "regressing")
    improving = sum(1 for t in trends_by_job.values() if t.direction == "improving")

    lines.append("")
    lines.append(f"  Jobs analyzed: {len(jobs)}")
    lines.append(f"  Total signals: {total_signals} ({critical} critical, {warnings} warnings)")
    lines.append(f"  Average quality score: {avg_score:.0f}/100")
    lines.append(f"  Trend overview: {regressing} regressing, {improving} improving")
    lines.append("")

    # Score table
    lines.append("─" * 60)
    lines.append(f"  {'Job':<28s} {'Score':>5s} {'Grade':>5s} {'Trend':>7s} {'Signals':>7s}")
    lines.append("─" * 60)

    for s in scores:
        sig_count = len(signals_by_job.get(s.job_name, []))
        trend = trends_by_job.get(s.job_name)
        trend_label = _trend_icon(trend.direction) if trend else "·"
        lines.append(
            f"  {s.job_name:<28.28s} {s.score:>5d} {s.grade:>5s} {trend_label:>7s} {sig_count:>7d}"
        )

    lines.append("─" * 60)

    # Signal details
    if signals_by_job:
        lines.append("")
        lines.append("  SIGNALS DETECTED")
        lines.append("  " + "─" * 56)
        for job_name, sigs in sorted(signals_by_job.items()):
            lines.append(f"  [{job_name}]")
            for sig in sigs:
                icon = _severity_icon(sig.severity)
                lines.append(f"    {icon} [{sig.kind}] {sig.message}")
            lines.append("")

    # Worst jobs detail
    worst = [s for s in scores if s.score < 60]
    if worst:
        lines.append("  ⚠️  JOBS NEEDING ATTENTION")
        lines.append("  " + "─" * 56)
        for s in worst:
            trend = trends_by_job.get(s.job_name)
            trend_text = f", trend {trend.direction}" if trend and trend.direction != "insufficient_data" else ""
            lines.append(f"  {s.job_name} — score {s.score}/100 (grade {s.grade}{trend_text})")
            if s.breakdown:
                for comp, val in s.breakdown.items():
                    if val < 0:
                        lines.append(f"    ↳ {comp}: {val:.0f}")
        lines.append("")

    # Recommendations
    recs_section = format_recommendations_report(signals_by_job)
    if recs_section:
        lines.append(recs_section)

    lines.append("=" * 60)
    return "\n".join(lines)


def generate_json_report(jobs: list[JobState]) -> str:
    """Generate a structured JSON report."""
    signals_by_job = analyze_all(jobs)
    scores = score_all(jobs)
    trends_by_job = {job.name: analyze_trend(job) for job in jobs}

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "jobs_analyzed": len(jobs),
            "total_signals": sum(len(s) for s in signals_by_job.values()),
            "critical_signals": sum(
                1 for sl in signals_by_job.values() for s in sl if s.severity == Severity.CRITICAL
            ),
            "average_score": sum(s.score for s in scores) / len(scores) if scores else 0,
            "trend_counts": {
                "improving": sum(1 for t in trends_by_job.values() if t.direction == "improving"),
                "stable": sum(1 for t in trends_by_job.values() if t.direction == "stable"),
                "regressing": sum(1 for t in trends_by_job.values() if t.direction == "regressing"),
                "insufficient_data": sum(1 for t in trends_by_job.values() if t.direction == "insufficient_data"),
            },
        },
        "jobs": [],
    }

    score_by_name = {s.job_name: s for s in scores}
    for job in jobs:
        score = score_by_name[job.name]
        sigs = signals_by_job.get(job.name, [])
        report["jobs"].append(
            {
                "name": job.name,
                "score": score.score,
                "grade": score.grade,
                "trend": trend_to_dict(trends_by_job[job.name]),
                "total_runs": job.total_runs,
                "error_rate": round(job.error_rate, 2),
                "consecutive_errors": job.consecutive_errors,
                "signals": [
                    {
                        "kind": s.kind,
                        "severity": s.severity.value,
                        "message": s.message,
                        "details": s.details,
                    }
                    for s in sigs
                ],
            }
        )

    # Add recommendations
    report["recommendations"] = recommendations_to_json(signals_by_job)

    return json.dumps(report, indent=2, ensure_ascii=False)
