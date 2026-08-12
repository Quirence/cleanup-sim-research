# План: pre-final 10-seed прогон belief_horizon/belief_orienteering по всем 4 сценариям

Дата: 2026-08-13

## Зачем именно это и именно сейчас

Собственная документация проекта фиксирует статус `cleanup_sim_v2` как
`READY FOR ALGORITHM DESIGN`, `NOT READY FOR FINAL CONFIRMATORY RUN`
(`simulator_v2_1_closure_report.md`). Decision gate для алгоритма уже
сформулирован в `algorithm_implementation_roadmap_2026-08-02.md`:

> если `belief_horizon` лучше `greedy` хотя бы в части сценариев по
> paired-seed метрикам — развиваем его; если он только равен `greedy`, но
> снижает пустые визиты/путь — можно писать статью как trade-off analysis;
> если он хуже `greedy` по всем ключевым метрикам — не подгоняем веса
> вслепую, а переходим к `pareto_horizon` или усиливаем adaptive coverage.

Всё, что реально проверено на сегодня — `belief_orienteering_initial_report_2026-08-02.md`,
10 seed, только `static_calm`/`weak_drift`. `strong_drift` и `robot_disturbed`
**ни разу не проверялись** ни для `belief_horizon`, ни для `belief_orienteering`
на сколько-нибудь надёжном числе seed — только в разовом 3-seed
all-modes sweep. Собственный вывод отчёта: *"Нельзя заявлять финальное
статистическое превосходство над `belief_horizon`: 10 seed недостаточно, а
CI включает ноль."*

Поэтому следующий осмысленный шаг — не сразу 30-seed "финал" (это было бы
дорого и преждевременно, если что-то поедет не так на новых сценариях), а
**10-seed pre-final по всем 4 сценариям сразу**, с ablation-режимами обеих
belief-семей, чтобы:

1. увидеть, держится ли текущее преимущество `belief_orienteering` над
   `belief_horizon`/`greedy` на `strong_drift`/`robot_disturbed`, а не
   только на "лёгких" `static_calm`/`weak_drift`;
2. подтвердить, что абляции (`belief_horizon_no_efficiency` и т.д.) всё ещё
   осмысленно проседают на новых сценариях, а не только на тех двух, где их
   уже проверяли.

## Состав прогона

Профиль — `nominal` (дефолтный, "заморожен" по умолчанию; sensitivity по
`low`/`high` — отдельный следующий шаг, не в этой команде).

Режимы (12): 3 baseline + 2 кандидата + 6 абляций + 1 oracle.

- `lawnmower_collect`, `greedy`, `confirmed_route` — baseline;
- `belief_horizon`, `belief_orienteering` — кандидаты;
- `belief_horizon_no_efficiency`, `belief_horizon_no_track_prediction`,
  `belief_horizon_no_refinement` — абляции `belief_horizon`;
- `belief_orienteering_depth1`, `belief_orienteering_no_opportunity_cost`,
  `belief_orienteering_density_disabled` — абляции `belief_orienteering`;
- `oracle_current_physics` — верхняя граница, нужна для авто-расчёта
  `oracle_gap_*` колонок в `run_experiments.py`.

Осознанно исключены: `lawnmower_survey`/`coverage` (чисто разведочные,
`collected_ratio` всегда `0`, не несут сигнала для этого сравнения),
`active` (помечен как legacy/черновой режим), `belief_cluster_route`
(промежуточный шаг перед `belief_orienteering`, не входит в decision gate
роадмапа), `oracle_perfect_static`/`oracle_route_heuristic` (не нужны для
`oracle_gap`, `oracle_current_physics` — основной верхний ориентир).

Сценарии — все 4: `static_calm weak_drift strong_drift robot_disturbed`.

Seeds — 10 (pre-final, не 30 — сознательно дешевле; если результат
подтвердит гипотезу, следующим шагом будет 30-seed confirmatory на этом же
составе режимов).

