# trajectory-monitor — Product Requirements Document (PRD)

**Version:** v0.2
**Status:** Active
**Phase:** ACTIVE
**Tagline:** Analyse les trajectoires d'exécution des agents — détecte boucles, stagnation et anomalies avant qu'elles coûtent cher.

---

## 1. Vision

trajectory-monitor est un outil d'analyse de trajectoires d'exécution pour agents LLM. Il ingère les logs de sessions (jobs.json OpenClaw, JSONL, transcripts Markdown), détecte les anomalies comportementales, et produit des rapports avec des action policies configurables (normal/watch/stabilize/bugfix_only).

Conçu pour être utilisé directement par des agents via MCP, ou intégré dans des crons de supervision.

---

## 2. Problème

Les agents LLM en production tombent dans des patterns dysfonctionnels invisibles :
- **Boucles :** l'agent répète la même action sans avancer (>60% word overlap sur 3+ runs)
- **Stagnation :** l'agent tourne mais ne produit aucun résultat mesurable
- **Crash répété :** erreur récurrente qui bloque le pipeline
- **Token bloat :** contexte qui gonfle de session en session (output tokens ×1.5 sur 3 runs)
- **Feature race :** l'agent ajoute des features sans valider les précédentes
- **Regression :** score qualité qui décline entre fenêtres de runs

Sans outil d'analyse, ces patterns sont invisibles jusqu'à l'incident.

---

## 3. Cible

- Développeurs d'agents LLM en production
- SRE qui maintiennent des pipelines d'agents autonomes
- Équipes OpenClaw qui supervisent des chantiers forge

---

## 4. Architecture

```
trajectory_monitor/
├── parser.py           # Parsing multi-format : jobs.json, JSONL, transcripts Markdown
├── signals.py          # 9 détecteurs d'anomalies (crash_repeat, loop, stagnation, ...)
├── scorer.py           # Quality score 0-100 + trends + action policies configurables
├── report.py           # Terminal (Rich) + JSON + Markdown outputs
├── recommendations.py  # Suggestions actionnables par type de signal
├── mcp_server.py       # MCP server FastMCP : 6 outils
├── cli.py              # Click CLI : analyze, serve
└── tools/
    └── analyze_openclaw.py  # Rapport forge-specific (jobs forge-* uniquement)
```

**Stack :** stdlib Python, mcp (FastMCP). Zéro dépendance externe pour l'analyse core.

---

## 5. Fonctionnalités V1 (MVP — DONE)

**Parsing multi-format :**
- jobs.json OpenClaw (JobState avec consecutiveErrors, lastError, lastDurationMs)
- JSONL transcripts (RunEntry)
- Transcripts Markdown/texte (parsing heuristique, validation-aware : pytest keywords suppriment faux feature_race)

**9 détecteurs d'anomalies :**
- crash_repeat, loop, stagnation, duration_spike, token_bloat, consecutive_errors, feature_race, hallucination_pattern, regression_trend

**Scoring qualité :**
- Score 0-100 (grade A-F) : reliability 30%, activity 20%, consistency 20%, enabled 10%, recovery 10%
- Pénalités par signal, pondérées par type (crash_repeat/hallucination > duration_spike)
- Trend analysis : improving/stable/regressing, score_delta, error_rate_delta

**Action policies configurables :**
- Modes : normal, watch, stabilize, bugfix_only
- Seuils externalisés via `--policy-config` (JSON inline ou fichier)
- Chaque policy inclut : feature_delivery_allowed, should_alert, max_new_features

**MCP server (6 outils) :**
- `analyze_jobs`, `analyze_session`, `check_job`, `get_score`, `get_recommendations`, `list_signals`

**Intégration OpenClaw :**
- Validé sur le vrai jobs.json OpenClaw (44 jobs, 39 signaux détectés)
- Report forge-specific avec filtre jobs forge-*
- 128 tests passants

---

## 6. Critères de succès

- Détection de 6+ types d'anomalies avec < 5% faux positifs
- Analyse jobs.json complet en < 5 secondes
- Les action policies sont exploitables directement par un agent ou cron
- Compatible avec n'importe quel agent MCP

---

## 7. Hors scope (V1)

- Interface web / dashboard temps réel
- MCP live mode (streaming)
- Alertes webhook / notifications externes
- ML-based anomaly detection
