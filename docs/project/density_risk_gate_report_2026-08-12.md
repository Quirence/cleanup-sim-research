# Density Risk Gate Report

Дата: 2026-08-12.

## Цель

Проверить гипотезу:

> В статическом кластерном сценарии `belief_horizon` проседает из-за пустых поездок к неподтвержденным density-целям; если ограничить такие цели по ожидаемой пользе на метр, итоговый сбор должен вырасти.

## Реализация

Добавлен отдельный режим:

```text
belief_horizon_density_risk_gate
```

Базовый `belief_horizon` не изменен.

В `PlannerConfig` добавлены параметры:

- `belief_density_risk_gate_enabled`;
- `belief_density_gate_min_expected_collection`;
- `belief_density_gate_min_expected_per_m`;
- `belief_density_gate_min_benefit_per_m`;
- `belief_density_gate_penalty_weight`;
- `belief_density_gate_hard_reject_expected`;
- `belief_density_gate_hard_reject_benefit_per_m`;
- `belief_density_gate_hard_reject_effort_m`.

## Calibration From Diagnostics

По старым `events.csv` для `static_calm`, `belief_horizon`, 3000 m, 10 seed:

- density-целей: 259;
- empty rate: 0.788;
- суммарный сбор на density-целях: 62 объекта;
- суммарный путь на density-целях: 7616 m.

`score_expected_collection` отделял пустые цели плохо. Более информативным оказался показатель expected collection per meter.

Низкоэффективные density-заезды действительно имели очень низкий сбор на метр, но часть полезных ранних переходов к кластерам тоже выглядела рискованной по тем же признакам.

## Version A: Hard Gate

Первый вариант жестко отбрасывал density-кандидаты, если они не проходили пороги expected collection / expected per meter / benefit per meter.

Команда:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 10 --scenarios static_calm weak_drift --modes greedy belief_horizon belief_horizon_density_risk_gate oracle_current_physics --max-path-m 3000 --tmax-s 30000 --out-dir out\cleanup_sim_v2\density_risk_gate_3000m_10seed_2026-08-12 --checkpoint
```

Результат:

| Scenario | Base `belief_horizon` | Hard gate | Delta | Wins vs base |
|---|---:|---:|---:|---:|
| `static_calm` | 0.453 | 0.398 | -0.055 | 2/10 |
| `weak_drift` | 0.637 | 0.545 | -0.093 | 4/10 |

Вывод: hard gate резко снижает density-wasted-path, но ухудшает сбор. Особенно плохо, что в `weak_drift` появились катастрофические seed-ы.

## Version B: Soft Penalty

Второй вариант заменил жесткое отсечение на штраф за низкую ожидаемую пользу на метр. Жесткий reject оставлен только для совсем слабых дальних density-кандидатов.

Команда:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 10 --scenarios static_calm weak_drift --modes greedy belief_horizon belief_horizon_density_risk_gate oracle_current_physics --max-path-m 3000 --tmax-s 30000 --out-dir out\cleanup_sim_v2\density_risk_penalty_3000m_10seed_2026-08-12 --checkpoint
```

Результат:

| Scenario | Base `belief_horizon` | Soft gate | Delta | Wins vs base |
|---|---:|---:|---:|---:|
| `static_calm` | 0.453 | 0.407 | -0.045 | 4/10 |
| `weak_drift` | 0.637 | 0.641 | +0.004 | 5/10, 3 ties |

Secondary metrics:

| Scenario | Mode | Density wasted path | Wasted path | Goal success |
|---|---|---:|---:|---:|
| `static_calm` | base | 0.195 | 0.528 | 0.356 |
| `static_calm` | soft gate | 0.154 | 0.553 | 0.315 |
| `weak_drift` | base | 0.190 | 0.412 | 0.382 |
| `weak_drift` | soft gate | 0.097 | 0.400 | 0.354 |

Вывод: soft gate исправляет локальную метрику `density_wasted_path_ratio`, но не улучшает главную метрику в static. Он почти нейтрален в weak drift, но этого недостаточно.

## Scientific Interpretation

Гипотеза в простой форме не подтвердилась.

Да, density-кандидаты часто пустые. Но они выполняют две функции:

1. иногда являются плохими целями для физического сбора;
2. иногда являются нужным мостом к обнаружению нового кластера.

Простой gate умеет подавлять первую функцию, но одновременно ломает вторую. Поэтому проблема static не сводится к “меньше ездить к density”. Нужен более контекстный механизм.

## Revised Hypothesis

Более правдоподобная гипотеза:

> В static-режиме алгоритм должен использовать density-карту для выхода к областям мусора, но после первого успешного сбора должен переключаться в короткий локальный режим эксплуатации найденного кластера. Основной проигрыш oracle связан не только с пустыми density-заездами, а с недостаточным добором внутри уже найденной области.

## What Not To Claim

Нельзя заявлять, что density risk gate улучшает static-сбор. Он этого не делает.

Можно заявить как диагностический результат:

> Простое ограничение неподтвержденных вероятностных целей снижает путь, потраченный на density-кандидаты, но ухудшает или не улучшает итоговый сбор, поскольку density-карта также играет роль механизма выхода к новым кластерам.

## Next Candidate

Следующий кандидат:

```text
belief_horizon_local_exploit
```

Ключевая идея:

- не запрещать density-карту глобально;
- после успешного сбора проверить локальную область;
- если рядом есть поддержка от карты/треков, выполнить одно короткое локальное действие;
- после одного действия снова пересчитать карту и вернуться к обычному `belief_horizon`.

Acceptance:

- `static_calm`, 3000 m: прирост не меньше `+0.03` к базовому `belief_horizon`;
- wins vs base не меньше `7/10`;
- `weak_drift` не хуже `-0.02`;
- `wasted_path_ratio` не выше базы более чем на `0.03`.

## Verification

```powershell
python -m pytest -q
```

Результат:

```text
45 passed
```

