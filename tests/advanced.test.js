import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { detectHallucinations, detectTimeouts, detectAll } from '../src/detector.js';
import { normalizeSession } from '../src/parser.js';

function makeSession(events, opts = {}) {
  return normalizeSession({
    sessionId: opts.sessionId || 'test',
    status: opts.status || 'completed',
    startTime: opts.startTime || null,
    endTime: opts.endTime || null,
    events,
  });
}

// ─── Hallucination: missing tool name ───

describe('detector — detectHallucinations (missing_tool)', () => {
  it('detects tool_call with empty tool name', () => {
    const session = makeSession([
      { type: 'tool_call', tool: '', args: { path: 'x' } },
    ]);
    const h = detectHallucinations(session);
    assert.equal(h.length, 1);
    assert.equal(h[0].subtype, 'missing_tool');
    assert.equal(h[0].index, 0);
  });

  it('detects tool_call with null tool name', () => {
    const session = makeSession([
      { type: 'tool_call', tool: null, args: { path: 'x' } },
    ]);
    const h = detectHallucinations(session);
    assert.equal(h.length, 1);
    assert.equal(h[0].subtype, 'missing_tool');
  });

  it('does not flag tool_call with valid tool name', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'x' } },
    ]);
    const h = detectHallucinations(session);
    assert.equal(h.filter(a => a.subtype === 'missing_tool').length, 0);
  });
});

// ─── Hallucination: garbled tool name ───

describe('detector — detectHallucinations (garbled_tool)', () => {
  it('detects single-character tool name', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'x', args: {} },
    ]);
    const h = detectHallucinations(session);
    assert.ok(h.some(a => a.subtype === 'garbled_tool'));
  });

  it('detects all-digits tool name', () => {
    const session = makeSession([
      { type: 'tool_call', tool: '123', args: {} },
    ]);
    const h = detectHallucinations(session);
    assert.ok(h.some(a => a.subtype === 'garbled_tool'));
  });

  it('does not flag normal tool names', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read_file', args: { path: 'a' } },
    ]);
    const h = detectHallucinations(session);
    assert.equal(h.filter(a => a.subtype === 'garbled_tool').length, 0);
  });
});

// ─── Hallucination: empty args for tools that need them ───

describe('detector — detectHallucinations (empty_args)', () => {
  it('detects read with no args', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read' },
    ]);
    const h = detectHallucinations(session);
    assert.ok(h.some(a => a.subtype === 'empty_args' && a.tool === 'read'));
  });

  it('detects exec with empty args object', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'exec', args: {} },
    ]);
    const h = detectHallucinations(session);
    assert.ok(h.some(a => a.subtype === 'empty_args' && a.tool === 'exec'));
  });

  it('does not flag tool with valid args', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'file.js' } },
    ]);
    const h = detectHallucinations(session);
    assert.equal(h.filter(a => a.subtype === 'empty_args').length, 0);
  });

  it('does not flag tools not in the requires-args list', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'status' },
    ]);
    const h = detectHallucinations(session);
    assert.equal(h.filter(a => a.subtype === 'empty_args').length, 0);
  });
});

// ─── Hallucination: repeated failures ───

describe('detector — detectHallucinations (repeated_failures)', () => {
  it('detects 3+ failed calls with same tool', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'exec', args: { cmd: 'rm -rf /' } },
      { type: 'tool_result', output: 'denied', error: 'Permission denied' },
      { type: 'tool_call', tool: 'exec', args: { cmd: 'rm -rf /' } },
      { type: 'tool_result', output: 'denied', error: 'Permission denied' },
      { type: 'tool_call', tool: 'exec', args: { cmd: 'rm -rf /' } },
      { type: 'tool_result', output: 'denied', error: 'Permission denied' },
    ]);
    const h = detectHallucinations(session);
    assert.ok(h.some(a => a.subtype === 'repeated_failures' && a.tool === 'exec'));
  });

  it('does not flag 2 failed calls (below threshold)', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'exec', args: { cmd: 'bad' } },
      { type: 'tool_result', output: 'err', error: 'fail' },
      { type: 'tool_call', tool: 'exec', args: { cmd: 'bad' } },
      { type: 'tool_result', output: 'err', error: 'fail' },
    ]);
    const h = detectHallucinations(session);
    assert.equal(h.filter(a => a.subtype === 'repeated_failures').length, 0);
  });

  it('does not count successful calls as failures', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'exec', args: { cmd: 'ls' } },
      { type: 'tool_result', output: 'files...' },
      { type: 'tool_call', tool: 'exec', args: { cmd: 'ls' } },
      { type: 'tool_result', output: 'files...' },
    ]);
    const h = detectHallucinations(session);
    assert.equal(h.filter(a => a.subtype === 'repeated_failures').length, 0);
  });
});

// ─── Hallucination: from sample data ───

