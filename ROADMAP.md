# trajectory-monitor — ROADMAP

## V1 — MVP ✅ DONE (P1→P15)

- [x] Parser multi-format (jobs.json, JSONL, Markdown)
- [x] 9 détecteurs d'anomalies
- [x] Scoring qualité 0-100 (grade A-F)
- [x] Trend analysis (improving/stable/regressing)
- [x] Action policies (normal/watch/stabilize/bugfix_only)
- [x] Policy thresholds configurables (JSON/fichier)
- [x] MCP server FastMCP (6 outils)
- [x] Recommendations engine (8 types de signaux)
- [x] Transcript Markdown support + validation-aware parsing
- [x] Rapport forge-specific OpenClaw
- [x] 128 tests

---

## V2 — Live Mode & Alerting

**Objectif :** Passer du batch analysis au monitoring temps réel.

- [ ] MCP live mode : stream des signaux en temps réel depuis un job en cours
- [ ] Webhook notifications : Slack, Telegram, PagerDuty sur CRITICAL signals
- [ ] Promotion GitHub : `gh repo create trajectory-monitor --public --source=. --push` + tag v0.2.0
- [ ] PyPI release (`pip install trajectory-monitor`)

---

## V3 — Fleet Analysis & Custom Rules

**Objectif :** Analyser des flottes de jobs et permettre des règles custom.

- [ ] Fleet health dashboard : vue consolidée de tous les jobs OpenClaw
- [ ] Cross-job trend analysis : comparer la santé de plusieurs chantiers
- [ ] YAML DSL pour règles custom d'anomalie (signal patterns définis par l'utilisateur)
- [ ] Autofix suggestions : générer des patches CLI pour corriger les issues détectées

---

## V4 — Integration & Distribution

**Objectif :** S'intégrer dans les workflows existants et devenir réutilisable.

- [ ] GitHub Action pour analyse de sessions en CI
- [ ] Plugin trajectory-monitor pour patternlearn (auto-créer patterns depuis les succès)
- [ ] Intégration cron-ui : exposer les signaux dans le dashboard cron
- [ ] SQLite DB pour historique local des analyses (trend sur semaines/mois)
