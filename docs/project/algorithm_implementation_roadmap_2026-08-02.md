# Algorithm Implementation Roadmap for `cleanup_sim_v2.1`

Дата: 2026-08-02.

Цель: перевести литературный выбор алгоритмов в инженерный план реализации. Этот документ не заменяет статью; он задает порядок кодовых экспериментов, чтобы не начать с красивого, но плохо проверяемого метода.

## Решение

Основной алгоритм для реализации: `belief_horizon`.

Обязательные baseline перед ним:

1. `graph_mst_v2` - MST/preorder route по подтвержденным целям.
2. `route_2opt_v2` - локальное улучшение route-baseline поверх confirmed targets.
3. `adaptive_lawnmower` - плотность покрытия зависит от density-map.

Не реализовывать первым:

- full POMDP/POMCP;
- DRL planner;
- сложный multi-agent planner;
- CFD-aware planner.

## Этап 1: перенести route-baseline из `dev` в v2.1

Задача: получить сильный baseline для маршрутизации по подтвержденным целям, не претендуя на научную новизну.

Из `dev` переносить идею, но не делать прямой merge:

- `mst_route`;
- invalidation route при появлении новой подтвержденной цели;
- тесты, что MST-route посещает цели один раз и отличается от nearest-neighbor;
- CLI modes: `graph_mst_v2`, возможно `route_2opt_v2`.

Не переносить:

- старые результаты `cleanup_sim`;
- старые выводы про 100% сбор;
- прямую реализацию, если она конфликтует с v2.1 API.

Acceptance:

- `python -m pytest -q` зеленый;
- `graph_mst_v2` запускается в `cleanup_sim_v2.run_once`;
- `graph_mst_v2` не входит в default modes;
- planner не использует `source_index` и истинную карту;
- smoke `3 seeds x 4 scenarios` показывает summary без ошибок.

## Этап 2: реализовать `belief_horizon`

Задача: сделать первый научно интересный планировщик.

Статус на 2026-08-02: реализована базовая одношаговая версия. Она уже подключена к `cleanup_sim_v2`, имеет CLI-режим `belief_horizon`, логирует компоненты score и проходит тесты. Это пока не финальный алгоритм: beam search, явные collection-transects и прогноз виртуального сбора еще не реализованы.

Публичный режим:

```text
--mode belief_horizon
```

Новые параметры `PlannerConfig`:

```text
horizon_depth = 3
rollout_branching = 8
belief_candidate_count = 30
expected_collection_weight = 1.0
information_gain_weight = 0.25
target_confirmation_weight = 0.35
path_cost_weight = 0.01
empty_goal_risk_weight = 0.7
stale_target_risk_weight = 0.3
return_penalty_weight = 0.4
```

Кандидаты:

- confirmed targets из `TargetQueue`;
- локальные пики `DensityMap.expected_count`;
- локальные пики entropy;
- короткие collection-transects через плотные области;
- fallback coverage point;
- depot return action.

Score-компоненты:

- `expected_collection`: интеграл density/count-map вдоль swept-aperture примитива;
- `expected_info_gain`: entropy/FOV gain;
- `target_confirmation_gain`: шанс получить повторное наблюдение;
- `empty_goal_risk`: высокая уверенность карты, но низкая ожидаемая физическая масса по траектории;
- `staleness_risk`: возраст цели/карты и drift speed;
- `path_cost`: путь + разворот + время;
- `capacity_cost`: риск поехать в богатый кластер с почти полным бункером.

Rollout:

- beam search depth `H`;
- на каждом уровне брать top `rollout_branching` кандидатов;
- использовать детерминированную копию belief, без доступа к истинному `DebrisField`;
- после виртуального прохода уменьшать expected count вдоль swept-aperture;
- смещать belief по drift на ожидаемое время перехода.

Логирование:

- `goal_started.reason = belief_horizon`;
- `score_total`;
- `score_expected_collection`;
- `score_information_gain`;
- `score_empty_risk`;
- `score_path_cost`;
- `score_stale_risk`;
- `candidate_type`.

Acceptance:

- `belief_horizon` запускается на всех 4 сценариях;
- нет доступа к `source_index`/истинным позициям;
- deterministic same seed;
- summary содержит decomposition метрик;
- smoke `3 seeds x 4 scenarios x baseline modes` завершается.

