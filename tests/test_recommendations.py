"""Tests for the recommendations module."""

from __future__ import annotations

import pytest

from trajectory_monitor.signals import Signal, Severity
from trajectory_monitor.recommendations import (
    Recommendation,
    generate_recommendations,
    generate_recommendations_for_all,
    format_recommendations_report,
    recommendations_to_json,
)


def _signal(kind: str, severity: Severity, details: dict | None = None) -> Signal:
    return Signal(
        kind=kind,
        severity=severity,
        message=f"test {kind}",
        job_name="test-job",
        details=details,
    )


class TestGenerateRecommendations:
    def test_empty_signals(self):
        recs = generate_recommendations([])
        assert recs == []

    def test_crash_repeat_critical(self):
        sig = _signal("crash_repeat", Severity.CRITICAL, {"streak": 5})
        recs = generate_recommendations([sig])
        assert len(recs) >= 1
        assert recs[0].priority == "high"
        assert recs[0].signal_kind == "crash_repeat"
        # streak count is in details string
        assert "5x" in recs[0].details

    def test_crash_repeat_warning(self):
        sig = _signal("crash_repeat", Severity.WARNING, {"streak": 2})
        recs = generate_recommendations([sig])
        assert len(recs) >= 1
        assert recs[0].priority == "medium"

    def test_consecutive_errors_critical(self):
        sig = _signal("consecutive_errors", Severity.CRITICAL, {"consecutive_errors": 4})
        recs = generate_recommendations([sig])
        assert len(recs) >= 1
        assert recs[0].priority == "high"
        assert "4" in recs[0].action

    def test_loop_warning(self):
        sig = _signal("loop", Severity.WARNING, {"streak": 3})
        recs = generate_recommendations([sig])
        assert len(recs) >= 1
        # streak count is in details
        assert "3x" in recs[0].details

    def test_feature_race_critical(self):
        sig = _signal("feature_race", Severity.CRITICAL, {"streak": 7})
        recs = generate_recommendations([sig])
        assert len(recs) >= 1
        assert recs[0].priority == "high"
        assert "STOP" in recs[0].action or "validate" in recs[0].action.lower()

    def test_hallucination_pattern_warning(self):
        sig = _signal("hallucination_pattern", Severity.WARNING)
        recs = generate_recommendations([sig])
        assert len(recs) >= 1
        assert "hallucination" in recs[0].action.lower() or "workspace" in recs[0].action.lower()

    def test_stagnation_info(self):
        sig = _signal("stagnation", Severity.INFO)
        recs = generate_recommendations([sig])
        assert len(recs) >= 1
        assert recs[0].priority == "low"

    def test_duration_spike_warning(self):
        sig = _signal("duration_spike", Severity.WARNING, {"ratio": 4.2})
        recs = generate_recommendations([sig])
        assert len(recs) >= 1
        assert "4.2x" in recs[0].action

    def test_token_bloat_warning(self):
        sig = _signal("token_bloat", Severity.WARNING, {"growth_factor": 3.5})
        recs = generate_recommendations([sig])
        assert len(recs) >= 1
        assert "3.5x" in recs[0].action

    def test_unknown_signal_kind(self):
        """Unknown signal kinds produce no recommendations (graceful)."""
        sig = _signal("unknown_detector", Severity.WARNING)
        recs = generate_recommendations([sig])
        assert recs == []

    def test_sorted_by_priority(self):
        """High priority recommendations come first."""
        sigs = [
            _signal("stagnation", Severity.INFO),
            _signal("crash_repeat", Severity.CRITICAL, {"streak": 4}),
            _signal("loop", Severity.WARNING, {"streak": 3}),
        ]
        recs = generate_recommendations(sigs)
        priorities = [r.priority for r in recs]
        assert priorities == sorted(priorities, key=lambda p: {"high": 0, "medium": 1, "low": 2}.get(p, 3))

    def test_multiple_signals(self):
        sigs = [
            _signal("crash_repeat", Severity.CRITICAL, {"streak": 3}),
            _signal("loop", Severity.WARNING, {"streak": 4}),
        ]
        recs = generate_recommendations(sigs)
        assert len(recs) >= 2

    def test_recommendation_has_details(self):
        sig = _signal("crash_repeat", Severity.CRITICAL, {"streak": 3})
        recs = generate_recommendations([sig])
        assert recs[0].details  # non-empty details string


class TestGenerateRecommendationsForAll:
    def test_empty(self):
        result = generate_recommendations_for_all({})
        assert result == {}

    def test_multiple_jobs(self):
        signals = {
            "job-a": [_signal("crash_repeat", Severity.CRITICAL, {"streak": 3})],
            "job-b": [_signal("loop", Severity.WARNING, {"streak": 4})],
        }
        result = generate_recommendations_for_all(signals)
        assert "job-a" in result
        assert "job-b" in result
        assert len(result["job-a"]) >= 1
        assert len(result["job-b"]) >= 1

    def test_job_with_no_matching_rules_produces_empty_list(self):
        signals = {
            "job-c": [_signal("nonexistent", Severity.WARNING)],
        }
        result = generate_recommendations_for_all(signals)
        assert "job-c" in result
        assert result["job-c"] == []


class TestFormatRecommendationsReport:
    def test_empty(self):
        result = format_recommendations_report({})
        assert result == ""

    def test_produces_output(self):
        signals = {
            "test-job": [_signal("crash_repeat", Severity.CRITICAL, {"streak": 4})],
        }
        result = format_recommendations_report(signals)
        assert "RECOMMENDATIONS" in result
        assert "test-job" in result
        assert "🔴" in result  # high priority icon

    def test_report_structure(self):
        signals = {
            "my-job": [_signal("consecutive_errors", Severity.CRITICAL, {"consecutive_errors": 3})],
        }
        result = format_recommendations_report(signals)
        assert "[my-job]" in result
        assert "→" in result  # details line starts with arrow

    def test_skips_jobs_with_no_recs(self):
        signals = {
            "empty-job": [_signal("nonexistent", Severity.WARNING)],
            "good-job": [_signal("crash_repeat", Severity.CRITICAL, {"streak": 3})],
        }
        result = format_recommendations_report(signals)
        assert "good-job" in result
        # nonexistent signal → no recs → not in report


class TestRecommendationsToJson:
    def test_empty(self):
        result = recommendations_to_json({})
        assert result == {}

    def test_structure(self):
        signals = {
            "job-a": [_signal("crash_repeat", Severity.CRITICAL, {"streak": 3})],
        }
        result = recommendations_to_json(signals)
        assert "job-a" in result
        rec = result["job-a"][0]
        assert rec["priority"] == "high"
        assert rec["signal_kind"] == "crash_repeat"
        assert "action" in rec
        assert "details" in rec

    def test_skips_empty_jobs(self):
        signals = {
            "job-a": [_signal("nonexistent", Severity.WARNING)],
            "job-b": [_signal("crash_repeat", Severity.CRITICAL, {"streak": 2})],
        }
        result = recommendations_to_json(signals)
        assert "job-a" not in result
        assert "job-b" in result
