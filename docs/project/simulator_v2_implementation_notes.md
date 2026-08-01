# Simulator v2 Implementation Notes

Дата: 2026-08-01.

## Что добавлено

- Новый пакет `cleanup_sim_v2`, не заменяющий legacy `cleanup_sim`.
- `swept-aperture` модель сбора вместо кругового мгновенного радиуса.
- Object-level camera/radar-like detection model:
  - вероятность детекции зависит от расстояния и размера объекта;
  - ложные срабатывания задаются Poisson clutter;
  - события детекции имеют `source_index` только для синтетической оценки, planner его не использует.
- Лагранжева динамика мусора:
  - течение;
  - windage;
  - случайная диффузия;
  - простое отталкивание от робота для stress-сценария.
- Density/count-map вместо только binary occupancy.
- Общие метрики пустых целей для всех стратегий:
  - `empty_goal_arrivals`;
  - `wasted_path_to_empty_goals`;
  - `goal_success_rate`;
  - `route_false_visits` как частный случай;
  - `collection_precision`;
  - `detection_precision` / `detection_recall`.

## Команды

Одиночный запуск:

```powershell
python -m cleanup_sim_v2.run_once --scenario weak_drift --mode active --seed 0 --out-dir out/cleanup_sim_v2/run_once
```

Smoke-серия:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 3 --scenarios static_calm weak_drift strong_drift robot_disturbed --modes coverage greedy active confirmed_route --out-dir out/cleanup_sim_v2/smoke_v2
```

Baseline-серия:

```powershell
python -m cleanup_sim_v2.run_experiments --baseline-only --seeds 10 --max-path-m 3600 --tmax-s 9000 --out-dir out/cleanup_sim_v2/baseline_v2_10seeds_2026-08-01
```

Именованные baseline-режимы:

- `lawnmower_survey` - галсовое сенсорное обследование;
- `lawnmower_collect` - плотный физический сбор с шагом по ширине сборщика;
- `greedy` - жадное движение к максимуму текущей density-map.

## Текущий научный статус

`cleanup_sim_v2` - первая реализованная основа новой постановки, а не финальный симулятор для статьи. Ее задача сейчас:

1. убрать очевидно нереалистичный физический сбор;
2. сделать ложные цели измеримыми для `greedy` и остальных режимов;
3. открыть путь к честной калибровке параметров и sensitivity;
4. позволить заново разрабатывать алгоритмы уже на более строгой модели.

## Оставшиеся крупные задачи

- Уточнить численные параметры по статьям и datasheet-ам, перенести ссылки в методологию.
- Добавить физическую sensitivity-серию.
- Оптимизировать долгие серии после стабилизации модели.
- Разработать новые алгоритмы уже с учетом дрейфа, промахов захвата и object-level сенсоров.
