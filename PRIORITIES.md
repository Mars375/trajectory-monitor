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

## [x] P4 — Intégration OpenClaw native ✅ (2026-04-08)
**Objectif** : Script `tools/analyze_openclaw.py` qui analyse les crons forge et produit un rapport markdown.

Implémenté :
- `tools/analyze_openclaw.py` : rapport forge-focused markdown
- Filtre forge-* jobs, génère tableau de scores, signaux détaillés, recommandations
- Mode `--json` pour rapport complet, `--output` pour fichier, `--all` pour tous les jobs
- Comparaison automatique forge vs non-forge
- 20 nouveaux tests (50 total, tous verts)
- Auto-détection des paths OpenClaw

Validé : 10 forge jobs analysés, 4 signaux critiques détectés, rapport markdown de 130 lignes.

---

## [x] P5 — Hallucination-pattern detector ✅ (2026-04-08)
**Objectif** : Détecter les références à des fichiers/fonctions qui n'existent pas dans les summaries de runs.

Implémenté :
- Extraction de chemins de fichiers depuis les summaries (regex: paths avec dirs + bare filenames en backticks)
- **Re-creation detection** : fichier clamé "created" dans 2+ runs différents → probablement jamais persisté
- **Burst detection** : un run référence 5+ fichiers uniques non mentionnés ailleurs → hallucination potentielle
- **Workspace existence check** :  vérifie les fichiers sur disque
- 22 nouveaux tests (72 total, tous verts)
- Recommandation ajoutée au rapport forge

Validé sur données réelles : 9 hallucination signals détectés sur les crons OpenClaw (re-creation + burst).
Exemples : forge-imagine re-crée PLAN.md/RESULT.md/TOOLS.md sur plusieurs runs, orphan jobs avec burst de fichiers uniques.

### Next
- V2 backlog: feature-race avancé, hallucination avec vérification filesystem intégrée au MCP, scoring par type de signal

---

## [x] P6 — Recommendations Engine ✅ (2026-04-09)
**Objectif** : Générer des recommandations actionables à partir des signaux détectés.

Implémenté :
- `recommendations.py` : moteur de recommandations par type de signal + sévérité
- 8 jeux de règles (1 par type de signal) avec context templates
- Priorisation automatique (high/medium/low)
- Intégration rapport terminal : section "📋 RECOMMENDATIONS"
- Intégration rapport JSON : clé `recommendations` par job
- 24 nouveaux tests unitaires (96 total, tous verts)

Validé sur données réelles : 60 recommandations sur 34 jobs, couvrant 18 signaux critiques et 40 warnings.

### Next
- V2 backlog: MCP tool `get_recommendations`, trend analysis, JSONL transcript analysis


## [x] P7 — MCP tool `get_recommendations` ✅ (2026-04-09)
**Objectif** : Exposer les recommandations actionables directement via MCP pour l'auto-inspection agent.

Implémenté :
- `mcp_server.py` : nouveau tool `get_recommendations`
  - mode job spécifique ou vue agrégée de tous les jobs avec recommandations
  - retourne score, grade, signaux et suggestions JSON prêtes à consommer
- `analyze_session` enrichi avec la clé `recommendations` pour l'auto-inspection live
- README MCP mis à jour : 6 tools documentés
- 3 nouveaux tests MCP + 2 assertions renforcées → **99 tests** au total, tous verts

Validé sur données réelles : `get_recommendations(job_name="forge-chantier-trajectory-monitor")` remonte correctement `consecutive_errors` + `crash_repeat` avec 2 actions prioritaires.

### Next
- V2 backlog: trend analysis, JSONL transcript analysis, MCP live mode


## [x] P8 — MCP workspace-aware transcript analysis ✅ (2026-04-09)
**Objectif** : Fiabiliser `analyze_session` sur les transcripts JSONL réels et intégrer la vérification filesystem directement dans le MCP.

Implémenté :
- `parser.py` : parsing JSONL partagé via `parse_run_jsonl_text()`
- Fallback de résumé : `summary` → `result.summary` / `result.text` / `message` / `text`
- `mcp_server.py` : `analyze_session(..., workspace_path=...)` ajoute `workspace_check` au payload
- Vérification disque intégrée : signal `hallucination_pattern` type `missing_on_disk` si les fichiers référencés n'existent pas
- Le score de session tient aussi compte des signaux filesystem ajoutés côté MCP
- 2 nouveaux tests unitaires → **101 tests** au total, tous verts

Validé :
- `python -m pytest tests/ -x -q` → 101 passed
- `analyze_session` sur le transcript réel du cron `forge-chantier-trajectory-monitor` → 26 runs analysés, `workspace_check` actif

## [x] P9 — Trend analysis entre runs successifs ✅ (2026-04-09)
**Objectif** : Détecter si un job s'améliore ou régresse entre deux fenêtres de runs, au lieu de ne regarder que l'état courant.

Implémenté :
- `scorer.py` : analyse de tendance basée sur les deux dernières fenêtres de runs (score delta, error-rate delta, dérive durée/tokens)
- `report.py` : trend overview + colonne `Trend` dans les rapports terminal/JSON
- `mcp_server.py` : `check_job`, `get_score`, `get_recommendations` et `analyze_session` exposent maintenant la tendance
- `tools/analyze_openclaw.py` : rapport forge enrichi avec jobs regressing/improving
- 6 nouveaux tests unitaires/MCP → **107 tests** au total, tous verts

