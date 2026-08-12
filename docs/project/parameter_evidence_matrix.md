# Parameter Evidence Matrix for `cleanup_sim_v2`

Дата обновления: 2026-08-01.

Назначение: зафиксировать параметры симулятора так, чтобы они не выглядели подобранными “на глаз” и не выдавались за характеристики конкретного промышленного аппарата. `cleanup_sim_v2` моделирует абстрактный cleaning-oriented USV с вероятностными camera/radar-like наблюдениями, лагранжевым дрейфом частиц и физически ограниченным передним сборщиком.

Старые результаты `cleanup_sim` и ранние результаты `cleanup_sim_v2` до версии v2.1 считаются legacy. Их нельзя использовать как финальные результаты статьи без полного перерасчета.

## Источниковая база

| Источник | Что обосновывает | Как используется |
|---|---|---|
| [RanMarine WasteShark](https://www.ranmarine.io/wasteshark/) | класс автономного/полуавтономного мусоросборщика, наличие корзины/накопителя, низкоскоростной режим очистки | задает инженерный образ cleaning-oriented USV; не используется как точная копия платформы |
| [Blue Robotics BlueBoat](https://bluerobotics.com/store/boat/blueboat/blueboat/) | масштаб малого USV, ограничения скорости, полезной нагрузки и энергетики | нижняя граница платформенного класса; не обосновывает большую корзину без оговорок |
| [Clearpath Heron USV](https://clearpathrobotics.com/heron-unmanned-surface-vessel/) | исследовательская USV-платформа с сенсорной интеграцией и полезной нагрузкой | робототехнический контекст, но не прямая модель мусоросборщика |
| [FloW: A Dataset and Benchmark for Floating Waste Detection](https://openaccess.thecvf.com/content/ICCV2021/papers/Cheng_FloW_A_Dataset_and_Benchmark_for_Floating_Waste_Detection_in_ICCV_2021_paper.pdf) | camera + mmWave radar как возможная пара сенсоров для floating waste detection | обосновывает object-level вероятностную модель наблюдений; не дает готовой точности для нашей сцены |
| [OpenDrift references](https://opendrift.github.io/references.html) | лагранжевый подход к дрейфу частиц, течение, windage, стохастическая диффузия | форма модели дрейфа без заявления полноценной гидродинамики |

## Базовые параметры v2.1

| Параметр | Nominal | Low / High | Evidence level | Влияние на выводы |
|---|---:|---:|---|---|
| `world.width_m`, `world.height_m` | `200 x 200` | фиксировано | synthetic scenario | задает масштаб задачи; не является моделью конкретного порта |
| `world.n_debris` | `150` | future sensitivity | synthetic density | задает плотность загрязнения; должен описываться как сценарный параметр |
| `platform.cruise_speed_mps` | `1.0` | `0.8 / 1.3` | USV platform range | влияет на время транзита между целями |
| `platform.collection_speed_mps` | `0.6` | `0.45 / 0.8` | cleaning-USV assumption | влияет на время и эффективность физического сбора |
| `platform.physics_substeps` | `4` | future sensitivity | numerical assumption | уменьшает грубость дискретизации движения/дрейфа/сбора |
| `platform.turn_rate_rad_s` | `0.7` | future sensitivity | simplified maneuvering assumption | заменяет мгновенный разворот простой кинематической ценой |
| `platform.collection_width_m` | `1.0` | `0.6 / 1.5` | collection mechanism assumption | главный физический параметр; заменяет некорректный круговой `collect_radius_m=5` |
| `platform.collection_length_m` | `1.8` | future sensitivity | engineering assumption | задает переднюю зону сборщика |
| `platform.collection_approach_radius_m` | `6.0` | future sensitivity | controller abstraction | определяет, когда робот замедляется перед физическим сбором |
| `platform.target_dwell_time_s` | `4.0` | future sensitivity | capture-process assumption | позволяет отличать прибытие к цели от завершенного захвата |
| `platform.capture_probability` | `0.75` | `0.62 / 0.86` | unvalidated mechanism assumption | моделирует промахи механизма; обязательно для sensitivity |
| `platform.capture_time_s` | `2.0` | future sensitivity | engineering assumption | делает сбор накопительным, а не мгновенным |
| `platform.collection_throughput_kg_s` | `0.8` | future sensitivity | engineering assumption | ограничивает массовый поток в кластерах |
| `platform.bin_capacity_kg` | `30` | `15 / 60` | cleaning-USV assumption | нельзя описывать как payload конкретного малого research-USV |
| `hydro.current_*_mps` | `0-0.055` | scenario-based | Lagrangian drift assumption | влияет на рассогласование карты и реального мусора |
| `hydro.windage` | `0-0.015` | scenario-based | Lagrangian drift assumption | задает ветровой снос плавающих объектов |
| `hydro.diffusivity_m2_s` | `0-0.05` | scenario-based | stochastic drift assumption | добавляет непредсказуемость; требует paired-seed comparisons |
| `hydro.robot_repulsion_radius_m` | `4.0` | future sensitivity | simplified wake assumption | только stress-scenario; не CFD |
| `camera.range_m` | `25` | `20 / 30` | object-detector abstraction | не depth range RealSense; это эффективная дальность обнаружения |
| `camera.fov_deg` | `70` | fixed | camera abstraction | влияет на обзор и информационный выигрыш |
| `camera.p_detect_max` | `0.82` | `0.68 / 0.90` | calibrated assumption | нельзя цитировать как реальную precision/recall без CV-эксперимента |
| `camera.clutter_rate_per_m2` | `2.5e-5` | `5e-5 / 1.2e-5` | calibrated assumption | моделирует ложные object-level detections |
| `radar.range_m` | `45` | `36 / 55` | mmWave/radar-like abstraction | дальний, но более шумный источник |
| `radar.p_detect_max` | `0.62` | `0.50 / 0.72` | calibrated assumption | должен проверяться sensitivity |
| `radar.clutter_rate_per_m2` | `7.5e-5` | `1.3e-4 / 4e-5` | calibrated assumption | ожидаемо выше camera clutter |
| `planner.coverage_spacing_m` для `lawnmower_survey` | около `14` | profile-dependent | camera effective swath assumption | сенсорное обследование, не физическое траление |
| `planner.coverage_spacing_m` для `lawnmower_collect` | `0.8 * collection_width_m` | profile-dependent | collection aperture geometry | плотный физический сбор, но очень дорогой по длине маршрута |
| `planner.target_stale_after_s` | `300` | future sensitivity | tracking assumption | не дает старым ложным целям жить бесконечно |
| `planner.target_suppression_radius_m` | `6` | future sensitivity | tracking assumption | подавляет повторные ложные цели после пустого визита |

## Что изменилось в v2.1

- Сбор стал накопительным: объект может попасть в переднюю полосу, получить частичный контакт и быть собран только после достаточной работы захвата.
- Движение разделено на cruise и collection speed; при быстром проходе эффективность захвата ниже.
- Добавлена простая цена разворота через `turn_rate_rad_s`.
- Движение, дрейф и сбор считаются на физических подшагах.
- Цели имеют жизненный цикл: подтверждение, старение и подавление после пустого визита.
- Добавлены oracle-режимы: `oracle_perfect_static`, `oracle_current_physics`, `oracle_route_heuristic`.
- В summary добавлены нормализованные метрики пустых визитов, capture/contact метрики, sensor-level метрики, `config_hash`, `git_commit` и `git_dirty`.

## Границы заявлений

- Нельзя писать: “реализована реалистичная гидродинамика”. Правильно: “использована упрощенная лагранжева модель дрейфа частиц”.
- Нельзя писать: “камера и радар имеют подтвержденную точность для данной платформы”. Правильно: “сенсоры моделируются как object-level probabilistic detectors с параметрами, выбранными по литературному контексту и проверяемыми sensitivity”.
- Нельзя писать: “робот собирает мусор в радиусе 5 м”. В v2.1 физический сбор происходит только в передней swept-aperture зоне.
- Нельзя писать: “oracle является математически оптимальным маршрутом”. Правильно: “oracle-режимы задают верхние ориентиры качества при разных уровнях доступа к истинной информации”.
- Нельзя использовать таблицы старого `cleanup_sim` и pre-v2.1 результатов как финальные научные выводы.

## Обязательные проверки перед финальной статьей

- Sensitivity по `collection_width_m`, `capture_probability`, `collection_speed_mps`, `target_dwell_time_s`.
- Sensitivity по `camera/radar` clutter и `p_detect_max`.
- Сравнение `static_calm`, `weak_drift`, `strong_drift`, `robot_disturbed`.
- Paired-seed сравнение всех будущих алгоритмов с `greedy`, `confirmed_route`, `lawnmower_collect` и `oracle_current_physics`.
- Явное указание oracle-gap: насколько обычный/новый алгоритм далек от верхнего ориентира при той же физике.
