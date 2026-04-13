# ACTIVE.md — trajectory-monitor

**Phase**: VEILLE
**Repo**: https://github.com/Mars375/trajectory-monitor
**Tag**: v0.2.0
**Last validated**: 2026-04-10

## État (updated 2026-04-10 13:08)
- 128/128 tests passants
- 9 détecteurs: crash_repeat, loop, stagnation, duration_spike, token_bloat, consecutive_errors, feature_race, hallucination_pattern, regression_trend
- Score qualité 0-100 avec breakdown pondéré par type de signal
- Trend analysis entre fenêtres de runs successifs
- CLI + rapport terminal + JSON
- MCP server (6 outils: analyze_jobs, check_job, get_score, get_recommendations, analyze_session, list_signals)
- **tools/analyze_openclaw.py** : rapport forge-focused markdown
- **Recommendations engine** : suggestions actionables par signal type + sévérité
- **MCP analyze_session workspace-aware** : parsing JSONL partagé + `workspace_path` pour vérifier les fichiers référencés sur disque
- **🆕 Action policies** : `normal`, `watch`, `stabilize`, `bugfix_only` exposées dans JSON + MCP avec raisons, budget de nouvelles features et `policy_counts`

## Backlog V2 (quand activité reprend)
- [ ] Intégration MCP live avec OpenClaw
- [ ] Analyse JSONL/tool-call level plus riche que les seuls événements `finished`
- [ ] Brancher `action_policy` sur de vrais seuils d’alerte externes / automations

## Critères réouverture ACTIVE
- Issue GitHub ouverte par communauté ou handler
- Demande explicite d'évolution
- Découverte de bug en production

## Session 2026-04-10 13:08 — P15 DONE
- `parser.py` ingère maintenant les lignes utiles dans les blocs de code markdown quand elles ressemblent à de vraies commandes ou sorties de validation/erreur
- `signals.py` supprime le faux `feature_race` sur les transcripts markdown-only dès qu’une validation existe quelque part dans la même recap
- `mcp_server.py` dérive aussi `consecutive_errors` depuis les dernières lignes d’un transcript, ce qui rend `bugfix_only` cohérent même sans `jobs.json`
- Validation: **128/128 tests verts**, CLI OK, analyse live `/home/orion/.openclaw/cron/jobs.json` OK, smoke `analyze_session()` markdown OK
- Phase: VEILLE maintenue, prochain incrément utile = MCP live / vrai parsing tool-call level / alertes externes

## Session 2026-04-10 03:07 — P12 DONE
- `scorer.py` dérive maintenant une `action_policy` par job/session à partir du score pondéré, des signaux et de la tendance
- Modes: `normal`, `watch`, `stabilize`, `bugfix_only`
- `report.py` expose `policy_counts` en JSON et affiche la politique des jobs à surveiller
- `mcp_server.py` expose `action_policy` dans `check_job`, `get_score`, `get_recommendations` et `analyze_session`
- Validation: **118/118 tests verts**, CLI OK, `python3 -m trajectory_monitor analyze /home/orion/.openclaw/cron/jobs.json --json` OK, `python3 tools/analyze_openclaw.py` OK
- Phase: VEILLE maintenue, prochain incrément utile = richer JSONL transcripts / MCP live / seuils d’alerte externes

## Session 2026-04-09 18:58 — MCP workspace-aware transcript analysis
- `parser.py` factorisé avec `parse_run_jsonl_text()` pour partager le parsing entre fichiers et texte brut
- Fallback de résumé ajouté (`result.summary` / `result.text` / `message` / `text`) pour mieux couvrir les transcripts réels
- `analyze_session(..., workspace_path=...)` retourne maintenant `workspace_check` et ajoute un signal `missing_on_disk` si besoin
- Score MCP cohérent avec les signaux filesystem additionnels
- Validation: **101/101 tests verts**, CLI OK, analyse live `/home/orion/.openclaw/cron/jobs.json` OK, transcript réel du cron analysé (26 runs)
- Phase: VEILLE maintenue, backlog V2 recentré sur trend analysis / richer transcripts / MCP live mode

## Session 2026-04-11 13:08 — Maintenance

- **Phase**: MAINTENANCE (all P1-P15 DONE, no open issues)
- **Smoke test**: 128 tests pass, live analysis OK (51 jobs, 66 signals)
- **Self-analysis**: Score 41/D, improving (score_delta +17), 1 signal (crash_repeat critical — write failures 3x)
- **Maintenance**: Committed PRD.md + ROADMAP.md, pushed 2 commits to origin
- **Next**: V2 backlog items (MCP live mode, GitHub public promo, PyPI release) — needs forge-maintainer decision
