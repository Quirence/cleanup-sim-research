# Sensitivity OFAT pilot v1

Дата: 2026-07-31

> Важно: после этого pilot-run была исправлена методика расчета `auc_collected_by_path`: AUC теперь нормируется на общий бюджет пути, а не на фактически пройденный путь. Поэтому AUC-числа в этом файле следует считать историческими и не цитировать в статье. Актуальная проверка candidate-v2 приведена в `docs/article/results/confirmatory_hybrid_v2_pilot.md`.

Цель: проверить, насколько вывод о пользе `hybrid`-планировщика зависит от выбранных параметров подтверждения целей и переключения между exploration/routing.

## Дизайн

Использован one-factor-at-a-time дизайн вокруг базового `hybrid`, а не полный перебор всех комбинаций. Это сделано намеренно: на текущем этапе мы проверяем устойчивость алгоритмического эффекта, а не подбираем параметры под лучший результат.

Команда:

```powershell
python -m cleanup_sim.run_sensitivity --seeds 3 --scenarios clustered_base clustered_noisy uniform_base --out-dir out\cleanup_sim\sensitivity_ofat_v1 --max-path-m 6000
```

Проверенные параметры:

| parameter | baseline | tested values |
|---|---:|---|
| `target_confirm_hits` | 2 | 1, 3 |
| `detected_confirm_prob` | 0.72 | 0.65, 0.8 |
| `target_false_suppress_radius_m` | 12.0 | 8.0, 16.0 |
| `hybrid_explore_entropy_threshold` | 0.18 | 0.12, 0.24 |

## Сводные результаты

| scenario | sensitivity_case | collected_ratio | AUC path | false_visits | target_precision |
|---|---|---:|---:|---:|---:|
| clustered_base | baseline | 0.920 | 0.593 | 111.3 | 0.100 |
| clustered_base | detected_confirm_prob=0.65 | 0.938 | 0.600 | 124.7 | 0.099 |
| clustered_base | detected_confirm_prob=0.8 | 0.833 | 0.568 | 85.3 | 0.072 |
| clustered_base | hybrid_explore_entropy_threshold=0.12 | 0.816 | 0.439 | 81.3 | 0.091 |
| clustered_base | hybrid_explore_entropy_threshold=0.24 | 0.922 | 0.663 | 103.0 | 0.083 |
| clustered_base | target_confirm_hits=1 | 0.920 | 0.563 | 180.3 | 0.057 |
| clustered_base | target_confirm_hits=3 | 0.873 | 0.593 | 67.3 | 0.143 |
| clustered_base | target_false_suppress_radius_m=16.0 | 0.860 | 0.562 | 93.3 | 0.095 |
| clustered_base | target_false_suppress_radius_m=8.0 | 0.971 | 0.617 | 136.7 | 0.103 |
| clustered_noisy | baseline | 0.804 | 0.451 | 81.7 | 0.060 |
| clustered_noisy | detected_confirm_prob=0.65 | 0.816 | 0.457 | 94.0 | 0.048 |
| clustered_noisy | detected_confirm_prob=0.8 | 0.787 | 0.455 | 67.3 | 0.046 |
| clustered_noisy | hybrid_explore_entropy_threshold=0.12 | 0.562 | 0.400 | 0.0 | 0.000 |
| clustered_noisy | hybrid_explore_entropy_threshold=0.24 | 0.811 | 0.518 | 76.0 | 0.081 |
| clustered_noisy | target_confirm_hits=1 | 0.798 | 0.448 | 124.3 | 0.045 |
| clustered_noisy | target_confirm_hits=3 | 0.747 | 0.449 | 50.7 | 0.071 |
| clustered_noisy | target_false_suppress_radius_m=16.0 | 0.784 | 0.452 | 70.0 | 0.061 |
| clustered_noisy | target_false_suppress_radius_m=8.0 | 0.847 | 0.452 | 94.0 | 0.061 |
| uniform_base | baseline | 0.842 | 0.483 | 122.7 | 0.071 |
| uniform_base | detected_confirm_prob=0.65 | 0.927 | 0.514 | 139.3 | 0.081 |
| uniform_base | detected_confirm_prob=0.8 | 0.804 | 0.473 | 100.0 | 0.080 |
| uniform_base | hybrid_explore_entropy_threshold=0.12 | 0.762 | 0.371 | 99.3 | 0.071 |
| uniform_base | hybrid_explore_entropy_threshold=0.24 | 0.878 | 0.564 | 112.7 | 0.083 |
| uniform_base | target_confirm_hits=1 | 0.891 | 0.491 | 199.3 | 0.057 |
| uniform_base | target_confirm_hits=3 | 0.836 | 0.479 | 83.3 | 0.067 |
| uniform_base | target_false_suppress_radius_m=16.0 | 0.798 | 0.478 | 103.7 | 0.088 |
| uniform_base | target_false_suppress_radius_m=8.0 | 0.911 | 0.507 | 152.3 | 0.078 |

