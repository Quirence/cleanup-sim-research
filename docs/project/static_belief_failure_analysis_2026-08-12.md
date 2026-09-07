# Static Belief Failure Analysis

Дата: 2026-08-12.

## Цель

Глубоко проверить, почему текущий `belief_horizon` в статическом кластерном сценарии (`static_calm`) все еще существенно уступает oracle, несмотря на устойчивое превосходство над `greedy`.

Главная метрика: `collected_ratio` при фиксированном бюджете пути.

## Что добавлено в диагностику

В `cleanup_sim_v2.simulation` добавлены только диагностические поля. Логика выбора целей не изменялась.

Новые поля в `summary.csv`:

- `first_detection_path_m` - путь до первого истинного обнаружения;
- `first_collection_path_m` - путь до первого успешного сбора;
- `true_empty_goal_rate` - доля целей, где по истинному миру рядом не было остаточного мусора;
- `density_goal_count`, `density_empty_goal_rate`, `density_wasted_path_ratio`;
- `target_goal_count`, `target_empty_goal_rate`, `target_wasted_path_ratio`;
- `refinement_path_ratio`;
- `missed_local_opportunity_count`, `missed_local_opportunity_rate`;
- `post_success_departures_from_rich_area`;
- `missed_local_opportunity_path_ratio`.

Новые поля в `events.csv` для `goal_started` / `goal_completed`:

- `candidate_group`;
- `true_local_count`;
- `true_local_mass_kg`;
- `nearest_true_debris_m`;
- `true_swept_count`;
- `true_local_remaining_count`;
- `missed_local_opportunity`.

Эти поля используют истинное состояние мира только для offline-аудита. Планировщик к ним доступа не получает.

## Команды

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 10 --scenarios static_calm --modes greedy belief_horizon oracle_current_physics --max-path-m 1000 --tmax-s 10000 --out-dir out\cleanup_sim_v2\static_failure_diag_1000m_10seed_2026-08-12 --checkpoint

python -m cleanup_sim_v2.run_experiments --seeds 10 --scenarios static_calm weak_drift --modes greedy belief_horizon oracle_current_physics --max-path-m 3000 --tmax-s 30000 --out-dir out\cleanup_sim_v2\static_failure_diag_3000m_10seed_2026-08-12 --save-runs --checkpoint

