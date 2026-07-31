# Валидация доработки `cleanup_sim`: hybrid planner

> **Статус на 2026-07-31: историческая валидация, не финальная статистика.**
> Документ полезен как журнал разработки, но его численные выводы устарели после P0-ремонта baseline-ов и метрик. Финальные таблицы статьи должны строиться только из нового pre-final/final output directory.

Дата: 2026-07-11

## Что реализовано

- Добавлен режим `hybrid`: переключение между active exploration и маршрутизацией по подтвержденным целям.
- Добавлены ablation-режимы:
  - `active_entropy`;
  - `active_probability`;
  - `active_no_distance`.
- Добавлен `TargetQueue` для подтвержденных целей:
  - цели формируются только из наблюдений;
  - близкие детекции объединяются;
  - `source_index` не используется для планирования.
- `detected_tsp` переведен на подтвержденные цели из `TargetQueue`.
- Добавлен лимит пути `max_path_m` и поле `stop_reason`.
- Добавлены метрики:
  - AUC `collected_ratio vs path`;
  - доля сбора на 2, 4, 6, 8, 10, 12 км;
  - `stop_reason`;
  - `planner_mode` во временном ряду.
- Уточнена трактовка `false_visits`:
  - теперь это ложные визиты к подтвержденным route-целям;
  - active/greedy arrival без сбора больше не раздувает эту метрику.
- Добавлены target-метрики:
  - `target_confirmed`;
  - `target_route_attempts`;
  - `target_visit_successes`;
  - `target_visit_false`;
  - `target_precision`.
- Добавлены события:
  - `target_confirmed`;
  - `target_routed`;
  - `target_visit_success`;
  - `target_visit_false`.
- Добавлен модуль статистики:
  - парные разности по одинаковым seed;
  - bootstrap confidence interval;
  - Holm correction;
  - `paired_comparisons.csv`.
- Расширены графики:
  - средняя кривая сбора по пути;
  - средняя кривая сбора по времени;
  - Brier score по режимам;
  - false visits по режимам.
- В `run_experiments` добавлены smoke-overrides:
  - `--tmax-s`;
  - `--max-path-m`.

## Проверки

Unit/integration tests:

```powershell
python -m pytest tests -q
```

Результат:

```text
29 passed
```

Smoke experiment:

```powershell
python -m cleanup_sim.run_experiments --seeds 1 --scenarios clustered_base --modes active detected_tsp hybrid --out-dir out/cleanup_sim/smoke_target_metrics --tmax-s 900 --max-path-m 1800 --plot-examples
```

Созданы:

- `out/cleanup_sim/smoke_target_metrics/summary.csv`;
- `out/cleanup_sim/smoke_target_metrics/aggregate_mean_std.csv`;
- `out/cleanup_sim/smoke_target_metrics/paired_comparisons.csv`;
- `out/cleanup_sim/smoke_target_metrics/figures/*`.

## Предварительные smoke-результаты

Для `clustered_base`, `seed=0`, короткий бюджет:

| mode | collected_ratio | false_visits | target_confirmed | target_route_attempts | target_precision |
|---|---:|---:|---:|---:|---:|
| active | 0.207 | 0 | 61 | 0 | 0.000 |
| detected_tsp | 0.507 | 73 | 98 | 82 | 0.110 |
| hybrid | 0.293 | 13 | 104 | 14 | 0.071 |

Эти значения не являются итоговым экспериментом для статьи. Они нужны только для проверки работоспособности пайплайна.

## Ограничения текущей версии

- Hybrid rule пока простой: маршрутизация включается только по порогу числа целей и средней энтропии.
- Expected information gain пока не реализован; active использует текущую энтропию в FOV.
- Полноценный full-run на 30 seed может быть долгим; для разработки следует использовать `--tmax-s` и `--max-path-m`.
- Реальная CV-детекция, SLAM, NMHE, NMPC и ROS/Gazebo не входят в эту версию.

## Следующие шаги

## Pilot v2: 5 seed, suppression, max_path=6000 m

Команда:

```powershell
python -m cleanup_sim.run_experiments --seeds 5 --scenarios clustered_base clustered_noisy uniform_base --modes lawnmower greedy active detected_tsp hybrid --out-dir out/cleanup_sim/pilot_hybrid_v2_suppression --max-path-m 6000 --plot-examples
```

Ключевые средние результаты:

