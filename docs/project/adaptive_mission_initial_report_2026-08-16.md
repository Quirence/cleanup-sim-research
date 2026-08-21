# Adaptive mission: первичная реализация и диагностический smoke

Дата: 2026-08-16.

Статус: реализован технический каркас `adaptive_mission`, но результат еще не является финальным экспериментом для статьи. Текущие числа нужно рассматривать как диагностические: они помогают понять, есть ли смысл развивать идею адаптивного переключения, но не заменяют pre-final и final серию.

Уточнение после пересборки научного направления: `adaptive_mission` не должен подаваться как алгоритм, который обязан превосходить все baseline-ы. В текущей постановке это прототип **переключателя режимов миссии**, который должен проверяться через режимные показатели из `mission_regime_analysis_direction_2026-08-16.md`: дрейф, неопределенность цели, ложные обнаружения, плотность свежих подтверждений, пустые визиты и разрыв до oracle.

## Что реализовано

Добавлены режимы планирования:

- `adaptive_mission`;
- `adaptive_mission_no_route`;
- `adaptive_mission_no_orienteering`;
- `adaptive_mission_no_local_exploit`;
- `adaptive_mission_no_hysteresis`.

`adaptive_mission` выбирает между четырьмя примитивами:

- `belief_horizon` - свободная разведка и сбор по вероятностной density-map;
- `belief_orienteering` - короткий receding-horizon маршрут по вероятным целям;
- `confirmed_route` - маршрут по свежим подтвержденным целям;
- `local_exploit` - локальный сборочный проход по подтвержденной плотной области.

Выбор выполняется через единую utility-функцию, а не через прямое сравнение внутренних score разных планировщиков. В utility входят ожидаемый физический сбор, последующая маршрутная польза, информационный выигрыш, число и свежесть подтвержденных целей, штраф за путь, риск пустого визита, старение цели и риск дрейфа.

## Дисциплина без oracle-доступа

Для `adaptive_mission` добавлены тесты, проверяющие, что не-oracle режим не использует истинное поле мусора, `source_index` или координаты объектов напрямую. Предпросмотр кандидатов выполняется на копиях `PlannerState` и `TargetQueue`, чтобы оценка альтернатив не изменяла фактическое состояние планировщика.

`field` передается в `choose_goal()` только для существующих oracle-режимов и старых интерфейсов, но `adaptive_mission` не должен зависеть от его содержимого.

## Интерфейсы и воспроизводимость

Добавлено:

- CLI-поддержка всех `adaptive_mission*` режимов;
- аргумент `--seed-start` в `run_experiments`;
- запись `seed_start` в `run_manifest.json`;
- автоматическое формирование `paired_comparisons.csv`, если в серии есть `adaptive_mission`;
- расширенные поля в `events.csv`:
  - `adaptive_selected_policy`;
  - `adaptive_confirmed_count`;
  - `adaptive_fresh_confirmed_count`;
  - `adaptive_density_signal`;
  - `adaptive_drift_speed_mps`;
  - `adaptive_switch_margin_used`;
  - `adaptive_score_*` для рассмотренных политик.

## Проверки

Выполнено:

```powershell
python -m pytest -q
```

Результат: все тесты прошли.

Покрыты unit/regression проверки:

- выбор `belief_horizon`, когда нет подтвержденных целей;
- выбор `confirmed_route` при свежих подтвержденных целях и дрейфе;
- выбор `belief_orienteering`, когда короткий маршрутный горизонт дает лучшую unified utility;
- hysteresis против частых переключений;
- preview без мутации состояния;
- отсутствие oracle-доступа у `adaptive_mission`;
- CLI `--seed-start`;
- создание `paired_comparisons.csv`.

## Диагностический smoke

Основной smoke:

```powershell
python -m cleanup_sim_v2.run_experiments `
  --seeds 2 `
  --seed-start 0 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes greedy confirmed_route belief_horizon belief_orienteering adaptive_mission oracle_current_physics `
  --max-path-m 3600 `
  --tmax-s 12000 `
  --checkpoint `
  --out-dir out/cleanup_sim_v2/adaptive_mission_smoke_2seed_final_2026-08-16
```

Прогон уперся в лимит времени и завершил 45 из 48 строк. Недостающий хвост `robot_disturbed` был догнан отдельно:

