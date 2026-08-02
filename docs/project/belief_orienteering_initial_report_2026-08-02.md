# Первичная реализация `belief_orienteering`

Дата: 2026-08-02.

## Зачем добавлен режим

`belief_cluster_route` показал важное ограничение: закрепленный короткий маршрут уменьшает пустые визиты, но может снижать долю сбора, потому что робот продолжает исполнять старое маршрутное решение после изменения карты и новых наблюдений.

Новый режим `belief_orienteering` проверяет более сильную гипотезу:

> маршрутный горизонт полезен не как жестко исполняемый маршрут, а как способ оценить первую целевую точку с учетом вероятной последующей пользы.

То есть планировщик строит короткую последовательность кандидатов, оценивает ее по ожидаемому сбору/информации/пути, но исполняет только первый шаг. После прибытия к цели карта обновляется, и горизонт пересчитывается заново.

## Что реализовано

Добавлен новый режим:

```powershell
python -m cleanup_sim_v2.run_experiments --modes belief_orienteering
```

Измененные элементы:

- `PlannerMode`: добавлен `belief_orienteering`;
- `PlannerConfig`: добавлены параметры короткого маршрутного горизонта;
- `planners.py`: добавлен beam-search по вероятностным кандидатам;
- `simulation.py`: `belief_orienteering` обрабатывается как belief-style цель для скорости подхода, выдержки у цели и подавления пустых областей;
- `run_experiments.py`: режим подключен к CLI;
- `tests/test_cleanup_sim_v2.py`: добавлены тесты парсера, построения горизонта и запуска симуляции.

## Важное отличие от `belief_cluster_route`

`belief_cluster_route` записывает `current_route` и пытается исполнить маршрут.

`belief_orienteering` не записывает `current_route`. Он использует маршрут только для оценки:

1. сформировать кандидатов из карты и подтвержденных целей;
2. построить несколько коротких последовательностей beam-search;
3. оценить последовательность по полезности на путь;
4. вернуть только первую точку;
5. после прибытия пересчитать все заново.

Это ближе к receding-horizon informative/orienteering planning.

## Ограничение после первичной диагностики

Первый вариант иногда вел себя как еще одна одношаговая эвристика по плотностным пикам. Это ухудшало результат: планировщик выбирал одиночные density-точки, которые не давали настоящего маршрутного преимущества.

Поэтому добавлено правило:

```python
belief_orienteering_min_route_points = 2
```

Если лучший горизонт содержит только одну точку, режим откатывается к `belief_horizon`. Это научно важно: новый алгоритм должен проверять именно маршрутную гипотезу, а не подменять одношаговый baseline.

## Проверки

Выполнено:

```powershell
python -m pytest -q tests\test_cleanup_sim_v2.py
python -m pytest -q
```

Результат: все тесты прошли.

## 10-seed промежуточный прогон

Команда:

```powershell
python -m cleanup_sim_v2.run_experiments `
  --seeds 10 `
  --scenarios static_calm weak_drift `
  --modes greedy belief_horizon belief_orienteering oracle_current_physics `
  --max-path-m 1000 `
  --tmax-s 2000 `
  --out-dir out\cleanup_sim_v2\belief_orienteering_min2_1000m_10seed_2026-08-02 `
  --checkpoint
