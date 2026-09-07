# Дополнительные проверки гипотез

Дата: 2026-08-03.

Статус: диагностический отчет без изменения рабочего кода.

## Цель

Проверить несколько гипотез после восстановления лучшей рабочей версии `belief_horizon`:

- станет ли полное/систематическое покрытие полезным при большем бюджете пути;
- есть ли среди уже реализованных режимов кандидат сильнее базового `belief_horizon`;
- насколько меняется интерпретация разрыва с oracle при `2000-3000 м`.

## H1. Покрытие может стать полезным при большем бюджете

Проверены бюджеты `2000 м` и `3000 м`, `2 seed`, сценарии `static_calm` и `weak_drift`.

Режимы:

- `lawnmower_survey`;
- `lawnmower_collect`;
- `greedy`;
- `belief_horizon`;
- `oracle_current_physics`.

Команды:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 2 --scenarios static_calm weak_drift --modes lawnmower_survey lawnmower_collect greedy belief_horizon oracle_current_physics --max-path-m 2000 --tmax-s 20000 --out-dir out\cleanup_sim_v2\budget_2000m_hypothesis_2seed_2026-08-03 --checkpoint

python -m cleanup_sim_v2.run_experiments --seeds 2 --scenarios static_calm weak_drift --modes lawnmower_survey lawnmower_collect greedy belief_horizon oracle_current_physics --max-path-m 3000 --tmax-s 30000 --out-dir out\cleanup_sim_v2\budget_3000m_hypothesis_2seed_2026-08-03 --checkpoint
```

### Результаты

| scenario | mode | 1000 м | 2000 м | 3000 м |
|---|---:|---:|---:|---:|
| static_calm | belief_horizon | 0.160 | 0.280 | 0.427 |
| static_calm | greedy | 0.104 | 0.170 | 0.263 |
| static_calm | lawnmower_collect | - | 0.020 | 0.037 |
| static_calm | lawnmower_survey | - | 0.000 | 0.000 |
| static_calm | oracle_current_physics | 0.598 | 1.000 | 1.000 |
| weak_drift | belief_horizon | 0.191 | 0.493 | 0.597 |
| weak_drift | greedy | 0.100 | 0.113 | 0.213 |
| weak_drift | lawnmower_collect | - | 0.003 | 0.003 |
| weak_drift | lawnmower_survey | - | 0.000 | 0.000 |
| weak_drift | oracle_current_physics | 0.531 | 1.000 | 1.000 |

### Вывод

Гипотеза не подтвердилась для задачи сбора при фиксированном бюджете пути. `lawnmower_survey` может быть полезен для картирования, но как стратегия физического сбора почти бесполезен из-за узкой передней полосы захвата. `lawnmower_collect` слишком дорог по длине маршрута.

Важно: при росте бюджета `belief_horizon` масштабируется лучше `greedy`, особенно в `weak_drift`. Но oracle к `2000 м` уже собирает все объекты в этих seed-ах, поэтому разрыв остается очень большим.

## H2. Среди существующих умных режимов может быть режим сильнее `belief_horizon`

Проверка на `2000 м`, `2 seed`.

Режимы:

- `belief_horizon`;
- `belief_horizon_provisional`;
- `belief_cluster_route`;
- `belief_orienteering`;
- `belief_orienteering_provisional`;
- `confirmed_route`;
- `oracle_current_physics`.

Команда:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 2 --scenarios static_calm weak_drift --modes belief_horizon belief_horizon_provisional belief_cluster_route belief_orienteering belief_orienteering_provisional confirmed_route oracle_current_physics --max-path-m 2000 --tmax-s 20000 --out-dir out\cleanup_sim_v2\smart_modes_2000m_2seed_2026-08-03 --checkpoint
```

### Результаты

| scenario | mode | collected_ratio | wasted_path_ratio | goal_success_rate |
|---|---:|---:|---:|---:|
| static_calm | belief_horizon | 0.280 | 0.613 | 0.347 |
| static_calm | belief_horizon_provisional | 0.350 | 0.590 | 0.367 |
| static_calm | belief_cluster_route | 0.240 | 0.588 | 0.382 |
| static_calm | belief_orienteering | 0.250 | 0.581 | 0.374 |
| static_calm | confirmed_route | 0.180 | 0.720 | 0.331 |
| weak_drift | belief_horizon | 0.493 | 0.355 | 0.397 |
| weak_drift | belief_horizon_provisional | 0.433 | 0.439 | 0.337 |
| weak_drift | belief_cluster_route | 0.323 | 0.592 | 0.362 |
| weak_drift | belief_orienteering | 0.350 | 0.400 | 0.449 |
| weak_drift | confirmed_route | 0.147 | 0.873 | 0.191 |

### Вывод

`belief_horizon_provisional` выглядит полезным в `static_calm`, но слабее в `weak_drift`. Это не готовый победитель, но важная подсказка: предварительные цели могут помогать, если мир статичен, и вредить, если мусор дрейфует.

