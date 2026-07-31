# Confirmatory hybrid v2 pilot

> **Статус на 2026-07-31: исторический pilot, не финальные результаты.**
> Числа из этого файла нельзя цитировать как актуальные после P0-ремонта: `greedy` был исправлен, `lawnmower` разделен на sparse/dense, active fallback очищен от greedy, а map quality разделена на initial/residual. Для новой статьи нужен свежий confirmatory-run с `hybrid_final_v1`.

Дата: 2026-07-31

Цель: проверить candidate-v2 настройку `hybrid` после sensitivity-анализа и после исправления двух методических проблем:

- `auc_collected_by_path` теперь нормируется на общий бюджет пути `max_path_m`, а не на фактически пройденный путь;
- `lawnmower` теперь повторяет coverage-маршрут до исчерпания бюджета, а не простаивает после одного прохода.

## Команда

```powershell
python -m cleanup_sim.run_confirmatory --seeds 3 --scenarios clustered_base clustered_noisy uniform_base --out-dir out\cleanup_sim\confirmatory_hybrid_v2_pilot_fixed_auc_lawnmower --max-path-m 6000 --tmax-s 12000
```

Сравнивались:

- `lawnmower`;
- `active`;
- `detected_tsp`;
- `hybrid_base`: `hybrid_explore_entropy_threshold=0.18`;
- `hybrid_candidate_v2`: `hybrid_explore_entropy_threshold=0.24`.

## Сводные результаты

| scenario | mode | collected_ratio | AUC path | path length, m | false_visits | target_precision | Brier |
|---|---|---:|---:|---:|---:|---:|---:|
| clustered_base | active | 0.716 | 0.462 | 6000.5 | 0.0 | 0.000 | 0.014 |
| clustered_base | detected_tsp | 0.916 | 0.591 | 6000.7 | 96.0 | 0.092 | 0.008 |
| clustered_base | hybrid_base | 0.920 | 0.593 | 6001.0 | 111.3 | 0.100 | 0.008 |
| clustered_base | hybrid_candidate_v2 | 0.922 | 0.678 | 5665.7 | 103.0 | 0.083 | 0.008 |
| clustered_base | lawnmower | 0.522 | 0.407 | 6000.4 | 0.0 | 0.000 | 0.006 |
| clustered_noisy | active | 0.653 | 0.366 | 6001.4 | 0.0 | 0.000 | 0.018 |
| clustered_noisy | detected_tsp | 0.847 | 0.464 | 6001.7 | 65.7 | 0.099 | 0.013 |
| clustered_noisy | hybrid_base | 0.804 | 0.451 | 6001.2 | 81.7 | 0.060 | 0.017 |
| clustered_noisy | hybrid_candidate_v2 | 0.811 | 0.518 | 6000.7 | 76.0 | 0.081 | 0.017 |
| clustered_noisy | lawnmower | 0.522 | 0.407 | 6000.4 | 0.0 | 0.000 | 0.013 |
| uniform_base | active | 0.549 | 0.333 | 6000.6 | 0.0 | 0.000 | 0.013 |
| uniform_base | detected_tsp | 0.878 | 0.535 | 6001.0 | 108.7 | 0.065 | 0.008 |
| uniform_base | hybrid_base | 0.842 | 0.483 | 6000.8 | 122.7 | 0.071 | 0.006 |
| uniform_base | hybrid_candidate_v2 | 0.878 | 0.563 | 6001.1 | 112.7 | 0.083 | 0.007 |
| uniform_base | lawnmower | 0.500 | 0.400 | 6000.8 | 0.0 | 0.000 | 0.006 |

## Интерпретация

1. `hybrid_candidate_v2` стабильно лучше `hybrid_base` по AUC во всех сценариях:
   - `clustered_base`: +0.085;
   - `clustered_noisy`: +0.066;
   - `uniform_base`: +0.081.

2. По итоговой доле сбора candidate-v2 почти равен или немного выше `hybrid_base`, но главный выигрыш именно в эффективности по пути.

3. В `clustered_base` и `uniform_base` candidate-v2 сопоставим с `detected_tsp` по доле сбора, но лучше по AUC. В `clustered_noisy` `detected_tsp` собрал больше мусора в конце, но candidate-v2 имеет более высокий AUC.

4. По сравнению с `active` candidate-v2 резко лучше по сбору и AUC, но платит за это ложными route-визитами. Это не недостаток, который нужно скрывать: это центральный exploration/collection trade-off статьи.

5. `lawnmower` после исправления стал честнее как baseline и расходует около 6000 м, но остается заметно слабее маршрутизации по обнаруженным целям и гибридного подхода.

## Осторожность

Серия использует только 3 seed, поэтому p-value и Holm-коррекция имеют диагностический, а не доказательный смысл. Для статьи нужны 30 seed после заморозки параметров.

В `clustered_base` у `hybrid_candidate_v2` два запуска завершились по `time_budget`, средний путь составил 5665.7 м. Для финального эксперимента нужно:

- увеличить `tmax_s`, например до `20000`;
- проверить, не возникают ли микро-перемещения между близкими route-целями;
- в статье явно использовать path-normalized метрики и доли сбора на фиксированных дистанциях.

## Решение

На следующий этап можно заморозить candidate-v2:

| parameter | value |
|---|---:|
| `target_confirm_hits` | 2 |
| `detected_confirm_prob` | 0.72 |
| `target_false_suppress_radius_m` | 12.0 |
| `hybrid_explore_entropy_threshold` | 0.24 |

Но перед финальным 30-seed запуском нужно технически закрыть вопрос `time_budget` у candidate-v2 в `clustered_base`.

## Артефакты

- `out/cleanup_sim/confirmatory_hybrid_v2_pilot_fixed_auc_lawnmower/summary.csv`;
- `out/cleanup_sim/confirmatory_hybrid_v2_pilot_fixed_auc_lawnmower/aggregate_mean_std.csv`;
- `out/cleanup_sim/confirmatory_hybrid_v2_pilot_fixed_auc_lawnmower/paired_comparisons.csv`;
- `out/cleanup_sim/confirmatory_hybrid_v2_pilot_fixed_auc_lawnmower/experiment_config.json`.
