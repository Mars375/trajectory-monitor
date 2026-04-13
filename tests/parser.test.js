import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { normalizeSession, parseFile, sessionDuration } from '../src/parser.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const sample = (name) => join(__dirname, '..', 'samples', name);

describe('parser — normalizeSession', () => {
  it('normalizes a standard session object', () => {
    const raw = {
      sessionId: 's1',
      agentId: 'codex',
      startTime: '2026-01-01T00:00:00Z',
      endTime: '2026-01-01T00:01:00Z',
      status: 'completed',
      events: [
        { type: 'tool_call', tool: 'read', args: { path: 'a.js' }, output: null },
        { type: 'tool_result', tool: 'read', output: 'contents' },
      ],
    };
    const s = normalizeSession(raw);
    assert.equal(s.sessionId, 's1');
    assert.equal(s.agentId, 'codex');
    assert.equal(s.status, 'completed');
    assert.equal(s.events.length, 2);
    assert.equal(s.events[0].tool, 'read');
    assert.equal(s.events[1].output, 'contents');
  });

  it('handles alternative field names (snake_case)', () => {
    const raw = {
      session_id: 's2',
      agent_id: 'claude',
      start_time: '2026-01-01T00:00:00Z',
      end_time: '2026-01-01T00:05:00Z',
      status: 'running',
      steps: [
        { role: 'assistant', name: 'edit', input: { file: 'x' }, content: 'ok' },
      ],
    };
    const s = normalizeSession(raw);
    assert.equal(s.sessionId, 's2');
    assert.equal(s.agentId, 'claude');
    assert.equal(s.events.length, 1);
    assert.equal(s.events[0].tool, 'edit');
    assert.equal(s.events[0].args.file, 'x');
    assert.equal(s.events[0].output, 'ok');
  });

  it('handles minimal/empty session', () => {
    const s = normalizeSession({});
    assert.equal(s.sessionId, 'unknown');
    assert.equal(s.agentId, 'unknown');
    assert.equal(s.status, 'unknown');
    assert.equal(s.events.length, 0);
  });

  it('throws on null or non-object', () => {
    assert.throws(() => normalizeSession(null), /Invalid session data/);
    assert.throws(() => normalizeSession('string'), /Invalid session data/);
    assert.throws(() => normalizeSession(42), /Invalid session data/);
  });

  it('preserves index on events', () => {
    const raw = {
      sessionId: 's3',
      events: [
        { type: 'tool_call', tool: 'a' },
        { type: 'tool_call', tool: 'b' },
        { type: 'tool_call', tool: 'c' },
      ],
    };
    const s = normalizeSession(raw);
    assert.equal(s.events[0].index, 0);
    assert.equal(s.events[1].index, 1);
    assert.equal(s.events[2].index, 2);
  });
});

describe('parser — parseFile', () => {
  it('parses a single session file', () => {
    const sessions = parseFile(sample('normal-session.json'));
    assert.equal(sessions.length, 1);
    assert.equal(sessions[0].sessionId, 'sess-normal-001');
    assert.equal(sessions[0].events.length, 7);
  });

  it('parses a loop session file', () => {
    const sessions = parseFile(sample('loop-session.json'));
    assert.equal(sessions.length, 1);
    assert.equal(sessions[0].sessionId, 'sess-loop-001');
  });

  it('parses a crash session file', () => {
    const sessions = parseFile(sample('crash-session.json'));
    assert.equal(sessions.length, 1);
    assert.equal(sessions[0].status, 'crashed');
  });

  it('parses a stagnation session file', () => {
    const sessions = parseFile(sample('stagnation-session.json'));
    assert.equal(sessions.length, 1);
    assert.equal(sessions[0].sessionId, 'sess-stagnation-001');
  });
});

describe('parser — sessionDuration', () => {
  it('computes duration in milliseconds', () => {
    const session = normalizeSession({
      sessionId: 'x',
      startTime: '2026-01-01T00:00:00Z',
      endTime: '2026-01-01T00:05:00Z',
      events: [],
    });
    assert.equal(sessionDuration(session), 5 * 60 * 1000);
  });

  it('returns null when start or end missing', () => {
    assert.equal(sessionDuration(normalizeSession({ events: [] })), null);
    assert.equal(sessionDuration(normalizeSession({ startTime: '2026-01-01', events: [] })), null);
  });
});
