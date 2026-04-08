# ACTIVE.md — trajectory-monitor

**Phase**: VEILLE
**Repo**: https://github.com/Mars375/trajectory-monitor
**Tag**: v0.1.0
**Last validated**: 2026-04-08

## État
- 13/13 tests passants
- 6 détecteurs: crash_repeat, loop, stagnation, duration_spike, token_bloat, consecutive_errors
- Score qualité 0-100 avec breakdown
- CLI + rapport terminal + JSON
- MCP server placeholder prêt

## Backlog V2 (quand activité reprend)
- [ ] Détecteur feature-race (N features sans validation intermédiaire)
- [ ] Détecteur hallucination-pattern (refs fichiers/fonctions inexistantes)
- [ ] Intégration MCP live avec OpenClaw
- [ ] Analyse JSONL transcripts complets (pas juste jobs.json state)

## Critères réouverture ACTIVE
- Issue GitHub ouverte par communauté ou handler
- Demande explicite d'évolution
- Découverte de bug en production

## Veille run 2026-04-08 12:44
- 13/13 tests ✅
- 0 open GitHub issues
- Real analysis: 45 jobs, 45 signals (11 critical, 33 warnings), avg score 55/100
- Trend: critical signals stable (11 vs 12 last run)
- Top failures: forge-scout-signals (8/F), forge-imagine (19/F), forge-meta-improve (33/F)
- forge-chantier-mcp-audit improved: 39/F (was 14/F — possible recovery)
- trajectory-monitor itself: 36/F (1 consecutive error — self-detecting own past failures)
- PRIORITIES.md updated: P1 marked DONE (was stale), P2 marked IN PROGRESS
- No bugs found, no new features needed
- Phase remains VEILLE
