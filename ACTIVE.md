# ACTIVE.md — trajectory-monitor

**Phase**: ACTIVE
**Repo**: https://github.com/Mars375/trajectory-monitor
**Tag**: v0.1.0
**Last validated**: 2026-04-08

## État (updated 2026-04-08 20:52)
- 50/50 tests passants
- 7 détecteurs: crash_repeat, loop, stagnation, duration_spike, token_bloat, consecutive_errors, feature_race
- Score qualité 0-100 avec breakdown
- CLI + rapport terminal + JSON
- MCP server (5 outils: analyze_jobs, check_job, get_score, analyze_session, list_signals)
- **tools/analyze_openclaw.py** : rapport forge-focused markdown pour forge-meta-improve

## Backlog V2 (quand activité reprend)
- [ ] Détecteur hallucination-pattern (refs fichiers/fonctions inexistantes)
- [ ] Intégration MCP live avec OpenClaw
- [ ] Analyse JSONL transcripts complets (pas juste jobs.json state)
- [ ] Trend analysis (comparer scores entre runs successifs)

## Critères réouverture ACTIVE
- Issue GitHub ouverte par communauté ou handler
- Demande explicite d'évolution
- Découverte de bug en production

## Session 2026-04-08 20:52 — P4 DONE
- **P4 — Intégration OpenClaw native** : DONE
- Créé `tools/analyze_openclaw.py` : rapport markdown forge-focused
  - Filtre forge-*, scores, signaux, recommandations, comparaison non-forge
  - CLI: --output, --json, --all, --jobs-json, --runs-dir
  - 20 nouveaux tests → 50 total
- Validation réelle: 10 forge jobs, 4 critiques, score moyen 49/100
- Top problèmes: forge-imagine (19/F), forge-meta-improve (33/F), trajectory-monitor self (37/F)
- Phase: ACTIVE → reste ACTIVE (P5 dans le backlog)
