#!/usr/bin/env node
// index.js — CLI entry point for trajectory-monitor

import { parseFile } from './parser.js';
import { detectAll } from './detector.js';
import { scoreSession } from './scorer.js';
import { formatReport, jsonReport } from './reporter.js';

const args = process.argv.slice(2);

if (args.length === 0 || args.includes('--help')) {
  console.log(`
trajectory-monitor — Analyse agent execution trajectories

Usage:
  node src/index.js <input.json>          Console report
  node src/index.js <input.json> --json   JSON output
  node src/index.js <input.json> --quiet  Score only (exit code = 0 if score >= 60)

Supports: single session, array of sessions, or { sessions: [...] } wrapper.
`);
  process.exit(0);
}

const filePath = args[0];
const asJson = args.includes('--json');
const quiet = args.includes('--quiet');

try {
  const sessions = parseFile(filePath);

  let totalScore = 0;
  let totalAnomalies = 0;

  for (const session of sessions) {
    const anomalies = detectAll(session);
    const scoring = scoreSession(session, anomalies);
    totalScore += scoring.score;
    totalAnomalies += anomalies.length;

    if (quiet) continue;

    if (asJson) {
      console.log(jsonReport(session, anomalies, scoring));
    } else {
      console.log(formatReport(session, anomalies, scoring));
    }
  }

  if (sessions.length > 1 && !quiet) {
    const avg = Math.round(totalScore / sessions.length);
    console.log(`\n📊 Average score across ${sessions.length} sessions: ${avg}/100`);
    console.log(`⚠️  Total anomalies: ${totalAnomalies}`);
  }

  if (quiet) {
    const avg = totalScore / sessions.length;
    process.exit(avg >= 60 ? 0 : 1);
  }
} catch (err) {
  console.error(`Error: ${err.message}`);
  process.exit(2);
}
