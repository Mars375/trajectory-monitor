# PRD — Trajectory Monitor

## Vision
Analyser les trajectoires d'exécution des agents IA pour détecter automatiquement les anomalies (boucles, stagnation, crashes) et scorer la qualité des sessions.

## Architecture

```
trajectory-monitor/
├── src/
│   ├── parser.js          — Parse jobs.json et fichiers de session
│   ├── detector.js         — Détection d'anomalies (boucles, stagnation, crashes)
│   ├── scorer.js           — Scoring de qualité de session
│   ├── reporter.js         — Génération de rapports lisible
│   └── index.js            — CLI entry point
├── tests/
│   ├── parser.test.js
│   ├── detector.test.js
│   ├── scorer.test.js
│   └── reporter.test.js
├── data/                   — Données de production
├── samples/                — Samples pour les tests
└── PRD.md, ROADMAP.md, PRIORITIES.md
```

## Modules

### 1. Parser (`parser.js`)
- Lit et normalise les données de trajectoire (jobs.json, logs de session)
- Extrait les événements séquentiels (tool calls, erreurs, outputs)
- Structure : `{ sessionId, events: [{timestamp, type, tool?, output?, error?}] }`

### 2. Détecteur (`detector.js`)
Types d'anomalies détectées :
1. **Loop** — Même tool/args répété 3+ fois consécutivement
2. **Stagnation** — Pas de progression pendant N événements (même output, pas de nouveaux outils)
3. **Crash** — Session terminée brutalement (erreur non catchée, pas de output final)
4. **Hallucination** — Tool call avec des arguments impossibles/incohérents
5. **Timeout** — Session dépassant un seuil de durée sans résultat

### 3. Scorer (`scorer.js`)
Score de qualité 0-100 basé sur :
- Présence d'anomalies (pénalités)
- Complétion de la tâche (bonus)
- Efficacité tool usage (ratio utile/inutile)
- Durée vs complexité attendue

### 4. Reporter (`reporter.js`)
- Sortie console lisible
- Format JSON structuré
- Résumé par type d'anomalie

## Critères de Succès
- Détecter 3+ types d'anomalies distincts ✅
- Analyser des données jobs.json ✅
- Tous les tests passent ✅
- CLI fonctionnel avec `node src/index.js <input>` ✅

## Stack
- Node.js (ESM)
- Pas de dépendances externes (stdlib only)
- Tests : Node.js built-in test runner (`node:test`)
