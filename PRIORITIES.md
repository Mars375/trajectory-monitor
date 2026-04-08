# PRIORITIES.md — Feuille de route du chantier trajectory-monitor

> Ce fichier est le pilote du cron forge-chantier-trajectory-monitor.
> Le cron lit ce fichier au début de chaque session et travaille sur la première priorité OPEN.
> Si toutes les priorités sont DONE → le cron travaille sur les issues GitHub ouvertes.
> forge-maintainer peut modifier ce fichier pour orienter le chantier.

## Format
- `[ ]` OPEN — à faire
- `[~]` IN PROGRESS — commencé, continuer
- `[x]` DONE — terminé

---

## [x] P1 — parser.py + signaux Loop et Crash-repeat ✅ (2026-04-07)
**Objectif** : Ingérer jobs.json OpenClaw et détecter les 2 signaux les plus utiles immédiatement.

Implémenté :
- `parser.py` : lit jobs.json, extrait state (consecutiveErrors, lastError, lastDurationMs, lastRunStatus)
- `signals.py` : 6 détecteurs (crash_repeat, loop, stagnation, duration_spike, token_bloat, consecutive_errors)
- `cli.py` + `report.py` : sortie terminal + JSON structuré

Validé : `python -m trajectory_monitor analyze /home/orion/.openclaw/cron/jobs.json` produit un rapport sensé sur les crons réels.

---

## [x] P2 — Signaux Feature-race + Stagnation ✅ (2026-04-08)
**Objectif** : Détecter les sessions agents qui n'avancent pas ou ajoutent des features sans valider.

Implémenté :
- Stagnation : aucune action concrète depuis N étapes dans un transcript
- Feature-race : N+3 runs consécutifs avec ajout de features sans validation intermédiaire
  - Mots-clés EN/FR : added, implemented, created, built, ajouté, implémenté, créé
  - Validation keywords cassent le streak : test, validated, fix, corrigé, vérifié
  - Seuils : WARNING à 3 streak, CRITICAL à 5+
  - Tests unitaires : 6 nouveaux tests (trigger, critical, no-signal-with-validation, too-few, french-keywords)

Validé sur données réelles : 3 jobs with feature_race signal (orphan:a4c76d01=10x CRITICAL, orphan:158055cd=3x, orphan:c703caef=3x)

---

## [x] P3 — MCP server (auto-introspection agent) ✅ (2026-04-08)
**Objectif** : L'agent peut appeler trajectory-monitor sur lui-même en cours de session.

Implémenté :
- `mcp_server.py` : Serveur MCP avec FastMCP (mcp 1.27.0)
- 5 outils MCP : `analyze_jobs`, `check_job`, `get_score`, `analyze_session`, `list_signals`
- `analyze_session` : accepte texte JSONL ou chemin fichier, analyse complète (signaux + score)
- `list_signals` : liste les 7 détecteurs disponibles
- CLI `serve` command : `trajectory-monitor serve` démarre le serveur MCP
- 12 nouveaux tests unitaires (30 total, tous verts)
- Auto-détection des paths OpenClaw

Validé : `python -m trajectory_monitor serve` démarre le serveur MCP stdio.

---

## [ ] P4 — Intégration OpenClaw native
**Objectif** : forge-meta-improve appelle trajectory-monitor pour enrichir son analyse hebdo.

Script `tools/analyze_openclaw.py` qui analyse tous les crons forge et produit un rapport markdown.
