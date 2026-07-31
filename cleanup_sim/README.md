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
  --modes lawnmower greedy active_entropy active_probability active_no_distance active detected_tsp hybrid `
  --out-dir out/cleanup_sim/hybrid_experiments `
  --plot-examples
```

Важно: эту серию пока не запускать как финальную. После аудита 2026-07-31 требуется сначала исправить baseline-ы и метрики; см. `docs/article/stage2/stage2_repair_and_final_experiment_plan.md`.

## Стратегии

- `lawnmower`: равномерное serpentine-покрытие.
- `greedy`: движение к максимуму текущей карты вероятностей.
- `active_entropy`: абляция, использует энтропию карты и штраф расстояния.
- `active_probability`: абляция, использует вероятность мусора и штраф расстояния.
- `active_no_distance`: абляция полного active score без штрафа расстояния.
- `active`: entropy + candidate/probability exploitation + local collect value + distance penalty.
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

Candidate-v2 для дальнейшей проверки:

```text
hybrid_explore_entropy_threshold = 0.24
```

Базовый `PlannerConfig` пока не изменен, чтобы не смешивать baseline и candidate-настройку.

## Выходные файлы

- `summary.csv`: все прогоны.
- `aggregate_mean_std.csv`: среднее и стандартное отклонение по сценариям/стратегиям.
- `paired_comparisons.csv`: парные сравнения `hybrid` с baseline-ами по одинаковым seed.
- `runs/*_series.csv`: динамика сбора по времени и пути.
- `figures/*.png`: карты, траектории, средние кривые и bar charts.

## Ключевые метрики

- доля собранного мусора;
- путь и время до 50%, 80%, 95% сбора;
- AUC кривой `collected_ratio vs path`;
- доля сбора на 2, 4, 6, 8, 10, 12 км;
- ложные посещения подтвержденных route-целей;
- число подтвержденных целей;
- число попыток route-визита;
- успешные и ложные route-визиты;
- target precision;
- Brier score, F1, IoU и итоговая энтропия карты.

`false_visits` считается как `target_visit_false`: это не любой arrival без сбора, а только визит к подтвержденной цели в режиме маршрутизации, после которого мусор не был собран.

## Проверка

```powershell
python -m pytest tests -q
```