| scenario | mode | collected_ratio | AUC path | false_visits |
|---|---|---:|---:|---:|
| clustered_base | lawnmower | 0.511 | 0.233 | 0.0 |
| clustered_base | active | 0.739 | 0.482 | 0.0 |
| clustered_base | detected_tsp | 0.909 | 0.584 | 95.4 |
| clustered_base | hybrid | 0.924 | 0.612 | 110.8 |
| clustered_noisy | lawnmower | 0.511 | 0.233 | 0.0 |
| clustered_noisy | active | 0.669 | 0.420 | 0.0 |
| clustered_noisy | detected_tsp | 0.777 | 0.356 | 60.2 |
| clustered_noisy | hybrid | 0.824 | 0.482 | 86.6 |
| uniform_base | lawnmower | 0.488 | 0.254 | 0.0 |
| uniform_base | active | 0.541 | 0.322 | 0.0 |
| uniform_base | detected_tsp | 0.891 | 0.542 | 107.8 |
| uniform_base | hybrid | 0.864 | 0.500 | 124.2 |

Предварительная интерпретация:

- `hybrid` лучше `active` и `lawnmower` во всех сценариях по доле сбора и AUC.
- `hybrid` немного превосходит `detected_tsp` в `clustered_base` и `clustered_noisy`.
- В `uniform_base` `detected_tsp` остается сильнее, особенно по AUC.
- `hybrid` чаще выполняет ложные route-визиты, чем `detected_tsp`; это указывает на необходимость отдельной абляции подтверждения целей и правила переключения.
- Результат уже выглядит научно интерпретируемым: гибридный подход полезнее в кластерных и шумных условиях, но не является универсально лучшим.

## Следующие шаги

## Ablation pilot v1

Подробный файл:

`docs/article/results/ablation_pilot_v1.md`

Команда:

```powershell
python -m cleanup_sim.run_experiments --seeds 5 --scenarios clustered_base clustered_noisy uniform_base --modes active_entropy active_probability active_no_distance active hybrid --out-dir out/cleanup_sim/pilot_ablation_v1 --max-path-m 6000 --plot-examples
```

Главный вывод:

> `hybrid` превосходит все active-ablation варианты во всех сценариях по доле сбора и AUC. Это означает, что выигрыш не сводится к одному компоненту active score; основной вклад дает переключение от exploration к target routing.

Кратко:

| scenario | лучший pure-active вариант | collected_ratio | hybrid collected_ratio |
|---|---|---:|---:|
| clustered_base | active_probability | 0.756 | 0.924 |
| clustered_noisy | active_no_distance | 0.680 | 0.824 |
| uniform_base | active_probability | 0.567 | 0.864 |

## Следующие шаги

1. Проверить чувствительность `hybrid` к `target_confirm_hits`, `detected_confirm_prob` и `target_false_suppress_radius_m`.
2. Зафиксировать параметры до финальных 30 seed.
3. После стабилизации запустить 30 seed и обновить таблицы статьи.

## Sensitivity OFAT pilot v1

Подробный файл:

`docs/article/results/sensitivity_ofat_v1.md`

Команда:

```powershell
python -m cleanup_sim.run_sensitivity --seeds 3 --scenarios clustered_base clustered_noisy uniform_base --out-dir out\cleanup_sim\sensitivity_ofat_v1 --max-path-m 6000
```

Главный вывод:

> Наиболее устойчивым кандидатом является увеличение `hybrid_explore_entropy_threshold` с `0.18` до `0.24`: AUC по пути вырос во всех трех сценариях, при этом ложные визиты не увеличились.

Осторожность:

- это только 3 seed, поэтому результат нельзя считать финальным доказательством;
- параметр `0.24` следует зафиксировать как candidate-v2 и проверить отдельным confirmatory-run;
- варианты `target_confirm_hits=1` и `target_false_suppress_radius_m=8.0` могут повышать сбор, но часто увеличивают ложные route-визиты.

Следующий шаг:

1. Запустить confirmatory-run для `hybrid_base`, `hybrid_candidate_v2`, `detected_tsp`, `active`, `lawnmower`.
2. После подтверждения заморозить параметры.
3. Только затем запускать финальные 30 seed.

## Methodology corrections: AUC and lawnmower

Дата: 2026-07-31

В ходе проверки научной строгости обнаружены две проблемы:

- `auc_collected_by_path` нормировался на фактическую длину пути, а не на общий бюджет `max_path_m`;
- `lawnmower` выполнял один coverage-проход и затем простаивал.

Исправлено:

- `summarize_run` принимает `path_budget_m`, а `run_simulation` передает `config.planner.max_path_m`;
- `next_lawnmower` повторяет coverage-маршрут после завершения одного прохода;
- добавлены regression tests.

Проверка:

```powershell
python -m pytest -q
```

Результат:

```text
37 passed
```

Актуальный confirmatory pilot:

`docs/article/results/confirmatory_hybrid_v2_pilot.md`

Главный вывод после исправлений:

> `hybrid_candidate_v2` сохраняет преимущество над `hybrid_base` по AUC во всех трех сценариях и остается сопоставимым с `detected_tsp` по итоговой доле сбора, но требует проверки `time_budget` в `clustered_base` перед финальным 30-seed запуском.
