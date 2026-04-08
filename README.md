# trajectory-monitor

Analyse les trajectoires d'exécution des agents LLM — détecte les anomalies, score la qualité, expose une interface MCP.

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

────────────────────────────────────────────────────────────
  Job                                 Score Grade Signals
────────────────────────────────────────────────────────────
  forge-imagine                          17     F       1
  forge-chantier-memos                   64     C       1
  forge-chantier-mcp-audit               75     B       0
  forge-scout-needs                      74     C       0
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

## Quality Score (0-100)

Composite score with components:
- **Reliability** (0-30): Based on error rate
- **Activity** (0-20): Number of recorded runs
- **Consistency** (0-20): Duration variance across runs
- **Enabled** (0-10): Whether job is active
- **Recovery** (0-10): Had errors but recovered
- Penalties for consecutive errors and detected signals

Grades: A (≥90) / B (≥75) / C (≥60) / D (≥40) / F (<40)

## Architecture

```
trajectory_monitor/
├── parser.py        # Parse jobs.json + JSONL run transcripts
├── signals.py       # 7 anomaly detectors (crash_repeat, loop, stagnation, duration_spike, token_bloat, consecutive_errors, feature_race)
├── scorer.py        # Quality score (0-100) with breakdown
├── report.py        # Terminal + JSON output
├── mcp_server.py    # MCP tool functions (for agent self-inspection)
└── cli.py           # CLI interface
```

## MCP Integration

```python
from trajectory_monitor.mcp_server import tool_analyze_jobs, tool_check_job, tool_get_score

# Full analysis
report_json = tool_analyze_jobs("/path/to/jobs.json", "/path/to/runs")

# Single job
status = tool_check_job("/path/to/jobs.json", "forge-imagine", "/path/to/runs")

# Quick score
score = tool_get_score("/path/to/jobs.json", "forge-imagine", "/path/to/runs")
```

## Requirements

- Python ≥ 3.10
- No external dependencies (stdlib only)
- pytest for tests
