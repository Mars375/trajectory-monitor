# PRIORITIES — Trajectory Monitor

## Phase ACTIVE

### P1 — Parser : lecture et normalisation des trajectoires [DONE]
- Lire un jobs.json ou fichier de session
- Normaliser en structure `{ sessionId, events: [...] }`
- Gérer formats d'entrée variés

### P2 — Détecteur : anomalies de base (loop, stagnation, crash) [DONE]
- Loop : même tool/args 3+ fois consécutif
- Stagnation : pas de progression pendant N événements
- Crash : session terminée brutalement

### P3 — Scorer : scoring de qualité 0-100 [DONE]
- Pénalités par anomalie
- Bonus complétion
- Score final agrégé

### P4 — Reporter : sortie lisible [DONE]
- Format console coloré
- Résumé par type d'anomalie
- Score affiché

### P5 — CLI entry point [DONE]
- `node src/index.js <input-file>`
- Pipeline complet : parse → detect → score → report

### P6 — Tests unitaires complets [DONE]
- Parser tests (7 tests)
- Detector tests (17 tests)
- Scorer tests (19 tests)
- Reporter tests (9 tests)
- Integration test avec sample data (5 tests)

### P7 — Détection avancée (hallucination, timeout) [DONE]
- Hallucination : tool call avec arguments impossibles/incohérents
- Timeout : session dépassant un seuil de durée sans résultat

### P8 — Analyse en batch (dossier de jobs.json) [OPEN]
- Accepter un dossier en entrée
- Agréger les résultats multi-sessions
- Statistiques globales

### P9 — Export HTML/Markdown [OPEN]
- Rapport en format Markdown structuré
- Rapport en format HTML avec styles

## Légende
- `[OPEN]` — À faire
- `[DONE]` — Terminé
- `[BLOCKED]` — Bloqué
