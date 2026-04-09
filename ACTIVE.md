# ACTIVE.md — trajectory-monitor

**Phase**: VEILLE
**Repo**: https://github.com/Mars375/trajectory-monitor
**Tag**: v0.2.0
**Last validated**: 2026-04-09

## État (updated 2026-04-09 18:58)
- 101/101 tests passants
- 8 détecteurs: crash_repeat, loop, stagnation, duration_spike, token_bloat, consecutive_errors, feature_race, hallucination_pattern
- Score qualité 0-100 avec breakdown
- CLI + rapport terminal + JSON
- MCP server (6 outils: analyze_jobs, check_job, get_score, get_recommendations, analyze_session, list_signals)
- **tools/analyze_openclaw.py** : rapport forge-focused markdown
- **Hallucination detector** : re-creation + burst + workspace existence check
- **Recommendations engine** : suggestions actionables par signal type + sévérité
- **🆕 MCP analyze_session workspace-aware** : parsing JSONL partagé + `workspace_path` pour vérifier les fichiers référencés sur disque

## Backlog V2 (quand activité reprend)
- [ ] Intégration MCP live avec OpenClaw
- [ ] Trend analysis (comparer scores entre runs successifs)
- [ ] Analyse transcripts plus riches que les seuls événements `finished`
- [ ] MCP live mode pour introspection en cours d'exécution

## Critères réouverture ACTIVE
- Issue GitHub ouverte par communauté ou handler
- Demande explicite d'évolution
- Découverte de bug en production

## Session 2026-04-09 02:47 — Recommendations Engine
- **Nouveau module**: `recommendations.py` — moteur de recommandations actionables
  - Mappe chaque type de signal + sévérité → actions spécifiques
  - Contextuel: utilise les détails du signal (streak, ratio, growth_factor, etc.)
  - Priorisation: high/medium/low triée automatiquement
  - Intégré aux rapports terminal + JSON
- **24 nouveaux tests** → 96 total (tous verts)
- **Validation live**: 60 recommandations générées sur 34 jobs
- **Données réelles**:
  - Score moyen crons: 50/100
  - 18 signaux critiques, 40 warnings
  - Top problèmes: forge-imagine (1/100), forge-chantier-trajectory-monitor (10/100), forge-gate (19/100)
- Phase: VEILLE — aucune issue GitHub, backlog V2 prêt

## Session 2026-04-08 22:55 — P5 DONE
- P1-P5: DONE ✅


## Session 2026-04-09 18:58 — MCP workspace-aware transcript analysis
- `parser.py` factorisé avec `parse_run_jsonl_text()` pour partager le parsing entre fichiers et texte brut
- Fallback de résumé ajouté (`result.summary` / `result.text` / `message` / `text`) pour mieux couvrir les transcripts réels
- `analyze_session(..., workspace_path=...)` retourne maintenant `workspace_check` et ajoute un signal `missing_on_disk` si besoin
- Score MCP cohérent avec les signaux filesystem additionnels
- Validation: **101/101 tests verts**, CLI OK, analyse live `/home/orion/.openclaw/cron/jobs.json` OK, transcript réel du cron analysé (26 runs)
- Phase: VEILLE maintenue, backlog V2 recentré sur trend analysis / richer transcripts / MCP live mode
