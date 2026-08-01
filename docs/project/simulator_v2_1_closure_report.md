# Simulator v2.1 Closure Report

Дата: 2026-08-01.

Цель этапа: закрыть основные физические, метрические и воспроизводимые слабые места `cleanup_sim_v2` перед разработкой нового алгоритма планирования. Береговая линия, причалы, мосты и препятствия намеренно не добавлялись.

## Что закрыто

| Блок | Статус | Что изменено |
|---|---|---|
| Физика сбора | закрыто для pre-final | мгновенный круговой сбор заменен накопительным захватом в передней swept-aperture зоне |
| Throughput | закрыто | объект больше не становится “невозможным” из-за массы за один тик; работа захвата копится |
| Движение | закрыто частично | разделены cruise/collection speed, добавлена простая цена разворота |
| Дрейф | закрыто для v2.1 | движение мусора, возмущение от робота и сбор считаются на подшагах |
| Сенсоры | закрыто инструментально | object-level camera/radar detections, Poisson clutter, sensor-level precision/recall |
| Цели | закрыто | подтверждение, старение, suppression после пустого визита, отсутствие oracle-доступа через `source_index` |
| Метрики | закрыто | добавлены normalized empty-goal metrics, wasted-time/path ratios, capture/contact metrics |
| Oracle | закрыто | добавлены `oracle_perfect_static`, `oracle_current_physics`, `oracle_route_heuristic` |
| Reproducibility | закрыто | сохраняются `config_hash`, `git_commit`, `run_manifest.json` |

## Smoke-прогон v2.1

Команда:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 3 --scenarios static_calm weak_drift strong_drift robot_disturbed --modes lawnmower_survey lawnmower_collect greedy confirmed_route oracle_current_physics --max-path-m 600 --tmax-s 1800 --out-dir out\cleanup_sim_v2\v2_1_smoke_3seed_2026-08-01_refresh
```

Результаты являются smoke-проверкой, а не финальным экспериментом.

| scenario | mode | collected ratio mean | empty goals/km mean | oracle gap mean |
|---|---:|---:|---:|---:|
| `static_calm` | `lawnmower_survey` | 0.000 | 8.3 | 0.487 |
| `static_calm` | `lawnmower_collect` | 0.000 | 8.3 | 0.487 |
| `static_calm` | `greedy` | 0.047 | 45.5 | 0.440 |
| `static_calm` | `confirmed_route` | 0.027 | 16.7 | 0.460 |
| `static_calm` | `oracle_current_physics` | 0.487 | 4.4 | 0.000 |
| `weak_drift` | `lawnmower_survey` | 0.000 | 8.3 | 0.438 |
| `weak_drift` | `lawnmower_collect` | 0.011 | 6.7 | 0.427 |
| `weak_drift` | `greedy` | 0.060 | 55.5 | 0.378 |
| `weak_drift` | `confirmed_route` | 0.020 | 30.5 | 0.418 |
| `weak_drift` | `oracle_current_physics` | 0.438 | 20.0 | 0.000 |
| `strong_drift` | `lawnmower_survey` | 0.000 | 8.3 | 0.476 |
| `strong_drift` | `lawnmower_collect` | 0.004 | 7.8 | 0.471 |
| `strong_drift` | `greedy` | 0.029 | 57.8 | 0.447 |
| `strong_drift` | `confirmed_route` | 0.031 | 31.7 | 0.444 |
| `strong_drift` | `oracle_current_physics` | 0.476 | 11.1 | 0.000 |
| `robot_disturbed` | `lawnmower_survey` | 0.000 | 8.3 | 0.453 |
| `robot_disturbed` | `lawnmower_collect` | 0.009 | 6.7 | 0.444 |
| `robot_disturbed` | `greedy` | 0.031 | 53.9 | 0.422 |
| `robot_disturbed` | `confirmed_route` | 0.013 | 33.3 | 0.440 |
| `robot_disturbed` | `oracle_current_physics` | 0.453 | 7.2 | 0.000 |

## Интерпретация smoke

- Новая физика резко снижает сбор при малом бюджете пути: это ожидаемый результат после отказа от “радиуса 5 м”.
- `lawnmower_survey` почти не собирает мусор, потому что это режим сенсорного обследования с широкой разметкой маршрута, а не физическое траление.
- `lawnmower_collect` честнее физически, но при ширине сборщика около 1 м и бюджете 600 м почти не успевает покрыть поле.
- `greedy` остается сильнее простого покрытия при малом бюджете, но имеет высокую цену пустых визитов.
- `oracle_current_physics` показывает большой достижимый зазор: при той же физике и бюджете путь к улучшению алгоритма существует.

## Что еще не закрыто

| Приоритет | Проблема | Почему важно |
|---|---|---|
| P1 | Нет навигационной ошибки | пока робот идеально знает свое положение; для статьи нужно либо оставить как допущение, либо добавить отдельный сценарий localization noise |
| P1 | Нет береговой линии и препятствий | сознательно исключено из v2.1, но снижает реализм городской акватории |
| P1 | Не проведена sensitivity-серия | без нее нельзя утверждать устойчивость выводов к параметрам сенсоров и сборщика |
| P2 | `active` пока не является финальным алгоритмом | нельзя делать научный вывод о качестве гибридного планирования на его основе |
| P2 | Нет реального CV/radar пайплайна | сенсоры являются вероятностной моделью, а не обученной системой детекции |
| P2 | Дрейф не валидирован по реальным течениям | модель подходит для сравнительного симуляционного исследования, не для прогноза загрязнений в конкретном водоеме |

## Решение

Вердикт: `READY FOR ALGORITHM DESIGN`, но `NOT READY FOR FINAL 30-SEED CONFIRMATORY RUN`.

Следующий научный шаг: разработать алгоритм, который использует карту неопределенности, подтвержденные цели и ожидаемую физическую цену сбора так, чтобы сокращать oracle-gap относительно `greedy` и `confirmed_route`.
