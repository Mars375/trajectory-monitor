import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { parseFile } from '../src/parser.js';
import { detectAll } from '../src/detector.js';
import { scoreSession, grade } from '../src/scorer.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const sample = (name) => join(__dirname, '..', 'samples', name);

describe('integration — full pipeline with sample data', () => {
  it('normal-session: clean session, high score', () => {
    const sessions = parseFile(sample('normal-session.json'));
    assert.equal(sessions.length, 1);
    const anomalies = detectAll(sessions[0]);
    assert.equal(anomalies.length, 0);
    const { score } = scoreSession(sessions[0], anomalies);
    assert.ok(score >= 90, `Expected score >= 90, got ${score}`);
    assert.equal(grade(score), 'A');
  });

  it('loop-session: detects loop anomaly', () => {
    const sessions = parseFile(sample('loop-session.json'));
    const anomalies = detectAll(sessions[0]);
    const types = anomalies.map(a => a.type);
    assert.ok(types.includes('loop'), 'Expected loop anomaly');
    const { score } = scoreSession(sessions[0], anomalies);
    assert.ok(score < 90, `Expected score < 90 for loop session, got ${score}`);
  });

  it('crash-session: detects crash anomaly', () => {
    const sessions = parseFile(sample('crash-session.json'));
    const anomalies = detectAll(sessions[0]);
    const types = anomalies.map(a => a.type);
    assert.ok(types.includes('crash'), 'Expected crash anomaly');
    const { score } = scoreSession(sessions[0], anomalies);
    assert.ok(score < 80, `Expected score < 80 for crash, got ${score}`);
  });

  it('stagnation-session: detects stagnation anomaly', () => {
    const sessions = parseFile(sample('stagnation-session.json'));
    const anomalies = detectAll(sessions[0]);
    const types = anomalies.map(a => a.type);
    assert.ok(types.includes('stagnation') || types.includes('loop'),
      'Expected stagnation or loop anomaly');
    const { score } = scoreSession(sessions[0], anomalies);
    assert.ok(score < 80, `Expected score < 80 for stagnation, got ${score}`);
  });

  it('all samples produce valid scores (0-100)', () => {
    const files = [
      sample('normal-session.json'),
      sample('loop-session.json'),
      sample('crash-session.json'),
      sample('stagnation-session.json'),
    ];
    for (const file of files) {
      const sessions = parseFile(file);
      for (const session of sessions) {
        const anomalies = detectAll(session);
        const { score } = scoreSession(session, anomalies);
        assert.ok(score >= 0 && score <= 100, `Score ${score} out of range for ${file}`);
      }
    }
  });
});
