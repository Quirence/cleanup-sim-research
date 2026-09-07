# Отчет: patch-pass для `belief_horizon`

Дата: 2026-08-03.

Статус после восстановления рабочей версии: архивный отчет по временной экспериментальной ветке. Patch-pass не вошел в текущий рабочий код, потому что smoke-проверка не подтвердила устойчивого прироста относительно базового `belief_horizon` после scout-spacing. Отчет оставлен как отрицательный результат и источник гипотез для будущей реализации.

## Цель изменения

Проверить гипотезу, что `belief_horizon` теряет эффективность потому, что после обнаружения локальной области мусора выбирает отдельную цель, а не физически осмысленный сборочный проход через вероятностное пятно.

Основная метрика проверки: `collected_ratio` при фиксированном бюджете пути `1000 м`.

## Что реализовано

- В основной режим `belief_horizon` добавлена логика `patch-pass`: маршрут `entry -> exit` через локальное вероятностное пятно.
- Старая логика сохранена как абляция `belief_horizon_no_patch_pass`.
- Добавлены параметры:
  - `belief_patch_pass_enabled`;
  - `belief_patch_radius_m`;
  - `belief_patch_min_expected_count`;
  - `belief_patch_half_length_m`;
  - `belief_patch_max_route_m`;
  - `belief_patch_switch_margin`;
  - `belief_patch_orientation_count`;
  - `belief_patch_density_anchors_enabled`;
  - `belief_patch_min_swept_target_count`;
  - `belief_patch_density_expected_cap_per_target`.
- Добавлена очередь details для многоточечного маршрута, чтобы `swept_patch_entry` и `swept_patch_pass` имели разные типы движения и диагностику.
- Для `swept_patch_entry` используется переходная скорость, для `swept_patch_pass` - скорость физического сбора.
- При пустом проходе подавляется не только конечная точка, а swept-corridor.
- В `events.csv` добавлены диагностические поля:
  - `patch_expected_collection`;
  - `patch_density_expected_raw`;
  - `patch_target_expected_collection`;
  - `patch_swept_target_count`;
  - `patch_route_length_m`;
  - `patch_orientation_rad`;
  - `patch_density_mass`;
  - `patch_vs_point_score`;
  - `patch_anchor_kind`;
  - `patch_target_count`.

## Тесты

Команда:

```powershell
python -m pytest -q
```

Результат:

```text
99 passed
```

Добавлены проверки:

- patch-pass не требует истинных координат мусора;
- на синтетическом вытянутом пятне сборочный проход имеет большую ожидаемую полезность, чем точечная цель;
- `choose_goal()` создает маршрут `swept_patch_entry -> swept_patch_pass`;
- route details queue синхронно извлекается вместе с route points;
- скорость движения различается для entry и pass;
- пустой patch-pass подавляет swept corridor.

## Smoke-результаты

Команда:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 5 --scenarios static_calm weak_drift --modes greedy belief_horizon_no_patch_pass belief_horizon --max-path-m 1000 --tmax-s 10000 --out-dir out\cleanup_sim_v2\belief_patch_pass_target_support_smoke_1000m_5seed_2026-08-03 --checkpoint
```

Средние значения по 5 seed-ам:

| scenario | mode | collected_ratio mean | wasted_path_ratio mean | goal_success_rate mean |
|---|---:|---:|---:|---:|
| static_calm | greedy | 0.1360 | 0.7733 | 0.2598 |
| static_calm | belief_horizon_no_patch_pass | 0.1840 | 0.5215 | 0.4097 |
| static_calm | belief_horizon | 0.1840 | 0.5215 | 0.4097 |
| weak_drift | greedy | 0.0853 | 0.8795 | 0.1388 |
| weak_drift | belief_horizon_no_patch_pass | 0.2507 | 0.3888 | 0.3800 |
| weak_drift | belief_horizon | 0.2507 | 0.3888 | 0.3800 |

Итог: строгая версия patch-pass не ухудшает результат, но и не дает прироста на smoke-наборе. Причина: условие нескольких подтвержденных целей в одной узкой swept-полосе почти не возникает.

## Диагностика отрицательного результата

Первичная мягкая версия patch-pass иногда улучшала отдельные seed-ы, но также создавала пустые длинные проходы. Типовой симптом: карта ожидаемой плотности давала высокий `patch_expected_collection`, но реальный `collected_delta` был равен нулю.

Причина не в баге доступа к истинной карте, а в несогласованности уровней:

- `density_map` намеренно размыта из-за неопределенности сенсоров;
- физический сбор выполняется узкой передней полосой шириной порядка `collection_width_m`;
- одна прямая линия через размытую область не гарантирует контакт с реальными объектами;
- старый `belief_horizon_no_patch_pass` уже использует короткие целевые заходы и транзиты через цель, поэтому конкурировать с ним сложнее, чем с простой точечной логикой.

После добавления поддержки несколькими track-целями вредные проходы были отсечены, но вместе с ними исчезла почти вся активность patch-pass.

## Сравнение с соседними режимами

Дополнительная проверка:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 5 --scenarios static_calm weak_drift --modes belief_horizon_no_patch_pass belief_cluster_route belief_orienteering oracle_current_physics --max-path-m 1000 --tmax-s 10000 --out-dir out\cleanup_sim_v2\cluster_orienteering_check_1000m_5seed_2026-08-03 --checkpoint
```

Краткий вывод:

- `belief_cluster_route` и `belief_orienteering` пока уступают `belief_horizon_no_patch_pass`;
- `oracle_current_physics` значительно выше: `0.6173` в `static_calm` и `0.5760` в `weak_drift`;
- значит, резерв качества большой, но текущие route-усложнения не извлекают его.

## Acceptance status

Требования первого успешного улучшения:

- `static_calm`: не ниже старой версии, целевой прирост `+0.02`;
- `weak_drift`: целевой прирост `+0.03`;
- против `greedy`: не менее `8/10` побед;
- `wasted_path_ratio` не должен вырасти более чем на `0.05`.

Статус:

- безопасность относительно старой версии: выполнено на smoke, новая версия равна старой;
- целевой прирост: не выполнено;
- превосходство над `greedy`: выполнено на smoke за счет базовой силы `belief_horizon`, а не за счет patch-pass;
- рост wasted path: не наблюдается, потому что строгий patch-pass почти не включается.

Вердикт: patch-pass как один прямой проход реализован и протестирован, но не является достаточным алгоритмическим улучшением.

## Что делать дальше

Следующий научно более перспективный шаг: не один проход через пятно, а режим локальной эксплуатации обнаруженного кластера.

Рабочая гипотеза:

> После обнаружения устойчивой области мусора робот должен временно переходить из режима глобального поиска в локальный режим сбора, где планируется несколько коротких физических действий с пересчетом карты после каждого действия.

Минимальные требования к следующему алгоритму:

- не использовать истинные координаты мусора;
- выбирать локальную область только по `density_map` и `TargetQueue`;
- пересчитывать полезность после каждого короткого действия;
- явно ограничивать стоимость локальной эксплуатации;
- сравнивать с `belief_horizon_no_patch_pass`, `greedy` и `oracle_current_physics`.

Дополнительный технический долг:

- ускорить single-run: текущие серии стали слишком медленными для быстрой калибровки;
- добавить отдельную диагностику “почему patch-pass не включился”;
- перекалибровать density-map, чтобы expected count не переоценивал физически узкий сбор.
