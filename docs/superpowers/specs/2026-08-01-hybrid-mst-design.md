# Design: MST-routed hybrid planner (`hybrid_mst`)

Дата: 2026-08-01
Ветка: `dev` (продолжение работы над `graph_mst`, не мержится в `main` автоматически)
Статус: экспериментальная проверка, не для статьи

## Контекст и цель

Предыдущий эксперимент (`graph_mst` vs `detected_tsp`) показал: MST-обход
подтверждённых целей стабильно чуть лучше nearest-neighbor (выше AUC, выше
`target_precision`), но ни `graph_mst`, ни `detected_tsp`, ни `hybrid` не
приближаются к `greedy`/`lawnmower_dense`, потому что все три режима
маршрутизации по целям перестают исследовать карту, как только появилась
хотя бы одна подтверждённая цель — `graph_mst`/`detected_tsp` навсегда,
`hybrid` — до следующего пересчёта explore/route переключателя, который
срабатывает только когда текущая пачка целей (`hybrid_target_batch_size`)
полностью пройдена.

Гипотеза: если скрестить exploration-логику `hybrid` (переключатель
explore/route + `active`-скоринг в EXPLORE) с MST-обходом вместо
nearest-neighbor в ROUTE-фазе, результат может быть ближе к `greedy`, чем
любой из существующих route-based режимов — потому что (а) сама
маршрутизация по целям эффективнее (MST), и (б) робот не перестаёт
исследовать карту насовсем.

Как и `graph_mst`, это не претендует на научную новизну для статьи и не
трогает `cleanup_sim/confirmatory.py`/preregistration.

## Алгоритм

Новый режим `hybrid_mst` — точная копия `hybrid` с одной заменой:

1. Переключатель explore/route — **без изменений**, тот же
   `choose_hybrid_mode()` из [cleanup_sim/hybrid.py](../../../cleanup_sim/hybrid.py)
   (тот же порог `hybrid_min_confirmed_targets`,
   `hybrid_explore_entropy_threshold`).
2. EXPLORE-фаза — **без изменений**, тот же `next_active(...)`.
3. ROUTE-фаза — вместо `nearest_neighbor_route(current, confirmed_targets, planner.hybrid_target_batch_size)`
   вызывается `mst_route(current, confirmed_targets, planner.hybrid_target_batch_size)`
   (функция уже реализована и протестирована в рамках `graph_mst`).

## Инкрементальность

Переиспользуется существующий `should_invalidate_graph_route` из
[cleanup_sim/planners.py](../../../cleanup_sim/planners.py). Условие
расширяется с `mode == "graph_mst"` на `mode in {"graph_mst", "hybrid_mst"}`.
Хук в [cleanup_sim/simulation.py](../../../cleanup_sim/simulation.py) не
меняется — он уже вызывает эту функцию по `config.planner.mode` для любого
режима.

Побочный эффект, который стоит явно зафиксировать: когда маршрут
инвалидируется новым подтверждением, следующий вызов `choose_next_goal`
заново проходит **весь** hybrid-переключатель (не только перестраивает
MST) — то есть может решить переключиться обратно в EXPLORE, если энтропия
карты успела вырасти. Это отличает `hybrid_mst` от `graph_mst`, где решение
"ехать по целям" не пересматривается, пока список целей не пуст.

## Не-цели

- Не меняются `hybrid_min_confirmed_targets`, `hybrid_explore_entropy_threshold`,
  `hybrid_target_batch_size` — переиспользуются как есть, новых полей
  `PlannerConfig` не добавляется.
- `cleanup_sim/hybrid.py` не редактируется — используется как есть.
- `cleanup_sim/confirmatory.py` и `docs/article/stage2/` не трогаются.
- `hybrid_mst` не добавляется в `DEFAULT_MODES` — только в CLI `choices`.

## Изменяемые файлы

- **cleanup_sim/config.py** — `"hybrid_mst"` в `Literal` `PlannerMode`.
- **cleanup_sim/planners.py**:
  - новая ветка в `choose_next_goal` для `mode == "hybrid_mst"` (копия ветки
    `hybrid`, `mst_route` вместо `nearest_neighbor_route`);
  - `should_invalidate_graph_route`: условие `mode == "graph_mst"` →
    `mode in {"graph_mst", "hybrid_mst"}`.
- **cleanup_sim/run_experiments.py** / **cleanup_sim/run_once.py** —
  `"hybrid_mst"` в CLI `choices` (не в `DEFAULT_MODES`).
- **tests/test_graph_mst.py** — новые тесты: dispatch-ветка `hybrid_mst`
  (ROUTE через MST при выполнении условия переключателя, EXPLORE иначе),
  `should_invalidate_graph_route` покрывает `hybrid_mst`, CLI принимает
  `hybrid_mst`, интеграционный smoke-тест полного прогона.

## Обязательное условие приёмки: сравнение с прошлым прогоном

После реализации **обязательно** запустить `run_experiments` с тем же
набором seed/сценариев, что и в прошлый раз, добавив `hybrid_mst` к списку
режимов, и сравнить результат с уже полученными числами
(`out/cleanup_sim/graph_mst_probe/`):

```powershell
python -m cleanup_sim.run_experiments `
  --seeds 5 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --modes greedy lawnmower_dense detected_tsp hybrid graph_mst hybrid_mst `
  --out-dir out/cleanup_sim/hybrid_mst_probe `
  --plot-examples
```

Так как это те же seed/сценарии/бюджеты, что и в прошлом прогоне, результаты
по `greedy`/`lawnmower_dense`/`detected_tsp`/`hybrid`/`graph_mst`
детерминированно воспроизведутся (симуляция полностью seed-детерминирована,
см. `test_reproducible_same_seed`) — новый прогон можно напрямую сравнивать
с `out/cleanup_sim/graph_mst_probe/aggregate_mean_std.csv` построчно.

Явная проверка гипотезы: приближается ли `hybrid_mst` по `collected_ratio`/
`path_length_m` к `greedy`/`lawnmower_dense` заметнее, чем `hybrid` и
`graph_mst` по отдельности, или нет.
