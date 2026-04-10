"""Session quality scorer, produces a 0-100 score per job."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .parser import JobState, RunEntry
from .signals import Signal, Severity, analyze_job


@dataclass
class QualityScore:
    """Quality score for a single job."""

    job_name: str
    score: int
    breakdown: dict[str, float]
    signals_count: int
    critical_count: int
    warning_count: int
    signal_penalties: dict[str, float]

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


@dataclass(frozen=True)
class PolicyThresholds:
    """Configurable thresholds driving action policy decisions."""

    stop_score_below: int = 40
    stabilize_score_below: int = 60
    stop_penalty_at: float = 35.0
    stabilize_penalty_at: float = 20.0
    watch_penalty_at: float = 12.0
    stop_consecutive_errors: int = 2
    watch_warning_count: int = 2

    @classmethod
    def from_mapping(cls, data: dict[str, object]) -> "PolicyThresholds":
        defaults = cls()
        allowed = set(policy_thresholds_to_dict(defaults))
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise ValueError(f"Unknown policy threshold keys: {', '.join(unknown)}")

        def _read_int(key: str) -> int:
            value = data.get(key, getattr(defaults, key))
            if not isinstance(value, (int, float)):
                raise ValueError(f"Policy threshold '{key}' must be numeric")
            return int(value)

        def _read_float(key: str) -> float:
            value = data.get(key, getattr(defaults, key))
            if not isinstance(value, (int, float)):
                raise ValueError(f"Policy threshold '{key}' must be numeric")
            return float(value)

        return cls(
            stop_score_below=_read_int("stop_score_below"),
            stabilize_score_below=_read_int("stabilize_score_below"),
            stop_penalty_at=_read_float("stop_penalty_at"),
            stabilize_penalty_at=_read_float("stabilize_penalty_at"),
            watch_penalty_at=_read_float("watch_penalty_at"),
            stop_consecutive_errors=_read_int("stop_consecutive_errors"),
            watch_warning_count=_read_int("watch_warning_count"),
        )


@dataclass
class ActionPolicy:
    """Operational policy derived from score, signals, and trend."""

    mode: str
    summary: str
    feature_delivery_allowed: bool
    should_alert: bool
    validation_required: bool
    max_new_features: int
    reasons: list[str]
    thresholds: dict[str, int | float]


_BASE_SIGNAL_PENALTIES = {
    Severity.CRITICAL: 15.0,
    Severity.WARNING: 8.0,
    Severity.INFO: 2.0,
}

_SIGNAL_KIND_WEIGHTS = {
    "consecutive_errors": 1.4,
    "crash_repeat": 1.3,
    "hallucination_pattern": 1.3,
    "regression_trend": 1.2,
    "feature_race": 1.2,
    "loop": 1.1,
    "duration_spike": 0.8,
    "token_bloat": 0.7,
    "stagnation": 0.5,
}


def policy_thresholds_to_dict(thresholds: PolicyThresholds) -> dict[str, int | float]:
    """Serialize policy thresholds for JSON/MCP output."""
    return asdict(thresholds)


def _path_string_exists(value: str) -> bool:
    if not value or "\n" in value or "\r" in value:
        return False
    try:
        return Path(value).expanduser().exists()
    except OSError:
        return False


def resolve_policy_thresholds(
    source: PolicyThresholds | dict[str, object] | str | None = None,
) -> PolicyThresholds:
    """Resolve policy thresholds from defaults, mapping, JSON string, or JSON file path."""
    if source is None or source == "":
        return PolicyThresholds()
    if isinstance(source, PolicyThresholds):
        return source
    if isinstance(source, dict):
        return PolicyThresholds.from_mapping(source)
    if not isinstance(source, str):
        raise ValueError("policy thresholds must be a dict, JSON string, or file path")

    raw = source.strip()
    if not raw:
        return PolicyThresholds()
    if _path_string_exists(raw):
        raw = Path(raw).expanduser().read_text()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid policy threshold JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("policy thresholds JSON must decode to an object")
    return PolicyThresholds.from_mapping(data)


def _score_signal_penalties(signals: list[Signal]) -> tuple[float, dict[str, float]]:
    """Return weighted signal penalties, keyed by signal kind."""
    penalties: dict[str, float] = {}
    total = 0.0

    for signal in signals:
        base = _BASE_SIGNAL_PENALTIES.get(signal.severity, 2.0)
        weight = _SIGNAL_KIND_WEIGHTS.get(signal.kind, 1.0)
        penalty = round(base * weight, 1)
        penalties[signal.kind] = round(penalties.get(signal.kind, 0.0) + penalty, 1)
        total += penalty

    return round(total, 1), penalties


def score_job(job: JobState, extra_signals: list[Signal] | None = None) -> QualityScore:
    """Score a single job's trajectory quality."""
    signals = analyze_job(job)
    if extra_signals:
        signals = [*signals, *extra_signals]
    breakdown: dict[str, float] = {}

    if job.total_runs > 0:
        error_rate = job.error_rate
        breakdown["reliability"] = 30 * (1 - error_rate)
    else:
        breakdown["reliability"] = 15.0

    if job.consecutive_errors >= 3:
        breakdown["consecutive_penalty"] = -20
    elif job.consecutive_errors >= 2:
        breakdown["consecutive_penalty"] = -10
    elif job.consecutive_errors == 1:
        breakdown["consecutive_penalty"] = -5
    else:
        breakdown["consecutive_penalty"] = 0

    if job.total_runs >= 5:
        breakdown["activity"] = 20.0
    elif job.total_runs >= 2:
        breakdown["activity"] = 15.0
    elif job.total_runs >= 1:
        breakdown["activity"] = 10.0
    else:
        breakdown["activity"] = 0.0

    durations = [r.duration_ms for r in job.runs if r.duration_ms > 0]
    if len(durations) >= 2:
        avg = sum(durations) / len(durations)
        if avg > 0:
            variance = sum((d - avg) ** 2 for d in durations) / len(durations)
            cv = (variance**0.5) / avg
            breakdown["consistency"] = max(0, 20 * (1 - cv))
        else:
            breakdown["consistency"] = 10.0
    else:
        breakdown["consistency"] = 10.0

    signal_penalty, signal_penalties = _score_signal_penalties(signals)
    breakdown["signal_penalty"] = -signal_penalty

    breakdown["enabled"] = 10.0 if job.enabled else 0.0

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
        signal_penalties=signal_penalties,
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


