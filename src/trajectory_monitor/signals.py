"""Signal detectors for agent trajectory anomalies.

Signals:
1. CrashRepeat — same error pattern repeated across consecutive runs
2. Loop — same summary/action repeated without progression
3. Stagnation — no runs recorded (job exists but never executed)
4. DurationSpike — run duration suddenly 3x+ the average
5. TokenBloat — output tokens spiraling upward across runs
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from .parser import JobState, RunEntry


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Signal:
    """Detected anomaly signal."""

    kind: str
    severity: Severity
    message: str
    job_name: str
    details: dict | None = None


def _normalize_error(error: str) -> str:
    """Strip specific paths/values to group similar errors."""
    # Remove file paths
    s = re.sub(r"/[/\w.-]+", "<path>", error)
    # Remove numbers (ids, sizes, etc.)
    s = re.sub(r"\b\d{3,}\b", "<num>", s)
    # Remove hex ids
    s = re.sub(r"[0-9a-f]{8,}", "<hex>", s)
    return s.strip()


def detect_crash_repeat(job: JobState) -> Signal | None:
    """Same error pattern repeated across 2+ consecutive runs."""
    errors = [(r, _normalize_error(r.error)) for r in job.runs if r.is_error and r.error]

    if len(errors) < 2:
        return None

    # Check for consecutive same normalized error
    streak = 1
    max_streak = 1
    streak_error = errors[0][1]
    for i in range(1, len(errors)):
        if errors[i][1] == errors[i - 1][1]:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 1

    if max_streak >= 2:
        severity = Severity.CRITICAL if max_streak >= 3 else Severity.WARNING
        return Signal(
            kind="crash_repeat",
            severity=severity,
            message=f"Same error repeated {max_streak}x: {streak_error[:80]}",
            job_name=job.name,
            details={"streak": max_streak, "error_pattern": streak_error[:120]},
        )
    return None


def detect_loop(job: JobState) -> Signal | None:
    """Similar summaries repeated without progression (loop detection).

    Heuristic: if 3+ consecutive runs have summaries sharing >60% word overlap.
    """
    ok_runs = [r for r in job.runs if r.summary and not r.is_error]
    if len(ok_runs) < 3:
        return None

    def word_set(text: str) -> set[str]:
        return set(re.findall(r"\b\w{4,}\b", text.lower()))

    max_streak = 1
    streak = 1
    for i in range(1, len(ok_runs)):
        ws1 = word_set(ok_runs[i - 1].summary)
        ws2 = word_set(ok_runs[i].summary)
        if not ws1 or not ws2:
            continue
        overlap = len(ws1 & ws2) / min(len(ws1), len(ws2))
        if overlap > 0.6:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 1

    if max_streak >= 3:
        return Signal(
            kind="loop",
            severity=Severity.WARNING,
            message=f"Similar output repeated {max_streak}x — possible loop",
            job_name=job.name,
            details={"streak": max_streak},
        )
    return None


def detect_stagnation(job: JobState) -> Signal | None:
    """Job exists but has never run (stagnation)."""
    if job.total_runs == 0 and job.enabled:
        return Signal(
            kind="stagnation",
            severity=Severity.INFO,
            message="Job enabled but never executed",
            job_name=job.name,
            details={"consecutive_errors": job.consecutive_errors},
        )
    return None


def detect_duration_spike(job: JobState) -> Signal | None:
    """Last run duration is 3x+ the historical average."""
    if len(job.runs) < 2:
        return None

    runs_with_dur = [r for r in job.runs if r.duration_ms > 0]
    if len(runs_with_dur) < 2:
        return None

    # Average excluding the last run
    historical = runs_with_dur[:-1]
    avg = sum(r.duration_ms for r in historical) / len(historical)
    last = runs_with_dur[-1].duration_ms

    if avg > 0 and last > avg * 3:
        return Signal(
            kind="duration_spike",
            severity=Severity.WARNING,
            message=f"Last run {last / 1000:.0f}s vs avg {avg / 1000:.0f}s (>{3}x spike)",
            job_name=job.name,
            details={"last_ms": last, "avg_ms": avg, "ratio": round(last / avg, 1)},
        )
    return None


def detect_token_bloat(job: JobState) -> Signal | None:
    """Output tokens increasing monotonically across 3+ runs."""
    ok_runs = [r for r in job.runs if r.output_tokens > 0 and not r.is_error]
    if len(ok_runs) < 3:
        return None

    # Check if last 3 runs have monotonically increasing output tokens
    last_3 = ok_runs[-3:]
    if all(last_3[i].output_tokens < last_3[i + 1].output_tokens for i in range(2)):
        growth = last_3[-1].output_tokens / last_3[0].output_tokens
        if growth > 1.5:
            return Signal(
                kind="token_bloat",
                severity=Severity.WARNING,
                message=f"Output tokens growing: {last_3[0].output_tokens}→{last_3[-1].output_tokens} ({growth:.1f}x)",
                job_name=job.name,
                details={"growth_factor": round(growth, 1)},
            )
    return None


def detect_consecutive_errors(job: JobState) -> Signal | None:
    """Job has consecutiveErrors > 0 in state."""
    if job.consecutive_errors >= 2:
        return Signal(
            kind="consecutive_errors",
            severity=Severity.CRITICAL,
            message=f"{job.consecutive_errors} consecutive errors",
            job_name=job.name,
            details={"consecutive_errors": job.consecutive_errors},
        )
    elif job.consecutive_errors == 1:
        return Signal(
            kind="consecutive_errors",
            severity=Severity.WARNING,
            message="1 consecutive error (watch)",
            job_name=job.name,
            details={"consecutive_errors": 1},
        )
    return None


# Registry of all detectors
DETECTORS = [
    detect_consecutive_errors,
    detect_crash_repeat,
    detect_loop,
    detect_stagnation,
    detect_duration_spike,
    detect_token_bloat,
]


def analyze_job(job: JobState) -> list[Signal]:
    """Run all detectors on a single job."""
    signals: list[Signal] = []
    for detector in DETECTORS:
        result = detector(job)
        if result is not None:
            signals.append(result)
    return signals


def analyze_all(jobs: list[JobState]) -> dict[str, list[Signal]]:
    """Run all detectors on all jobs. Returns {job_name: [signals]}."""
    results: dict[str, list[Signal]] = {}
    for job in jobs:
        signals = analyze_job(job)
        if signals:
            results[job.name] = signals
    return results