Текущий smoke базовой версии:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 3 --scenarios static_calm weak_drift --modes greedy belief_horizon oracle_current_physics --max-path-m 300 --tmax-s 900 --out-dir out/cleanup_sim_v2/belief_horizon_basic_smoke_3seed_2026-08-02
```

| scenario | mode | collected mean | empty goals/km mean | wasted path ratio mean | oracle gap mean |
|---|---:|---:|---:|---:|---:|
| `static_calm` | `belief_horizon` | 0.007 | 3.3 | 0.653 | 0.218 |
| `static_calm` | `greedy` | 0.013 | 32.2 | 0.904 | 0.211 |
| `static_calm` | `oracle_current_physics` | 0.224 | 3.3 | 0.047 | 0.000 |
| `weak_drift` | `belief_horizon` | 0.000 | 3.3 | 0.653 | 0.187 |
| `weak_drift` | `greedy` | 0.029 | 53.3 | 0.878 | 0.158 |
| `weak_drift` | `oracle_current_physics` | 0.187 | 12.2 | 0.079 | 0.000 |

Интерпретация: базовая версия резко снижает число пустых целей относительно `greedy`, но проигрывает по фактическому сбору. Следующий инженерный шаг - добавить реальные collection-transects и хотя бы shallow rollout, иначе алгоритм остается осторожным разведчиком, а не search-and-collection planner.

## Этап 3: pre-final evaluation

Команда-скелет:

```powershell
python -m cleanup_sim_v2.run_experiments `
  --seeds 10 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes lawnmower_survey lawnmower_collect greedy confirmed_route graph_mst_v2 adaptive_lawnmower belief_horizon oracle_current_physics `
  --max-path-m 3600 `
  --tmax-s 9000 `
  --out-dir out/cleanup_sim_v2/belief_horizon_prefinal_10seed
```

Primary metrics:

- `collected_ratio`;
- `auc_collected_by_path`;
- `collected_ratio_at_3km`;
- `oracle_gap_collected_ratio`;
- `empty_goal_arrivals_per_km`;
- `wasted_path_ratio`.

Secondary diagnostics:

- capture/contact metrics;
- sensor-level precision/recall;
- map quality;
- `goal_success_rate`;
- decomposition score statistics.

Decision gate:

- если `belief_horizon` лучше `greedy` хотя бы в части сценариев по paired-seed метрикам, развиваем его;
- если он только равен `greedy`, но снижает пустые визиты/путь, можно писать статью как trade-off analysis;
- если он хуже `greedy` по всем ключевым метрикам, не подгоняем веса вслепую, а переходим к `pareto_horizon` или усиливаем adaptive coverage.

## Этап 4: `adaptive_lawnmower`

Роль: сильный coverage baseline между `lawnmower_survey` и `lawnmower_collect`.

Идея:

- идти галсами, но менять расстояние между проходами;
- плотнее проходить зоны с высокой expected density;
- реже проходить низкоплотные области;
- сохранять простоту и интерпретируемость.

Acceptance:

- не использует истинную карту;
- имеет меньше пути, чем `lawnmower_collect`;
- собирает больше, чем `lawnmower_survey`;
- является честным baseline против `belief_horizon`.

## Этап 5: Pareto / MCTS только после первого цикла

Запускать, если:

- `belief_horizon` слишком чувствителен к весам;
- рецензентская логика требует явно показать trade-off;
- pre-final показывает разные победители по сценариям.

Идея:

- строить Pareto-front по collection/info/risk/path;
- выбирать действие правилом “max collection under risk bound” или “min oracle-gap proxy”;
- не скрывать конфликт целей в одном hand-tuned score.

## Итоговый порядок

1. `graph_mst_v2`.
2. `route_2opt_v2`, если MST недостаточно силен как route baseline.
3. `belief_horizon`.
4. `adaptive_lawnmower`.
5. `10 seed` pre-final.
6. Решение: улучшать `belief_horizon`, переходить к Pareto или менять статью на анализ ограничений.

Главное правило: не тюнить алгоритм по финальным `30 seeds`. После pre-final параметры должны быть заморожены.
