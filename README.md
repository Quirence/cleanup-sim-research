# Cleanup Simulation Research Project

Проект для статьи о вероятностном планировании поиска и сбора плавающего мусора автономным надводным роботом при шумных и неполных наблюдениях.

## Содержимое

- `cleanup_sim_v2/` - актуальный 2D Python-симулятор (density/count-map, лагранжев дрейф, физический swept-aperture сбор, `belief_horizon`/`belief_orienteering` планировщики). Основа текущей работы над статьёй.
- `cleanup_sim/` - legacy-симулятор (occupancy grid, `hybrid`/`graph_mst`/`hybrid_mst`). Не использовать для финальных результатов статьи; сохранён ради воспроизводимости старых экспериментов и как источник идей (MST-маршрутизация уже перенесена в план `cleanup_sim_v2` как baseline-слой).
- `tests/` - regression/unit tests для обоих симуляторов.
- `docs/project/` - актуальное состояние проекта, ревью репозитория, планы исправлений.
- `docs/article/stage1/`, `docs/article/stage2/` - научная постановка и вклад; написаны под архитектуру `cleanup_sim` и пока не пересобраны под `cleanup_sim_v2` (см. `docs/project/repository_review_2026-08-12.md`).
- `docs/article/results/` - Markdown-отчёты по pilot-результатам.

Главный ориентир по текущему состоянию проекта: `docs/project/current_state.md`.

## Проверка

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

Текущее ожидаемое состояние:

```text
123 passed
```

Legacy-вариант через `requirements.txt` оставлен для совместимости:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

## Запуск симулятора

```powershell
python -m cleanup_sim_v2.run_once --scenario weak_drift --mode greedy --seed 0 --out-dir out/cleanup_sim_v2/run_once
python -m cleanup_sim_v2.run_experiments --seeds 3 --modes greedy belief_horizon oracle_current_physics --out-dir out/cleanup_sim_v2/smoke
```

Подробности - в `docs/project/simulator_v2_implementation_notes.md`.

## Важное ограничение

Финальные confirmatory-результаты для статьи ещё не заморожены. `cleanup_sim_v2` готов для разработки алгоритма (`READY FOR ALGORITHM DESIGN`), но не для финального прогона (`NOT READY FOR FINAL CONFIRMATORY RUN`) - подробности в `docs/project/simulator_v2_1_closure_report.md`.

Не использовать старые raw-результаты из `out/` (особенно из `cleanup_sim`, до v2.1) как финальные таблицы статьи.

Подробный маршрут воспроизводимости: `docs/project/reproducibility_notes.md`.
