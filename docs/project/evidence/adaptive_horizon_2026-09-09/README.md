# Adaptive horizon evidence

Компактные результаты разработочного эксперимента 2026-09-09:

- `summary.csv` — все 80 строк матрицы;
- `paired_effects.csv` — сценарные и seed-блочные эффекты с интервалами;
- `analysis_report.json` — результат заранее заданного правила решения;
- `verification.json` — происхождение, входные хеши и проверка raw-артефактов.

Сырые events/series/config/map/positions и run-manifests занимают около 314 МБ и
остаются в локальных игнорируемых каталогах `out/adaptive_horizon_2026-09-09*`.
Их 480 перечисленных артефактов проверены по SHA-256 до подготовки этой копии.

Интерпретация и ограничения приведены в
`docs/project/adaptive_horizon_experiment_report_2026-09-09.md`.
