# Логический аудит результатов layer1

Дата: 2026-08-22.

Цель: проверить не только полноту CSV и отсутствие `NaN`, но и логическую корректность интерпретации результатов перед повторным тяжелым прогоном.

## Проверенные данные

Pre-fix calibration:

- `out/cleanup_sim_v2/layer1_budget_calibration_2026-08-21/summary_enriched.csv`;
- `640 / 640` строк;
- бюджеты: `1200`, `2400`, `3600`, `7200`;
- сценарии: `static_calm`, `weak_drift`, `strong_drift`, `robot_disturbed`;
- режимы: `lawnmower_collect`, `greedy`, `confirmed_route`, `belief_horizon`, `belief_orienteering`, `belief_orienteering_depth1`, `adaptive_mission`, `oracle_current_physics`;
- seed: `30-34`.

Post-fix audit smoke:

- `out/cleanup_sim_v2/layer1_postfix_audit_2026-08-22/layer1_budget_calibration_2026-08-21/summary_enriched.csv`;
- `80 / 80` строк;
- бюджеты: `1200`, `7200`;
- режимы: `lawnmower_collect`, `greedy`, `belief_horizon`, `adaptive_mission`, `oracle_current_physics`;
- seed: `30-31`.

## Найденный дефект: отступ `lawnmower_collect`

В pre-fix calibration нулевой сбор наблюдался только у `lawnmower_collect`:

- `strong_drift`, seed `31` и `34` при всех бюджетах;
- `weak_drift`, seed `34` при `1200 м`.

Причина: режим физического сбора наследовал общий `coverage_margin_m = 6 м`. При сильном дрейфе мусор скапливался у восточной границы, а маршрут шел между `x=6` и `x=194`. При `collection_width_m = 1 м` крайняя зона становилась физически недостижимой.

Исправление:

- для `lawnmower_collect` теперь задается `coverage_margin_m = 0.5 * collection_width_m`;
- добавлен тест `test_lawnmower_collect_sweeps_near_domain_edges`;
- старый проблемный кейс `strong_drift`, seed `34`, `7200 м` изменился с `0/150` до `56/150`.

Вывод: pre-fix calibration нельзя использовать как финальную серию. Ее можно использовать только как диагностический прогон.

## Проверка post-fix smoke

Для post-fix smoke не найдено нарушений базовых инвариантов:

- нет дубликатов строк;
- нет `time_budget`;
- `collected_ratio` и `auc_collected_by_path` в `[0, 1]`;
- `auc_collected_by_path <= collected_ratio`;
- `done` означает полный сбор;
- полный сбор не помечается как `path_budget`;
- `oracle_current_physics` не хуже non-oracle по `collected_ratio` и AUC на тех же seed;
- `successful_captures == collected`;
- нулевого или почти нулевого сбора больше нет;
- `wasted_path_ratio` в `[0, 1]`.

Медианный `lawnmower_collect` после фикса в smoke:

| Scenario | `1200 м` | `7200 м` |
|---|---:|---:|
| `static_calm` | `0.040` | `0.173` |
| `weak_drift` | `0.023` | `0.193` |
| `strong_drift` | `0.040` | `0.257` |
| `robot_disturbed` | `0.033` | `0.183` |

## Исправленная интерпретация `regret`

В pre-fix таблицах `regret_to_best_fixed_*` мог быть отрицательным:

- для `adaptive_mission`, если он лучше лучшего fixed режима;
- для `oracle_current_physics`, где сравнение с fixed режимами вообще не является корректной "потерей".

Это не искажало сам сбор, но могло искажать интерпретацию таблиц.

Исправление:

- `regret_to_best_fixed_*` теперь неотрицателен и означает только потерю относительно лучшего fixed режима;
- `gain_vs_best_fixed_*` показывает выигрыш;
- `delta_vs_best_fixed_*` показывает signed-разницу;
- для `oracle_current_physics` эти колонки выставляются в `NaN`;
- `oracle_gap_*` остается отдельной метрикой разрыва до oracle.

## Логический риск: `adaptive_mission` почти всегда равен `belief_horizon`

Trace на `1200 м`, seed `30-31` показал:

- `static_calm`: в основном `belief_horizon`;
- `weak_drift`: `belief_horizon` в `100%` событий;
- `strong_drift`: `belief_horizon` в `100%` событий;
- `robot_disturbed`: `belief_horizon` примерно `99%`, редкие включения `belief_orienteering`.

Вывод: текущий `adaptive_mission` нельзя заявлять как самостоятельный убедительный алгоритмический вклад. Сейчас это скорее wrapper, который часто вырождается в `belief_horizon`. Для статьи его можно использовать только как диагностический режим или после доработки правил переключения.

## Логический риск: метрики пустых целей у coverage-режимов

`empty_goal_arrivals`, `empty_goal_arrivals_per_km` и `wasted_path_ratio` для `lawnmower_collect` интерпретируются иначе, чем для goal-driven режимов:

- для `greedy`, `belief_horizon`, `confirmed_route` пустая цель означает неудачную проверку ожидаемой цели;
- для `lawnmower_collect` пустой проход может быть нормальной частью равномерного физического покрытия.

Вывод: эти метрики нельзя напрямую сравнивать между coverage и target-driven режимами без пояснения. Для coverage лучше использовать их как диагностический показатель пустого покрытия, а не как "ошибку выбора цели".

## Логический риск: маршрут `lawnmower_collect` является center-out coverage

Текущий coverage-route упорядочивает строки по близости к depot, то есть покрытие идет от центральной зоны наружу, а не как классический непрерывный проход от одной границы к другой.

Это не ошибка исполнения, но это влияет на интерпретацию:

- при ограниченном бюджете путь тратится преимущественно около depot/центральной полосы;
- такой baseline не равен "полное равномерное покрытие всей акватории";
- в статье его надо называть `center-out lawnmower_collect` или добавить второй baseline с boundary-to-boundary serpentine.

## Рекомендация перед следующим тяжелым прогоном

Перед финальной или pre-final серией нужно:

1. Перезапустить budget calibration после фикса `lawnmower_collect`.
2. Не использовать pre-fix calibration как публикационные результаты.
3. В таблицах использовать `gain/delta/regret` с новой семантикой.
4. Для `adaptive_mission` обязательно сохранять trace хотя бы на части seed-ов.
5. Отдельно решить, нужен ли второй coverage-baseline: классический boundary-to-boundary serpentine.
6. В статье не сравнивать `wasted_path_ratio` coverage и target-driven режимов без оговорок.

## Текущий verdict

Симулятор после фикса проходит базовые логические проверки на smoke-серии, но прежняя тяжелая calibration-серия признана **pre-fix invalid для финальных выводов**.
