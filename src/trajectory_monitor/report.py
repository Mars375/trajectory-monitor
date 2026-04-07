"""Report generator — terminal output + structured JSON."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .parser import JobState
from .scorer import QualityScore, score_all
from .signals import Severity, analyze_all


def _severity_icon(sev: Severity) -> str:
    return {
        Severity.INFO: "💡",
        Severity.WARNING: "⚠️",
        Severity.CRITICAL: "🔴",
    }.get(sev, "??")


def generate_terminal_report(jobs: list[JobState]) -> str:
    """Generate a human-readable terminal report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  TRAJECTORY MONITOR — Session Analysis Report")
    lines.append(f"  Generated: {datetime.now(timezone.utc).isoformat()[:19]}Z")
    lines.append("=" * 60)

    signals_by_job = analyze_all(jobs)
    scores = score_all(jobs)

    # Summary
    total_signals = sum(len(s) for s in signals_by_job.values())
    critical = sum(1 for sl in signals_by_job.values() for s in sl if s.severity == Severity.CRITICAL)
    warnings = sum(1 for sl in signals_by_job.values() for s in sl if s.severity == Severity.WARNING)
    avg_score = sum(s.score for s in scores) / len(scores) if scores else 0

    lines.append("")
    lines.append(f"  Jobs analyzed: {len(jobs)}")
    lines.append(f"  Total signals: {total_signals} ({critical} critical, {warnings} warnings)")
    lines.append(f"  Average quality score: {avg_score:.0f}/100")
    lines.append("")

    # Score table
    lines.append("─" * 60)
    lines.append(f"  {'Job':<35s} {'Score':>5s} {'Grade':>5s} {'Signals':>7s}")
    lines.append("─" * 60)

    for s in scores:
        sig_count = len(signals_by_job.get(s.job_name, []))
        lines.append(
            f"  {s.job_name:<35s} {s.score:>5d} {s.grade:>5s} {sig_count:>7d}"
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
            lines.append(f"  {s.job_name} — score {s.score}/100 (grade {s.grade})")
            if s.breakdown:
                for comp, val in s.breakdown.items():
                    if val < 0:
                        lines.append(f"    ↳ {comp}: {val:.0f}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


def generate_json_report(jobs: list[JobState]) -> str:
    """Generate a structured JSON report."""
    signals_by_job = analyze_all(jobs)
    scores = score_all(jobs)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "jobs_analyzed": len(jobs),
            "total_signals": sum(len(s) for s in signals_by_job.values()),
            "critical_signals": sum(
                1 for sl in signals_by_job.values() for s in sl if s.severity == Severity.CRITICAL
            ),
            "average_score": sum(s.score for s in scores) / len(scores) if scores else 0,
        },
        "jobs": [],
    }

    for job, score in zip(jobs, [s for s in sorted(scores, key=lambda x: x.job_name)]):
        sigs = signals_by_job.get(job.name, [])
        report["jobs"].append(
            {
                "name": job.name,
                "score": score.score,
                "grade": score.grade,
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

    return json.dumps(report, indent=2, ensure_ascii=False)
