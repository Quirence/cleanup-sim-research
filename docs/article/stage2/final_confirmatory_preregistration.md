# Preregistration финального confirmatory-прогона

Дата: 2026-07-31

Статус: техническая preregistration перед финальным `30 seed` прогоном. Финальная серия пока не запущена из-за нерешенной научной развилки по интерпретации `hybrid_final_v1`.

## Цель Preregistration

Исключить tuning-on-test:

- зафиксировать arms;
- зафиксировать сценарии;
- зафиксировать seed-ы;
- зафиксировать бюджеты;
- зафиксировать основные метрики;
- зафиксировать правило интерпретации до запуска финальной серии.

## Arms

Финальный confirmatory runner должен использовать `cleanup_sim.confirmatory.build_confirmatory_arms()`:

| Label в таблицах | Internal planner mode | Назначение |
|---|---|---|
| `lawnmower_sparse` | `lawnmower_sparse` | экономичный sparse coverage baseline |
| `lawnmower_dense` | `lawnmower_dense` | честный dense coverage baseline |
| `greedy` | `greedy` | сильный локальный baseline по максимуму текущей вероятности |
| `active` | `active` | heuristic uncertainty-aware active baseline |
| `detected_tsp` | `detected_tsp` | route baseline по подтвержденным целям без доступа к истинной карте |
| `hybrid_base` | `hybrid` | baseline hybrid с `hybrid_explore_entropy_threshold = 0.18` |
| `hybrid_final_v1` | `hybrid` | заранее замороженный reference arm с `hybrid_explore_entropy_threshold = 0.24` |

Запрещено после запуска финальной серии:

- менять `hybrid_final_v1`;
- удалять неудобные baseline-ы;
- подбирать threshold по финальным seed;
- объявлять новый winner-arm без отдельной preregistration.

## Сценарии

Финальные сценарии:

| Scenario | Назначение |
|---|---|
| `clustered_base` | кластерный мусор, базовый шум |
| `clustered_noisy` | кластерный мусор, повышенный шум и ложные наблюдения |
| `uniform_base` | контрольный равномерный сценарий |

## Seed-ы

Финальный набор:

```text
0, 1, 2, ..., 29
```

Seed-ы парные: каждый mode в одном scenario должен запускаться на одном и том же seed, чтобы paired comparisons были осмысленными.

## Бюджеты

Основной confirmatory:

```text
max_path_m = 6000
tmax_s = 12000
```

Путь является главным бюджетом сравнения. `tmax_s` остается safety-limit, а не основной критерий равенства.

Если после запуска появятся `time_budget` вместо `path_budget`, финальный прогон считается проблемным и требует отдельного аудита.

## Основные Метрики

Primary metrics:

- `collected_ratio`;
- `auc_collected_by_path`;
- `path_to_50_m`;
- `path_to_80_m`;
- `target_precision`;
- `target_visit_false`.

Secondary metrics:

- `time_to_50_s`, `time_to_80_s`, `time_to_95_s`;
- `path_to_95_m`;
- `mass_ratio`;
- `initial_map_f1`, `initial_map_iou`, `initial_brier_score`;
- `residual_map_f1`, `residual_map_iou`, `residual_brier_score`;
- `initial_occupancy_collision_ratio`, `residual_occupancy_collision_ratio`;
- `false_visits`, `target_route_attempts`, `target_visit_successes`;
- `collected_ratio_at_2km` ... `collected_ratio_at_12km`.

## Статистика

Обязательные таблицы:

- `summary.csv`;
- `aggregate_mean_std.csv`;
- `paired_comparisons.csv`.

Paired comparison:

- reference mode: `hybrid_final_v1`;
- primary p-value: paired sign-flip permutation `p_permutation`;
- multiplicity correction: Holm `p_holm`;
- effect sizes: `cohen_dz`, `rank_biserial`;
- threshold metrics must report reach-rate and censored pairs.

## Publication Figures

Минимальные фигуры после финального прогона:

- `collected_ratio vs path` по каждому scenario;
- `collected_ratio vs time` по каждому scenario;
- aggregate bar chart по `brier_score` или `residual_brier_score`;
- aggregate bar chart по `false_visits`;
- минимум один example trajectory + final belief map для обсуждения механизма поведения.

## Команда Финального Запуска

Запускать только после выбора научной интерпретации из `prefinal_smoke_interpretation_decision.md`:

```powershell
python -m cleanup_sim.run_confirmatory `
  --seeds 30 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --out-dir out/cleanup_sim/final_30seed_confirmatory `
  --max-path-m 6000 `
  --tmax-s 12000 `
  --save-runs
```

## Команда Физической Sensitivity-Серии

```powershell
python -m cleanup_sim.run_sensitivity `
  --seeds 5 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --components robot `
  --out-dir out/cleanup_sim/final_physical_sensitivity `
  --max-path-m 6000 `
  --tmax-s 12000
```

## Правило Интерпретации

Если `hybrid_final_v1` не превосходит `greedy` или `lawnmower_dense`, это не считается ошибкой эксперимента само по себе.

Тогда статья должна формулироваться как:

> сравнительное исследование условий применимости hybrid switching и trade-off между coverage, greedy exploitation, active exploration и route-to-confirmed-targets.

Недопустимая интерпретация:

> hybrid_final_v1 является универсально лучшим методом.

## Статус

Preregistration закрывает `P2-07`, но не закрывает `P1-08`: финальная серия все еще требует решения пользователя по научному направлению.
