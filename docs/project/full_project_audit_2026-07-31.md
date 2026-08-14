# Полный аудит проекта перед финальным прогоном

> **Историческая заметка (2026-08-13):** документ описывает состояние проекта на legacy `cleanup_sim`, до пивота на `cleanup_sim_v2`. Актуальное состояние — `docs/project/current_state.md`, ревью репозитория — `docs/project/repository_review_2026-08-12.md`. Не использовать как актуальный источник для статьи без сверки с `cleanup_sim_v2`.

Дата: 2026-07-31  
Вердикт: **NOT READY** к финальному 30-seed прогону.

Цель аудита: проверить проект как ВАК-ориентированное симуляционное исследование малого исследовательского USV 1-2 м для задачи гибридного вероятностного планирования поиска и сбора плавающего мусора при шумных и неполных наблюдениях.

## Краткий вывод

Проект уже имеет рабочую модульную архитектуру, тестируемый Python-симулятор, воспроизводимые seed-ы, runners для пилотных и confirmatory-прогонов, а также корректно выбранную научную рамку: не SLAM/NMHE/NMPC, а decision-level planning по вероятностной карте загрязнений.

Но финальный прогон пока запускать нельзя. Основные блокеры относятся не к синтаксису и не к общей архитектуре, а к научной честности сравнения:

- `greedy` остается артефактным baseline-ом и залипает в локальном argmax.
- `lawnmower` использует разреженный шаг покрытия `22 м` при радиусе сбора `5 м`; это делает baseline систематически слабым.
- Метрики качества карты сравнивают финальную belief-map с исходной картой мусора, хотя часть мусора уже собрана.
- Физическая модель сбора сильно оптимистична: мгновенный сбор в радиусе `5 м`, без ширины захвата, времени маневра, пропускной способности механизма, волн, течений и дрейфа мусора.
- Текущий черновик статьи и часть result-документов нельзя использовать как финальные: они относятся к предыдущим поколениям эксперимента или к pilot-данным.

Тесты проходят, но это означает только техническую непротиворечивость текущей реализации, а не готовность результатов к публикационной интерпретации.

## Проверенные артефакты

Локально проверены:

- `cleanup_sim/config.py`, `world.py`, `sensors.py`, `mapping.py`, `targets.py`, `planners.py`, `hybrid.py`, `simulation.py`, `metrics.py`, `statistics.py`, runners.
- `tests/`: 37 unit/regression тестов.
- `docs/project/`, `docs/article/stage1/`, `docs/article/stage2/`, `docs/article/results/`, `docs/article/drafts/`.
- `.gitignore`, tracked files, ignored generated outputs.

