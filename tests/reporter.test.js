import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { formatReport, jsonReport } from '../src/reporter.js';
import { normalizeSession } from '../src/parser.js';

function makeSession(events, status = 'completed') {
  return normalizeSession({
    sessionId: 'sess-test',
    agentId: 'test-agent',
    startTime: '2026-04-13T10:00:00Z',
    endTime: '2026-04-13T10:05:00Z',
    status,
    events,
  });
}

describe('reporter — formatReport', () => {
  it('includes session ID in header', () => {
    const session = makeSession([]);
    const report = formatReport(session, [], { score: 100, breakdown: { base: 100, loopPenalty: 0, stagnationPenalty: 0, crashPenalty: 0, completionBonus: 0, efficiencyBonus: 0 } });
    assert.ok(report.includes('sess-test'));
    assert.ok(report.includes('test-agent'));
  });

  it('shows no anomalies message when clean', () => {
    const session = makeSession([]);
    const report = formatReport(session, [], { score: 100, breakdown: { base: 100, loopPenalty: 0, stagnationPenalty: 0, crashPenalty: 0, completionBonus: 0, efficiencyBonus: 0 } });
    assert.ok(report.includes('No anomalies'));
  });

  it('formats loop anomalies', () => {
    const session = makeSession([]);
    const anomalies = [{ type: 'loop', tool: 'read', args: { path: 'x' }, count: 5, startIndex: 0 }];
    const report = formatReport(session, anomalies, { score: 75, breakdown: { base: 100, loopPenalty: 25, stagnationPenalty: 0, crashPenalty: 0, completionBonus: 0, efficiencyBonus: 0 } });
    assert.ok(report.includes('LOOP'));
    assert.ok(report.includes('read'));
    assert.ok(report.includes('5x'));
  });

  it('formats crash anomalies', () => {
    const session = makeSession([], 'crashed');
    const anomalies = [{ type: 'crash', error: 'segfault', lastIndex: 5 }];
    const report = formatReport(session, anomalies, { score: 60, breakdown: { base: 100, loopPenalty: 0, stagnationPenalty: 0, crashPenalty: 40, completionBonus: 0, efficiencyBonus: 0 } });
    assert.ok(report.includes('CRASH'));
    assert.ok(report.includes('segfault'));
  });

  it('formats stagnation anomalies', () => {
    const session = makeSession([]);
    const anomalies = [{ type: 'stagnation', windowSize: 6, startIndex: 2 }];
    const report = formatReport(session, anomalies, { score: 70, breakdown: { base: 100, loopPenalty: 0, stagnationPenalty: 25, crashPenalty: 0, completionBonus: 0, efficiencyBonus: 0 } });
    assert.ok(report.includes('STAGNATION'));
  });

  it('includes score and grade', () => {
    const session = makeSession([]);
    const report = formatReport(session, [], { score: 85, breakdown: { base: 100, loopPenalty: 0, stagnationPenalty: 0, crashPenalty: 0, completionBonus: 0, efficiencyBonus: 0 } });
    assert.ok(report.includes('85'));
    assert.ok(report.includes('B'));
  });

  it('shows duration when available', () => {
    const session = makeSession([]);
    const report = formatReport(session, [], { score: 100, breakdown: { base: 100, loopPenalty: 0, stagnationPenalty: 0, crashPenalty: 0, completionBonus: 0, efficiencyBonus: 0 } });
    assert.ok(report.includes('5m'));
  });
});

describe('reporter — jsonReport', () => {
  it('produces valid JSON', () => {
    const session = makeSession([{ type: 'tool_call', tool: 'read' }]);
    const anomalies = [];
    const scoring = { score: 100, breakdown: { base: 100, loopPenalty: 0, stagnationPenalty: 0, crashPenalty: 0, completionBonus: 10, efficiencyBonus: 5 } };
    const json = jsonReport(session, anomalies, scoring);
    const parsed = JSON.parse(json);
    assert.equal(parsed.sessionId, 'sess-test');
    assert.equal(parsed.score, 100);
  });

  it('includes anomalies in JSON output', () => {
    const session = makeSession([]);
    const anomalies = [
      { type: 'loop', tool: 'exec', count: 3 },
      { type: 'crash', error: 'timeout' },
    ];
    const scoring = { score: 40, breakdown: { base: 100, loopPenalty: 15, stagnationPenalty: 0, crashPenalty: 40, completionBonus: 0, efficiencyBonus: 0 } };
    const parsed = JSON.parse(jsonReport(session, anomalies, scoring));
    assert.equal(parsed.anomalyCount, 2);
    assert.equal(parsed.anomalies[0].type, 'loop');
    assert.equal(parsed.anomalies[1].type, 'crash');
  });
});
