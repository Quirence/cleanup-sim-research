# Ablation pilot v1

Дата: 2026-07-11

Цель: проверить, является ли выигрыш `hybrid` следствием одного компонента active score или именно режима переключения exploration/routing.

Команда:

```powershell
python -m cleanup_sim.run_experiments --seeds 5 --scenarios clustered_base clustered_noisy uniform_base --modes active_entropy active_probability active_no_distance active hybrid --out-dir out/cleanup_sim/pilot_ablation_v1 --max-path-m 6000 --plot-examples
```

## Стратегии

- `active_entropy`: энтропия + штраф расстояния.
- `active_probability`: вероятность мусора + штраф расстояния.
- `active_no_distance`: полный active score без штрафа расстояния.
- `active`: полный active score.
- `hybrid`: active exploration + routing по подтвержденным целям.

## Сводные результаты

| scenario | mode | collected_ratio_mean | AUC path | Brier score |
|---|---|---:|---:|---:|
| clustered_base | hybrid | 0.924 | 0.612 | 0.0080 |
| clustered_base | active_probability | 0.756 | 0.489 | 0.0143 |
| clustered_base | active_no_distance | 0.747 | 0.475 | 0.0147 |
| clustered_base | active | 0.739 | 0.482 | 0.0148 |
| clustered_base | active_entropy | 0.692 | 0.453 | 0.0155 |
| clustered_noisy | hybrid | 0.824 | 0.482 | 0.0169 |
| clustered_noisy | active_no_distance | 0.680 | 0.411 | 0.0194 |
| clustered_noisy | active_probability | 0.677 | 0.408 | 0.0196 |
| clustered_noisy | active | 0.669 | 0.420 | 0.0190 |
| clustered_noisy | active_entropy | 0.617 | 0.392 | 0.0200 |
| uniform_base | hybrid | 0.864 | 0.500 | 0.0064 |
| uniform_base | active_probability | 0.567 | 0.343 | 0.0131 |
| uniform_base | active | 0.541 | 0.322 | 0.0129 |
| uniform_base | active_no_distance | 0.541 | 0.326 | 0.0128 |
| uniform_base | active_entropy | 0.487 | 0.308 | 0.0136 |

## Интерпретация

1. `hybrid` превосходит все active-ablation варианты во всех трех сценариях по `collected_ratio_mean` и AUC.

2. Лучший одиночный active-компонент зависит от сценария:
   - `clustered_base`: лучше всего `active_probability`;
   - `clustered_noisy`: по collected ratio немного лучше `active_no_distance`, по AUC лучше полный `active`;
   - `uniform_base`: лучше всего `active_probability`.

3. `active_entropy` является самым слабым active-вариантом во всех сценариях. Значит, одного информационного исследования карты недостаточно для задачи физического сбора.

4. Штраф расстояния не является единственным источником эффекта: `active_no_distance` иногда близок к full `active`, но все равно значительно уступает `hybrid`.

5. Выигрыш `hybrid` не сводится к настройке одного коэффициента active score. Основной вклад дает переход от pure active planning к маршрутизации по подтвержденным целям.

## Предварительный научный вывод

Для задачи сбора плавающего мусора вероятностное active mapping полезно, но недостаточно как самостоятельный режим. Наибольший эффект дает гибридная стратегия, которая использует active exploration для формирования карты и подтверждения целей, а затем переключается к target routing для физического сбора.

## Осторожность интерпретации

- Серия выполнена только на 5 seed; для статьи требуется 30 seed.
- Параметры hybrid пока не прошли sensitivity-анализ.
- `hybrid` сравнивался с active-ablation режимами, но не с полным набором coverage/TSP baseline-ов в этом файле; см. `pilot_hybrid_v2_suppression`.