describe('detector — detectHallucinations (sample data)', () => {
  it('detects hallucinations from hallucination-session.json', async () => {
    const { readFileSync } = await import('node:fs');
    const { parseFile } = await import('../src/parser.js');
    const sessions = parseFile('./samples/hallucination-session.json');
    const h = detectHallucinations(sessions[0]);
    // Should detect: missing_tool (empty name), empty_args (exec ×3), garbled (tool "7"), empty_args (read)
    assert.ok(h.length >= 3, `expected >= 3 hallucinations, got ${h.length}`);
    const subtypes = new Set(h.map(a => a.subtype));
    assert.ok(subtypes.has('missing_tool'));
    assert.ok(subtypes.has('empty_args'));
  });
});

// ─── Timeout detection ───

describe('detector — detectTimeouts', () => {
  it('detects session exceeding threshold without completion', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'search', args: { query: 'fix' } },
      { type: 'tool_result', output: 'results' },
    ], {
      status: 'running',
      startTime: '2026-04-14T08:00:00Z',
      endTime: '2026-04-14T09:30:00Z',
    });
    const t = detectTimeouts(session, 30 * 60 * 1000);
    assert.equal(t.length, 1);
    assert.equal(t[0].type, 'timeout');
    assert.ok(t[0].durationMs > 30 * 60 * 1000);
  });

  it('does not flag session with completion even if long', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'x' } },
      { type: 'tool_result', output: 'content' },
      { type: 'completion', output: 'done' },
    ], {
      status: 'completed',
      startTime: '2026-04-14T08:00:00Z',
      endTime: '2026-04-14T10:00:00Z',
    });
    assert.equal(detectTimeouts(session, 30 * 60 * 1000).length, 0);
  });

  it('does not flag short session without completion', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'x' } },
      { type: 'tool_result', output: 'content' },
    ], {
      status: 'running',
      startTime: '2026-04-14T08:00:00Z',
      endTime: '2026-04-14T08:05:00Z',
    });
    assert.equal(detectTimeouts(session, 30 * 60 * 1000).length, 0);
  });

  it('uses event timestamps as fallback when session timestamps missing', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'x' }, timestamp: '2026-04-14T08:00:00Z' },
      { type: 'tool_result', output: 'content', timestamp: '2026-04-14T09:00:00Z' },
    ], {
      status: 'unknown',
    });
    const t = detectTimeouts(session, 30 * 60 * 1000);
    assert.equal(t.length, 1);
    assert.ok(t[0].durationMs >= 60 * 60 * 1000);
  });

  it('returns empty when no timestamps available', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'x' } },
      { type: 'tool_result', output: 'content' },
    ], { status: 'unknown' });
    assert.equal(detectTimeouts(session, 30 * 60 * 1000).length, 0);
  });

  it('detects timeout from sample data', async () => {
    const { parseFile } = await import('../src/parser.js');
    const sessions = parseFile('./samples/timeout-session.json');
    const t = detectTimeouts(sessions[0], 30 * 60 * 1000);
    assert.equal(t.length, 1);
    assert.ok(t[0].durationMs > 30 * 60 * 1000);
  });

  it('respects custom threshold', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'x' } },
      { type: 'tool_result', output: 'content' },
    ], {
      status: 'running',
      startTime: '2026-04-14T08:00:00Z',
      endTime: '2026-04-14T08:10:00Z',
    });
    // 10 minutes exceeds 5-minute threshold
    assert.equal(detectTimeouts(session, 5 * 60 * 1000).length, 1);
    // 10 minutes does NOT exceed 15-minute threshold
    assert.equal(detectTimeouts(session, 15 * 60 * 1000).length, 0);
  });
});

// ─── detectAll includes new detectors ───

describe('detector — detectAll (with hallucination + timeout)', () => {
  it('includes hallucination anomalies', () => {
    const session = makeSession([
      { type: 'tool_call', tool: '', args: {} },
    ]);
    const all = detectAll(session);
    assert.ok(all.some(a => a.type === 'hallucination'));
  });

  it('includes timeout anomalies', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'x' } },
      { type: 'tool_result', output: 'content' },
    ], {
      status: 'running',
      startTime: '2026-04-14T08:00:00Z',
      endTime: '2026-04-14T09:00:00Z',
    });
    const all = detectAll(session);
    assert.ok(all.some(a => a.type === 'timeout'));
  });

  it('detects 5 anomaly types from combined session', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_call', tool: '', args: {} },
      { type: 'error', error: 'fatal' },
    ], {
      status: 'crashed',
      startTime: '2026-04-14T08:00:00Z',
      endTime: '2026-04-14T09:30:00Z',
    });
    const all = detectAll(session);
    const types = new Set(all.map(a => a.type));
    assert.ok(types.has('loop'), 'should detect loop');
    assert.ok(types.has('stagnation'), 'should detect stagnation');
    assert.ok(types.has('crash'), 'should detect crash');
    assert.ok(types.has('hallucination'), 'should detect hallucination');
    assert.ok(types.has('timeout'), 'should detect timeout');
    assert.equal(types.size, 5, 'should detect all 5 anomaly types');
  });
});
