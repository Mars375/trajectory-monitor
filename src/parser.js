// parser.js — Parse trajectory data from jobs.json or session files
import { readFileSync } from 'node:fs';

/**
 * Normalize a raw session object into a standard trajectory format.
 * @param {object} raw - Raw session data (various formats)
 * @returns {{ sessionId: string, agentId: string, startTime: string|null, endTime: string|null, status: string, events: Array }}
 */
export function normalizeSession(raw) {
  if (!raw || typeof raw !== 'object') {
    throw new Error('Invalid session data: expected object');
  }

  const sessionId = raw.sessionId || raw.session_id || raw.id || 'unknown';
  const agentId = raw.agentId || raw.agent_id || raw.agent || 'unknown';
  const startTime = raw.startTime || raw.start_time || raw.created_at || null;
  const endTime = raw.endTime || raw.end_time || raw.completed_at || null;
  const status = raw.status || 'unknown';

  const events = (raw.events || raw.messages || raw.steps || []).map((ev, i) => ({
    index: i,
    timestamp: ev.timestamp || ev.ts || ev.created_at || null,
    type: ev.type || ev.role || 'unknown',
    tool: ev.tool || ev.name || ev.tool_name || null,
    args: ev.args || ev.arguments || ev.input || null,
    output: ev.output || ev.content || ev.result || null,
    error: ev.error || ev.err || null,
  }));

  return { sessionId, agentId, startTime, endTime, status, events };
}

/**
 * Parse a JSON file containing one or more sessions.
 * Supports: single session object, array of sessions, or { sessions: [...] } wrapper.
 * @param {string} filePath - Path to JSON file
 * @returns {Array} Array of normalized session trajectories
 */
export function parseFile(filePath) {
  const content = readFileSync(filePath, 'utf-8');
  const raw = JSON.parse(content);

  if (Array.isArray(raw)) {
    return raw.map(normalizeSession);
  }

  if (raw.sessions && Array.isArray(raw.sessions)) {
    return raw.sessions.map(normalizeSession);
  }

  // Single session object
  return [normalizeSession(raw)];
}

/**
 * Compute duration of a session in milliseconds.
 * @param {object} session - Normalized session
 * @returns {number|null}
 */
export function sessionDuration(session) {
  if (!session.startTime || !session.endTime) return null;
  return new Date(session.endTime) - new Date(session.startTime);
}
