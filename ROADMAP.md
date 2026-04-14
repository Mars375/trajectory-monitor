# ROADMAP — Trajectory Monitor

## Phase 1 : Foundation ✅
- [x] Structure du projet (dossiers, fichiers)
- [x] Parser — lecture et normalisation des trajectoires
- [x] Détecteur — anomalies de base (loop, stagnation, crash)
- [x] Scorer — scoring de qualité 0-100
- [x] Reporter — sortie console lisible
- [x] CLI entry point
- [x] Tests unitaires complets (61 tests, node:test)

## Phase 2 : Robustesse
- [x] Samples de données réalistes pour les tests
- [x] Détection avancée (hallucination, timeout)
- [ ] Benchmarks de performance
- [ ] Intégration continue

## Phase 3 : Production
- [ ] Analyse en batch (dossier de jobs.json)
- [ ] Export HTML/Markdown
- [ ] Seuils configurables
- [ ] Dashboard temps réel