`belief_orienteering` имеет более высокий `goal_success_rate` в `weak_drift`, но собирает меньше. Вероятно, он слишком осторожен или недоэксплуатирует найденные зоны.

`confirmed_route` слабый: ехать только по подтвержденным целям слишком поздно и слишком шумно.

## H3. Предварительные цели могут быть особенно полезны при сильном дрейфе

После сценарного sweep отдельно проверен `strong_drift` на `5 seed`.

Команда:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 5 --scenarios strong_drift --modes greedy belief_horizon belief_horizon_provisional belief_orienteering oracle_current_physics --max-path-m 1000 --tmax-s 10000 --out-dir out\cleanup_sim_v2\strong_drift_provisional_signal_1000m_5seed_2026-08-03 --checkpoint
```

Результат:

| mode | collected_ratio | wasted_path_ratio | goal_success_rate | empty_goal_arrivals |
|---|---:|---:|---:|---:|
| greedy | 0.048 | 0.896 | 0.068 | 56.0 |
| belief_horizon | 0.395 | 0.374 | 0.472 | 19.6 |
| belief_horizon_provisional | 0.469 | 0.246 | 0.649 | 12.6 |
| belief_orienteering | 0.388 | 0.370 | 0.542 | 16.0 |
| oracle_current_physics | 0.748 | 0.049 | 0.887 | 14.2 |

Paired-сравнение `belief_horizon_provisional` против `belief_horizon`:

- средний прирост `+0.0747`;
- победы `4/5`;
- одна ничья;
- доля от oracle: `0.659` против `0.535` у базового `belief_horizon`.

### Вывод

Это самый живой сигнал из дополнительных проверок. В сильном дрейфе ожидание полного подтверждения цели может быть слишком дорогим: пока цель подтверждается, мусор смещается, а карта/трек стареют. Использование предварительных целей повышает риск, но в этом сценарии риск окупается.

Осторожная формулировка для будущей статьи:

> В сценариях с выраженным дрейфом предварительные треки могут повышать эффективность сбора по сравнению с ожиданием полного подтверждения, если планировщик учитывает неопределенность, возраст наблюдения и стоимость пустого визита.

Это не доказывает универсальное превосходство `belief_horizon_provisional`, потому что в `static_calm` и `weak_drift` эффект слабее и не всегда устойчив.

## Трезвый общий вывод

На текущем этапе мы добились не финального сильного алгоритма, а нормальной исследовательской платформы и набора отрицательных результатов:

- старые упрощения симулятора убраны;
- `belief_horizon` устойчивее простого `greedy` и масштабируется лучше;
- coverage-стратегии теперь честно слабые для физического сбора, а не искусственно сильные;
- oracle показывает большой реальный зазор;
- простые идеи усиления не дали надежного выигрыша.

Это не провал, но и не готовая ВАК-история про новый алгоритм. Сейчас у нас есть честная база, на которой можно делать следующий алгоритм без самообмана.

## Куда копать дальше

Наиболее разумные направления:

1. **Условные предварительные цели**  
   Не просто включить `belief_horizon_provisional`, а сделать их drift-aware: предварительная цель используется только если ее неопределенность, возраст и ожидаемый выигрыш проходят порог.

2. **Риск-ограничение неподтвержденных density-кандидатов**  
   Полный запрет density помогает в статике, но вредит при дрейфе. Значит нужен не запрет, а gate: когда можно доверять неподтвержденной карте, а когда лучше продолжать scout/coverage.

3. **Осторожная локальная эксплуатация после успеха**  
   Не mini-lawnmower и не длинный patch-pass. После успеха выбирать одно короткое локальное действие из нескольких вариантов, затем сразу пересчитывать карту.

4. **Разделить цели статьи по горизонту миссии**  
   При `1000 м` это задача быстрого сбора, а не полного картирования. Если делать статью про вероятностное картирование, надо вводить отдельные метрики карты и не продавать `lawnmower_survey` как сборщик.

5. **Сделать oracle сильнее и честнее описать gap**  
   Текущий `oracle_current_physics` - nearest-neighbor по истинному текущему мусору, не оптимум. Для статьи полезно иметь еще `oracle_route_heuristic` и, возможно, улучшенный upper-bound, но не смешивать его с доступными алгоритмами.

## Практическая рекомендация

Следующий кодовый шаг стоит делать не в сторону coverage, а в сторону отдельного режима:

```text
risk_gated_belief
```

Минимальная проверка должна быть жесткой:

- `3 seeds x static_calm, weak_drift`;
- сравнение против `greedy`, `belief_horizon`, `oracle_current_physics`;
- критерий продолжения: не хуже `belief_horizon` в обоих сценариях и хотя бы локальный прирост без роста `wasted_path_ratio`.