Бюджет — не переопределяется (`--max-path-m`/`--tmax-s` не заданы),
используются дефолты `PlatformConfig` (`max_path_m=3600`, `tmax_s=5400`) —
тот же бюджет, что уже использовался в `belief_scout_spacing_report`/
`belief_horizon_efficiency_diagnosis`.

Итого: `12 режимов × 4 сценария × 10 seed = 480 прогонов`. По замерам на
этой машине (по одиночным прогонам varies `~0.6`-`~11` с на прогон, у
`belief_orienteering` дороже всего из-за beam-search) — ожидаемое время
**около 30-50 минут**, сильно зависит от машины. `--checkpoint` добавлен,
чтобы не потерять прогресс при прерывании; при необходимости можно
перезапустить с `--resume` на тот же `--out-dir`.

## Команда

```powershell
python -m cleanup_sim_v2.run_experiments `
  --seeds 10 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes lawnmower_collect greedy confirmed_route belief_horizon belief_horizon_no_efficiency belief_horizon_no_track_prediction belief_horizon_no_refinement belief_orienteering belief_orienteering_depth1 belief_orienteering_no_opportunity_cost belief_orienteering_density_disabled oracle_current_physics `
  --checkpoint `
  --out-dir out/cleanup_sim_v2/prefinal_10seed_all_scenarios_2026-08-13
```

Bash/Linux-эквивалент (без обратного апострофа для переноса строк):

```bash
python -m cleanup_sim_v2.run_experiments \
  --seeds 10 \
  --scenarios static_calm weak_drift strong_drift robot_disturbed \
  --modes lawnmower_collect greedy confirmed_route belief_horizon belief_horizon_no_efficiency belief_horizon_no_track_prediction belief_horizon_no_refinement belief_orienteering belief_orienteering_depth1 belief_orienteering_no_opportunity_cost belief_orienteering_density_disabled oracle_current_physics \
  --checkpoint \
  --out-dir out/cleanup_sim_v2/prefinal_10seed_all_scenarios_2026-08-13
```

Если прервётся на середине, продолжить без пересчёта уже готового:

```bash
python -m cleanup_sim_v2.run_experiments \
  --seeds 10 \
  --scenarios static_calm weak_drift strong_drift robot_disturbed \
  --modes lawnmower_collect greedy confirmed_route belief_horizon belief_horizon_no_efficiency belief_horizon_no_track_prediction belief_horizon_no_refinement belief_orienteering belief_orienteering_depth1 belief_orienteering_no_opportunity_cost belief_orienteering_density_disabled oracle_current_physics \
  --checkpoint --resume \
  --out-dir out/cleanup_sim_v2/prefinal_10seed_all_scenarios_2026-08-13
```

## Что смотреть по результату (когда прогон завершится)

Файлы в `--out-dir`: `summary.csv` (480 строк), `aggregate_mean_std.csv`,
`run_manifest.json`.

Ключевые метрики для decision gate: `collected_ratio`, `oracle_gap_collected_ratio`,
`auc_collected_by_path`, `empty_goal_arrivals_per_km`, `wasted_path_ratio`,
paired по `(scenario, seed)` сравнение `belief_orienteering` против `greedy`
и против `belief_horizon`.

## Следующие шаги после этого прогона (не в этой команде)

1. Sensitivity по `--profile low`/`--profile high` (те же режимы/сценарии,
   меньше seed — 5 достаточно для sensitivity, не для confirmatory).
2. Если pre-final подтверждает гипотезу на всех 4 сценариях (или явно и
   стабильно только на части — тоже валидный, просто более узкий вывод) —
   30-seed confirmatory на этом же составе режимов, с заморозкой параметров
   до запуска.
3. Пересчёт `docs/article/stage1/stage2` под архитектуру v2.1 (отдельное
   решение о содержании статьи, не автоматическое).
