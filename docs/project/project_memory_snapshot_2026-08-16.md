# Project Memory Snapshot

Дата: 2026-08-16

Назначение: компактно зафиксировать актуальную карту файлов, конфигурации и
научных границ после merge `dev`, ревью репозитория и pre-final результатов.
Этот файл нужен как быстрый старт для следующей итерации без повторной
археологии по старым отчетам.

## Главный рабочий вектор

Текущая тема:

> планирование миссии поиска и сбора плавающего мусора автономным
> надводным роботом при неполной, шумной и устаревающей информации о целях,
> физически ограниченном сборе и дрейфе объектов.

Вероятностная карта не является всей темой статьи. Это инструмент учета
неопределенности в более широкой задаче планирования миссии.

Уточненный научный вектор:

> режимный анализ планирования миссии: определить, как параметры робота,
> сенсоров, мусорного поля, дрейфа и физического сборщика переводят задачу
> между режимами разведки, вероятностного планирования, короткого маршрутного
> горизонта, маршрутизации по подтвержденным целям и локальной эксплуатации.

Актуальная научная рамка:

- `docs/article/stage1/stage1_reframing_after_prefinal_2026-08-16.md`.
- `docs/project/mission_regime_analysis_direction_2026-08-16.md`.

## Актуальные директории

| Путь | Статус | Назначение |
|---|---|---|
| `cleanup_sim_v2/` | актуально | основной симулятор для дальнейшей статьи |
| `cleanup_sim/` | legacy | старая occupancy-grid/hybrid/MST версия; не использовать для финальных результатов |
| `tests/` | актуально | unit/regression/CLI тесты для legacy и v2 |
| `docs/project/` | актуально + история | состояние проекта, аудиты, отчеты экспериментов, параметры |
| `docs/article/stage1/` | частично исторично | старая постановка + актуальный reframing от 2026-08-16 |
| `docs/article/stage2/` | исторично | pre-v2/pre-final планы; использовать только после сверки с актуальной рамкой |
| `out/cleanup_sim_v2/` | committed experiment evidence | содержит результаты коллеги; не генерировать новые файлы туда без явного решения |

## Модули `cleanup_sim_v2`

| Модуль | Роль |
|---|---|
| `config.py` | dataclass-конфигурация мира, сетки, платформы, гидродинамики, сенсоров, планировщика; `scenario_config()` |
| `world.py` | генерация поля мусора, clustered/uniform распределения, count-map |
| `hydrodynamics.py` | лагранжев дрейф частиц, windage, diffusion, robot repulsion |
| `collection.py` | swept-aperture сбор, накопительный контакт, промах, throughput/bin limits |
| `sensors.py` | object-level camera/radar-like detections, FOV/range, Poisson clutter |
| `mapping.py` | density/count-map, prediction, update, entropy, visible masks, suppression |
| `targets.py` | жизненный цикл целей: подтверждение, старение, suppression, prediction |
| `planners.py` | coverage/greedy/active/belief/route/oracle планировщики |
| `simulation.py` | основной цикл движения, сенсоров, дрейфа, сбора, событий, summary |
| `metrics.py` | map quality, AUC по пути, fixed-distance values, sensor metrics |
| `io.py` | сохранение runs, config hash, git metadata |
| `run_once.py` | одиночный запуск |
| `run_experiments.py` | серии запусков, checkpoint/resume, aggregate summaries |

## Сценарии

Базовые сценарии:

- `static_calm`;
- `weak_drift`;
- `strong_drift`;
- `robot_disturbed`.

Uniform-контроли:

- `uniform_static_calm`;
- `uniform_weak_drift`;
- `uniform_strong_drift`;
- `uniform_robot_disturbed`.

## Режимы планирования

Baseline:

- `coverage`;
- `lawnmower_survey`;
- `lawnmower_collect`;
- `greedy`;
- `active`;
- `confirmed_route`.

Belief-based:

- `belief_horizon`;
- `belief_horizon_provisional`;
- `belief_cluster_route`;
- `belief_orienteering`;
- `belief_orienteering_provisional`.

Mission-level adaptive:

- `adaptive_mission`;
- `adaptive_mission_no_route`;
- `adaptive_mission_no_orienteering`;
- `adaptive_mission_no_local_exploit`;
- `adaptive_mission_no_hysteresis`.

Важно: первичная версия `adaptive_mission` технически интегрирована, но по
trace часто остается на `belief_horizon`. Для статьи ее нельзя подавать как
финальный лучший алгоритм без diagnostic trace, абляций и финального прогона.

Абляции:

- `belief_horizon_no_efficiency`;
- `belief_horizon_no_track_prediction`;
- `belief_horizon_no_refinement`;
- `belief_orienteering_depth1`;
- `belief_orienteering_no_opportunity_cost`;
- `belief_orienteering_density_disabled`.

