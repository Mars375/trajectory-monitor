// scorer.js — Score session quality 0-100

/**
 * Score a normalized session based on anomalies and completion.
 * @param {object} session - Normalized session
 * @param {Array} anomalies - Detected anomalies
 * @returns {{ score: number, breakdown: object }}
 */
export function scoreSession(session, anomalies) {
  const breakdown = {
    base: 100,
    loopPenalty: 0,
    stagnationPenalty: 0,
    crashPenalty: 0,
    hallucinationPenalty: 0,
    timeoutPenalty: 0,
    completionBonus: 0,
    efficiencyBonus: 0,
  };

  // Penalties
  for (const anomaly of anomalies) {
    switch (anomaly.type) {
      case 'loop':
        breakdown.loopPenalty += Math.min(anomaly.count * 5, 30);
        break;
      case 'stagnation':
        breakdown.stagnationPenalty += Math.min(anomaly.windowSize * 5, 25);
        break;
      case 'crash':
        breakdown.crashPenalty += 40;
        break;
      case 'hallucination':
        breakdown.hallucinationPenalty += 15;
        break;
      case 'timeout':
        breakdown.timeoutPenalty += 25;
        break;
    }
  }

  // Completion bonus
  const hasCompletion = session.events.some(e => e.type === 'completion' || e.type === 'done');
  if (hasCompletion) {
    breakdown.completionBonus = 10;
  }

  // Efficiency bonus: ratio of tool_result to tool_call (should be ~1:1)
  const toolCalls = session.events.filter(e => e.type === 'tool_call').length;
  const toolResults = session.events.filter(e => e.type === 'tool_result').length;
  if (toolCalls > 0) {
    const ratio = toolResults / toolCalls;
    if (ratio >= 0.8 && ratio <= 1.2) {
      breakdown.efficiencyBonus = 5;
    }
  }

  const score = Math.max(0, Math.min(100,
    breakdown.base
    - breakdown.loopPenalty
    - breakdown.stagnationPenalty
    - breakdown.crashPenalty
    - breakdown.hallucinationPenalty
    - breakdown.timeoutPenalty
    + breakdown.completionBonus
    + breakdown.efficiencyBonus
  ));

  return { score, breakdown };
}

/**
 * Get a letter grade from a score.
 * @param {number} score
 * @returns {string}
 */
export function grade(score) {
  if (score >= 90) return 'A';
  if (score >= 75) return 'B';
  if (score >= 60) return 'C';
  if (score >= 40) return 'D';
  return 'F';
}