```

Артефакты:

- `out/cleanup_sim_v2/belief_orienteering_min2_1000m_10seed_2026-08-02/summary.csv`;
- `out/cleanup_sim_v2/belief_orienteering_min2_1000m_10seed_2026-08-02/aggregate_mean_std.csv`;
- `out/cleanup_sim_v2/belief_orienteering_min2_1000m_10seed_2026-08-02/run_manifest.json`.

## Основные результаты

Средние значения по 10 seed:

| Сценарий | Режим | Доля сбора | Пустые цели/км | Доля пустого пути | Успешность целей | Доля от oracle |
|---|---:|---:|---:|---:|---:|---:|
| static_calm | greedy | 0.135 | 55.295 | 0.773 | 0.249 | 0.209 |
| static_calm | belief_horizon | 0.137 | 40.496 | 0.620 | 0.300 | 0.211 |
| static_calm | belief_orienteering | 0.132 | 40.096 | 0.590 | 0.292 | 0.204 |
| static_calm | oracle_current_physics | 0.633 | 2.800 | 0.029 | 0.971 | 1.000 |
| weak_drift | greedy | 0.088 | 65.394 | 0.876 | 0.145 | 0.156 |
| weak_drift | belief_horizon | 0.121 | 39.347 | 0.509 | 0.238 | 0.211 |
| weak_drift | belief_orienteering | 0.159 | 37.293 | 0.439 | 0.261 | 0.273 |
| weak_drift | oracle_current_physics | 0.576 | 17.098 | 0.144 | 0.832 | 1.000 |

## Парные различия

Для `collected_ratio`:

| Сценарий | Сравнение | Средняя разница | Победы |
|---|---:|---:|---:|
| static_calm | `belief_orienteering - greedy` | -0.003 | 6/10 |
| static_calm | `belief_orienteering - belief_horizon` | -0.005 | 5/10 |
| weak_drift | `belief_orienteering - greedy` | +0.071 | 10/10 |
| weak_drift | `belief_orienteering - belief_horizon` | +0.039 | 5/10 |

Bootstrap 95% CI для `collected_ratio`:

| Сценарий | Сравнение | Средняя разница | 95% CI |
|---|---:|---:|---:|
| static_calm | против `greedy` | -0.003 | [-0.037; 0.027] |
| static_calm | против `belief_horizon` | -0.005 | [-0.021; 0.008] |
| weak_drift | против `greedy` | +0.071 | [+0.027; +0.141] |
| weak_drift | против `belief_horizon` | +0.039 | [-0.021; +0.117] |

## Научная интерпретация

Текущий результат не доказывает универсальное превосходство `belief_orienteering`.

Более аккуратный вывод:

> receding-horizon маршрутная оценка оказывается полезной в динамическом сценарии со слабым дрейфом, где одношаговые и жадные решения чаще тратят путь на устаревающие/пустые цели; в статичном сценарии преимущество не проявляется, и алгоритм остается примерно на уровне существующих вероятностных baseline-ов.

Это гораздо сильнее предыдущей ситуации с `belief_cluster_route`, потому что появилась проверяемая условная гипотеза:

- не “наш алгоритм всегда лучше”;
- а “маршрутный горизонт дает выигрыш при динамике мусора и неполных наблюдениях, но не обязан выигрывать в статике”.

## Что нельзя заявлять

- Нельзя заявлять финальное статистическое превосходство над `belief_horizon`: 10 seed недостаточно, а CI включает ноль.
- Нельзя заявлять оптимальность маршрута: используется beam-search эвристика.
- Нельзя заявлять реальную CV/radar-детекцию: сенсоры остаются вероятностной моделью.
- Нельзя использовать эти результаты как финальные для статьи без 30-seed confirmatory-прогона.

## Что делать дальше

## Абляционные режимы

После первичного 10-seed результата добавлены режимы:

- `belief_orienteering_depth1` — глубина горизонта 1, минимальное число точек 1;
- `belief_orienteering_no_opportunity_cost` — отключен штраф за потерю лучшей одношаговой альтернативы;
- `belief_orienteering_density_disabled` — из горизонта исключены density/entropy-кандидаты, остаются только подтвержденные цели.

Эти режимы нужны, чтобы следующий эксперимент проверял вклад компонентов алгоритма, а не только итоговую строку `belief_orienteering`.

Smoke-команда:

```powershell
python -m cleanup_sim_v2.run_experiments `
  --seeds 3 `
  --scenarios weak_drift `
  --modes belief_orienteering belief_orienteering_depth1 belief_orienteering_no_opportunity_cost belief_orienteering_density_disabled `
  --max-path-m 1000 `
  --tmax-s 2000 `
  --out-dir out\cleanup_sim_v2\belief_orienteering_ablation_smoke_1000m_3seed_2026-08-02 `
  --checkpoint
```

Средние значения по `weak_drift`, 3 seed:

| Режим | Доля сбора | Пустые цели/км | Доля пустого пути | Успешность целей |
|---|---:|---:|---:|---:|
| `belief_orienteering` | 0.142 | 37.653 | 0.567 | 0.273 |
| `belief_orienteering_depth1` | 0.089 | 45.421 | 0.661 | 0.183 |
| `belief_orienteering_no_opportunity_cost` | 0.133 | 37.988 | 0.577 | 0.272 |
| `belief_orienteering_density_disabled` | 0.093 | 33.652 | 0.577 | 0.223 |

Предварительная интерпретация:

- `depth1` заметно хуже: текущий выигрыш не сводится к новой одношаговой формуле;
- отключение density-кандидатов уменьшает сбор на этих seed-ах, хотя может снижать часть пустых визитов;
- opportunity-cost дает небольшой прирост в smoke, но его стоит оставить как защиту от плохого первого шага до полной абляции на 30 seed.

## Следующие действия

1. Запустить 30-seed прогон на `static_calm`, `weak_drift`, `strong_drift`, `robot_disturbed`.
2. Включить в 30-seed прогон абляции `belief_orienteering_depth1`, `belief_orienteering_no_opportunity_cost`, `belief_orienteering_density_disabled`.
3. Проверить, сохраняется ли выигрыш при `strong_drift` и `robot_disturbed`.
4. Если выигрыш сохраняется только при слабом/среднем дрейфе, формулировать вклад как анализ условий применимости маршрутного горизонта.
5. Если на 30 seed преимущество над `greedy` при дрейфе останется устойчивым, это может стать ядром статьи уровня РИНЦ/ВАК-основа.
