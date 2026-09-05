Story s20-systeme-recompenses — split s20a/s20b validé.
AC couvertes (8/8): 5 pts succès, 7 pts 1er essai, 0 pts échec, 0 pts après 3 échecs + fermé, RewardLedger append-only + UserPoints, badge niveau (Apprenti/Confirmé/Expert) + points dashboard, scénario combiné, mutation AC8 gardée.
Fichiers: 19 (+1310 lignes) — models.py (+2), rewards/ (ledger/levels/init), exercises/router.py, tests (test_ledger, test_levels, test_scenarios, test_aggregator, test_schemas), LevelBadge.tsx, fr/en.json, docs.
Review: docs/reviews/s20-systeme-recompenses.md — initial major (3 findings: loguru, mutation, dashboard assertions) corrigés (886fcae fix); re-review Ship allowed: yes, Max severity: none. progressive.py (s08) intact. Multi-tenant préservé. Design-system non inventé.
Mode merge: manuel (défaut du projet).
