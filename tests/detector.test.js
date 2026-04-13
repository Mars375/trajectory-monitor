import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { detectLoops, detectStagnation, detectCrashes, detectAll } from '../src/detector.js';
import { normalizeSession } from '../src/parser.js';

function makeSession(events, status = 'completed') {
  return normalizeSession({ sessionId: 'test', status, events });
}

describe('detector — detectLoops', () => {
  it('detects a loop of 3+ identical tool calls', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'a.js' } },
      { type: 'tool_result', tool: 'read', output: 'x' },
      { type: 'tool_call', tool: 'read', args: { path: 'a.js' } },
      { type: 'tool_result', tool: 'read', output: 'x' },
      { type: 'tool_call', tool: 'read', args: { path: 'a.js' } },
      { type: 'tool_result', tool: 'read', output: 'x' },
    ]);
    const loops = detectLoops(session);
    assert.equal(loops.length, 1);
    assert.equal(loops[0].type, 'loop');
    assert.equal(loops[0].tool, 'read');
    assert.equal(loops[0].count, 3);
  });

  it('does not flag 2 repetitions as a loop (below threshold)', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'a.js' } },
      { type: 'tool_call', tool: 'read', args: { path: 'a.js' } },
    ]);
    const loops = detectLoops(session, 3);
    assert.equal(loops.length, 0);
  });

  it('detects loops from sample data', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'src/main.js' } },
      { type: 'tool_result', tool: 'read', output: 'file contents...' },
      { type: 'tool_call', tool: 'read', args: { path: 'src/main.js' } },
      { type: 'tool_result', tool: 'read', output: 'file contents...' },
      { type: 'tool_call', tool: 'read', args: { path: 'src/main.js' } },
      { type: 'tool_result', tool: 'read', output: 'file contents...' },
      { type: 'tool_call', tool: 'read', args: { path: 'src/main.js' } },
      { type: 'tool_result', tool: 'read', output: 'file contents...' },
    ]);
    const loops = detectLoops(session);
    assert.equal(loops.length, 1);
    assert.equal(loops[0].count, 4);
  });

  it('ignores non-tool_call events', () => {
    const session = makeSession([
      { type: 'message', output: 'a' },
      { type: 'message', output: 'a' },
      { type: 'message', output: 'a' },
    ]);
    assert.equal(detectLoops(session).length, 0);
  });

  it('returns empty for sessions with no events', () => {
    const session = makeSession([]);
    assert.equal(detectLoops(session).length, 0);
  });

  it('detects multiple separate loops', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_call', tool: 'edit', args: { path: 'b' } },
      { type: 'tool_call', tool: 'edit', args: { path: 'b' } },
      { type: 'tool_call', tool: 'edit', args: { path: 'b' } },
    ]);
    const loops = detectLoops(session);
    assert.equal(loops.length, 2);
    assert.equal(loops[0].tool, 'read');
    assert.equal(loops[1].tool, 'edit');
  });
});

describe('detector — detectStagnation', () => {
  it('detects repeated identical tool results', () => {
    const session = makeSession([
      { type: 'tool_result', output: 'same' },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_result', output: 'same' },
    ]);
    const stag = detectStagnation(session, 4);
    assert.equal(stag.length, 1);
    assert.equal(stag[0].type, 'stagnation');
    assert.equal(stag[0].windowSize, 4);
  });

  it('does not flag fewer than window repeated results', () => {
    const session = makeSession([
      { type: 'tool_result', output: 'same' },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_result', output: 'same' },
    ]);
    assert.equal(detectStagnation(session, 4).length, 0);
  });

  it('detects stagnation from sample data', () => {
    const session = makeSession([
      { type: 'tool_result', output: 'file1 file2' },
      { type: 'tool_result', output: 'file1 file2' },
      { type: 'tool_result', output: 'file1 file2' },
      { type: 'tool_result', output: 'file1 file2' },
      { type: 'tool_result', output: 'file1 file2' },
    ]);
    const stag = detectStagnation(session, 4);
    assert.equal(stag.length, 1);
    assert.ok(stag[0].windowSize >= 4);
  });

  it('returns empty for sessions with no results', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read' },
    ]);
    assert.equal(detectStagnation(session).length, 0);
  });
});

describe('detector — detectCrashes', () => {
  it('detects crashed status', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read' },
      { type: 'error', error: 'fatal' },
    ], 'crashed');
    const crashes = detectCrashes(session);
    assert.equal(crashes.length, 1);
    assert.equal(crashes[0].type, 'crash');
  });

  it('detects error without completion', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'exec' },
      { type: 'error', error: 'OOM killed' },
    ]);
    const crashes = detectCrashes(session);
    assert.equal(crashes.length, 1);
    assert.equal(crashes[0].error, 'OOM killed');
  });

  it('does not flag errors followed by completion', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'exec' },
      { type: 'error', error: 'transient' },
      { type: 'tool_call', tool: 'exec' },
      { type: 'completion', output: 'done' },
    ]);
    assert.equal(detectCrashes(session).length, 0);
  });

  it('detects failed status', () => {
    const session = makeSession([], 'failed');
    const crashes = detectCrashes(session);
    assert.equal(crashes.length, 1);
  });

  it('returns empty for clean sessions', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read' },
      { type: 'tool_result', output: 'ok' },
      { type: 'completion', output: 'done' },
    ]);
    assert.equal(detectCrashes(session).length, 0);
  });
});

describe('detector — detectAll', () => {
  it('aggregates all anomaly types', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_result', output: 'same' },
      { type: 'tool_call', tool: 'read', args: { path: 'a' } },
      { type: 'tool_result', output: 'same' },
      { type: 'error', error: 'crash' },
    ], 'crashed');
    const all = detectAll(session);
    const types = new Set(all.map(a => a.type));
    assert.ok(types.has('loop'));
    assert.ok(types.has('stagnation'));
    assert.ok(types.has('crash'));
  });

  it('returns empty for clean sessions', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'x' } },
      { type: 'tool_result', output: 'content' },
      { type: 'completion', output: 'done' },
    ]);
    assert.equal(detectAll(session).length, 0);
  });
});
