"""Session quality scorer — produces a 0-100 score per job."""

from __future__ import annotations

from dataclasses import dataclass

from .parser import JobState, RunEntry
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


@dataclass
class QualityTrend:
    """Comparison between the recent and previous windows of a job."""

    direction: str
    score_delta: int
    previous_score: int | None
    recent_score: int | None
    previous_window: int
    recent_window: int
    error_rate_delta: float
    duration_delta_pct: float | None = None
    token_delta_pct: float | None = None


def score_job(job: JobState, extra_signals: list[Signal] | None = None) -> QualityScore:
    """Score a single job's trajectory quality."""
    signals = analyze_job(job)
    if extra_signals:
        signals = [*signals, *extra_signals]
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


def _trailing_error_streak(runs: list[RunEntry]) -> int:
    streak = 0
    for run in reversed(runs):
        if run.is_error:
            streak += 1
        else:
            break
    return streak


def _window_job(job: JobState, runs: list[RunEntry]) -> JobState:
    last = runs[-1] if runs else None
    return JobState(
        job_id=job.job_id,
        name=job.name,
        description=job.description,
        enabled=job.enabled,
        consecutive_errors=_trailing_error_streak(runs),
        last_run_status=last.status if last else "",
        last_duration_ms=last.duration_ms if last else 0,
        runs=list(runs),
    )


def _avg(values: list[int]) -> float:
    return sum(values) / len(values) if values else 0.0


def _pct_change(previous: float, current: float) -> float | None:
    if previous <= 0:
        return None
    return ((current - previous) / previous) * 100


def analyze_trend(job: JobState, window_size: int = 3) -> QualityTrend:
    """Compare previous vs recent run windows to detect improvement or regression."""
    window = min(window_size, len(job.runs) // 2)
    if window < 2:
        return QualityTrend(
            direction="insufficient_data",
            score_delta=0,
            previous_score=None,
            recent_score=None,
            previous_window=window,
            recent_window=window,
            error_rate_delta=0.0,
        )

    previous_runs = job.runs[-window * 2:-window]
    recent_runs = job.runs[-window:]

    previous_job = _window_job(job, previous_runs)
    recent_job = _window_job(job, recent_runs)

    previous_score = score_job(previous_job)
    recent_score = score_job(recent_job)
    score_delta = recent_score.score - previous_score.score
    error_rate_delta = round(recent_job.error_rate - previous_job.error_rate, 2)

    previous_durations = [r.duration_ms for r in previous_runs if r.duration_ms > 0]
    recent_durations = [r.duration_ms for r in recent_runs if r.duration_ms > 0]
    previous_tokens = [r.total_tokens for r in previous_runs if r.total_tokens > 0]
    recent_tokens = [r.total_tokens for r in recent_runs if r.total_tokens > 0]

    duration_delta_pct = _pct_change(_avg(previous_durations), _avg(recent_durations))
    token_delta_pct = _pct_change(_avg(previous_tokens), _avg(recent_tokens))

    if score_delta >= 8 or error_rate_delta <= -0.25:
        direction = "improving"
    elif score_delta <= -8 or error_rate_delta >= 0.25:
        direction = "regressing"
    else:
        direction = "stable"

    return QualityTrend(
        direction=direction,
        score_delta=score_delta,
        previous_score=previous_score.score,
        recent_score=recent_score.score,
        previous_window=window,
        recent_window=window,
        error_rate_delta=error_rate_delta,
        duration_delta_pct=duration_delta_pct,
        token_delta_pct=token_delta_pct,
    )


def trend_to_dict(trend: QualityTrend) -> dict[str, object]:
    """Serialize a QualityTrend for JSON/MCP output."""
    return {
        "direction": trend.direction,
        "score_delta": trend.score_delta,
        "previous_score": trend.previous_score,
        "recent_score": trend.recent_score,
        "previous_window": trend.previous_window,
        "recent_window": trend.recent_window,
        "error_rate_delta": round(trend.error_rate_delta, 2),
        "duration_delta_pct": None if trend.duration_delta_pct is None else round(trend.duration_delta_pct, 1),
        "token_delta_pct": None if trend.token_delta_pct is None else round(trend.token_delta_pct, 1),
    }


def score_all(jobs: list[JobState]) -> list[QualityScore]:
    """Score all jobs, sorted by score ascending (worst first)."""
    scores = [score_job(j) for j in jobs]
    scores.sort(key=lambda s: s.score)
    return scores
