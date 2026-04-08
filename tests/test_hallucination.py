"""Tests for hallucination-pattern detector."""

import json
import tempfile
from pathlib import Path

import pytest

from trajectory_monitor.parser import JobState, RunEntry
from trajectory_monitor.signals import (
    Severity,
    detect_hallucination_pattern,
    check_file_existence,
    _extract_file_paths,
    _extract_creation_files,
)


# ── Helper ────────────────────────────────────────────────────────

def _make_run(ts: int, summary: str, status: str = "ok", error: str = "") -> RunEntry:
    return RunEntry(
        ts=ts,
        job_id="test-job",
        action="finished",
        status=status,
        duration_ms=30000,
        summary=summary,
        error=error,
        input_tokens=500,
        output_tokens=300,
        total_tokens=800,
    )


def _make_job(runs: list[RunEntry], name: str = "test-job") -> JobState:
    return JobState(job_id="test-job", name=name, runs=runs)


# ── File path extraction tests ────────────────────────────────────


class TestFilePathExtraction:
    def test_extracts_path_with_dirs(self):
        text = "Updated `src/trajectory_monitor/parser.py` with new logic"
        paths = _extract_file_paths(text)
        assert "src/trajectory_monitor/parser.py" in paths

    def test_extracts_bare_filename_in_backticks(self):
        text = "Modified `signals.py` to add detector"
        paths = _extract_file_paths(text)
        assert "signals.py" in paths

    def test_extracts_multiple_paths(self):
        text = "Created `src/parser.py` and `tests/test_parser.py`"
        paths = _extract_file_paths(text)
        assert "src/parser.py" in paths
        assert "tests/test_parser.py" in paths

    def test_ignores_short_non_paths(self):
        text = "The file a.b is too short"
        paths = _extract_file_paths(text)
        assert "a.b" not in paths

    def test_extracts_json_yaml(self):
        text = "Updated `config/settings.yaml` and `data/results.json`"
        paths = _extract_file_paths(text)
        assert "config/settings.yaml" in paths
        assert "data/results.json" in paths


class TestCreationFileExtraction:
    def test_extracts_created_files(self):
        text = "Created `src/parser.py` with new parsing logic"
        files = _extract_creation_files(text)
        assert "src/parser.py" in files

    def test_extracts_added_files(self):
        text = "Added `tests/test_signals.py` for new detector tests"
        files = _extract_creation_files(text)
        assert "tests/test_signals.py" in files

    def test_extracts_french_creation(self):
        text = "Ajouté `src/scorer.py` avec le nouveau scoring"
        files = _extract_creation_files(text)
        assert "src/scorer.py" in files

    def test_no_creation_verb_no_files(self):
        text = "Reviewed `src/parser.py` for potential issues"
        files = _extract_creation_files(text)
        # "Reviewed" is not a creation verb — should not match
        assert "src/parser.py" not in files


# ── Re-creation detection tests ───────────────────────────────────


class TestReCreationDetection:
    def test_re_creation_triggers_signal(self):
        """Same file claimed 'created' in 2 runs → signal."""
        job = _make_job([
            _make_run(1000, "Created `src/parser.py` with initial parsing"),
            _make_run(2000, "Created `src/parser.py` again with bug fixes"),
        ])
        signal = detect_hallucination_pattern(job)
        assert signal is not None
        assert signal.kind == "hallucination_pattern"
        assert signal.details["type"] == "re_creation"
        assert "src/parser.py" in signal.details["re_created_files"]

    def test_re_creation_multiple_files_critical(self):
        """3+ files re-created → CRITICAL severity."""
        job = _make_job([
            _make_run(1000, "Created `src/a.py`, `src/b.py`, and `src/c.py`"),
            _make_run(2000, "Created `src/a.py`, `src/b.py`, and `src/c.py` again"),
        ])
        signal = detect_hallucination_pattern(job)
        assert signal is not None
        assert signal.severity == Severity.CRITICAL

    def test_different_files_no_signal(self):
        """Different files created in each run → no signal."""
        job = _make_job([
            _make_run(1000, "Created `src/parser.py` with initial parsing"),
            _make_run(2000, "Created `src/scorer.py` with scoring logic"),
        ])
        signal = detect_hallucination_pattern(job)
        assert signal is None

    def test_single_run_no_signal(self):
        """Only one run → no signal (need 2+ runs for comparison)."""
        job = _make_job([
            _make_run(1000, "Created `src/parser.py` with parsing"),
        ])
        signal = detect_hallucination_pattern(job)
        assert signal is None