def _add_reason(reasons: list[str], message: str) -> None:
    if message and message not in reasons:
        reasons.append(message)


def build_action_policy(
    job: JobState,
    score: QualityScore | None = None,
    signals: list[Signal] | None = None,
    trend: QualityTrend | None = None,
    thresholds: PolicyThresholds | dict[str, object] | str | None = None,
) -> ActionPolicy:
    """Derive an operational policy from score, signals, trend, and optional thresholds."""
    signals = list(signals) if signals is not None else analyze_job(job)
    score = score or score_job(job)
    trend = trend or analyze_trend(job)
    resolved_thresholds = resolve_policy_thresholds(thresholds)

    total_penalty = round(sum(score.signal_penalties.values()), 1)
    critical_kinds = {s.kind for s in signals if s.severity == Severity.CRITICAL}
    warning_kinds = {s.kind for s in signals if s.severity == Severity.WARNING}
    reasons: list[str] = []

    if job.consecutive_errors >= resolved_thresholds.stop_consecutive_errors:
        _add_reason(reasons, f"{job.consecutive_errors} consecutive errors")
    if score.score < resolved_thresholds.stop_score_below:
        _add_reason(reasons, f"score {score.score}/100")
    if total_penalty >= resolved_thresholds.stop_penalty_at:
        _add_reason(reasons, f"heavy signal penalties ({total_penalty})")
    if trend.direction == "regressing":
        _add_reason(reasons, f"regressing trend (Δ{trend.score_delta})")

    if "crash_repeat" in critical_kinds:
        _add_reason(reasons, "repeated crash pattern")
    if "consecutive_errors" in critical_kinds:
        _add_reason(reasons, "critical consecutive error state")
    if "hallucination_pattern" in critical_kinds:
        _add_reason(reasons, "critical hallucination risk")
    if "feature_race" in critical_kinds:
        _add_reason(reasons, "feature race detected")
    if "regression_trend" in critical_kinds:
        _add_reason(reasons, "critical regression trend")

    stop_conditions = [
        job.consecutive_errors >= resolved_thresholds.stop_consecutive_errors,
        score.score < resolved_thresholds.stop_score_below,
        total_penalty >= resolved_thresholds.stop_penalty_at,
        "crash_repeat" in critical_kinds,
        "consecutive_errors" in critical_kinds,
        "hallucination_pattern" in critical_kinds,
        "feature_race" in critical_kinds,
    ]
    stabilize_conditions = [
        trend.direction == "regressing",
        score.critical_count >= 1,
        total_penalty >= resolved_thresholds.stabilize_penalty_at,
        score.score < resolved_thresholds.stabilize_score_below,
        "regression_trend" in critical_kinds,
    ]
    watch_conditions = [
        score.warning_count >= resolved_thresholds.watch_warning_count,
        total_penalty >= resolved_thresholds.watch_penalty_at,
        bool(warning_kinds & {"loop", "token_bloat", "duration_spike", "stagnation"}),
    ]

    if any(stop_conditions):
        mode = "bugfix_only"
        summary = "Stop feature work, fix failures, then rerun validation."
        feature_delivery_allowed = False
        should_alert = True
        max_new_features = 0
    elif any(stabilize_conditions):
        if score.score < resolved_thresholds.stabilize_score_below:
            _add_reason(reasons, f"score below safety margin ({score.score}/100)")
        mode = "stabilize"
        summary = "Prefer fixes and validation before shipping more changes."
        feature_delivery_allowed = False
        should_alert = trend.direction == "regressing" or score.critical_count >= 1
        max_new_features = 0
    elif any(watch_conditions):
        if score.warning_count >= resolved_thresholds.watch_warning_count:
            _add_reason(reasons, f"{score.warning_count} warning signals")
        if total_penalty >= resolved_thresholds.watch_penalty_at:
            _add_reason(reasons, f"moderate signal penalties ({total_penalty})")
        mode = "watch"
        summary = "Proceed carefully and validate after each increment."
        feature_delivery_allowed = True
        should_alert = False
        max_new_features = 1
    else:
        _add_reason(reasons, "no blocking signals detected")
        mode = "normal"
        summary = "Healthy enough for normal iteration."
        feature_delivery_allowed = True
        should_alert = False
        max_new_features = 3

    return ActionPolicy(
        mode=mode,
        summary=summary,
        feature_delivery_allowed=feature_delivery_allowed,
        should_alert=should_alert,
        validation_required=True,
        max_new_features=max_new_features,
        reasons=reasons,
        thresholds=policy_thresholds_to_dict(resolved_thresholds),
    )


def action_policy_to_dict(policy: ActionPolicy) -> dict[str, object]:
    """Serialize an ActionPolicy for JSON/MCP output."""
    return {
        "mode": policy.mode,
        "summary": policy.summary,
        "feature_delivery_allowed": policy.feature_delivery_allowed,
        "should_alert": policy.should_alert,
        "validation_required": policy.validation_required,
        "max_new_features": policy.max_new_features,
        "reasons": policy.reasons,
        "thresholds": policy.thresholds,
    }


def score_all(jobs: list[JobState]) -> list[QualityScore]:
    """Score all jobs, sorted by score ascending (worst first)."""
    scores = [score_job(j) for j in jobs]
    scores.sort(key=lambda s: s.score)
    return scores
