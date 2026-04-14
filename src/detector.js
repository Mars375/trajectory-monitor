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
 * Detect hallucinations: tool calls with impossible or incoherent arguments.
 * Checks for:
 *   - Missing tool name on a tool_call event
 *   - Empty/null args for tools that typically require arguments
 *   - Repeated failed tool calls (call → error pattern 3+ times)
 *   - Garbled/suspicious tool names
 * @param {object} session - Normalized session
 * @returns {Array<{ type: 'hallucination', subtype: string, tool?: string, details: string, index: number }>}
 */
export function detectHallucinations(session) {
  const anomalies = [];
  const events = session.events;

  // Tools that typically require args
  const toolsRequiringArgs = new Set([
    'read', 'write', 'edit', 'exec', 'bash', 'run',
    'fetch', 'request', 'search', 'query', 'mkdir',
    'delete', 'move', 'copy', 'rename', 'create',
  ]);

  for (const ev of events) {
    if (ev.type !== 'tool_call') continue;

    // Missing tool name
    if (!ev.tool || ev.tool.trim() === '') {
      anomalies.push({
        type: 'hallucination',
        subtype: 'missing_tool',
        details: 'tool_call event with no tool name',
        index: ev.index,
      });
      continue;
    }

    // Garbled tool name: single char, or contains only symbols/digits
    if (ev.tool.length <= 1 || /^[\d\W]+$/.test(ev.tool)) {
      anomalies.push({
        type: 'hallucination',
        subtype: 'garbled_tool',
        tool: ev.tool,
        details: `suspicious tool name: "${ev.tool}"`,
        index: ev.index,
      });
      continue;
    }

    // Empty args for tools that need them
    if (toolsRequiringArgs.has(ev.tool) && (!ev.args || (typeof ev.args === 'object' && Object.keys(ev.args).length === 0))) {
      anomalies.push({
        type: 'hallucination',
        subtype: 'empty_args',
        tool: ev.tool,
        details: `tool "${ev.tool}" called with no arguments`,
        index: ev.index,
      });
    }
  }

  // Repeated failed tool calls: call → error pattern 3+ times with same tool
  const failedCalls = {};
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    if (ev.type !== 'tool_call' || !ev.tool) continue;
    const next = events[i + 1];
    if (next && next.type === 'tool_result' && next.error) {
      failedCalls[ev.tool] = (failedCalls[ev.tool] || 0) + 1;
    }
  }
  for (const [tool, count] of Object.entries(failedCalls)) {
    if (count >= 3) {
      anomalies.push({
        type: 'hallucination',
        subtype: 'repeated_failures',
        tool,
        details: `tool "${tool}" failed ${count} consecutive times (possible hallucinated usage)`,
        index: -1,
      });
    }
  }

  return anomalies;
}

/**
 * Detect timeouts: sessions exceeding a duration threshold without completion.
 * @param {object} session - Normalized session
 * @param {number} thresholdMs - Duration threshold in milliseconds (default: 30 min)
 * @returns {Array<{ type: 'timeout', durationMs: number, thresholdMs: number, details: string }>}
 */
export function detectTimeouts(session, thresholdMs = 30 * 60 * 1000) {
  const anomalies = [];

  const hasCompletion = session.events.some(e => e.type === 'completion' || e.type === 'done');
  if (hasCompletion) return anomalies;

  let durationMs = null;

  // Try startTime/endTime first
  if (session.startTime && session.endTime) {
    durationMs = new Date(session.endTime) - new Date(session.startTime);
  } else {
    // Fallback: use first and last event timestamps
    const timestamps = session.events
      .map(e => e.timestamp)
      .filter(Boolean)
      .map(t => new Date(t).getTime())
      .filter(t => !isNaN(t));

    if (timestamps.length >= 2) {
      durationMs = Math.max(...timestamps) - Math.min(...timestamps);
    }
  }

  if (durationMs !== null && durationMs > thresholdMs) {
    const mins = Math.round(durationMs / 60000);
    anomalies.push({
      type: 'timeout',
      durationMs,
      thresholdMs,
      details: `session ran for ${mins} minutes without completion (threshold: ${Math.round(thresholdMs / 60000)} min)`,
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
    ...detectHallucinations(session),
    ...detectTimeouts(session),
  ];
}
