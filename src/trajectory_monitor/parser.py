"""Parse OpenClaw cron data: jobs.json state + run transcripts (JSONL/markdown)."""

from __future__ import annotations

import json
import re
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


def _extract_summary(obj: dict) -> str:
    """Best-effort summary extraction from OpenClaw-style finished entries."""
    result = obj.get("result") or {}
    return (
        obj.get("summary")
        or result.get("summary", "")
        or result.get("text", "")
        or obj.get("message", "")
        or obj.get("text", "")
        or ""
    )


def _parse_run_object(obj: dict, default_job_id: str = "") -> RunEntry | None:
    """Parse a single finished JSON object into a RunEntry."""
    if obj.get("action") != "finished":
        return None

    usage = obj.get("usage") or {}
    return RunEntry(
        ts=obj.get("ts", 0),
        job_id=obj.get("jobId") or default_job_id,
        action=obj.get("action", ""),
        status=obj.get("status", "unknown"),
        duration_ms=obj.get("durationMs", 0),
        model=obj.get("model", ""),
        provider=obj.get("provider", ""),
        error=obj.get("error", ""),
        summary=_extract_summary(obj),
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
        session_id=obj.get("sessionId", ""),
    )


def parse_run_jsonl_text(text: str, default_job_id: str = "") -> list[RunEntry]:
    """Parse finished run entries from raw JSONL text."""
    entries: list[RunEntry] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        entry = _parse_run_object(obj, default_job_id=default_job_id)
        if entry is not None:
            entries.append(entry)

    return entries


_MARKDOWN_ERROR_RE = re.compile(
    r"\b(?:error|failed?|failure|exception|traceback|timeout|timed out|"
    r"permission denied|not found|no such file|crash(?:ed)?|refused)\b",
    re.I,
)


def _clean_markdown_line(line: str) -> str:
    text = line.strip()
    text = re.sub(r"^#{1,6}\s+", "", text)
    text = re.sub(r"^>+\s*", "", text)
    text = re.sub(r"^(?:[-*+]\s*)?\[[ xX]\]\s*", "", text)
    text = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", text)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" :-")


def parse_markdown_transcript_text(text: str, default_job_id: str = "") -> list[RunEntry]:
    """Parse markdown-ish action transcripts into pseudo-runs.

    Heuristic: each non-empty bullet or paragraph line becomes a run-like entry,
    which lets the existing signal detectors work on human-written summaries.
    """
    entries: list[RunEntry] = []
    in_code_block = False
    ts = 0

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if stripped.startswith("#"):
            continue
        if re.fullmatch(r"[-=*_]{3,}", stripped):
            continue

        cleaned = _clean_markdown_line(stripped)
        if not cleaned:
            continue

        ts += 1
        is_error = bool(_MARKDOWN_ERROR_RE.search(cleaned))
        entries.append(
            RunEntry(
                ts=ts,
                job_id=default_job_id,
                action="transcript_line",
                status="error" if is_error else "ok",
                duration_ms=0,
                error=cleaned if is_error else "",
                summary=cleaned,
            )
        )

    return entries


def parse_transcript_text(text: str, default_job_id: str = "") -> list[RunEntry]:
    """Parse either OpenClaw JSONL or markdown/text transcripts."""
    jsonl_entries = parse_run_jsonl_text(text, default_job_id=default_job_id)
    if jsonl_entries:
        return jsonl_entries
    return parse_markdown_transcript_text(text, default_job_id=default_job_id)


def parse_transcript_file(path: str | Path) -> list[RunEntry]:
    """Parse a transcript file, auto-detecting JSONL vs markdown/text."""
    p = Path(path)
    if not p.exists():
        return []
    return parse_transcript_text(p.read_text(), default_job_id=p.stem)


def parse_run_jsonl(path: str | Path) -> list[RunEntry]:
    """Parse a single JSONL run transcript file."""
    p = Path(path)
    if not p.exists():
        return []

    return parse_run_jsonl_text(p.read_text(), default_job_id=p.stem)


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
