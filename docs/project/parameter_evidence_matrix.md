# Parameter Evidence Matrix for `cleanup_sim_v2`

Дата: 2026-08-01.

Назначение: зафиксировать параметры новой версии симулятора так, чтобы они не выглядели "подобранными на глаз" и не выдавались за свойства конкретного аппарата без источника. `cleanup_sim_v2` моделирует **cleaning-oriented USV** с вероятностными camera/radar-like наблюдениями и лагранжевым дрейфом мусора. Старые результаты `cleanup_sim` считаются legacy и не должны использоваться в статье без полного перерасчета.

## Источниковая база

| Источник | Что обосновывает | Как используется |
|---|---|---|
| RanMarine WasteShark / WasteShark Classic | сам класс автономного/полуавтономного мусоросборщика, корзина/полезная нагрузка, низкая скорость уборки | базовый образ платформы: cleaning USV, а не исследовательский катамаран |
| Blue Robotics BlueBoat | реалистичность малого USV 1-2 м, скорость/энергетика/полезная нагрузка для исследовательской платформы | нижняя граница платформенного класса; не используется как прямое обоснование большой корзины |
| Clearpath Heron USV | исследовательский USV с полезной нагрузкой и сенсорной интеграцией | контекст робототехнической платформы, не прямая модель мусоросборщика |
| FloW: Floating Waste Detection dataset | camera + mmWave radar как возможная сенсорная пара для floating waste detection | обоснование object-level вероятностной модели, но не готовых чисел точности для нашей сцены |
| OpenDrift / Lagrangian ocean drift literature | лагранжевы частицы, течение, windage, диффузия | базовая форма модели дрейфа без CFD |

## Базовые параметры v2

| Параметр | Nominal | Low / High | Evidence level | Влияние на выводы |
|---|---:|---:|---|---|
| `world.width_m`, `world.height_m` | `200 x 200` | фиксировано | synthetic scenario | влияет на покрытие и бюджет пути; не является реальным портом |
| `world.n_debris` | `150` | sensitivity позже | synthetic density | задает плотность загрязнения, обязательно указывать как сценарный параметр |
| `platform.collection_speed_mps` | `0.6` | `0.45 / 0.8` | cleaning-USV assumption | сильно влияет на time metrics; path metrics устойчивее |
| `platform.cruise_speed_mps` | `1.0` | `0.8 / 1.3` | USV platform range | пока почти не используется, зарезервировано для режимов транзита |
| `platform.collection_width_m` | `1.0` | `0.6 / 1.5` | collection mechanism assumption | главный физический параметр; заменяет некорректный `collect_radius_m=5` |
| `platform.collection_length_m` | `1.8` | future sensitivity | engineering assumption | задает переднюю зону воронки/приемника |
| `platform.capture_probability` | `0.75` | `0.62 / 0.86` | unvalidated mechanism assumption | отражает промахи захвата, требует sensitivity |
| `platform.capture_time_s` | `2.0` | future sensitivity | engineering assumption | делает сбор не мгновенным |
| `platform.collection_throughput_kg_s` | `0.8` | future sensitivity | engineering assumption | ограничивает массовый поток, важно для кластеров |
| `platform.bin_capacity_kg` | `30` | `15 / 60` | cleaning-USV assumption | нельзя описывать как payload BlueBoat без оговорки |
| `hydro.current_*_mps` | `0-0.055` | scenario-based | Lagrangian drift assumption | влияет на расхождение карты и реального мусора |
| `hydro.windage` | `0-0.015` | scenario-based | Lagrangian drift assumption | задает ветровой снос плавающих объектов |
| `hydro.diffusivity_m2_s` | `0-0.05` | scenario-based | stochastic drift assumption | добавляет непредсказуемость, требует seed-paired comparisons |
| `hydro.robot_repulsion_radius_m` | `4.0` | future sensitivity | simplified wake assumption | только stress-scenario, не CFD |
| `camera.range_m` | `25` | `20 / 30` | object-detector abstraction | не depth range RealSense; описывать как RGB detector range |
| `camera.fov_deg` | `70` | fixed | camera abstraction | влияет на exploration vs collection |
| `camera.p_detect_max` | `0.82` | `0.68 / 0.90` | calibrated assumption | не цитировать как реальную precision/recall без CV-эксперимента |
| `camera.clutter_rate_per_m2` | `2.5e-5` | `5e-5 / 1.2e-5` | calibrated assumption | заменяет cell-level false positive |
| `radar.range_m` | `45` | `36 / 55` | mmWave/radar-like abstraction | дальний, но более шумный источник |
| `radar.p_detect_max` | `0.62` | `0.50 / 0.72` | calibrated assumption | должен проверяться sensitivity |
| `radar.clutter_rate_per_m2` | `7.5e-5` | `1.3e-4 / 4e-5` | calibrated assumption | ожидаемо выше camera clutter |
| `planner.coverage_spacing_m` для `lawnmower_survey` | около `14` | зависит от camera profile | camera effective swath assumption | сенсорное обследование, не физическое траление |
| `planner.coverage_spacing_m` для `lawnmower_collect` | `0.8 * collection_width_m` | зависит от platform profile | collection aperture geometry | физически плотный сбор, но очень дорогой по длине маршрута |

## Границы заявлений

- Нельзя писать: "реализована реалистичная гидродинамика". Правильно: "использована упрощенная лагранжева модель дрейфа частиц".
- Нельзя писать: "камера и радар имеют подтвержденную точность для данной платформы". Правильно: "сенсоры моделируются как object-level probabilistic detectors с параметрами, выбранными по диапазонам из литературы и проверяемыми sensitivity".
- Нельзя писать: "робот собирает мусор в радиусе 5 м". В v2 физический сбор происходит только в swept aperture перед корпусом.
- Нельзя использовать таблицы старого `cleanup_sim` как финальные результаты статьи. Они годятся только для истории разработки и мотивации переработки.

## Что обязательно проверить перед финальной статьей

- Sensitivity по `collection_width_m`, `capture_probability`, `collection_speed_mps`.
- Sensitivity по `camera/radar` clutter и `p_detect_max`.
- Сравнение `static_calm` против `weak_drift` и `strong_drift`.
- Проверка, что `empty_goal_arrivals` и `wasted_path_to_empty_goals` считаются для всех стратегий, включая `greedy`.
