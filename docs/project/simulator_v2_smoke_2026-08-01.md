# Smoke v2: 3 seeds x 4 scenarios x 4 modes

Дата: 2026-08-01.

Команда:

```powershell
python -m cleanup_sim_v2.run_experiments `
  --seeds 3 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes coverage greedy active confirmed_route `
  --out-dir out\cleanup_sim_v2\smoke_v2_3seeds
```

Результат: 48 прогонов завершились за 284 секунды, примерно 5.9 секунды на прогон.

## Агрегаты

| scenario | mode | collected_ratio | empty_goal_arrivals | collection_precision | detection_precision |
|---|---:|---:|---:|---:|---:|
| robot_disturbed | active | 0.078 | 148.333 | 0.704 | 0.943 |
| robot_disturbed | confirmed_route | 0.689 | 228.333 | 0.656 | 0.965 |
| robot_disturbed | coverage | 0.042 | 390.333 | 0.739 | 0.916 |
| robot_disturbed | greedy | 0.204 | 148.000 | 0.753 | 0.904 |
| static_calm | active | 0.004 | 173.000 | 0.667 | 0.965 |
| static_calm | confirmed_route | 0.413 | 242.000 | 0.645 | 0.935 |
| static_calm | coverage | 0.064 | 386.000 | 0.722 | 0.940 |
| static_calm | greedy | 0.364 | 154.667 | 0.777 | 0.955 |
| strong_drift | active | 0.044 | 132.000 | 0.734 | 0.901 |
| strong_drift | confirmed_route | 0.969 | 157.000 | 0.619 | 0.958 |
| strong_drift | coverage | 0.004 | 396.667 | 0.167 | 0.898 |
| strong_drift | greedy | 0.487 | 126.000 | 0.690 | 0.914 |
| weak_drift | active | 0.084 | 144.333 | 0.749 | 0.953 |
| weak_drift | confirmed_route | 0.551 | 226.000 | 0.686 | 0.949 |
| weak_drift | coverage | 0.053 | 389.000 | 0.727 | 0.916 |
| weak_drift | greedy | 0.351 | 146.667 | 0.644 | 0.920 |

## Интерпретация

Это **smoke**, а не научный результат. Его задача - проверить, что новая модель запускается, считает физический сбор и выдает диагностические метрики. По этим числам нельзя делать вывод о превосходстве алгоритмов.

Важные наблюдения:

- `empty_goal_arrivals` теперь считается для всех стратегий, включая `greedy`.
- `coverage` больше не получает бесплатный сбор полосой 10 м, поэтому при ширине захвата 1 м собирает мало за тот же бюджет.
- `active` в текущем виде слабый: это ожидаемо, потому что алгоритмы еще не переработаны под v2.
- `confirmed_route` местами слишком силен, особенно в `strong_drift`; это признак, что sensor/target confirmation параметры требуют калибровки до финального эксперимента.
- Производительность достигла целевого порядка: средний single run меньше 10 секунд.

## Следующие проверки

- Калибровка sensor clutter / `p_detect_max` по источникам и sensitivity.
- Sensitivity по `collection_width_m`, `capture_probability`, `collection_speed_mps`.
- Новая разработка planning-алгоритмов уже под v2, а не перенос старого `hybrid` без изменений.