python -m cleanup_sim_v2.run_experiments --seeds 10 --scenarios static_calm --modes greedy belief_horizon oracle_current_physics --max-path-m 5000 --tmax-s 50000 --out-dir out\cleanup_sim_v2\static_failure_diag_5000m_10seed_2026-08-12 --checkpoint
```

## Основные результаты в static

| Budget | Mode | Collected ratio | Wasted path | Goal success | First collection |
|---:|---|---:|---:|---:|---:|
| 1000 m | `greedy` | 0.135 | 0.773 | 0.249 | 225 m |
| 1000 m | `belief_horizon` | 0.179 | 0.498 | 0.392 | 156 m |
| 1000 m | `oracle_current_physics` | 0.633 | 0.029 | 0.972 | 26 m |
| 3000 m | `greedy` | 0.333 | 0.802 | 0.228 | 225 m |
| 3000 m | `belief_horizon` | 0.453 | 0.528 | 0.356 | 156 m |
| 3000 m | `oracle_current_physics` | 1.000 | 0.028 | 0.971 | 26 m |
| 5000 m | `greedy` | 0.435 | 0.831 | 0.190 | 225 m |
| 5000 m | `belief_horizon` | 0.647 | 0.564 | 0.335 | 156 m |
| 5000 m | `oracle_current_physics` | 1.000 | 0.028 | 0.971 | 26 m |

Paired-сравнение `belief_horizon - greedy`:

| Budget | Mean delta | Wins |
|---:|---:|---:|
| 1000 m | +0.044 | 8/10 |
| 3000 m | +0.120 | 9/10 |
| 5000 m | +0.212 | 10/10 |

Вывод: `belief_horizon` уже уверенно лучше `greedy`, особенно при увеличении бюджета. Но до oracle в static остается большой разрыв: при 3000 m алгоритм собирает около 45% доступного upper-bound.

## Где теряется путь в static

Для `belief_horizon`, `static_calm`, 3000 m, 10 seed:

| Diagnostic | Mean |
|---|---:|
| `wasted_path_ratio` | 0.528 |
| `density_empty_goal_rate` | 0.764 |
| `density_wasted_path_ratio` | 0.195 |
| `target_empty_goal_rate` | 0.605 |
| `target_wasted_path_ratio` | 0.278 |
| `refinement_path_ratio` | 0.206 |
| `missed_local_opportunity_rate` | 0.698 |
| `post_success_departures_from_rich_area` | 4.5 |

Корреляции с `collected_ratio` по 10 seed-ам в static 3000 m:

| Metric | Correlation |
|---|---:|
| `density_wasted_path_ratio` | -0.828 |
| `density_empty_goal_rate` | -0.746 |
| `wasted_path_ratio` | -0.698 |
| `first_collection_path_m` | -0.317 |
| `target_empty_goal_rate` | -0.229 |
| `refinement_path_ratio` | +0.038 |

Главный количественный сигнал: в static качество сильнее всего проседает там, где планировщик тратит путь на неподтвержденные density-цели. Пустые target-визиты тоже дороги, но связь с итоговым сбором слабее.

## Интерпретация

### H1. Алгоритм поздно находит мусор

Частично подтверждается.

В static 3000 m:

- `belief_horizon`: первый сбор в среднем после 156 m;
- `greedy`: после 225 m;
- `oracle_current_physics`: после 26 m.

Но это не единственная причина. Даже после первого сбора остается большой wasted path.

### H2. Алгоритм слишком доверяет неподтвержденной карте

Подтверждается сильнее всего.

Для `belief_horizon` в static 3000 m:

- `density_empty_goal_rate = 0.764`;
- `density_wasted_path_ratio = 0.195`;
- корреляция `density_wasted_path_ratio` с итоговым сбором: `-0.828`.

Значит первый кандидат на улучшение - не новый глобальный маршрут, а риск-фильтр неподтвержденных density-областей.

### H3. Алгоритм плохо вычерпывает найденный кластер

Подтверждается, но требует осторожной интерпретации.

`missed_local_opportunity_rate = 0.698`: после большого числа успешных целей в диагностическом радиусе еще остается несколько живых объектов. Это не значит, что алгоритм всегда прямо уезжает далеко, но показывает, что локальная область часто не исчерпана.

Временная гипотеза:

> После успешного сбора планировщик должен не запускать жесткий мини-прочес, а выполнить одно короткое локальное действие с пересчетом карты.

### H4. Refinement является главным источником потерь

Не подтверждается как главный фактор.

`refinement_path_ratio` около `0.206`, но корреляция с итоговым сбором почти нулевая (`+0.038`). Уточнение целей стоит пути, но, вероятно, также предотвращает часть пустых визитов. Полное отключение refinement ранее ухудшало результат.

### H5. Greedy проигрывает из-за пустых визитов, а не только из-за простоты

Подтверждается.

В static 3000 m:

- `greedy`: wasted path 0.802, success rate 0.228;
- `belief_horizon`: wasted path 0.528, success rate 0.356.

Текущий `belief_horizon` лучше именно потому, что снижает пустой путь, но пока делает это недостаточно.

## Что улучшать первым

### Priority 1: `belief_static_risk_gated`

Цель: уменьшить пустые поездки к неподтвержденным density-целям в static.

Минимальная логика:

1. Для `density_peak` и `density_transect` считать:
   - ожидаемый сбор в swept-полосе;
   - расстояние до цели;
   - локальную массу density-карты;
   - риск пустого визита.
2. Если ожидаемый сбор на метр ниже порога, density-кандидат не запрещается навсегда, а проигрывает coverage/scout или target-кандидату.
3. Порог должен быть мягким и аблируемым.

Acceptance:

- static 3000 m: `+0.03` к `belief_horizon`;
- static wins: минимум `7/10`;
- weak_drift не хуже `-0.02`;
- `density_wasted_path_ratio` ниже базы.

### Priority 2: one-step local exploitation

Цель: после успешного сбора не уходить из вероятного кластера слишком рано.

Минимальная логика:

1. После успешного сбора определить, есть ли высокая локальная density/track-поддержка в радиусе 12-20 m.
2. Сгенерировать 3-5 коротких действий:
   - вперед через локальный максимум;
   - небольшой боковой смещенный проход;
   - цель к ближайшему подтвержденному track;
   - короткий transect через локальный weighted centroid.
3. Выбрать одно действие только если его ожидаемая польза на метр выше глобального кандидата.
4. После одного действия вернуться к обычному receding-horizon выбору.

Acceptance:

- уменьшить `missed_local_opportunity_rate` или увеличить сбор без роста wasted path;
- не повторить неудачу старого fixed mini-lawnmower.

### Priority 3: approach-aware target selection

Цель: выбирать не только точку, но и направление захода, чтобы физическая полоса сборщика проходила через область с высокой вероятностью мусора.

Это сложнее, поэтому после risk-gate и one-step exploitation.

## Что пока не делать

- Не возвращать обязательную фазу полной разведки как главный режим.
- Не включать длинный patch-pass через размытую density-карту.
- Не отключать refinement полностью.
- Не менять физику и сенсоры одновременно с алгоритмом.
- Не запускать финальный 30-seed прогон до выбора нового кандидата.

## Следующий кодовый шаг

Реализовать отдельный режим:

```text
belief_static_risk_gated
```

или, если хотим не расширять список режимов, добавить абляционный режим:

```text
belief_horizon_density_risk_gate
```

Рекомендую второй вариант: он яснее как экспериментальная модификация существующего алгоритма.

Минимальный smoke:

```text
10 seeds
scenarios: static_calm, weak_drift
modes: greedy, belief_horizon, belief_horizon_density_risk_gate, oracle_current_physics
budget: 3000 m
```

## Verification

```powershell
python -m pytest -q
```

Результат после добавления диагностики:

```text
43 passed
```

