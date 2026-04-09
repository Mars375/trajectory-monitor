"""Recommendation engine — generates actionable fix suggestions from signals.

Maps each signal type + severity to specific, contextual recommendations
that tell the user WHAT to do, not just what's wrong.
"""

from __future__ import annotations

from dataclasses import dataclass

from .signals import Signal, Severity


@dataclass
class Recommendation:
    """A single actionable recommendation."""

    priority: str  # "high" | "medium" | "low"
    signal_kind: str
    action: str
    details: str

    @property
    def icon(self) -> str:
        return {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(self.priority, "⚪")


# ── Recommendation rules per signal type ─────────────────────────

_RULES: dict[str, dict] = {
    "crash_repeat": {
        "critical": [
            (
                "Investigate the error pattern and fix root cause before re-enabling",
                "The same error repeats {streak}x. Check recent code changes or dependency updates. "
                "If the job keeps failing on the same issue, disable it temporarily to stop wasting runs.",
            ),
        ],
        "warning": [
            (
                "Monitor the error pattern — may need intervention soon",
                "Error repeating {streak}x. Check if this is a transient failure or an emerging pattern.",
            ),
        ],
    },
    "loop": {
        "critical": [
            (
                "Review the agent prompt — it may lack a clear exit condition",
                "Agent is repeating similar output {streak}x. This often means the task description "
                "is too broad, or the agent can't determine when it's done. Add explicit completion criteria.",
            ),
        ],
        "warning": [
            (
                "Check if the agent is stuck in a repetitive pattern",
                "Similar output repeated {streak}x. Consider adding a max-iteration guard "
                "or refining the task objective.",
            ),
        ],
    },
    "consecutive_errors": {
        "critical": [
            (
                "Urgent: {consecutive_errors} consecutive failures — disable or fix immediately",
                "The job has failed {consecutive_errors} times in a row. Each failed run wastes tokens. "
                "Either fix the root cause or disable the job until you can investigate.",
            ),
        ],
        "warning": [
            (
                "One consecutive error — keep an eye on next run",
                "If the next run also fails, escalate to fix mode. "
                "A single error may be transient but two is a pattern.",
            ),
        ],
    },
    "stagnation": {
        "info": [
            (
                "Job is enabled but has never run — check schedule or remove",
                "A job with no runs is either misconfigured or unnecessary. "
                "Verify the cron schedule and ensure the job is still needed.",
            ),
        ],
    },
    "duration_spike": {
        "warning": [
            (
                "Last run was {ratio}x slower than average — check for resource issues",
                "Sudden duration spikes often indicate: resource contention on the host, "
                "an increasingly complex task (context bloat), or an external API slowdown.",
            ),
        ],
    },
    "token_bloat": {
        "warning": [
            (
                "Output tokens growing {growth_factor}x — check for context accumulation",
                "The agent may be accumulating context across runs without pruning. "
                "Review the session configuration and consider reducing context window "
                "or adding periodic cleanup.",
            ),
        ],
    },
    "feature_race": {
        "critical": [
            (
                "STOP adding features — validate existing ones first (enforce 'validate before build')",
                "{streak} consecutive feature-add runs without any validation. This is the #1 cause of "
                "accumulated broken code. Add a validation step (tests, smoke test) between features. "
                "Consider splitting the job's responsibilities into smaller, focused tasks.",
            ),
        ],
        "warning": [
            (
                "Feature streak detected — insert a validation run before continuing",
                "{streak} features added without validation. Insert a test/validate run "
                "to catch regressions before they compound.",
            ),
        ],
    },
    "hallucination_pattern": {
        "critical": [
            (
                "Agent claims to create files that don't persist — verify workspace state",
                "The agent repeatedly claims to create files across runs, suggesting they "
                "were never actually saved. Check: workspace permissions, mount points, "
                "and whether the agent writes to the correct directory.",
            ),
        ],
        "warning": [
            (
                "Potential file hallucination — cross-reference with actual workspace",
                "Some referenced files may not exist. Run with --workspace-check to verify "
                "file existence against the actual filesystem.",
            ),
        ],
    },
    "regression_trend": {
        "critical": [
            (
                "Job quality dropping sharply (delta={score_delta}) — investigate recent changes",
                "Score dropped from {previous_score} to {recent_score} across the last {window_size} runs. "
                "This is a strong regression signal. Check: recent prompt/code changes, "
                "dependency updates, or environment shifts that may have introduced failures.",
            ),
        ],
        "warning": [
            (
                "Job regressing (delta={score_delta}) — monitor closely",
                "Score trending down from {previous_score} to {recent_score}. "
                "If the next window also regresses, escalate to investigation. "
                "Early intervention is cheaper than recovery.",
            ),
        ],
    },
}


def generate_recommendations(signals: list[Signal]) -> list[Recommendation]:
    """Generate actionable recommendations from a list of signals.

    Returns recommendations sorted by priority (high first).
    """
    recs: list[Recommendation] = []

    for signal in signals:
        sev_key = signal.severity.value
        rules_for_kind = _RULES.get(signal.kind, {})

        # Try exact severity match, then fallback to first available
        rules = rules_for_kind.get(sev_key, [])
        if not rules:
            # Fall back to any available severity for this kind
            for v in rules_for_kind.values():
                rules = v
                break

        for action_template, details_template in rules:
            # Format with signal details if available
            fmt = signal.details or {}
            try:
                action = action_template.format(**fmt)
                details = details_template.format(**fmt)
            except (KeyError, IndexError):
                action = action_template
                details = details_template

            priority = (
                "high"
                if signal.severity == Severity.CRITICAL
                else "medium" if signal.severity == Severity.WARNING else "low"
            )

            recs.append(
                Recommendation(
                    priority=priority,
                    signal_kind=signal.kind,
                    action=action,
                    details=details,
                )
            )

    # Sort: high > medium > low
    order = {"high": 0, "medium": 1, "low": 2}
    recs.sort(key=lambda r: order.get(r.priority, 3))

    return recs


def generate_recommendations_for_all(
    signals_by_job: dict[str, list[Signal]],
) -> dict[str, list[Recommendation]]:
    """Generate recommendations for all jobs. Returns {job_name: [recs]}."""
    return {
        name: generate_recommendations(sigs)
        for name, sigs in signals_by_job.items()
    }


def format_recommendations_report(
    signals_by_job: dict[str, list[Signal]],
) -> str:
    """Generate a human-readable recommendations section for reports."""
    lines: list[str] = []
    all_recs = generate_recommendations_for_all(signals_by_job)

    # Only include jobs that have recommendations
    jobs_with_recs = {
        name: recs for name, recs in all_recs.items() if recs
    }

    if not jobs_with_recs:
        return ""

    lines.append("  📋 RECOMMENDATIONS")
    lines.append("  " + "─" * 56)

    for job_name, recs in sorted(jobs_with_recs.items()):
        lines.append(f"  [{job_name}]")
        for rec in recs:
            lines.append(f"    {rec.icon} {rec.action}")
            lines.append(f"       → {rec.details}")
        lines.append("")

    return "\n".join(lines)


def recommendations_to_json(
    signals_by_job: dict[str, list[Signal]],
) -> dict[str, list[dict]]:
    """Generate JSON-serializable recommendations."""
    all_recs = generate_recommendations_for_all(signals_by_job)
    return {
        name: [
            {
                "priority": r.priority,
                "signal_kind": r.signal_kind,
                "action": r.action,
                "details": r.details,
            }
            for r in recs
        ]
        for name, recs in all_recs.items()
        if recs
    }
