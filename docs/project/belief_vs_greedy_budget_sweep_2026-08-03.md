# Belief Horizon vs Greedy: budget sweep, 2026-08-03

## Purpose

Проверить, насколько текущий `belief_horizon` превосходит `greedy` при увеличении путевого бюджета.

Главная метрика: `collected_ratio` при фиксированном максимальном пути.

## Runs

| Budget, m | Seeds | Scenarios | Modes |
|---:|---:|---|---|
| 1000 | 3 | `static_calm`, `weak_drift` | `greedy`, `belief_horizon`, `oracle_current_physics` |
| 2000 | 5 | `static_calm`, `weak_drift` | `greedy`, `belief_horizon`, `oracle_current_physics` |
| 3000 | 5 | `static_calm`, `weak_drift` | `greedy`, `belief_horizon`, `oracle_current_physics` |
| 5000 | 3 | `static_calm`, `weak_drift` | `greedy`, `belief_horizon`; oracle run separately |

## Main Results

| Scenario | Budget, m | Greedy mean | Belief mean | Absolute gain | Ratio | Paired wins |
|---|---:|---:|---:|---:|---:|---:|
| `static_calm` | 1000 | 0.104 | 0.160 | +0.056 | 1.53x | 2/3 |
| `static_calm` | 2000 | 0.253 | 0.327 | +0.073 | 1.29x | 4/5 |
| `static_calm` | 3000 | 0.351 | 0.473 | +0.123 | 1.35x | 4/5 |
| `static_calm` | 5000 | 0.402 | 0.649 | +0.247 | 1.61x | 3/3 |
| `weak_drift` | 1000 | 0.100 | 0.191 | +0.091 | 1.91x | 2/3 |
| `weak_drift` | 2000 | 0.140 | 0.529 | +0.389 | 3.78x | 5/5 |
| `weak_drift` | 3000 | 0.184 | 0.616 | +0.432 | 3.35x | 5/5 |
| `weak_drift` | 5000 | 0.224 | 0.827 | +0.602 | 3.68x | 3/3 |

## Oracle Context

`oracle_current_physics` collected all debris at budgets of 2000, 3000 and 5000 m in the tested clustered scenarios.

At 5000 m:

| Scenario | Greedy / oracle | Belief / oracle | Belief remaining gap |
|---|---:|---:|---:|
| `static_calm` | 0.402 | 0.649 | 0.351 |
| `weak_drift` | 0.224 | 0.827 | 0.173 |

## Secondary Metrics At 5000 m

| Scenario | Mode | Empty goals per km | Wasted path ratio | Goal success rate | Collection precision |
|---|---|---:|---:|---:|---:|
| `static_calm` | `greedy` | 51.87 | 0.832 | 0.184 | 0.759 |
| `static_calm` | `belief_horizon` | 31.93 | 0.585 | 0.338 | 0.718 |
| `weak_drift` | `greedy` | 44.80 | 0.930 | 0.125 | 0.764 |
| `weak_drift` | `belief_horizon` | 26.67 | 0.517 | 0.312 | 0.737 |

## Interpretation

Текущий `belief_horizon` уже не дает прирост только на уровне нескольких процентов.

В clustered `static_calm` преимущество умеренное: примерно +7-12 п.п. на 2000-3000 м и +25 п.п. на 5000 м, но выборка на 5000 м пока только 3 seed-а.

В clustered `weak_drift` преимущество сильное: примерно +39-43 п.п. на 2000-3000 м и +60 п.п. на 5000 м. Здесь `greedy` деградирует из-за преследования устаревающих/смещающихся целей, а `belief_horizon` лучше использует разведку и менее часто тратит путь на пустые цели.

При этом разрыв до oracle остается большим. Даже при 5000 м `belief_horizon` достигает около 65% oracle в `static_calm` и 83% oracle в `weak_drift`. Это означает, что алгоритм уже превосходит простой baseline, но еще оставляет пространство для научно осмысленной доработки маршрутизации внутри найденных областей и работы с динамическими целями.

## Caution

Эти результаты не являются финальной статистикой для статьи:

- 1000 и 5000 м рассчитаны только на 3 seed-ах.
- 2000 и 3000 м рассчитаны на 5 seed-ах.
- Для публикационного вывода нужен confirmatory-прогон после заморозки параметров и кода.

