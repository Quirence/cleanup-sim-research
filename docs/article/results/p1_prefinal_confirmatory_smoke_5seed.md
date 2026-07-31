# P1 Pre-Final Confirmatory Smoke

Дата: 2026-07-31

Статус: диагностический smoke после закрытия P0/P1-ремонта. Это **не финальные результаты статьи**.

## Команда

```powershell
python -m cleanup_sim.run_confirmatory `
  --seeds 5 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --out-dir out\audit\p1_prefinal_confirmatory_smoke_5seed `
  --max-path-m 3000 `
  --tmax-s 6000
```

## Проверка Завершения

Все `105` запусков завершились по `path_budget`. Залипаний, `time_budget`-артефактов и неполного расхода бюджета не обнаружено.

## Средние Значения

| Scenario | Mode | Collected Ratio | AUC By Path | False Visits | Target Precision |
|---|---|---:|---:|---:|---:|
| clustered_base | lawnmower_sparse | 0.511 | 0.291 | 0.0 | 0.000 |
| clustered_base | lawnmower_dense | 0.663 | 0.254 | 0.0 | 0.000 |
| clustered_base | greedy | 0.803 | 0.447 | 0.0 | 0.000 |
| clustered_base | active | 0.465 | 0.333 | 0.0 | 0.000 |
| clustered_base | detected_tsp | 0.588 | 0.250 | 21.2 | 0.440 |
| clustered_base | hybrid_base | 0.640 | 0.373 | 25.2 | 0.379 |
| clustered_base | hybrid_final_v1 | 0.643 | 0.413 | 23.2 | 0.439 |
| clustered_noisy | lawnmower_sparse | 0.511 | 0.291 | 0.0 | 0.000 |
| clustered_noisy | lawnmower_dense | 0.663 | 0.254 | 0.0 | 0.000 |
| clustered_noisy | greedy | 0.569 | 0.329 | 0.0 | 0.000 |
| clustered_noisy | active | 0.485 | 0.307 | 0.0 | 0.000 |
| clustered_noisy | detected_tsp | 0.532 | 0.218 | 18.4 | 0.308 |
| clustered_noisy | hybrid_base | 0.485 | 0.307 | 0.0 | 0.000 |
| clustered_noisy | hybrid_final_v1 | 0.556 | 0.318 | 19.8 | 0.371 |
| uniform_base | lawnmower_sparse | 0.488 | 0.309 | 0.0 | 0.000 |
| uniform_base | lawnmower_dense | 0.643 | 0.317 | 0.0 | 0.000 |
| uniform_base | greedy | 0.613 | 0.331 | 0.0 | 0.000 |
| uniform_base | active | 0.331 | 0.217 | 0.0 | 0.000 |
| uniform_base | detected_tsp | 0.477 | 0.248 | 23.2 | 0.393 |
| uniform_base | hybrid_base | 0.433 | 0.240 | 21.4 | 0.368 |
| uniform_base | hybrid_final_v1 | 0.420 | 0.257 | 21.4 | 0.369 |

## Научный Вывод

`hybrid_final_v1` не является универсальным победителем:

- в `clustered_base` он лучше `detected_tsp`, `active`, `hybrid_base` и sparse coverage по AUC, но уступает `greedy` по collected ratio и AUC;
- в `clustered_noisy` он улучшает `hybrid_base` и `detected_tsp`, но уступает `lawnmower_dense` по collected ratio и `greedy` по AUC;
- в `uniform_base` он уступает `lawnmower_dense` и `greedy` по collected ratio и AUC.

Это означает, что финальная статья не должна заявлять:

> `hybrid_final_v1` превосходит все baseline-стратегии.

Более защитимая формулировка:

> Гибридное переключение между exploration и routing полезно для анализа trade-off между ранним сбором подтвержденных целей, ложными route-визитами и равномерным покрытием, однако его эффективность зависит от пространственного распределения мусора и качества подтверждения целей.

## Решение Перед Финальным Прогоном

Перед запуском 30 seed нужно согласовать один из вариантов:

1. Оставить `hybrid_final_v1` как заранее зафиксированный метод и писать статью как честное сравнительное исследование условий применимости.
2. Вернуться к проектированию hybrid-правила, потому что текущая версия недостаточно сильна относительно `greedy` и `lawnmower_dense`.
3. Сместить основной вклад с “hybrid лучше всех” на “симуляционный протокол и анализ trade-off route/explore/coverage”.

## Артефакты

- `out/audit/p1_prefinal_confirmatory_smoke_5seed/summary.csv`;
- `out/audit/p1_prefinal_confirmatory_smoke_5seed/aggregate_mean_std.csv`;
- `out/audit/p1_prefinal_confirmatory_smoke_5seed/paired_comparisons.csv`;
- `out/audit/p1_prefinal_confirmatory_smoke_5seed/experiment_config.json`.