## Интерпретация

1. Наиболее устойчивым кандидатом выглядит `hybrid_explore_entropy_threshold=0.24`.
   Он увеличил AUC по пути во всех сценариях:
   - `clustered_base`: +0.070 к baseline;
   - `clustered_noisy`: +0.066 к baseline;
   - `uniform_base`: +0.081 к baseline.

2. Уменьшение порога до `0.12` резко ухудшает результат. В `clustered_noisy` ложные route-визиты падают до нуля, но это не улучшение: планировщик фактически недостаточно переходит к сбору подтвержденных целей.

3. `target_confirm_hits=1` делает систему слишком агрессивной: ложные визиты резко растут, а AUC не улучшается. Это важный аргумент против слишком слабого подтверждения целей.

4. `target_confirm_hits=3` снижает ложные визиты, но обычно ухудшает долю сбора. Это показывает ожидаемый компромисс между надежностью подтверждения и скоростью эксплуатации обнаружений.

5. `target_false_suppress_radius_m=8.0` часто повышает итоговую долю сбора, но покупает это ростом ложных визитов. Поэтому этот вариант не следует автоматически принимать как лучший.

6. `detected_confirm_prob=0.65` повышает итоговую долю сбора в части сценариев, но эффект менее устойчив по AUC и сопровождается ростом ложных визитов. Это скорее кандидат для отдельного ablation, чем финальный параметр.

## Методологическое предупреждение

Серия выполнена только на 3 seed. Поэтому результаты нельзя использовать как финальное статистическое доказательство. Их корректная роль:

- выявить грубо неудачные зоны параметров;
- выбрать кандидат-настройку для следующего confirmatory-run;
- зафиксировать, что параметр не будет подбираться после просмотра финальных 30 seed.

В нескольких прогонах наблюдался `time_budget` вместо `path_budget`, хотя средняя длина пути была близка к 6000 м. Для финального эксперимента нужно либо увеличить `tmax_s`, либо явно анализировать только path-normalized метрики. Для статьи основными метриками следует считать `AUC collected_ratio vs path`, `path_to_80_m`, `path_to_95_m` и доли сбора на фиксированных расстояниях.

## Решение для следующего этапа

Не менять все параметры одновременно.

Предлагаемая candidate-v2 настройка:

| parameter | value |
|---|---:|
| `target_confirm_hits` | 2 |
| `detected_confirm_prob` | 0.72 |
| `target_false_suppress_radius_m` | 12.0 |
| `hybrid_explore_entropy_threshold` | 0.24 |

Эту настройку нужно подтвердить отдельной серией против baseline `hybrid=0.18`, `detected_tsp`, `active` и `lawnmower` на большем числе seed. Если преимущество по AUC сохранится, можно заморозить ее перед финальными 30 seed.

## Артефакты

- `out/cleanup_sim/sensitivity_ofat_v1/summary.csv`;
- `out/cleanup_sim/sensitivity_ofat_v1/aggregate_sensitivity.csv`;
- `out/cleanup_sim/sensitivity_ofat_v1/sensitivity_cases.csv`;
- `out/cleanup_sim/sensitivity_ofat_v1/experiment_config.json`.