Oracle:

- `oracle_perfect_static`;
- `oracle_current_physics`;
- `oracle_route_heuristic`.

Важное ограничение: oracle-режимы задают верхние ориентиры при доступе к
истинным положениям мусора. Они не являются математически оптимальным TSP/VRP.

## Nominal-конфигурация

Мир:

- акватория `200 x 200 м`;
- `150` объектов мусора;
- clustered distribution по умолчанию, uniform только для `uniform_*`;
- depot: `(10, 100)`;
- grid: `100 x 100`.

Платформа:

- `cruise_speed_mps = 1.0`;
- `collection_speed_mps = 0.6`;
- `dt_s = 1.0`;
- `physics_substeps = 4`;
- `tmax_s = 5400`;
- `max_path_m = 3600`;
- `arrival_tolerance_m = 1.0`;
- `turn_rate_rad_s = 0.7`;
- `sensor_period_s = 2.0`;
- `collection_width_m = 1.0`;
- `collection_length_m = 1.8`;
- `collection_approach_radius_m = 6.0`;
- `target_dwell_time_s = 4.0`;
- `capture_probability = 0.75`;
- `capture_time_s = 2.0`;
- `collection_throughput_kg_s = 0.8`;
- `bin_capacity_kg = 30`;
- `return_ratio = 0.9`.

Сенсоры:

- camera: range `25 м`, FOV `70 deg`, `p_detect_max = 0.82`,
  localization sigma `0.8 м`, clutter `2.5e-5 / м2`;
- radar: range `45 м`, FOV `120 deg`, `p_detect_max = 0.62`,
  localization sigma `1.8 м`, clutter `7.5e-5 / м2`.

Профили:

- `low`: ниже скорости/ширина/емкость/качество сенсоров, выше clutter;
- `nominal`: базовый сценарий;
- `high`: выше скорости/ширина/емкость/качество сенсоров, ниже clutter.

## Важные реализации после follow-up

- `belief_cluster_route` теперь пишет свои route/transect события как
  `belief_cluster_route`, а не как `belief_horizon`.
- Общая физика belief-целей (`_motion_speed`, dwell, suppression) явно
  поддерживает `belief_cluster_route`, `belief_horizon` и `belief_orienteering`.
- Post-review тест для swept-density поведения `belief_horizon` ожидает
  `density_transect`, что соответствует текущему алгоритму.
- Полный `pytest -q`: `161 passed`.

## Что считать актуальным evidence

Результаты pre-final:

- `out/cleanup_sim_v2/prefinal_10seed_all_scenarios_2026-08-13/summary.csv`;
- `out/cleanup_sim_v2/prefinal_10seed_all_scenarios_2026-08-13/run_manifest.json`;
- commit в manifest: `317f685`, `git_dirty=false`.

Основной вывод по pre-final:

- `belief_horizon` лучше `greedy` во всех четырех сценариях;
- `belief_horizon` лучше `confirmed_route` по итоговой доле сбора в
  `static_calm`, примерно равен в `weak_drift`, хуже в `strong_drift` и
  `robot_disturbed`;
- по AUC относительно пути `belief_horizon` сильнее `confirmed_route` почти
  везде, то есть лучше по ранней/средней эффективности;
- stop reasons смешивают time-budget и path-budget, поэтому нужен отдельный
  path-budget-fair pre-final перед финальными выводами.

Первичная реализация `adaptive_mission`:

- `docs/project/adaptive_mission_initial_report_2026-08-16.md`;
- диагностический 2-seed smoke показывает выигрыш по AUC в 3 из 4 сценариев,
  но выборка мала;
- trace seed 0 показывает, что режим пока почти всегда копирует
  `belief_horizon`, поэтому вклад переключения не доказан.

## Нельзя заявлять

- Реализованный SLAM/NMHE/NMPC.
- Реальную CV/radar-детекцию мусора.
- Полноценную гидродинамику или CFD.
- Универсальное превосходство `belief_horizon`/`belief_orienteering`.
- Математическую оптимальность `oracle_current_physics`.
- Переносимость результатов на реальную акваторию без натурной проверки.
- Старые результаты `cleanup_sim` как финальные результаты статьи.

## Ближайший технический следующий шаг

Перед новым алгоритмом или финальным прогоном:

1. синхронизировать рабочую ветку с `origin/main` и follow-up правками;
2. добавить расчет режимных показателей (`drift_ratio`,
   `capture_uncertainty_ratio`, `clutter_pressure`, `fresh_target_density`,
   `empty_visit_pressure`, `oracle_gap`);
3. провести diagnostic trace и sensitivity по ключевым параметрам;
4. построить regime-map и уточнить правило выбора режима миссии;
5. затем замораживать параметры и запускать 30 seed.
