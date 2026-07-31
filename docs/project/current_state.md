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
51 passed
```

Ключевые реализованные компоненты:

- генерация clustered/uniform debris field;
- camera/radar probabilistic detections;
- Bayesian update карты вероятностей;
- `TargetQueue` без oracle-доступа к истинной карте;
- стратегии `lawnmower_sparse`, `lawnmower_dense`, legacy `lawnmower`, `greedy`, `active`, `detected_tsp`, `hybrid`;
- ablation-режимы active score;
- sensitivity runner;
- confirmatory runner с замороженным reference-arm `hybrid_final_v1`;
- path budget `max_path_m`;
- path-normalized AUC по общему бюджету пути;
- paired permutation statistics, Holm correction и effect size;
- reach-rate/censored accounting для threshold metrics;
- area-normalized active score terms;
- multisensor target confirmation;
- en-route route-target success accounting;
- OFAT sensitivity around `hybrid_final_v1`;
- physical sensitivity cases for `collect_radius_m`, `bin_capacity_kg`, `speed_mps`;
- физическая интерпретация параметров и границы сенсорной модели: `docs/project/platform_sensor_parameter_notes.md`;
- повторяющийся coverage baseline;
- подавление посещенных greedy-регионов;
- разделенные метрики карты `initial_*` и `residual_*`.

## Актуальные результаты

Финальных результатов статьи пока нет.

Актуальный диагностический smoke после закрытия P0/P1:

`out/audit/p1_prefinal_confirmatory_smoke_5seed/`

Документ:

`docs/article/results/p1_prefinal_confirmatory_smoke_5seed.md`

Этот smoke не является публикационной статистикой, но показывает новую честную картину после ремонта baseline-ов, статистики, target-учета и sensitivity-инструментария:

- `greedy` стал сильным baseline-ом и больше не может считаться “провальным” по старым таблицам;
- `lawnmower_dense` обязателен как честный coverage baseline, `lawnmower_sparse` остается экономичным sparse-coverage вариантом;
- `hybrid_final_v1` заморожен как final-arm с `hybrid_explore_entropy_threshold = 0.24`;
- в 5-seed smoke `hybrid_final_v1` не является универсальным победителем и уступает `greedy`/`lawnmower_dense` в части сценариев;
- старые выводы про превосходство hybrid/active должны быть пересчитаны после pre-final и final-run.

## Исторические результаты

Результаты до исправления AUC и `lawnmower` нельзя цитировать в статье как актуальные.

Исторически полезны только для понимания эволюции:

- `docs/article/results/ablation_pilot_v1.md`;
- `docs/article/results/sensitivity_ofat_v1.md`;
- `docs/article/results/hybrid_simulator_validation.md`;
- `docs/article/drafts/2026-07-31_code_and_results_audit.md`;
- `docs/article/drafts/2026-07-31_audit_triage_after_current_fixes.md`.

## Блокеры перед финальной серией

P0-блокеры аудита закрыты:

- исправлен `greedy`;
- добавлены `lawnmower_sparse` и `lawnmower_dense`;
- разделены initial/residual map metrics;
- active больше не fallback-ится в `greedy`;
- `hybrid_final_v1` заморожен как final-arm;
- старые draft/result документы помечены как исторические;
- мертвый параметр `hybrid_switch_prob` удален.

Остаются блокеры уровня P2/final-run:

1. Согласовать научную интерпретацию pre-final smoke: оставить `hybrid_final_v1` как честный метод для анализа условий применимости или переработать hybrid-правило.

2. Только после этого запускать финальный 30-seed confirmatory-run.

## Следующий рабочий шаг

Не запускать финальные 30 seed до ремонта экспериментальной базы.

Следующий этап:

`docs/article/stage2/stage2_repair_and_final_experiment_plan.md`