Validé :
- `python -m pytest tests/ -x -q` → 107 passed
- `python -m trajectory_monitor analyze /home/orion/.openclaw/cron/jobs.json --json` → trend counts OK sur 47 jobs
- `python3 tools/analyze_openclaw.py` → rapport forge avec colonne Trend

### Next
- V2 backlog: transcripts plus riches que les seuls événements `finished`, MCP live mode, trend alerts exploitables directement comme signal


## [x] P10 — Regression-trend as Signal ✅ (2026-04-09)
**Objectif** : Transformer les tendances de régression en Signaux à part entière avec recommandations.

Implémenté :
- `signals.py` : nouveau détecteur `detect_regression_trend`
  - Lazy import depuis scorer.py pour éviter les imports circulaires
  - Détecte les jobs en régression (direction == "regressing")
  - Severity WARNING si score_delta > -20, CRITICAL si <= -20
  - Détails : score_delta, previous/recent scores, error_rate_delta, duration/token changes
- `recommendations.py` : règles de recommandation pour regression_trend (critical + warning)
- Ajouté au registry DETECTORS (9 détecteurs au total)
- 6 nouveaux tests unitaires (113 total, tous verts)

Validé sur données réelles : 7 nouveaux signaux regression_trend détectés sur les 47 jobs OpenClaw.
Exemples : forge-chantier-cron-ui (error rate +33%), orphan:2a20474b (score 17→0, duration +68%), orphan:87d94c48 (duration +343%).

### Next
- V2 backlog: MCP live mode, richer JSONL transcript parsing (tool-call level), weighted scoring per signal type

## [x] P11 — Weighted scoring per signal type ✅ (2026-04-10)
**Objectif** : Rendre le score qualité plus fidèle au risque réel, au lieu de pénaliser tous les signaux presque pareil.

Implémenté :
- `scorer.py` : pénalités pondérées par **sévérité + type de signal**
  - plus lourdes pour `consecutive_errors`, `crash_repeat`, `hallucination_pattern`, `regression_trend`, `feature_race`
  - plus légères pour `duration_spike`, `token_bloat`, `stagnation`
- `QualityScore` expose maintenant `signal_penalties` par type
- `mcp_server.py` et `report.py` exposent aussi `signal_penalties` en JSON/MCP
- 1 nouveau test + 1 assertion MCP renforcée → **114 tests** au total

Validé :
- `python -m pytest tests/ -x -q` → 114 passed
- `python -m trajectory_monitor analyze /home/orion/.openclaw/cron/jobs.json --json` → rapport OK avec `signal_penalties`

### Next
- V2 backlog: parsing JSONL plus riche que les seuls événements `finished`, MCP live mode, alert thresholds/action policies basés sur les signaux pondérés

## [x] P12 — Alert thresholds + action policies ✅ (2026-04-10)
**Objectif** : Transformer score + signaux + tendance en décisions directement exploitables par les agents (`normal`, `watch`, `stabilize`, `bugfix_only`).

Implémenté :
- `scorer.py` : nouveau dérivé `ActionPolicy` avec règles basées sur `signal_penalties`, tendances et signaux critiques
- `report.py` : `policy_counts` dans le JSON et politique visible dans les jobs à surveiller
- `mcp_server.py` : `check_job`, `get_score`, `get_recommendations` et `analyze_session` exposent maintenant `action_policy`
- 4 nouveaux tests ciblés → couverture des modes `bugfix_only` + JSON/MCP

Validé :
- les jobs en crash répété passent automatiquement en `bugfix_only`
- les sorties JSON/MCP donnent maintenant un feu vert / orange / rouge exploitable sans re-coder la logique côté agent

### Next
- V2 backlog: parsing JSONL plus riche que les seuls événements `finished`, MCP live mode, action policies branchées sur de vrais seuils d’alerte externes


## [x] P13 — Markdown transcript support for analyze_session ✅ (2026-04-10)
**Objectif** : Rendre l’auto-inspection MCP utile même quand l’agent ne fournit pas du JSONL OpenClaw brut, mais un transcript markdown/action-result plus humain.

Implémenté :
- `parser.py` : parsing auto-détecté `JSONL -> markdown/text` via `parse_transcript_text()` et `parse_transcript_file()`
- Heuristique markdown légère : chaque ligne d’action/résultat devient un pseudo-run exploitable par les détecteurs existants
- `mcp_server.py` : `analyze_session` accepte maintenant aussi les fichiers `.md`/`.txt` et le texte markdown brut
- README mise à jour avec formats d’entrée supportés
- 2 tests MCP supplémentaires ciblant markdown text/file + catalogue signaux renforcé

Validé :
- `python -m pytest tests/ -x -q` → 120 passed
- `analyze_session()` détecte `feature_race` sur transcript markdown et `crash_repeat` sur fichier `.md`

### Next
- V2 backlog: MCP live mode, parsing tool-call level encore plus riche, ou branchement des policies sur de vrais seuils d’alerte externes
