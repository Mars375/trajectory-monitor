"""Signal detectors for agent trajectory anomalies.

Signals:
1. CrashRepeat — same error pattern repeated across consecutive runs
2. Loop — same summary/action repeated without progression
3. Stagnation — no runs recorded (job exists but never executed)
4. DurationSpike — run duration suddenly 3x+ the average
5. TokenBloat — output tokens spiraling upward across runs
6. FeatureRace — multiple feature additions without intermediate validation
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


# ── Feature-race detector ───────────────────────────────────────

_FEATURE_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"\b(?:added?|impl(?:ement|ément)(?:ed|[eé]e?s?)?|"
        r"creat(?:ed|[eé]e?s?)|cr[eé]{2}s?|"
        r"built|introduced?|nouvelle?s?\s+feature|"
        r"ajout[eé]?s?|nouvelles?\s+fonction)\b",
        re.I,
    ),
]
_VALIDATION_PATTERNS: list[re.Pattern] = [
    re.compile(
        r"\b(test(?:ed?|s)?|valid(?:ated?|ation|é)|v[eé]rifi[eé]|fix(?:ed)?|"
        r"corrig[eé]|smoke\s*test|pytest|assert|bugfix)\b",
        re.I,
    ),
]


def _mentions_feature(summary: str) -> bool:
    return any(p.search(summary) for p in _FEATURE_PATTERNS)


def _mentions_validation(summary: str) -> bool:
    return any(p.search(summary) for p in _VALIDATION_PATTERNS)


def detect_feature_race(job: JobState) -> Signal | None:
    """Detect 3+ consecutive feature-adding runs without intermediate validation.

    Specific to the forge context: a cron that keeps shipping new features
    in every run without ever stopping to test/validate them is likely
    accumulating broken code.
    """
    ok_runs = [r for r in job.runs if r.summary and not r.is_error]
    if len(ok_runs) < 3:
        return None

    streak = 0
    max_streak = 0
    streak_summaries: list[str] = []

    for run in ok_runs:
        if _mentions_feature(run.summary) and not _mentions_validation(run.summary):
            streak += 1
            streak_summaries.append(run.summary[:60])
            if streak > max_streak:
                max_streak = streak
        else:
            streak = 0
            streak_summaries = []

    if max_streak >= 3:
        severity = Severity.CRITICAL if max_streak >= 5 else Severity.WARNING
        return Signal(
            kind="feature_race",
            severity=severity,
            message=(
                f"{max_streak} consecutive feature-add runs without validation"
            ),
            job_name=job.name,
            details={"streak": max_streak, "summaries": streak_summaries[:5]},
        )
    return None


# ── Hallucination-pattern detector ────────────────────────────────

# Extract file paths with directory components: src/foo.py, path/to/file.md
_FILE_PATH_RE = re.compile(
    r"(?:^|[\s,(\[{\"'])"
    r"(`{1,2})?"
    r"("
    r"(?:[\w.-]+/)+"
    r"[\w.-]+\.[a-zA-Z]{1,12}"
    r")"
    r"(?:\1)?"
    r"(?:[\s,)\]}\"]|$)",
    re.MULTILINE,
)

# Bare filenames in backticks with common extensions
_BARE_FILE_RE = re.compile(
    r"`([\w.-]+\.(?:py|js|ts|md|json|yaml|yml|toml|sh|txt|cfg|ini|rs|go))`"
)

# Verbs implying file creation
_CREATE_MODIFY_RE = re.compile(
    r"\b(?:created?|added?|wrote|writ(?:ing|ten)|built|implement(?:ed|ing)?|"
    r"generat(?:ed|ing)?|new\s+file|modifi(?:ed|cation)|"
    r"ajout[eé]s?|cr[eé]{2}[a-z]*|impl[eé]ment(?:é|e)s?)\b",
    re.I,
)


def _extract_file_paths(text: str) -> set[str]:
    """Extract file path references from text."""
    paths: set[str] = set()
    for m in _FILE_PATH_RE.finditer(text):
        paths.add(m.group(2))
    for m in _BARE_FILE_RE.finditer(text):
        paths.add(m.group(1))
    return {p for p in paths if len(p) >= 5 and "." in p.split("/")[-1]}


def _extract_creation_files(text: str) -> set[str]:
    """Extract file paths mentioned in a creation context."""
    files = _extract_file_paths(text)
    if not files:
        return set()

    creation_files: set[str] = set()
    for m in _CREATE_MODIFY_RE.finditer(text):
        start = max(0, m.start() - 40)
        end = min(len(text), m.end() + 80)
        context = text[start:end]
        for f in files:
            if f in context:
                creation_files.add(f)
    return creation_files


def detect_hallucination_pattern(job: JobState) -> Signal | None:
    """Detect potential hallucination: agent re-creates the same file across runs.

    Heuristic: If a run claims to create/add a file, and a later run
    claims to create/add the SAME file again, the file was likely
    never actually persisted (hallucinated creation).
    Also flags when a run references many files (>5) that never
    appear in any other run (potential bulk hallucination).
    """
    ok_runs = [r for r in job.runs if r.summary and not r.is_error]
    if len(ok_runs) < 2:
        return None

    creation_map: dict[str, list[int]] = {}
    all_referenced: dict[str, set[int]] = {}

    for i, run in enumerate(ok_runs):
        created = _extract_creation_files(run.summary)
        referenced = _extract_file_paths(run.summary)

        for f in created:
            creation_map.setdefault(f, []).append(i)
        for f in referenced:
            all_referenced.setdefault(f, set()).add(i)

    # Check 1: File claimed as 'created' in 2+ different runs
    re_created = {f: runs for f, runs in creation_map.items() if len(runs) >= 2}
    if re_created:
        files_str = ", ".join(f"`{f}`" for f in sorted(re_created)[:5])
        count = len(re_created)
        severity = Severity.CRITICAL if count >= 3 else Severity.WARNING
        return Signal(
            kind="hallucination_pattern",
            severity=severity,
            message=(
                f"{count} file(s) claimed as 'created' in multiple runs "
                f"(likely never persisted): {files_str}"
            ),
            job_name=job.name,
            details={
                "re_created_files": {f: len(runs) for f, runs in sorted(re_created.items())[:10]},
                "type": "re_creation",
            },
        )

    # Check 2: Single run references many unique files not seen elsewhere
    for i, run in enumerate(ok_runs):
        referenced = _extract_file_paths(run.summary)
        if len(referenced) < 5:
            continue
        unique = {f for f in referenced if all_referenced.get(f, set()) == {i}}
        if len(unique) >= 5:
            files_str = ", ".join(f"`{f}`" for f in sorted(unique)[:5])
            return Signal(
                kind="hallucination_pattern",
                severity=Severity.WARNING,
                message=(
                    f"Run references {len(unique)} files not mentioned in any "
                    f"other run: {files_str}"
                ),
                job_name=job.name,
                details={
                    "unique_files": sorted(unique)[:10],
                    "total_referenced": len(referenced),
                    "type": "burst",
                },
            )

    return None


def check_file_existence(
    job: JobState, workspace_path: str | Path
) -> Signal | None:
    """Check if file paths referenced in summaries actually exist on disk.

    Workspace-aware check requiring filesystem access.
    Not registered in DETECTORS — called explicitly with workspace context.
    """
    from pathlib import Path as _Path

    ws = _Path(workspace_path)
    ok_runs = [r for r in job.runs if r.summary and not r.is_error]
    if not ok_runs:
        return None

    all_files: dict[str, int] = {}
    for run in ok_runs:
        for f in _extract_file_paths(run.summary):
            all_files[f] = all_files.get(f, 0) + 1

    if not all_files:
        return None

    missing: dict[str, int] = {}
    for f, count in all_files.items():
        candidates = [_Path(f), ws / f]
        found = any(c.exists() for c in candidates)
        if not found:
            missing[f] = count

    if len(missing) >= 3:
        files_str = ", ".join(f"`{f}`" for f in sorted(missing)[:5])
        severity = Severity.CRITICAL if len(missing) >= 6 else Severity.WARNING
        return Signal(
            kind="hallucination_pattern",
            severity=severity,
            message=(
                f"{len(missing)} referenced file(s) not found in workspace: "
                f"{files_str}"
            ),
            job_name=job.name,
            details={
                "missing_files": sorted(missing.keys())[:15],
                "total_referenced": len(all_files),
                "workspace": str(ws),
                "type": "missing_on_disk",
            },
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
    detect_feature_race,
    detect_hallucination_pattern,
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
