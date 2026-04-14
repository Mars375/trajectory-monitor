// reporter.js — Generate human-readable reports

/**
 * Format a full analysis report for console output.
 * @param {object} session - Normalized session
 * @param {Array} anomalies - Detected anomalies
 * @param {{ score: number, breakdown: object }} scoring
 * @returns {string}
 */
export function formatReport(session, anomalies, scoring) {
  const lines = [];

  lines.push('═'.repeat(60));
  lines.push(`  TRAJECTORY REPORT — ${session.sessionId}`);
  lines.push('═'.repeat(60));
  lines.push(`  Agent:    ${session.agentId}`);
  lines.push(`  Status:   ${session.status}`);
  lines.push(`  Events:   ${session.events.length}`);
  lines.push(`  Duration: ${formatDuration(session)}`);
  lines.push('─'.repeat(60));

  // Score
  const gradeEmoji = { A: '🟢', B: '🟡', C: '🟠', D: '🔴', F: '💀' };
  const g = gradeFromScore(scoring.score);
  lines.push(`  SCORE: ${scoring.score}/100  ${gradeEmoji[g] || ''} Grade: ${g}`);
  lines.push('─'.repeat(60));

  // Anomalies
  if (anomalies.length === 0) {
    lines.push('  ✅ No anomalies detected');
  } else {
    lines.push(`  ⚠️  ${anomalies.length} anomaly(ies) detected:`);
    lines.push('');
    for (const a of anomalies) {
      switch (a.type) {
        case 'loop':
          lines.push(`    🔁 LOOP — tool "${a.tool}" repeated ${a.count}x`);
          lines.push(`       args: ${JSON.stringify(a.args)}`);
          break;
        case 'stagnation':
          lines.push(`    🕳️  STAGNATION — ${a.windowSize} identical results`);
          break;
        case 'crash':
          lines.push(`    💥 CRASH — ${a.error}`);
          break;
        case 'hallucination':
          lines.push(`    🌀 HALLUCINATION [${a.subtype}] — ${a.tool ? `tool "${a.tool}"` : 'unknown tool'}: ${a.details}`);
          break;
        case 'timeout':
          lines.push(`    ⏱️  TIMEOUT — ${a.details}`);
          break;
        default:
          lines.push(`    ❓ ${a.type}`);
      }
    }
  }

  lines.push('─'.repeat(60));

  // Breakdown
  const b = scoring.breakdown;
  lines.push('  Score Breakdown:');
  lines.push(`    Base:                 ${b.base}`);
  lines.push(`    Loop penalty:         -${b.loopPenalty}`);
  lines.push(`    Stagnation penalty:   -${b.stagnationPenalty}`);
  lines.push(`    Crash penalty:        -${b.crashPenalty}`);
  lines.push(`    Hallucination penalty: -${b.hallucinationPenalty}`);
  lines.push(`    Timeout penalty:      -${b.timeoutPenalty}`);
  lines.push(`    Completion bonus:     +${b.completionBonus}`);
  lines.push(`    Efficiency bonus:     +${b.efficiencyBonus}`);
  lines.push('═'.repeat(60));

  return lines.join('\n');
}

/**
 * Format as structured JSON.
 */
export function jsonReport(session, anomalies, scoring) {
  return JSON.stringify({
    sessionId: session.sessionId,
    agentId: session.agentId,
    status: session.status,
    eventCount: session.events.length,
    score: scoring.score,
    grade: gradeFromScore(scoring.score),
    anomalyCount: anomalies.length,
    anomalies: anomalies.map(a => ({ ...a })),
    breakdown: scoring.breakdown,
  }, null, 2);
}

function formatDuration(session) {
  if (!session.startTime || !session.endTime) return 'N/A';
  const ms = new Date(session.endTime) - new Date(session.startTime);
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return `${m}m ${s % 60}s`;
}

function gradeFromScore(score) {
  if (score >= 90) return 'A';
  if (score >= 75) return 'B';
  if (score >= 60) return 'C';
  if (score >= 40) return 'D';
  return 'F';
}