# ── Burst detection tests ─────────────────────────────────────────


class TestBurstDetection:
    def test_burst_unique_files_triggers_signal(self):
        """Single run references 5+ files not seen elsewhere → signal."""
        job = _make_job([
            _make_run(1000, "Reviewed code: `a.py`, `b.py`, `c.py`, `d.py`"),
            _make_run(2000, "Found issues in `unique1.py`, `unique2.py`, `unique3.py`, `unique4.py`, `unique5.py`"),
        ])
        signal = detect_hallucination_pattern(job)
        assert signal is not None
        assert signal.kind == "hallucination_pattern"
        assert signal.details["type"] == "burst"

    def test_shared_files_no_burst(self):
        """Files referenced in multiple runs → no burst signal."""
        job = _make_job([
            _make_run(1000, "Worked on `src/parser.py` and `src/signals.py`"),
            _make_run(2000, "Updated `src/parser.py` and `src/signals.py`"),
        ])
        signal = detect_hallucination_pattern(job)
        assert signal is None

    def test_few_unique_files_no_burst(self):
        """Less than 5 unique files → no burst signal."""
        job = _make_job([
            _make_run(1000, "Reviewed old code"),
            _make_run(2000, "Found issues in `unique1.py`, `unique2.py`, `unique3.py`"),
        ])
        signal = detect_hallucination_pattern(job)
        assert signal is None


# ── Workspace-aware existence check tests ─────────────────────────


class TestFileExistenceCheck:
    def test_missing_files_triggers_signal(self, tmp_path):
        """3+ referenced files not on disk → signal."""
        # Create only one file
        (tmp_path / "exists.py").touch()

        job = _make_job([
            _make_run(1000, "Updated `missing1.py`, `missing2.py`, `missing3.py`"),
        ])
        signal = check_file_existence(job, tmp_path)
        assert signal is not None
        assert signal.kind == "hallucination_pattern"
        assert signal.details["type"] == "missing_on_disk"

    def test_existing_files_no_signal(self, tmp_path):
        """All referenced files exist → no signal."""
        for name in ["a.py", "b.py", "c.py"]:
            (tmp_path / name).touch()

        job = _make_job([
            _make_run(1000, "Updated `a.py`, `b.py`, `c.py`"),
        ])
        signal = check_file_existence(job, tmp_path)
        assert signal is None

    def test_too_few_missing_no_signal(self, tmp_path):
        """<3 missing files → no signal."""
        (tmp_path / "exists.py").touch()

        job = _make_job([
            _make_run(1000, "Updated `missing1.py`, `missing2.py`"),
        ])
        signal = check_file_existence(job, tmp_path)
        assert signal is None

    def test_critical_when_many_missing(self, tmp_path):
        """6+ missing files → CRITICAL severity."""
        job = _make_job([
            _make_run(1000, "Files: `m1.py`, `m2.py`, `m3.py`, `m4.py`, `m5.py`, `m6.py`, `m7.py`"),
        ])
        signal = check_file_existence(job, tmp_path)
        assert signal is not None
        assert signal.severity == Severity.CRITICAL

    def test_empty_job_no_signal(self, tmp_path):
        """Job with no summaries → no signal."""
        job = _make_job([
            _make_run(1000, "", status="error", error="crashed"),
        ])
        signal = check_file_existence(job, tmp_path)
        assert signal is None


# ── Error run filtering ──────────────────────────────────────────


class TestErrorRunFiltering:
    def test_error_runs_ignored(self):
        """Error runs should be excluded from analysis."""
        job = _make_job([
            _make_run(1000, "Created `src/parser.py`", status="ok"),
            _make_run(2000, "Created `src/parser.py`", status="error", error="crash"),
            _make_run(3000, "Created `src/parser.py`", status="ok"),
        ])
        signal = detect_hallucination_pattern(job)
        # Only 2 ok runs both create parser.py → should trigger
        assert signal is not None
        assert signal.kind == "hallucination_pattern"
