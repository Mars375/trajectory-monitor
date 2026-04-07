"""Parse OpenClaw cron data: jobs.json state + run transcripts (JSONL)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RunEntry:
    """Single run from a JSONL transcript file."""

    ts: int
    job_id: str
    action: str
    status: str  # "ok" | "error"
    duration_ms: int
    model: str = ""
    provider: str = ""
    error: str = ""
    summary: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    session_id: str = ""

    @property
    def is_error(self) -> bool:
        return self.status == "error"


@dataclass
class JobState:
    """Aggregated state for a single cron job."""

    job_id: str
    name: str
    description: str = ""
    enabled: bool = True
    consecutive_errors: int = 0
    last_run_status: str = ""
    last_duration_ms: int = 0
    runs: list[RunEntry] = field(default_factory=list)

    @property
    def total_runs(self) -> int:
        return len(self.runs)

    @property
    def error_runs(self) -> list[RunEntry]:
        return [r for r in self.runs if r.is_error]

    @property
    def ok_runs(self) -> list[RunEntry]:
        return [r for r in self.runs if not r.is_error]

    @property
    def error_rate(self) -> float:
        if not self.runs:
            return 0.0
        return len(self.error_runs) / len(self.runs)

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self.runs)

    @property
    def avg_duration_ms(self) -> float:
        durations = [r.duration_ms for r in self.runs if r.duration_ms > 0]
        return sum(durations) / len(durations) if durations else 0.0


def parse_jobs_json(path: str | Path) -> list[JobState]:
    """Parse jobs.json and return list of JobState objects."""
    p = Path(path)
    if not p.exists():
        return []

    with open(p) as f:
        data = json.load(f)

    jobs: list[JobState] = []
    for raw in data.get("jobs", []):
        state = raw.get("state", {})
        jobs.append(
            JobState(
                job_id=raw.get("id", ""),
                name=raw.get("name", ""),
                description=raw.get("description", ""),
                enabled=raw.get("enabled", True),
                consecutive_errors=state.get("consecutiveErrors", 0),
                last_run_status=state.get("lastRunStatus", ""),
                last_duration_ms=state.get("lastDurationMs", 0),
            )
        )
    return jobs


def parse_run_jsonl(path: str | Path) -> list[RunEntry]:
    """Parse a single JSONL run transcript."""
    p = Path(path)
    if not p.exists():
        return []

    entries: list[RunEntry] = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if obj.get("action") != "finished":
                continue

            usage = obj.get("usage", {})
            entries.append(
                RunEntry(
                    ts=obj.get("ts", 0),
                    job_id=obj.get("jobId", ""),
                    action=obj.get("action", ""),
                    status=obj.get("status", "unknown"),
                    duration_ms=obj.get("durationMs", 0),
                    model=obj.get("model", ""),
                    provider=obj.get("provider", ""),
                    error=obj.get("error", ""),
                    summary=obj.get("summary", ""),
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    session_id=obj.get("sessionId", ""),
                )
            )
    return entries


def load_all_runs(runs_dir: str | Path) -> dict[str, list[RunEntry]]:
    """Load all run transcripts, keyed by job_id."""
    p = Path(runs_dir)
    if not p.exists():
        return {}

    by_job: dict[str, list[RunEntry]] = {}
    for jsonl_file in sorted(p.glob("*.jsonl")):
        entries = parse_run_jsonl(jsonl_file)
        for entry in entries:
            by_job.setdefault(entry.job_id, []).append(entry)

    # Sort each job's runs by timestamp
    for job_id in by_job:
        by_job[job_id].sort(key=lambda r: r.ts)

    return by_job


def build_job_states(jobs_json_path: str | Path, runs_dir: str | Path) -> list[JobState]:
    """Build complete JobState list with run history merged in."""
    jobs = parse_jobs_json(jobs_json_path)
    runs_by_job = load_all_runs(runs_dir)

    job_map = {j.job_id: j for j in jobs}

    for job_id, run_entries in runs_by_job.items():
        if job_id in job_map:
            job_map[job_id].runs = run_entries
        else:
            jobs.append(
                JobState(
                    job_id=job_id,
                    name=f"orphan:{job_id[:8]}",
                    runs=run_entries,
                )
            )

    return jobs
