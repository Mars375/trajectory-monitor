# trajectory-monitor

Analyse les trajectoires d'exécution des agents LLM — détecte les anomalies, score la qualité, et accepte aussi les transcripts JSONL ou markdown pour l'auto-inspection via MCP.

## Installation

```bash
cd trajectory-monitor
pip install -e .
```

## Usage

### CLI

```bash
# Analyze OpenClaw cron jobs (auto-detects paths)
python -m trajectory_monitor.cli analyze

# Specify custom paths
python -m trajectory_monitor.cli analyze /path/to/jobs.json --runs-dir /path/to/runs

# JSON output
python -m trajectory_monitor.cli analyze --json
```

### Example Report (Real Data)

```
============================================================
  TRAJECTORY MONITOR — Session Analysis Report
  Generated: 2026-04-07T10:50:21Z
============================================================

  Jobs analyzed: 44
  Total signals: 39 (7 critical, 30 warnings)
  Average quality score: 58/100
  Trend overview: 6 regressing, 11 improving

────────────────────────────────────────────────────────────
  Job                           Score Grade   Trend Signals
────────────────────────────────────────────────────────────
  forge-imagine                    17     F       ·       1
  forge-chantier-memos             64     C       ↗       1
  forge-chantier-mcp-audit         75     B       →       0
  forge-scout-needs                74     C       ↘       0
  ...

  SIGNALS DETECTED
  ────────────────────────────────────────────────────────
  [forge-chantier-memos]
    ⚠️ [crash_repeat] Same error repeated 2x: Write to <path> failed

  [orphan:4a10627b]
    🔴 [crash_repeat] Same error repeated 13x: cron: job execution timed out
    ⚠️ [loop] Similar output repeated 24x — possible loop

  [orphan:2a20474b]
    ⚠️ [token_bloat] Output tokens growing: 655→12647 (19.3x)
============================================================
```

## Signals Detected

| Signal | Description |
|--------|-------------|
| **crash_repeat** | Same error pattern repeated across consecutive runs (🔴 ≥3x, ⚠️ 2x) |
| **loop** | Similar output repeated 3+ times without progression |
| **stagnation** | Job enabled but never executed |
| **duration_spike** | Last run duration >3x the historical average |
| **token_bloat** | Output tokens monotonically increasing across 3+ runs (1.5x+ growth) |
| **consecutive_errors** | Job has consecutiveErrors > 0 in state |
| **feature_race** | 3+ consecutive feature-add runs without intermediate validation (🔴 ≥5x, ⚠️ 3x) |
| **hallucination_pattern** | References to files/functions that don't exist (re-creation, burst, workspace check) |
| **regression_trend** | Recent run window is materially worse than the previous one |

## Quality Score (0-100)

Composite score with components:
- **Reliability** (0-30): Based on error rate
- **Activity** (0-20): Number of recorded runs
- **Consistency** (0-20): Duration variance across runs
- **Enabled** (0-10): Whether job is active
- **Recovery** (0-10): Had errors but recovered
- Weighted penalties for consecutive errors and detected signals

Signal penalties are severity-based **and** weighted by impact. Example: `consecutive_errors`, `crash_repeat`, `hallucination_pattern`, and `regression_trend` cost more than softer signals like `duration_spike`, `token_bloat`, or `stagnation`. JSON and MCP outputs expose a `signal_penalties` map so agents can see why a score dropped.

Grades: A (≥90) / B (≥75) / C (≥60) / D (≥40) / F (<40)

## Trend Analysis

Each job also gets a lightweight trend verdict based on the last two run windows:
- **↗ improving**: recent runs are materially healthier than the previous window
- **→ stable**: no strong movement detected
- **↘ regressing**: recent runs are clearly worse than the previous window
- **· n/a**: not enough history yet

The JSON and MCP payloads expose `trend.direction`, `score_delta`, `error_rate_delta`, and duration/token deltas so other agents can react before a job fully crashes.

## Architecture

```
trajectory_monitor/
├── parser.py           # Parse jobs.json + transcript inputs (JSONL or markdown/text)
├── signals.py          # 9 anomaly detectors (crash_repeat, loop, stagnation, duration_spike, token_bloat, consecutive_errors, feature_race, hallucination_pattern, regression_trend)
├── scorer.py        # Quality score (0-100) + trend analysis between run windows
├── report.py           # Terminal + JSON output (with recommendations)
├── recommendations.py  # Actionable fix suggestions per signal type + severity
├── mcp_server.py       # MCP tool functions (6 tools for agent self-inspection)
└── cli.py              # CLI interface
tools/
└── analyze_openclaw.py # Forge-specific markdown report generator
```

