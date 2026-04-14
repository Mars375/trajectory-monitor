import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { scoreSession, grade } from '../src/scorer.js';
import { normalizeSession } from '../src/parser.js';

function makeSession(events, status = 'completed') {
  return normalizeSession({ sessionId: 'test', status, events });
}

describe('scorer — scoreSession', () => {
  it('gives 100 base + completion + efficiency for a perfect session', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'a.js' } },
      { type: 'tool_result', output: 'contents' },
      { type: 'tool_call', tool: 'edit', args: { path: 'a.js' } },
      { type: 'tool_result', output: 'ok' },
      { type: 'completion', output: 'done' },
    ]);
    const { score, breakdown } = scoreSession(session, []);
    assert.equal(score, 100); // capped at 100
    assert.equal(breakdown.completionBonus, 10);
    assert.equal(breakdown.efficiencyBonus, 5);
  });

  it('applies loop penalty', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read' },
      { type: 'tool_result', output: 'x' },
      { type: 'completion', output: 'done' },
    ]);
    const anomalies = [{ type: 'loop', tool: 'read', count: 5 }];
    const { breakdown } = scoreSession(session, anomalies);
    assert.equal(breakdown.loopPenalty, 25); // 5 * 5
  });

  it('caps loop penalty at 30', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read' },
      { type: 'tool_result', output: 'x' },
    ]);
    const anomalies = [{ type: 'loop', tool: 'read', count: 20 }];
    const { breakdown } = scoreSession(session, anomalies);
    assert.equal(breakdown.loopPenalty, 30);
  });

  it('applies stagnation penalty', () => {
    const session = makeSession([{ type: 'tool_result', output: 'x' }]);
    const anomalies = [{ type: 'stagnation', windowSize: 5 }];
    const { breakdown } = scoreSession(session, anomalies);
    assert.equal(breakdown.stagnationPenalty, 25); // 5 * 5
  });

  it('caps stagnation penalty at 25', () => {
    const session = makeSession([{ type: 'tool_result', output: 'x' }]);
    const anomalies = [{ type: 'stagnation', windowSize: 100 }];
    const { breakdown } = scoreSession(session, anomalies);
    assert.equal(breakdown.stagnationPenalty, 25);
  });

  it('applies crash penalty of 40', () => {
    const session = makeSession([], 'crashed');
    const anomalies = [{ type: 'crash', error: 'fatal' }];
    const { breakdown } = scoreSession(session, anomalies);
    assert.equal(breakdown.crashPenalty, 40);
  });

  it('score never goes below 0', () => {
    const session = makeSession([], 'crashed');
    const anomalies = [
      { type: 'crash', error: 'fatal' },
      { type: 'loop', tool: 'read', count: 10 },
      { type: 'stagnation', windowSize: 10 },
    ];
    const { score } = scoreSession(session, anomalies);
    assert.ok(score >= 0);
  });

  it('score never exceeds 100', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read' },
      { type: 'tool_result', output: 'x' },
      { type: 'completion', output: 'done' },
    ]);
    const { score } = scoreSession(session, []);
    assert.ok(score <= 100);
  });

  it('scores crash sample correctly', () => {
    const session = makeSession([
      { type: 'tool_call', tool: 'read', args: { path: 'src/main.js' } },
      { type: 'tool_result', output: 'contents' },
      { type: 'tool_call', tool: 'exec', args: { command: 'rm -rf /' } },
      { type: 'error', error: 'EACCES: permission denied' },
    ], 'crashed');
    const anomalies = [{ type: 'crash', error: 'EACCES: permission denied', lastIndex: 3 }];
    const { score, breakdown } = scoreSession(session, anomalies);
    assert.equal(breakdown.crashPenalty, 40);
    assert.equal(breakdown.completionBonus, 0);
    assert.ok(score < 100);
  });

  it('applies hallucination penalty of 15 per anomaly', () => {
    const session = makeSession([{ type: 'tool_result', output: 'x' }]);
    const anomalies = [
      { type: 'hallucination', subtype: 'missing_tool', details: 'no tool', index: 0 },
    ];
    const { breakdown } = scoreSession(session, anomalies);
    assert.equal(breakdown.hallucinationPenalty, 15);
  });

  it('applies timeout penalty of 25', () => {
    const session = makeSession([{ type: 'tool_result', output: 'x' }]);
    const anomalies = [
      { type: 'timeout', durationMs: 3600000, thresholdMs: 1800000, details: 'timed out' },
    ];
    const { breakdown } = scoreSession(session, anomalies);
    assert.equal(breakdown.timeoutPenalty, 25);
  });

  it('combined hallucination + timeout penalties', () => {
    const session = makeSession([], 'crashed');
    const anomalies = [
      { type: 'crash', error: 'fatal' },
      { type: 'hallucination', subtype: 'empty_args', tool: 'read', details: 'no args', index: 0 },
      { type: 'hallucination', subtype: 'garbled_tool', tool: '7', details: 'garbled', index: 1 },
      { type: 'timeout', durationMs: 3600000, thresholdMs: 1800000, details: 'timed out' },
    ];
    const { score, breakdown } = scoreSession(session, anomalies);
    assert.equal(breakdown.hallucinationPenalty, 30); // 2 * 15
    assert.equal(breakdown.timeoutPenalty, 25);
    assert.equal(breakdown.crashPenalty, 40);
    assert.ok(score >= 0);
  });
});

describe('scorer — grade', () => {
  it('returns A for 90+', () => assert.equal(grade(95), 'A'));
  it('returns A for exactly 90', () => assert.equal(grade(90), 'A'));
  it('returns B for 75-89', () => assert.equal(grade(80), 'B'));
  it('returns B for exactly 75', () => assert.equal(grade(75), 'B'));
  it('returns C for 60-74', () => assert.equal(grade(65), 'C'));
  it('returns C for exactly 60', () => assert.equal(grade(60), 'C'));
  it('returns D for 40-59', () => assert.equal(grade(50), 'D'));
  it('returns D for exactly 40', () => assert.equal(grade(40), 'D'));
  it('returns F for <40', () => assert.equal(grade(30), 'F'));
  it('returns F for 0', () => assert.equal(grade(0), 'F'));
});
