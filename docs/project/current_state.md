# Текущее состояние проекта

Дата обновления: 2026-08-16.

## Рабочая тема

Симуляционное исследование планирования миссии поиска и сбора плавающего мусора автономным надводным роботом при неполной, шумной и устаревающей информации о целях.

Текущий научный фокус: **режимный анализ планирования миссии**, а не SLAM/NMHE/NMPC, не реальная CV-детекция и не поиск алгоритма, который всегда превосходит все baseline-ы. Вероятностная карта используется как инструмент учета неопределенности, но центральная задача шире: по параметрам робота, сенсоров, мусорного поля, дрейфа и физического сборщика определить, когда рациональны разведка, вероятностное планирование, короткий маршрутный горизонт, маршрутизация по подтвержденным целям или локальная работа с найденной областью.

Практический выход статьи должен быть методическим: дать разработчику способ проанализировать конкретную акваторию и платформу через режимные показатели (`drift_ratio`, `capture_uncertainty_ratio`, `clutter_pressure`, `fresh_target_density`, `empty_visit_pressure`, `oracle_gap`) и выбрать/построить планировщик миссии под эти условия.

## Основной код

Актуальный симулятор:

```text
cleanup_sim_v2/
```

Legacy-код:

```text
cleanup_sim/
```

Старый симулятор и результаты до v2.1 не использовать как финальные результаты статьи.

## Что реализовано в v2.1

- Object-level camera/radar-like sensor model с Poisson clutter.
- Density/count-map с prediction step по модели дрейфа.
- Лагранжев дрейф мусора: течение, windage, диффузия, опциональное отталкивание от робота.
- Накопительный физический сбор в передней swept-aperture зоне.
- Разделение cruise speed и collection speed.
- Простая цена разворота и физические подшаги.
- Жизненный цикл целей: подтверждение, старение, suppression после пустого визита.
- Baseline-режимы: `lawnmower_survey`, `lawnmower_collect`, `greedy`, `confirmed_route`.
- Belief-режимы: `belief_horizon`, `belief_horizon_provisional`, `belief_cluster_route`, `belief_orienteering` и абляции.
- Oracle-режимы: `oracle_perfect_static`, `oracle_current_physics`, `oracle_route_heuristic`.
- Нормализованные метрики пустых визитов, wasted path/time, capture/contact и sensor-level метрики.
- `summary.csv`, `aggregate_mean_std.csv`, `run_manifest.json`, `config_hash`, `git_commit`, `git_dirty`.

## Текущая проверка

Тесты:

```powershell
python -m pytest -q
```

Актуальный результат после merge `dev` и follow-up к ревью:

```text
161 passed
```

Smoke v2.1:

```text
out/cleanup_sim_v2/v2_1_smoke_3seed_2026-08-01_refresh/
```

Краткий вывод smoke: физика стала строже, простые стратегии собирают мало при бюджете 600 м, а `oracle_current_physics` показывает большой зазор для будущего алгоритма.

## Главные документы

- `docs/project/parameter_evidence_matrix.md` - параметры, источники, ограничения заявлений.
- `docs/project/mission_regime_analysis_direction_2026-08-16.md` - актуальное научное направление: режимный анализ миссии и прикладной смысл статьи.
- `docs/project/simulator_v2_implementation_notes.md` - как запускать и что реализовано.
- `docs/project/simulator_v2_1_closure_report.md` - что закрыто в v2.1 и какие smoke-результаты получены.
- `docs/article/stage1/stage1_reframing_after_prefinal_2026-08-16.md` - актуальная научная постановка после pre-final результатов.
- `docs/project/adaptive_mission_initial_report_2026-08-16.md` - первичная реализация adaptive-переключателя и ограничение: текущая версия часто копирует `belief_horizon`.
- `docs/project/repository_review_2026-08-12.md` и `docs/project/repository_review_followup_2026-08-16.md` - ревью репозитория и статус исправлений.
- `docs/project/project_memory_snapshot_2026-08-16.md` - компактная карта файлов, режимов, сценариев и ключевой конфигурации.
- `docs/project/final_run_readiness_backlog.md` - исторический backlog аудита.

## Что нельзя заявлять в статье

- Что реализованы SLAM, NMHE, NMPC или ROS/Gazebo-эксперимент.
- Что реализована реальная CV/radar-система обнаружения мусора.
- Что дрейф является полноценной гидродинамикой или CFD.
- Что oracle является математически оптимальным маршрутом.
- Что старые таблицы `cleanup_sim` являются актуальными результатами.

## Следующий шаг

Проект готов к следующему циклу работы поверх v2.1, но финальная статья должна опираться на новую широкую постановку из `stage1_reframing_after_prefinal_2026-08-16.md` и уточнение из `mission_regime_analysis_direction_2026-08-16.md`.

Перед финальным `30 seed` прогоном нужно:

1. добавить расчет режимных показателей в summary/events или отдельный analysis-layer;
2. провести diagnostic trace с `--save-runs`, чтобы увидеть фактические переключения режимов миссии;
3. провести sensitivity по дрейфу, clutter, ошибке локализации, ширине сборщика и плотности целей;
4. построить regime-map: при каких значениях показателей рациональны разные классы стратегий;
5. уточнить `adaptive_mission` как проверяемое правило выбора режима, а не декоративное копирование `belief_horizon`;
6. заморозить параметры и выполнить paired-seed финальный прогон против диагностических режимов и `oracle_current_physics`.
