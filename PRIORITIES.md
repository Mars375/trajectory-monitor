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

## [~] P2 — Signaux Stagnation et Feature-race (stagnation done, feature-race TODO)
**Objectif** : Détecter les sessions agents qui n'avancent pas ou ajoutent des features sans valider.

Stagnation : aucune action concrète depuis N étapes dans un transcript.
Feature-race : N commits en <1h sans test run entre les deux.

---

## [ ] P3 — MCP server (auto-introspection agent)
**Objectif** : L'agent peut appeler trajectory-monitor sur lui-même en cours de session.

Outil MCP `analyze_session(log)` → retourne les signaux détectés + score qualité.

---

## [ ] P4 — Intégration OpenClaw native
**Objectif** : forge-meta-improve appelle trajectory-monitor pour enrichir son analyse hebdo.

Script `tools/analyze_openclaw.py` qui analyse tous les crons forge et produit un rapport markdown.
