# cleanup_sim

2D-симулятор для исследования вероятностного картирования плавающего мусора и адаптивного планирования маршрута автономного надводного робота.

## Назначение

Симулятор проверяет уровень принятия решений экологической миссии:

```text
шумные camera/radar наблюдения
    -> вероятностная карта загрязнений
    -> active exploration / target routing / hybrid switching
    -> сбор мусора и метрики миссии
```

Навигация, SLAM, NMHE, NMPC и реальная CV-детекция считаются внешними слоями и не являются вкладом этой версии.

## Одиночный запуск

```powershell
python -m cleanup_sim.run_once --scenario clustered_base --mode hybrid --seed 11
```

## Быстрая серия для проверки разработки

```powershell
python -m cleanup_sim.run_experiments `
  --seeds 1 `
  --scenarios clustered_base `
  --modes active detected_tsp hybrid `
  --out-dir out/cleanup_sim/smoke_hybrid_fast `
  --tmax-s 900 `
  --max-path-m 1800 `
  --plot-examples
```

## Полная серия для статьи

```powershell
python -m cleanup_sim.run_experiments `
  --seeds 30 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --modes lawnmower_sparse lawnmower_dense greedy active_entropy active_probability active_no_distance active detected_tsp hybrid `
  --out-dir out/cleanup_sim/hybrid_experiments `
  --plot-examples
```

Важно: эту серию пока не запускать как финальную. После аудита 2026-07-31 требуется сначала исправить baseline-ы и метрики; см. `docs/article/stage2/stage2_repair_and_final_experiment_plan.md`.

## Стратегии

- `lawnmower_sparse`: разреженное serpentine-покрытие с шагом `22 м`.
- `lawnmower_dense`: плотное serpentine-покрытие с шагом `10 м`, согласованным с `collect_radius_m = 5 м`.
- `lawnmower`: legacy alias для старых запусков.
- `greedy`: движение к максимуму текущей карты вероятностей.
- `active_entropy`: абляция, использует энтропию карты и штраф расстояния.
- `active_probability`: абляция, использует вероятность мусора и штраф расстояния.
- `active_no_distance`: абляция полного active score без штрафа расстояния.
- `active`: heuristic uncertainty-aware score: current entropy + candidate/probability exploitation + local collect value + distance penalty.
- `detected_tsp`: маршрут по подтвержденным детекциям без доступа к истинной карте.
- `hybrid`: переключение между active exploration и routing по подтвержденным целям.

## Подтвержденные цели

Положительные наблюдения camera/radar попадают в `TargetQueue`.

Цель считается подтвержденной, если:

- confidence >= `detected_confirm_prob`;
- число попаданий >= `target_confirm_hits`;
- близкие наблюдения объединяются по `detected_nms_radius_m`;
- `source_index` из симулятора не используется для планирования и остается только в логах.

## Hybrid rule

`hybrid` выбирает routing, если:

```text
confirmed_target_count >= hybrid_min_confirmed_targets
mean_entropy <= hybrid_explore_entropy_threshold
```

Иначе выполняется active exploration.

FOV-слагаемые active score нормируются по площади ячейки относительно `active_reference_cell_area_m2 = 4.0`, что соответствует базовой сетке `100 x 100` в акватории `200 x 200 м`.

Текущий `active` не является expected information gain planner: он использует текущую энтропию и вероятность в FOV, но не моделирует распределение будущих наблюдений и ожидаемый posterior.

Candidate-v2 для дальнейшей проверки:

```text
hybrid_final_v1:
  hybrid_explore_entropy_threshold = 0.24
```

Базовый `PlannerConfig` пока не изменен, чтобы не смешивать baseline и final-arm настройку. Для confirmatory/final-run использовать `python -m cleanup_sim.run_confirmatory`, где `hybrid_final_v1` сохранен как отдельная именованная ветка.

## Выходные файлы

- `summary.csv`: все прогоны.
- `aggregate_mean_std.csv`: среднее и стандартное отклонение по сценариям/стратегиям.
- `paired_comparisons.csv`: парные сравнения `hybrid` с baseline-ами по одинаковым seed.
- `runs/*_series.csv`: динамика сбора по времени и пути.
- `figures/*.png`: карты, траектории, средние кривые и bar charts.

## Sensitivity

Физическая OFAT-серия вокруг `hybrid_final_v1`:

```powershell
python -m cleanup_sim.run_sensitivity `
  --seeds 5 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --components robot `
  --out-dir out/cleanup_sim/physical_sensitivity_prefinal `
  --max-path-m 3000 `
  --tmax-s 6000
```

## Ключевые метрики

- доля собранного мусора;
- путь и время до 50%, 80%, 95% сбора;
- AUC кривой `collected_ratio vs path`;
- доля сбора на 2, 4, 6, 8, 10, 12 км;
- reach-rate для `path_to_50/80/95` и `time_to_50/80/95`;
- ложные посещения подтвержденных route-целей;
- число подтвержденных целей;
- число попыток route-визита;
- успешные и ложные route-визиты;
- target precision;
- `initial_map_f1`, `initial_map_iou`, `initial_brier_score`: качество карты относительно исходного загрязнения.
- `residual_map_f1`, `residual_map_iou`, `residual_brier_score`: качество карты относительно остаточного загрязнения после сбора.
- `map_f1`, `map_iou`, `brier_score`: legacy alias к residual-метрикам.
- итоговая энтропия карты.
- paired sign-flip permutation p-value, Holm correction, `cohen_dz`, `rank_biserial`.

`false_visits` считается как `target_visit_false`: это не любой arrival без сбора, а только визит к подтвержденной цели в режиме маршрутизации, после которого мусор не был собран.

## Проверка

```powershell
python -m pytest tests -q
```
