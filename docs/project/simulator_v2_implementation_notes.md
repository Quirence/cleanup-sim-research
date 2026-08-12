# Simulator v2.1 Implementation Notes

Дата обновления: 2026-08-01.

`cleanup_sim_v2` - текущая рабочая основа новой статьи. Старый `cleanup_sim` и ранние результаты v2 до v2.1 оставлены как legacy и не должны использоваться для финальных выводов.

## Что реализовано

- 2D-среда `200 x 200 м` без береговой линии и препятствий.
- Статическое или дрейфующее поле объектов мусора: clustered/uniform distribution, масса, размер и тип объекта.
- Упрощенная лагранжева динамика: течение, windage, стохастическая диффузия, опциональное отталкивание от робота.
- Object-level camera/radar-like сенсоры:
  - вероятность обнаружения зависит от расстояния и размера объекта;
  - ложные срабатывания моделируются как Poisson clutter;
  - `source_index` сохраняется только для синтетических метрик, не для planner-а.
- Density/count-map:
  - prediction step смещает и размывает карту по модели дрейфа;
  - detections добавляют локализованную интенсивность;
  - отсутствие наблюдения дает слабое отрицательное свидетельство.
- Физический сбор:
  - только в передней swept-aperture зоне;
  - сбор требует накопленного контакта/работы;
  - учитываются промахи, пропускная способность, емкость бункера и dwell-time у цели.
- Движение:
  - cruise speed и collection speed разделены;
  - есть простая цена разворота;
  - движение, дрейф и сбор считаются на физических подшагах.
- Планировщики и baseline:
  - `lawnmower_survey`;
  - `lawnmower_collect`;
  - `greedy`;
  - `active` как legacy/черновой режим;
  - `confirmed_route`;
  - `oracle_perfect_static`;
  - `oracle_current_physics`;
  - `oracle_route_heuristic`.
- Метрики:
  - collected ratio, AUC by path, fixed-distance ratios;
  - `empty_goal_arrivals_per_km`, `wasted_path_ratio`, `wasted_time_ratio`;
  - capture/contact metrics;
  - sensor-level precision/recall;
  - oracle-gap при наличии `oracle_current_physics` в той же серии.
- Reproducibility:
  - `summary.csv`;
  - `aggregate_mean_std.csv`;
  - `run_manifest.json`;
  - per-run `config_hash`, `git_commit` и `git_dirty`.

## Команды

Одиночный запуск:

```powershell
python -m cleanup_sim_v2.run_once --scenario weak_drift --mode greedy --seed 0 --out-dir out/cleanup_sim_v2/run_once
```

Smoke v2.1:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 3 --scenarios static_calm weak_drift strong_drift robot_disturbed --modes lawnmower_survey lawnmower_collect greedy confirmed_route oracle_current_physics --max-path-m 600 --tmax-s 1800 --out-dir out/cleanup_sim_v2/v2_1_smoke
```

Baseline-only:

```powershell
python -m cleanup_sim_v2.run_experiments --baseline-only --seeds 10 --max-path-m 3600 --tmax-s 9000 --out-dir out/cleanup_sim_v2/baseline_v2_10seeds
```

Oracle comparison:

```powershell
python -m cleanup_sim_v2.run_experiments --seeds 10 --scenarios static_calm weak_drift strong_drift robot_disturbed --modes greedy confirmed_route oracle_current_physics --max-path-m 3600 --tmax-s 9000 --out-dir out/cleanup_sim_v2/oracle_gap_10seeds
```

Тесты:

```powershell
python -m pytest -q
```

## Научный статус

v2.1 уже пригоден для проектирования новых алгоритмов и честного baseline-сравнения. Он еще не является финальным симулятором для статьи, потому что перед confirmatory run нужны:

- sensitivity по сборщику и сенсорам;
- заморозка параметров;
- paired-seed статистика будущего алгоритма против baseline;
- явное решение, добавляем ли отдельный сценарий навигационной ошибки.

Текущий вердикт: `READY FOR ALGORITHM DESIGN`, `NOT READY FOR FINAL 30-SEED CONFIRMATORY RUN`.