## MCP Integration

```python
from trajectory_monitor.mcp_server import (
    analyze_jobs,
    analyze_session,
    check_job,
    get_recommendations,
    get_score,
    list_signals,
)

# Full analysis
report_json = analyze_jobs(jobs_json_path="/path/to/jobs.json", runs_dir="/path/to/runs")

# Single job
status = check_job(job_name="forge-imagine", jobs_json_path="/path/to/jobs.json", runs_dir="/path/to/runs")

# Quick score
score = get_score(job_name="forge-imagine", jobs_json_path="/path/to/jobs.json", runs_dir="/path/to/runs")

# Actionable fix suggestions for one job or all failing jobs
job_recs = get_recommendations(job_name="forge-imagine", jobs_json_path="/path/to/jobs.json", runs_dir="/path/to/runs")
all_recs = get_recommendations(jobs_json_path="/path/to/jobs.json", runs_dir="/path/to/runs")

# Self-inspect a JSONL or markdown transcript mid-session
session_report = analyze_session(
    transcript_text_or_path,
    job_name="live-session",
    workspace_path="/path/to/workspace",  # optional, enables missing-file checks
)

# Discover available detectors
signal_catalog = list_signals()
```

## Forge Report Tool

The `tools/analyze_openclaw.py` script generates a forge-specific markdown report for `forge-meta-improve`:

```bash
# Analyze forge crons only (default)
python3 tools/analyze_openclaw.py

# Output to file
python3 tools/analyze_openclaw.py --output forge-report.md

# Full JSON report (all jobs)
python3 tools/analyze_openclaw.py --json

# Include all jobs, not just forge-*
python3 tools/analyze_openclaw.py --all

# Explicit paths
python3 tools/analyze_openclaw.py --jobs-json /path/to/jobs.json --runs-dir /path/to/runs
```

The report includes:
- Summary metrics (average score, signal counts, failing jobs)
- Score table for all forge jobs
- Detailed signal breakdown per job
- Actionable recommendations for failing jobs
- Run details (duration, tokens, status)
- Non-forge job context for comparison

## Recommendations Engine

Every analysis report includes an actionable **📋 RECOMMENDATIONS** section:

```
  📋 RECOMMENDATIONS
  ────────────────────────────────────────────────────────
  🔴 HIGH  [crash_repeat] forge-imagine
     → Investigate root cause: "cron: job execution timed out"
     Same error 17x. Check if target task is too large or has a bug.

  🟡 MED   [feature_race] orphan:a4c76d01
     → STOP adding features. Validate existing work first.
     10 consecutive feature-add runs without testing.

  🟢 LOW   [duration_spike] forge-gate
     → Check if last run had legitimate extra work.
     Duration spike: 29.1x average.
```

Each recommendation maps a signal type + severity to a specific action with context from the signal data (error messages, streak counts, growth factors). Recommendations are sorted by priority (high → medium → low).

## Transcript Inputs

`analyze_session(...)` accepts:
- OpenClaw JSONL with `action="finished"` entries
- Markdown/text transcripts with action/result bullets or plain lines
- File paths to `.jsonl`, `.md`, `.markdown`, or `.txt` transcripts

Markdown support is heuristic on purpose: each action/result line becomes a pseudo-run so the existing detectors can still spot loops, crash repeats, or feature races inside a human-written session recap.

## Requirements

- Python ≥ 3.10
- No external dependencies (stdlib only)
- pytest for tests

## Action Policies

En plus du score brut, chaque job expose maintenant une `action_policy` dérivée du risque réel :

- **normal**: itération normale autorisée
- **watch**: avancer prudemment, valider après chaque incrément
- **stabilize**: privilégier fixes + validation avant toute nouvelle feature
- **bugfix_only**: stop feature work, corriger puis revalider

Les sorties JSON et MCP exposent :
- `action_policy.mode`
- `action_policy.summary`
- `action_policy.feature_delivery_allowed`
- `action_policy.should_alert`
- `action_policy.max_new_features`
- `action_policy.reasons`

Ça permet à un autre agent de décider immédiatement s’il peut continuer à builder ou s’il doit passer en mode bugfix-only.
