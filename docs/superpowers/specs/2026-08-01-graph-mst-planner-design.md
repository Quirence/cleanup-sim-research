# Design: MST-based graph routing planner (`graph_mst`)

Дата: 2026-08-01
Ветка: `dev` (не мержится в `main` автоматически)
Статус: черновая экспериментальная проверка, не для статьи

## Контекст и цель

Пользователь хочет проверить личную гипотезу: будет ли обход подтверждённых
целей по минимальному остовному дереву (MST, алгоритм Прима) работать лучше,
чем текущий nearest-neighbor обход в `detected_tsp`/`hybrid` из
[cleanup_sim/planners.py](../../../cleanup_sim/planners.py).

Это не претендует на научную новизну для статьи (MST-эвристика для TSP —
классический результат, известный с 1970-х). Явно зафиксировано:
`cleanup_sim/confirmatory.py` и preregistration-документы статьи не
затрагиваются. Сравнение выполняется через штатный `run_experiments`.

## Не-цели (explicitly out of scope)

- Не добавляется в замороженный `confirmatory.py` / preregistration.
- Не встраивается в `hybrid`-переключатель explore/route.
- Не решается точный TSP (Held-Karp и т.п.) — только MST-эвристика.
- Не вводятся препятствия/граф проходимости — акватория остаётся открытой,
  вес ребра = евклидово расстояние.
- Не добавляются новые поля `PlannerConfig` — режим переиспользует
  существующие `detected_confirm_prob`, `detected_batch_size` и т.д.

## Алгоритм

Новая функция `mst_route(start, targets, limit)` в
[cleanup_sim/planners.py](../../../cleanup_sim/planners.py):

1. Строится полный граф: узлы = `start` (текущая позиция робота) + все ещё
   не посещённые подтверждённые цели из `target_queue.confirmed_targets()`
   (тот же источник данных, что и у `detected_tsp` — без oracle-доступа к
   истинной карте мусора).
2. На графе строится MST алгоритмом **Прима**, стартуя от `start`.
3. Дерево обходится **preorder DFS от `start`** — это даёт последовательность
   точек с 2-приближением к оптимальному туру.
4. Результат обрезается до `limit` точек (переиспользуем
   `detected_batch_size` для `graph_mst`, аналогично тому как
   `detected_batch_size`/`hybrid_target_batch_size` используются сейчас).

## Инкрементальное дополнение графа

Отличие от текущего `detected_tsp` (там маршрут строится пачкой и
проходится целиком, новые цели ждут следующей пачки):

- `update_detected_targets` уже возвращает список `confirmations` —
  вновь подтверждённые цели за тик. Сейчас это значение используется только
  для логов ([simulation.py](../../../cleanup_sim/simulation.py)).
- Для режима `graph_mst`: если во время движения по маршруту
  (`state.current_route` не пуст) приходит непустой `confirmations`,
  текущий маршрут инвалидируется (`state.current_route = []`/`None`).
- На следующем шаге `choose_next_goal` увидит пустой маршрут и пересчитает
  граф и MST заново — уже с учётом новой точки.
- Пересчёт с нуля осознанно выбран вместо точечной вставки узла в
  существующее дерево: целей мало (ограничены `detected_confirm_prob` +
  `target_confirm_hits`), Прим — O(n²), полный пересчёт дешёвый и при этом
  **всегда даёт корректный MST** (в отличие от "подключить новый узел к
  ближайшему существующему", что не гарантированно минимально).

Известный и осознанно принятый побочный эффект: при частых подтверждениях
маршрут может "передумывать" на лету — робот, следующий к точке A, может
переключиться на точку B, если появление точки C изменило оптимальный
обход. В этой симуляции у робота нет инерции (шаг пересчитывается заново
каждый тик в `_step_toward`), так что это не создаёт физически нереалистичного
поведения — это просто одно из свойств стратегии, которое интересно
сравнить с "стабильным батчем" nearest-neighbor. Дизайн не сглаживает это
поведение по явному запросу пользователя.

## Fallback при отсутствии целей

Как у `detected_tsp`: если `confirmed_targets()` пуст, режим `graph_mst`
использует стандартный `lawnmower`-маршрут покрытия
([next_lawnmower](../../../cleanup_sim/planners.py)) до появления первой
подтверждённой цели.

## Изменяемые файлы

- **[cleanup_sim/config.py](../../../cleanup_sim/config.py)** — добавить
  `"graph_mst"` в `Literal` `PlannerMode`.
- **[cleanup_sim/planners.py](../../../cleanup_sim/planners.py)**:
  - новая функция `mst_route(start, targets, limit)` (Prim + preorder DFS);
  - `choose_next_goal` получает ветку для `mode == "graph_mst"`, аналогичную
    ветке `detected_tsp`, но с инвалидацией маршрута при новых
    подтверждениях и вызовом `mst_route` вместо `nearest_neighbor_route`.
- **[cleanup_sim/simulation.py](../../../cleanup_sim/simulation.py)** —
  прокинуть список `confirmations` из `update_detected_targets` в
  `choose_next_goal` (сейчас используется только для логирования событий).
- **тесты** — новый `tests/test_graph_mst.py`:
  - `mst_route` посещает каждую точку ровно один раз;
  - на простом наборе точек на прямой обход идёт по порядку без "прыжков
    туда-обратно" (это то, что nearest-neighbor может ломать в некоторых
    конфигурациях, а MST-preorder — нет);
  - интеграционный smoke-тест полного прогона `run_simulation` с
    `mode="graph_mst"` (аналогично существующим тестам для `detected_tsp` в
    [tests/test_cleanup_sim.py](../../../tests/test_cleanup_sim.py)) —
    проверяет, что симуляция не падает и завершает работу штатно.

## Как сравнивать

Обычный CLI, без нового инструментария:

```powershell
python -m cleanup_sim.run_experiments `
  --seeds 5 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --modes greedy lawnmower_dense detected_tsp hybrid graph_mst `
  --out-dir out/cleanup_sim/graph_mst_probe `
  --plot-examples
```

Результат читается из тех же `summary.csv`/`aggregate_mean_std.csv`/
`paired_comparisons.csv`, что и для остальных режимов.

## Критерии готовности

- `graph_mst` запускается через `run_once`/`run_experiments` наравне с
  остальными режимами и не ломает существующие тесты (54 текущих + новые).
- Юнит-тесты на `mst_route` проходят.
- Полный прогон `run_experiments` с добавленным `graph_mst` завершается без
  ошибок и производит `summary.csv` со строками для `graph_mst`.
