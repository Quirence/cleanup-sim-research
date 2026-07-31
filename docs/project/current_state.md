# Текущее состояние проекта

Дата: 2026-07-31

## Рабочая тема

Гибридное вероятностное планирование поиска и сбора плавающего мусора одиночным автономным надводным роботом при шумных и неполных наблюдениях.

## Защитимая научная рамка

Текущая статья не должна заявляться как работа про SLAM, NMHE, NMPC, ROS/Gazebo или реальную CV-детекцию. Эти компоненты остаются внешним навигационным и аппаратным контекстом.

Защитимый вклад:

1. Вероятностная карта загрязнений на occupancy grid.
2. Вероятностная sensor fusion модель camera/radar.
3. Сравнение режимов exploration, routing и hybrid switching.
4. Анализ trade-off между сбором подтвержденных целей и ложными route-визитами.
5. Воспроизводимый 2D-симуляционный протокол.

Пока незащитимые сильные заявления:

- гибридный метод универсально лучше всех baseline;
- реализован полноценный expected information gain;
- реализована реальная компьютерная детекция мусора;
- реализована навигационная SLAM/NMHE/NMPC-система.

## Актуальное состояние кода

Основной модуль:

`cleanup_sim/`

Тесты:

```powershell
python -m pytest -q
```

Текущий результат:

```text
37 passed
```

Ключевые реализованные компоненты:

- генерация clustered/uniform debris field;
- camera/radar probabilistic detections;
- Bayesian update карты вероятностей;
- `TargetQueue` без oracle-доступа к истинной карте;
- стратегии `lawnmower`, `greedy`, `active`, `detected_tsp`, `hybrid`;
- ablation-режимы active score;
- sensitivity runner;
- confirmatory runner;
- path budget `max_path_m`;
- path-normalized AUC по общему бюджету пути;
- повторяющийся `lawnmower` baseline.

## Актуальные результаты

Использовать как текущий pilot:

`out/cleanup_sim/confirmatory_hybrid_v2_pilot_fixed_auc_lawnmower/`

Документ:

`docs/article/results/confirmatory_hybrid_v2_pilot.md`

Состояние уборки рабочей директории:

`docs/project/cleanup_manifest.md`

Краткий вывод:

- `hybrid_candidate_v2` с `hybrid_explore_entropy_threshold=0.24` лучше `hybrid_base=0.18` по AUC во всех трех сценариях pilot-серии.
- Относительно `detected_tsp` эффект сценарно-зависим:
  - в части сценариев hybrid лучше по AUC;
  - по итоговой доле сбора detected_tsp остается очень сильным baseline;
  - нельзя заявлять универсальное превосходство hybrid.
- `active` и `lawnmower` заметно слабее hybrid/target-routing по сбору, но `lawnmower` больше нельзя использовать как искусственно ослабленный baseline.

## Исторические результаты

Результаты до исправления AUC и `lawnmower` нельзя цитировать в статье как актуальные.

Исторически полезны только для понимания эволюции:

- `docs/article/results/ablation_pilot_v1.md`;
- `docs/article/results/sensitivity_ofat_v1.md`;
- `docs/article/results/hybrid_simulator_validation.md`;
- `docs/article/drafts/2026-07-31_code_and_results_audit.md`;
- `docs/article/drafts/2026-07-31_audit_triage_after_current_fixes.md`.

## Блокеры перед финальной серией

1. Сделать честный coverage baseline:
   - либо `coverage_spacing_m <= 10.0`;
   - либо отдельные режимы `lawnmower_sparse` и `lawnmower_dense`.

2. Исправить `greedy` baseline:
   - tabu/memory для недавно посещенных целей;
   - запрет выбора текущей ячейки как цели;
   - корректная обработка собственной ячейки в FOV.

3. Разделить метрики карты:
   - initial occupancy;
   - residual occupancy;
   - не штрафовать корректное снижение belief после сбора.

4. Убрать или использовать `hybrid_switch_prob`.

5. Улучшить статистику:
   - Wilcoxon signed-rank;
   - effect size;
   - явная обработка NaN/censored threshold metrics.

6. Проверить `time_budget` у `hybrid_candidate_v2` в `clustered_base`.

7. Нормировать active score или честно оставить его как эвристику.

## Следующий рабочий шаг

Не запускать финальные 30 seed до ремонта экспериментальной базы.

Следующий этап:

`docs/article/stage2/stage2_repair_and_final_experiment_plan.md`
