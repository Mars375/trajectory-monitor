# ACTIVE.md — trajectory-monitor

**Phase**: VEILLE
**Repo**: https://github.com/Mars375/trajectory-monitor
**Tag**: v0.1.0
**Last validated**: 2026-04-08

## État (updated 2026-04-08 22:55)
- 72/72 tests passants
- 8 détecteurs: crash_repeat, loop, stagnation, duration_spike, token_bloat, consecutive_errors, feature_race, **hallucination_pattern**
- Score qualité 0-100 avec breakdown
- CLI + rapport terminal + JSON
- MCP server (5 outils: analyze_jobs, check_job, get_score, analyze_session, list_signals)
- **tools/analyze_openclaw.py** : rapport forge-focused markdown
- **Hallucination detector** : re-creation + burst + workspace existence check

## Backlog V2 (quand activité reprend)
- [ ] Intégration MCP live avec OpenClaw
- [ ] Analyse JSONL transcripts complets (pas juste jobs.json state)
- [ ] Trend analysis (comparer scores entre runs successifs)
- [ ] Hallucination filesystem check intégré au MCP server

## Critères réouverture ACTIVE
- Issue GitHub ouverte par communauté ou handler
- Demande explicite d'évolution
- Découverte de bug en production

## Session 2026-04-08 22:55 — P5 DONE
- **P5 — Hallucination-pattern detector** : DONE
- Implémenté:
  - Re-creation detection: fichiers clamés "created" dans 2+ runs
  - Burst detection: run référence 5+ fichiers uniques
  - Workspace-aware: `check_file_existence(job, workspace_path)`
  - 22 nouveaux tests → 72 total
- Validé live: 9 hallucination signals détectés
  - forge-imagine re-crée PLAN.md/RESULT.md/TOOLS.md
  - orphan jobs avec burst de fichiers
- P4 également poussé (analyze_openclaw.py + 20 tests)
- Toutes les priorités P1-P5: DONE ✅
- Phase: VEILLE — toutes les priorités ouvertes sont terminées
