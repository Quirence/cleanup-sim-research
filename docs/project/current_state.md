# Текущее состояние проекта

Дата обновления: 2026-08-01.

## Рабочая тема

Симуляционное исследование планирования поиска и сбора плавающего мусора автономным надводным роботом при шумных и неполных наблюдениях.

Текущий научный фокус: не SLAM/NMHE/NMPC и не реальная CV-детекция, а честная постановка задачи `search-and-collection` с вероятностными наблюдениями, физически ограниченным сбором и сравнением стратегий относительно baseline и oracle-ориентиров.

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
- Oracle-режимы: `oracle_perfect_static`, `oracle_current_physics`, `oracle_route_heuristic`.
- Нормализованные метрики пустых визитов, wasted path/time, capture/contact и sensor-level метрики.
- `summary.csv`, `aggregate_mean_std.csv`, `run_manifest.json`, `config_hash`, `git_commit`, `git_dirty`.

## Текущая проверка

Тесты:

```powershell
python -m pytest -q
```

Актуальный результат после v2.1:

```text
68 passed
```

Smoke v2.1:

```text
out/cleanup_sim_v2/v2_1_smoke_3seed_2026-08-01_refresh/
```

Краткий вывод smoke: физика стала строже, простые стратегии собирают мало при бюджете 600 м, а `oracle_current_physics` показывает большой зазор для будущего алгоритма.

## Главные документы

- `docs/project/parameter_evidence_matrix.md` - параметры, источники, ограничения заявлений.
- `docs/project/simulator_v2_implementation_notes.md` - как запускать и что реализовано.
- `docs/project/simulator_v2_1_closure_report.md` - что закрыто в v2.1 и какие smoke-результаты получены.
- `docs/project/final_run_readiness_backlog.md` - исторический backlog аудита.

## Что нельзя заявлять в статье

- Что реализованы SLAM, NMHE, NMPC или ROS/Gazebo-эксперимент.
- Что реализована реальная CV/radar-система обнаружения мусора.
- Что дрейф является полноценной гидродинамикой или CFD.
- Что oracle является математически оптимальным маршрутом.
- Что старые таблицы `cleanup_sim` являются актуальными результатами.

## Следующий шаг

Проект готов к разработке нового алгоритма планирования поверх v2.1.

Перед финальным `30 seed` прогоном нужно:

1. разработать кандидатный алгоритм;
2. провести sensitivity по сенсорам и сборщику;
3. заморозить параметры;
4. выполнить paired-seed сравнение против `greedy`, `confirmed_route`, `lawnmower_collect` и `oracle_current_physics`.
