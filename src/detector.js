// detector.js — Detect anomalies in agent execution trajectories

/**
 * Detect loops: same tool+args repeated 3+ times consecutively.
 * @param {object} session - Normalized session
 * @returns {Array<{ type: 'loop', tool: string, args: object, count: number, startIndex: number }>}
 */
export function detectLoops(session, threshold = 3) {
  const anomalies = [];
  const events = session.events.filter(e => e.type === 'tool_call' && e.tool);

  if (events.length < threshold) return anomalies;

  let runStart = 0;
  for (let i = 1; i <= events.length; i++) {
    const same = i < events.length &&
      events[i].tool === events[runStart].tool &&
      JSON.stringify(events[i].args) === JSON.stringify(events[runStart].args);

    if (same) continue;

    const runLength = i - runStart;
    if (runLength >= threshold) {
      anomalies.push({
        type: 'loop',
        tool: events[runStart].tool,
        args: events[runStart].args,
        count: runLength,
        startIndex: events[runStart].index,
      });
    }
    runStart = i;
  }

  return anomalies;
}

/**
 * Detect stagnation: no progress (same outputs repeated) for N+ consecutive tool results.
 * @param {object} session - Normalized session
 * @param {number} window - Minimum window size for stagnation
 * @returns {Array<{ type: 'stagnation', windowSize: number, startIndex: number }>}
 */
export function detectStagnation(session, window = 4) {
  const anomalies = [];
  const results = session.events.filter(e => e.type === 'tool_result');

  if (results.length < window) return anomalies;

  let runStart = 0;
  for (let i = 1; i <= results.length; i++) {
    const same = i < results.length && results[i].output === results[runStart].output;
    if (same) continue;

    const runLength = i - runStart;
    if (runLength >= window) {
      anomalies.push({
        type: 'stagnation',
        windowSize: runLength,
        startIndex: results[runStart].index,
      });
    }
    runStart = i;
  }

  return anomalies;
}

/**
 * Detect crashes: session ended with an error event and no completion.
 * @param {object} session - Normalized session
 * @returns {Array<{ type: 'crash', error: string, lastIndex: number }>}
 */
export function detectCrashes(session) {
  const anomalies = [];

  const hasCompletion = session.events.some(e => e.type === 'completion' || e.type === 'done');
  const hasError = session.events.some(e => e.type === 'error');
  const isCrashStatus = session.status === 'crashed' || session.status === 'error' || session.status === 'failed';

  if ((hasError && !hasCompletion) || isCrashStatus) {
    const lastEvent = session.events[session.events.length - 1];
    const errorEvent = session.events.find(e => e.type === 'error');
    anomalies.push({
      type: 'crash',
      error: errorEvent?.error || lastEvent?.error || session.status,
      lastIndex: lastEvent?.index ?? session.events.length - 1,
    });
  }

  return anomalies;
}

/**
 * Run all anomaly detectors on a session.
 * @param {object} session - Normalized session
 * @returns {Array} All detected anomalies
 */
export function detectAll(session) {
  return [
    ...detectLoops(session),
    ...detectStagnation(session),
    ...detectCrashes(session),
  ];
}