```powershell
python -m cleanup_sim_v2.run_experiments `
  --seeds 2 `
  --seed-start 0 `
  --scenarios robot_disturbed `
  --modes adaptive_mission oracle_current_physics `
  --max-path-m 3600 `
  --tmax-s 12000 `
  --checkpoint `
  --out-dir out/cleanup_sim_v2/adaptive_mission_smoke_2seed_robot_tail_2026-08-16
```

Объединенная диагностическая картина по 2 seed:

| Сценарий | greedy | confirmed_route | belief_horizon | belief_orienteering | adaptive_mission | oracle_current_physics |
|---|---:|---:|---:|---:|---:|---:|
| `static_calm` | 0.1479 | 0.1402 | 0.2569 | 0.2046 | **0.2806** | 0.7759 |
| `weak_drift` | 0.1179 | 0.2133 | 0.3600 | 0.3286 | **0.4076** | 0.7665 |
| `strong_drift` | 0.0587 | **0.5180** | 0.4617 | 0.3555 | 0.4617 | 0.7993 |
| `robot_disturbed` | 0.0763 | 0.2279 | 0.3407 | 0.3154 | **0.3511** | 0.7680 |

Метрика в таблице: `auc_collected_by_path`.

## Первичная научная интерпретация

На малой диагностической выборке `adaptive_mission` показывает лучшую AUC среди не-oracle режимов в 3 из 4 сценариев: `static_calm`, `weak_drift`, `robot_disturbed`. В `strong_drift` лучший результат дает `confirmed_route`, а `adaptive_mission` после drift-gate фактически удерживается на поведении `belief_horizon`.

Это не доказывает универсальное превосходство, но поддерживает более аккуратную научную гипотезу:

> при неполной и устаревающей информации полезно не выбирать один фиксированный режим, а контекстно переключаться между разведкой, коротким маршрутным горизонтом и маршрутизацией по подтвержденным целям; однако при выраженном дрейфе подтвержденные цели могут требовать более агрессивного сопровождения, чем текущая AUC-ориентированная версия переключателя.

Сильный дрейф остается главным спорным режимом. Это важный результат: он показывает границу применимости текущей версии, а не просто техническую ошибку.

## Trace выбранных политик

Дополнительно выполнен один `--save-runs` прогон для `adaptive_mission`:

```powershell
python -m cleanup_sim_v2.run_experiments `
  --seeds 1 `
  --seed-start 0 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes adaptive_mission `
  --max-path-m 3600 `
  --tmax-s 12000 `
  --save-runs `
  --checkpoint `
  --out-dir out/cleanup_sim_v2/adaptive_mission_policy_trace_seed0_2026-08-16
```

Распределение выбранных политик по событиям:

| Сценарий | `belief_horizon` | `confirmed_route` | `belief_orienteering` | `local_exploit` |
|---|---:|---:|---:|---:|
| `static_calm` | 416 | 20 | 8 | 18 |
| `weak_drift` | 498 | 0 | 4 | 6 |
| `strong_drift` | 498 | 0 | 0 | 0 |
| `robot_disturbed` | 529 | 0 | 12 | 4 |

Это важное ограничение первичной версии: `adaptive_mission` пока является консервативным селектором, который в большинстве ситуаций остается на `belief_horizon`. Наблюдаемый прирост в части сценариев не следует интерпретировать как доказательство сильной мета-стратегии. Для статьи это означает, что абляции обязательны: нужно показать, действительно ли редкие переключения дают вклад, или эффект связан с малой выборкой и особенностями seed.

## Что пока нельзя заявлять

Пока нельзя писать, что:

- `adaptive_mission` статистически превосходит baseline-ы;
- эффект устойчив на 30 seed;
- `adaptive_mission` закрывает разрыв до oracle;
- `local_exploit` уже доказал пользу;
- текущий переключатель оптимален или близок к оптимальному.

## Что делать дальше

Перед pre-final серией нужно:

1. Снизить стоимость прогона или запускать серии частями, потому что `2 seeds x 4 scenarios x 6 modes` уже оказался тяжелым.
2. Провести tuning только на seed `10-29`, не трогая параметры симулятора.
3. Запустить абляции `adaptive_mission_no_*`, чтобы понять, какой компонент реально дает вклад.
4. Проверить отдельный вариант для `strong_drift`: большее доверие маршрутизации по подтвержденным целям при высоком дрейфе, но без ухудшения AUC в спокойных сценариях.
5. Только после этого выполнять final seed `100-129`.

## Текущий verdict

`adaptive_mission` технически интегрирован и научно перспективен как гипотеза, но еще не готов как финальный результат статьи.

Вердикт к финальному 30-seed прогону: **NOT READY**.