Команды проверки:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q
python -m cleanup_sim.run_experiments --seeds 2 --scenarios clustered_base clustered_noisy uniform_base --modes greedy lawnmower active detected_tsp hybrid --out-dir out\audit\baseline_smoke_2seed --max-path-m 3000 --tmax-s 6000
python -m cleanup_sim.run_confirmatory --seeds 2 --scenarios clustered_base clustered_noisy uniform_base --out-dir out\audit\confirmatory_smoke_2seed --max-path-m 3000 --tmax-s 6000
```

Результат тестов:

```text
37 passed
```

## Внешняя реалистичность

Использованные внешние ориентиры:

- [Blue Robotics BlueBoat datasheet](https://bluerobotics.com/wp-content/uploads/2023/03/BLUEBOAT-DATASHEET-v1.1-JAN-2025.pdf): около `3 м/с` максимальной скорости без полезной нагрузки, `15 кг` полезной нагрузки вместе с батареями/ payload.
- [BlueBoat product page](https://bluerobotics.com/store/boat/blueboat/blueboat/): исследовательская USV-платформа около 1.2 м.
- [Clearpath Heron brochure](https://www.generationrobots.com/media/clearpath_heron_USV_Brochure_2019.pdf): `1.7 м/с`, `10 кг` rated payload.
- [RanMarine WasteShark Classic](https://www.ranmarine.io/wastesharkclassic/): робот для очистки поверхности воды, около `3 км/ч`, корзина `160 л`, до `60 кг` веса в корзине.
- [Intel RealSense D435i official specs](https://www.intel.com/content/www/us/en/products/sku/190004/intel-realsense-depth-camera-d435i/specifications.html): depth range около `0.3-3 м`, depth FOV `87 x 58`.
- [TI IWR6843AOPEVM](https://www.ti.com/tool/IWR6843AOPEVM) и [IWR6843AOP](https://www.ti.com/product/IWR6843AOP): компактный 60 GHz mmWave sensor с wide-FOV AoP, point-cloud выходом; конкретная дальность зависит от конфигурации и цели.
- [Roboat II](https://arxiv.org/abs/2007.10220): ASV с LiDAR/IMU/GPS factor-graph SLAM, NMPC и NMHE; навигационный контекст, не прямой аналог задачи сбора мусора.
- [SeaClear project](https://seaclear-project.eu/about-main/about-seaclear): многороботная система для поиска, идентификации и сбора морского мусора, преимущественно подводного.
- [Li et al., 2025](https://researchportal.port.ac.uk/en/publications/an-unmanned-vessel-path-planning-method-for-floating-waste-cleani): floating-waste cleaning как TSP/IACO по patrol/target points.
- [Active Mapping of Underwater Litter Using Camera-Sonar Fusion](https://busoniu.net/files/papers/aqtr26-david.pdf): близкая работа по active mapping подводного мусора, но не по surface-USV сбору в вероятностной карте.

Вывод по параметрам:

| Параметр модели | Текущее значение | Оценка |
|---|---:|---|
| Акватория | `200 x 200 м` | Реалистично для малого порта/полигона. |
| Сетка | `100 x 100`, ячейка `2 м` | Приемлемо, но active-score зависит от разрешения. |
| Скорость | `2 м/с` | Похоже на верхний диапазон BlueBoat; выше типичной скорости WasteShark. Для cleaning-режима нужна sensitivity на `0.8-1.5 м/с`. |
| Мусор | `150` объектов | Нормально как синтетический сценарий; нужно не выдавать за полевую статистику. |
| Bin capacity | `30 кг` | Не подходит для BlueBoat/Heron как research-USV; правдоподобно только для cleaning-specific платформы класса WasteShark. |
| Радиус сбора | `5 м` | Главная физическая абстракция; как реальный механический захват завышен. |
| Sensor period | `10 с` | Может означать частоту mission-level fusion, но не частоту камеры/радара. Нужно явно описать. |
| Camera range/FOV | `28 м`, `70 deg` | Не соответствует RealSense depth range; допустимо только как абстракция RGB-детектора. |
| Radar range/FOV | `45 м`, `130 deg` | Широкий FOV правдоподобен для mmWave AoP; detection floating debris требует оговорки и sensitivity. |

## Код и архитектура

Сильные стороны:

- Архитектура разделена на `config -> world -> mapping -> sensors -> targets -> planners/hybrid -> simulation -> metrics/statistics -> runners`.
- Конфигурации в основном централизованы в `cleanup_sim/config.py`.
- Вероятностная карта реализована как occupancy-grid belief `b_i = P(m_i=1)`.
- Сенсоры обновляют карту через последовательный Bayesian update.
- Есть отдельные режимы `lawnmower`, `greedy`, `active`, `detected_tsp`, `hybrid` и ablation modes.
- Пилотные/confirmatory runners сохраняют `summary.csv`, `aggregate_mean_std.csv`, paired comparisons и series.
- Unit/regression тесты есть и проходят.

### Blocker: `greedy` залипает

Evidence:

- `cleanup_sim/planners.py:81`: `next_greedy` всегда выбирает глобальный максимум belief без памяти, tabu-списка и исключения текущей ячейки.
- Smoke `out/audit/baseline_smoke_2seed`: `greedy` завершился `time_budget` во всех 6 проверенных seed/scenario, проходя только десятки/сотни метров за `6000 с`.
- Средние collected ratio на 2 seed: `0.020` в `clustered_base`, `0.047` в `clustered_noisy`, `0.070` в `uniform_base`.

Impact: сравнение с greedy сейчас доказывает не слабость жадного подхода, а ошибку/незрелость baseline-а. Для ВАК-статьи это критично.

Fix:

- добавить память посещенных/подавленных argmax-целей;
- исключать кандидаты ближе `collect_radius_m` или `arrival_tolerance_m`, если они не дали сбора;
- снижать belief локально после физического посещения;
- добавить regression test, что greedy за smoke-run проходит ненулевую долю path budget и не выбирает одну и ту же цель бесконечно.

Acceptance:

- на `3 scenarios x 5 seeds` greedy не завершается по `time_budget` при path budget;
- путь greedy не меньше 80-90% `max_path_m`, кроме случая `done`;
- нет повторного выбора одной и той же цели без новой информации.

### Blocker: `lawnmower` не является честным dense-coverage baseline

Evidence:

- `cleanup_sim/config.py:87`: `collect_radius_m = 5.0`.
- `cleanup_sim/config.py:97`: `coverage_spacing_m = 22.0`.
- Геометрическая ширина сбора около `10 м`, шаг галса `22 м`; теоретически покрывается около `10 / 22 = 45%` площади.
- Smoke показывает `lawnmower` около `0.49` collected ratio в clustered-сценариях и `0.46` в uniform при path budget `3000 м`.

Impact: если adaptive/hybrid превосходит такой lawnmower, это может быть следствием намеренно слабого шага покрытия, а не алгоритмического преимущества.

Fix:

- добавить `lawnmower_dense` с `coverage_spacing_m <= 2 * collect_radius_m`, лучше `8-10 м`;
- оставить текущий `lawnmower_sparse` только как экономичное покрытие, а не основной baseline;
- в статье сравнивать hybrid минимум с dense-coverage и detected-target-routing.

Acceptance:

- в итоговом `summary.csv` присутствуют `lawnmower_sparse` и `lawnmower_dense`, либо default lawnmower обоснован как dense;
- dense baseline собирает существенно больше sparse при равном path budget;
- текст статьи не называет sparse baseline “полным равномерным покрытием”.

### Major: active fallback к `greedy`

Evidence:

- `cleanup_sim/planners.py:173-178`: active modes вызывают `next_active` только если прошло `replan_interval_s`.
- `cleanup_sim/planners.py:179`: иначе fallback идет в `next_greedy`.

Impact: поведение `active` частично загрязнено багом greedy, особенно если цель достигнута раньше интервала перепланирования. Это может искажать ablation и сравнение active/hybrid.

Fix:

- хранить предыдущую active goal до следующего replan;
- при раннем arrival выбирать ближайший допустимый active candidate или coverage continuation;
- не использовать greedy как технический fallback для active baseline-а.

Acceptance:

- серия active не содержит planner_mode `greedy`, если режим не `greedy`;
- active smoke проходит путь без локального залипания.

### Major: active-score не нормирован

Evidence:

- `cleanup_sim/planners.py:86-130`: `_score_candidate` суммирует entropy, count of candidate cells и probability по FOV.
- Значения зависят от числа ячеек в FOV и, следовательно, от `grid.nx`, `grid.ny`, `range_m`, `fov_deg`.

Impact: коэффициенты `active_alpha`, `active_mu`, `active_lambda` не переносимы между разрешениями карты. Для статьи нельзя заявлять универсальный метод без sensitivity.

Fix:

- нормировать компоненты по числу видимых ячеек или площади FOV;
- либо явно описать score как tuned heuristic для фиксированной сетки и добавить sensitivity по `50x50`, `100x100`, `200x200`.

Acceptance:

- изменение разрешения сетки не меняет качественный вывод, либо ограничение явно включено в статью.

### Moderate: `hybrid_switch_prob` не используется

Evidence:

- `cleanup_sim/config.py:111`: параметр объявлен.
- `cleanup_sim/hybrid.py:13-22`: переключение зависит от `hybrid_min_confirmed_targets` и `hybrid_explore_entropy_threshold`, но не от `hybrid_switch_prob`.

Impact: риск описать в статье несуществующий параметр и создать недоверие к конфигурации.

Fix:

- удалить параметр;
- или переименовать/использовать как порог confidence для route-mode, если нужен.

Acceptance:

- `rg "hybrid_switch_prob"` находит либо 0 вхождений, либо реальное использование в decision rule и тестах.

## Сенсоры и карта

### Сильные стороны

- `visible_mask` учитывает range и FOV.
- `apply_fusion_update` последовательно применяет radar и camera.
- Планировщики не используют `source_index`; он пишется в лог.
- Карта остается в `[0,1]`, Bayesian update покрыт тестами.

### Major: detection position частично строится от true debris

Evidence:

- `cleanup_sim/sensors.py:74-82`: для positive cell ищется ближайший истинный объект; если он достаточно близко, measured position генерируется вокруг истинной позиции, а не центра ячейки.

Impact: это не прямой oracle для planner-а, потому что позиция зашумлена и приходит только при положительном наблюдении. Но это более сильная модель сенсорной локализации, чем “детекция только ячейки”. В статье нужно честно сказать, что сенсорная модель симулирует локализованное object-level observation, а не реальный CV/radar pipeline.

Fix:

- либо оставить как explicit measurement model;
- либо сделать вариант `cell_center_measurement` для sensitivity.

Acceptance:

- в методологии есть формула/описание object-level measurement noise;
- ни один вывод не заявляет реализованную real-time CV/radar detection.

### Major: независимость camera/radar update не проверена

Evidence:

- `cleanup_sim/sensors.py:95-96`: radar и camera применяются последовательно к одной belief-map.

Impact: последовательный Bayes update фактически предполагает условную независимость наблюдений при заданной occupancy. В реальности ошибки camera/radar могут быть коррелированы через поверхность воды, блики, геометрию сцены.

Fix:

- явно описать conditional independence assumption;
- добавить sensitivity по false positive/false negative/noise;
- рассмотреть log-odds clamp или вероятность saturating behavior.

Acceptance:

- статья не говорит “реалистичная sensor fusion”, а говорит “вероятностная модель наблюдений с независимыми источниками”.

### Blocker: map quality сравнивает финальную belief-map с исходным мусором

Evidence:

- `cleanup_sim/simulation.py:68`: `true_occ` вычисляется до сбора.
- `cleanup_sim/sensors.py:51`: собранный мусор исключается из `occ`.
- `cleanup_sim/metrics.py:60-69`: `map_quality` сравнивает финальный belief с `true_occ`.

Impact: эффективный сбор может ухудшать `map_f1`, `IoU`, `Brier`, потому что карта корректно “забывает” собранный мусор, а метрика требует видеть его как присутствующий. Это ломает интерпретацию качества карты.

Fix:

- считать `initial_true_occ`;
- после миссии считать `residual_true_occ`;
- разделить `initial_map_*` и `residual_map_*`;
- возможно добавить object-level detection metrics отдельно от occupancy-grid metrics.

Acceptance:

- summary содержит отдельные initial/residual метрики;
- в result docs объяснено, какая метрика отвечает на какой исследовательский вопрос.

### Moderate: binary occupancy теряет плотность объектов

Evidence:

- `cleanup_sim/world.py:52-57`: `true_occupancy` бинаризует ячейки.

Impact: при нескольких объектах в одной ячейке карта не отражает density/count. Для `150` объектов на `100x100` это умеренно, но при кластеризации коллизии возможны.

Fix:

- добавить count-map/density-map для анализа;
- оставить occupancy как первый уровень, но не утверждать, что карта оценивает количество объектов в ячейке.

Acceptance:

- текст статьи различает `occupancy probability` и `expected debris count`.

## Физическая реализуемость модели USV

### Защитимо

- Малый USV с GPS/IMU/camera/radar и mission-level planner реалистичен.
- Акватория `200 x 200 м` подходит для симуляционного полигона.
- Скорость `2 м/с` допустима для исследовательских платформ типа BlueBoat, но является высокой для cleaning-specific режима.
- Возврат на depot при заполнении контейнера - разумная постановка.

### Major: модель сбора завышает эффективность

Evidence:

- `cleanup_sim/simulation.py:35-52`: `_collect_nearby` мгновенно собирает все объекты в радиусе.
- `cleanup_sim/config.py:87`: `collect_radius_m = 5.0`.
- Нет ограничений на ширину захвата, ориентацию корпуса, скорость при сборе, время захвата, отказ механизма.

Impact: результаты скорее отражают “зачистку диском радиуса 5 м”, чем физический сбор плавающего мусора. Это особенно влияет на fairness `lawnmower` и на путь до threshold-сбора.

Fix:

- для текущей статьи явно назвать `collect_radius_m` effective collection radius;
- добавить sensitivity `collect_radius_m = 1.0 / 2.5 / 5.0`;
- добавить dwell-time или max collection rate;
- в идеале заменить мгновенный диск на forward-facing collection aperture.

Acceptance:

- финальная таблица содержит sensitivity или выбранный radius обоснован;
- статья не изображает радиус 5 м как реальную ширину механического ковша.

### Major: bin capacity конфликтует с выбранным классом платформы

Evidence:

- `cleanup_sim/config.py:88`: `bin_capacity_kg = 30.0`.
- BlueBoat payload около `15 кг` вместе с батареями/payload; Heron rated payload около `10 кг`.
- WasteShark-like cleaning platform имеет существенно большую корзину и меньшую скорость.

Impact: нельзя одновременно описывать платформу как BlueBoat/Heron-like research USV и использовать `30 кг` полезного мусора без изменения водоизмещения/динамики.

Fix:

- выбрать reference class:
  - research-USV: снизить capacity до `5-10 кг`;
  - cleaning-USV: оставить `30 кг`, но скорость ближе `0.8-1.2 м/с` и ссылаться на WasteShark-like механику.
- добавить sensitivity по capacity.

Acceptance:

- в методологии есть таблица параметров с обоснованием по reference platforms;
- capacity/speed не противоречат друг другу.

### Moderate: нет волн, течений, ветра и дрейфа мусора

Evidence:

- `cleanup_sim/world.py`: мусор статичен.
- `cleanup_sim/simulation.py:54-62`: робот движется straight-line kinematics без drift/disturbance.

Impact: статья должна оставаться simulation-baseline для статичного мусора в спокойной акватории; нельзя обобщать на реальный порт без future work.

Fix:

- включить в ограничения;
- добавить future scenario: debris drift + current disturbance + navigation error.

Acceptance:

- раздел ограничений прямо называет static debris и no hydrodynamics.

## Планировщики

| Strategy | Текущее состояние | Научная оценка |
|---|---|---|
| `lawnmower` | Технически ходит по маршруту и после фикса повторяет route | Нужен dense baseline; текущий шаг sparse. |
| `greedy` | Залипает в argmax | Blocker для финального сравнения. |
| `active` | Работает, но score эвристический и fallback загрязнен greedy | Защитимо как heuristic baseline после ремонта fallback. |
| `detected_tsp` | Маршрутизирует по подтвержденным целям без true map | Важный baseline, но target precision низкая. |
| `hybrid` | Переключает exploration/routing по count + entropy | Научно перспективно, но нужно лучше описать как heuristic hybrid, а не optimal policy. |
| `hybrid_candidate_v2` | В 2-seed smoke лучше base по collected ratio | Только pilot; нельзя использовать как финальное доказательство. |

## Smoke-результаты аудита

Короткие 2-seed прогоны не являются статистикой для статьи, но полезны как диагностика.

Baseline smoke, средний collected ratio:

| Scenario | greedy | lawnmower | active | detected_tsp | hybrid |
|---|---:|---:|---:|---:|---:|
| clustered_base | 0.020 | 0.493 | 0.463 | 0.607 | 0.583 |
| clustered_noisy | 0.047 | 0.493 | 0.347 | 0.433 | 0.410 |
| uniform_base | 0.070 | 0.457 | 0.353 | 0.563 | 0.420 |

Confirmatory smoke с `hybrid_candidate_v2`, средний collected ratio:

| Scenario | active | detected_tsp | hybrid_base | hybrid_candidate_v2 | lawnmower |
|---|---:|---:|---:|---:|---:|
| clustered_base | 0.463 | 0.607 | 0.583 | 0.800 | 0.493 |
| clustered_noisy | 0.347 | 0.433 | 0.410 | 0.590 | 0.493 |
| uniform_base | 0.353 | 0.563 | 0.420 | 0.707 | 0.457 |

Важное наблюдение: `hybrid_candidate_v2` выглядит перспективно, но одновременно имеет много false route visits и низкий `target_precision` около `0.09-0.12` в smoke. Это нельзя подавать как устойчивую финальную победу без ремонта target filtering и независимого 30-seed confirmatory run.

## Метрики и статистика

Сильные стороны:

- Есть paired comparison по одинаковым seed.
- Есть bootstrap CI и Holm correction.
- AUC теперь считается относительно path budget, что лучше прежней схемы.
- Threshold metrics (`path_to_50/80/95`) уже есть.

Проблемы:

- `map_f1`, `IoU`, `Brier` сейчас имеют неправильный ground truth для финального состояния.
- `threshold_crossing` возвращает `None`, статистика затем делает `dropna`; для threshold-метрик это скрывает долю стратегий, не достигших порога.
- `normal_approx_p_value` в `cleanup_sim/statistics.py:61-70` использует нормальное приближение; для `n=3/5` это diagnostic-only, для `n=30` желательно добавить Wilcoxon/permutation test и effect size.
- Нет явной reach-rate метрики: сколько seed достигли 50/80/95%.

Требование к финальным таблицам:

- `mean ± std` по каждому scenario/mode.
- Paired mean difference относительно `hybrid_candidate_v2` или заранее выбранного `hybrid`.
- Bootstrap CI.
- Wilcoxon/permutation p-value + Holm.
- Effect size.
- Reach rate для threshold-метрик.
- Отдельные таблицы для mission performance, map quality, target queue quality.

## Соответствие статье и научным заявлениям

Подтверждается текущим проектом:

- 2D-симулятор вероятностного картирования загрязнений.
- Bayesian occupancy update для шумных camera/radar-like наблюдений.
- Несколько baseline-стратегий.
- Гибридное переключение между exploration и routing по подтвержденным целям.
- Возможность воспроизводимых seed-серий.

Подтверждается только как pilot:

- `hybrid_candidate_v2` может улучшать collected ratio/AUC в ряде сценариев.
- suppression false-target regions снижает часть ложных маршрутов.
- Гибридный подход может быть сильнее чистого active и sparse coverage.

Нельзя заявлять:

- реализованный SLAM/NMHE/NMPC;
- реальную компьютерную детекцию мусора;
- физически точную модель очистки;
- доказанную оптимальность планировщика;
- универсальное превосходство hybrid над всеми baseline-ами;
- реалистичную работу радара по малому floating debris без экспериментальной валидации;
- ВАК-уровень результатов до исправления baseline-ов и финального paired 30-seed run.

Научно защитимая формулировка после ремонта:

> Разработан воспроизводимый 2D-симулятор и исследован гибридный эвристический планировщик поиска-сбора плавающего мусора, использующий вероятностную occupancy-map и переключение между информативным обследованием и маршрутизацией по подтвержденным целям. На синтетических сценариях с шумными неполными наблюдениями анализируются условия, при которых гибридный подход снижает путь/время до заданной доли сбора относительно равномерного покрытия, жадного выбора и маршрутизации по обнаруженным целям.

## Экспериментальный дизайн

Сценарии `clustered_base`, `clustered_noisy`, `uniform_base` адекватны как минимальный набор:

- кластерный мусор, базовый шум;
- кластерный мусор, усиленный шум;
- равномерный мусор как контроль.

Но перед финальным прогоном нужно:

- починить `greedy`;
- добавить dense-coverage baseline;
- исправить map-quality ground truth;
- заморозить один final hybrid configuration до 30-seed;
- отделить tuning/pilot seed-ы от final confirmatory seed-ов или явно назвать финальный прогон confirmatory после pre-registration;
- добавить физическую sensitivity-серию хотя бы по `collect_radius_m`, `bin_capacity_kg`, `speed_mps`.

## Воспроизводимость и репозиторий

Текущее состояние:

- Git clean перед аудитом.
- `.gitignore` исключает `out/`, `_delete_later/`, `Материалы/`, кэш Python и IDE.
- Нет трекаемых raw output CSV/PNG.
- `requirements.txt` есть.
- `README.md` и `cleanup_sim/README.md` есть.
- Тесты проходят.

Улучшения:

- добавить `pyproject.toml` или явно зафиксировать Python version;
- добавить GitHub Actions для `pytest`;
- добавить `audit`/`final-run` commands в README;
- сохранять final config snapshot и commit SHA в output directory;
- проверить UTF-8 отображение русских документов в Windows shell/VS Code.

## Итоговый verdict

**NOT READY** к финальному 30-seed прогону.

Проект готов к следующему этапу ремонта экспериментальной базы. После закрытия P0/P1 backlog-а можно запускать сначала 5-seed smoke/confirmatory, затем финальный 30-seed прогон.

Минимальные условия смены verdict на `READY`:

1. `greedy` не залипает и проходит path budget.
2. Есть честный dense coverage baseline.
3. Map quality разделена на initial/residual.
4. `hybrid_switch_prob` удален или реализован.
5. Active modes не используют buggy greedy fallback.
6. Финальная конфигурация hybrid заморожена до запуска.
7. Smoke `3 scenarios x >=5 seeds` показывает отсутствие технических артефактов.
8. Статья помечает старые результаты как obsolete и не использует pilot как финальную статистику.
