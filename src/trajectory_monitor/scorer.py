"""Session quality scorer — produces a 0-100 score per job."""

from __future__ import annotations

from dataclasses import dataclass

from .parser import JobState
from .signals import Signal, Severity, analyze_job


@dataclass
class QualityScore:
    """Quality score for a single job."""

    job_name: str
    score: int  # 0-100
    breakdown: dict[str, float]  # component scores
    signals_count: int
    critical_count: int
    warning_count: int

    @property
    def grade(self) -> str:
        if self.score >= 90:
            return "A"
        elif self.score >= 75:
            return "B"
        elif self.score >= 60:
            return "C"
        elif self.score >= 40:
            return "D"
        return "F"


def score_job(job: JobState) -> QualityScore:
    """Score a single job's trajectory quality."""
    signals = analyze_job(job)
    breakdown: dict[str, float] = {}

    # 1. Error rate (0-30 points, penalized by error rate)
    if job.total_runs > 0:
        error_rate = job.error_rate
        breakdown["reliability"] = 30 * (1 - error_rate)
    else:
        # No runs = no data = neutral
        breakdown["reliability"] = 15.0

    # 2. Consecutive errors penalty
    if job.consecutive_errors >= 3:
        breakdown["consecutive_penalty"] = -20
    elif job.consecutive_errors >= 2:
        breakdown["consecutive_penalty"] = -10
    elif job.consecutive_errors == 1:
        breakdown["consecutive_penalty"] = -5
    else:
        breakdown["consecutive_penalty"] = 0

    # 3. Activity score (0-20 points)
    if job.total_runs >= 5:
        breakdown["activity"] = 20.0
    elif job.total_runs >= 2:
        breakdown["activity"] = 15.0
    elif job.total_runs >= 1:
        breakdown["activity"] = 10.0
    else:
        breakdown["activity"] = 0.0

    # 4. Duration consistency (0-20 points)
    durations = [r.duration_ms for r in job.runs if r.duration_ms > 0]
    if len(durations) >= 2:
        avg = sum(durations) / len(durations)
        if avg > 0:
            variance = sum((d - avg) ** 2 for d in durations) / len(durations)
            cv = (variance**0.5) / avg  # coefficient of variation
            breakdown["consistency"] = max(0, 20 * (1 - cv))
        else:
            breakdown["consistency"] = 10.0
    else:
        breakdown["consistency"] = 10.0

    # 5. Signal penalty (each signal costs points)
    signal_penalty = 0
    for s in signals:
        if s.severity == Severity.CRITICAL:
            signal_penalty += 15
        elif s.severity == Severity.WARNING:
            signal_penalty += 8
        else:
            signal_penalty += 2
    breakdown["signal_penalty"] = -signal_penalty

    # 6. Enabled bonus
    breakdown["enabled"] = 10.0 if job.enabled else 0.0

    # 7. Recovery bonus: had errors but last run OK
    if job.runs and job.consecutive_errors == 0:
        had_errors = any(r.is_error for r in job.runs)
        if had_errors:
            breakdown["recovery"] = 10.0
        else:
            breakdown["recovery"] = 5.0
    else:
        breakdown["recovery"] = 0.0

    raw = sum(breakdown.values())
    score = max(0, min(100, int(raw)))

    criticals = sum(1 for s in signals if s.severity == Severity.CRITICAL)
    warnings = sum(1 for s in signals if s.severity == Severity.WARNING)

    return QualityScore(
        job_name=job.name,
        score=score,
        breakdown=breakdown,
        signals_count=len(signals),
        critical_count=criticals,
        warning_count=warnings,
    )


def score_all(jobs: list[JobState]) -> list[QualityScore]:
    """Score all jobs, sorted by score ascending (worst first)."""
    scores = [score_job(j) for j in jobs]
    scores.sort(key=lambda s: s.score)
    return scores
