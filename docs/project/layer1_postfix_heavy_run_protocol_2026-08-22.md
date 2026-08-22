# Протокол post-fix heavy run layer1

Дата: 2026-08-22.

Статус: **готовится новый post-fix прогон; pre-fix результаты от 2026-08-21 не использовать как финальные**.

## Цель нового прогона

Получить честную regime-map серию после исправления `lawnmower_collect`:

- бюджеты пути: `1200`, `2400`, `3600`, `7200 м`;
- сценарии: `static_calm`, `weak_drift`, `strong_drift`, `robot_disturbed`;
- режимы: `lawnmower_collect`, `greedy`, `confirmed_route`, `belief_horizon`, `belief_orienteering`, `belief_orienteering_depth1`, `adaptive_mission`, `oracle_current_physics`;
- seed-ы для calibration/pre-final: `100-129`, если запускаем сразу 30 seed;
- основной ресурс сравнения: `path_budget_m`, не `time_budget`.

Ожидаемый размер:

```text
4 budgets * 4 scenarios * 8 modes * 30 seeds = 3840 runs
```

## Gate перед запуском

Перед тяжелым запуском обязательно:

```powershell
git status --short --branch --untracked-files=no
python -m pytest -q
python -m cleanup_sim_v2.run_layer1 --help
python -m cleanup_sim_v2.validate_layer1 --help
python -m cleanup_sim_v2.merge_layer1 --help
```

`git status --untracked-files=no` должен быть чистым. Локальные `out/`-папки можно игнорировать, но tracked-файлы должны быть закоммичены.

## Preflight

Preflight должен проверять всю матрицу режимов/сценариев, но с малым числом seed-ов.

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase calibration `
  --budgets 1200 7200 `
  --seed-start 100 `
  --seeds 1 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes lawnmower_collect greedy confirmed_route belief_horizon belief_orienteering belief_orienteering_depth1 adaptive_mission oracle_current_physics `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/layer1_postfix_preflight_2026-08-22
```

Preflight считается пройденным, если:

- runner завершился без `SystemExit`;
- создан `validation_issues.csv`;
- нет `major` и `blocker`;
- `lawnmower_collect` не имеет нулевого сбора на `7200 м`;
- `time_budget` у non-oracle равен `0`;
- `git_dirty` в summary равен `False`.

## Локальный heavy run

Один большой запуск:

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase calibration `
  --budgets 1200 2400 3600 7200 `
  --seed-start 100 `
  --seeds 30 `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/layer1_postfix_heavy_2026-08-22
```

Если процесс оборвался:

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase calibration `
  --budgets 1200 2400 3600 7200 `
  --seed-start 100 `
  --seeds 30 `
  --checkpoint `
  --resume `
  --fail-on major `
  --out-root out/cleanup_sim_v2/layer1_postfix_heavy_2026-08-22
```

## Распределенный запуск на нескольких машинах

Использовать независимые chunk-и по seed-диапазонам. Не нужен настоящий кластер: каждая машина считает свой диапазон seed-ов на одном и том же commit.

Пример для машины 0:

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase calibration `
  --budgets 1200 2400 3600 7200 `
  --seed-start 100 `
  --seeds 3 `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/layer1_postfix_chunk_00_2026-08-22
```

Машина 1:

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase calibration `
  --budgets 1200 2400 3600 7200 `
  --seed-start 103 `
  --seeds 3 `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/layer1_postfix_chunk_01_2026-08-22
```

Дальше: `106`, `109`, ..., пока не закрыт диапазон `100-129`.

## Merge chunks

После переноса chunk-папок на одну машину:

```powershell
python -m cleanup_sim_v2.merge_layer1 `
  out/cleanup_sim_v2/layer1_postfix_chunk_00_2026-08-22/layer1_postfix_budget_calibration_2026-08-22 `
  out/cleanup_sim_v2/layer1_postfix_chunk_01_2026-08-22/layer1_postfix_budget_calibration_2026-08-22 `
  out/cleanup_sim_v2/layer1_postfix_chunk_02_2026-08-22/layer1_postfix_budget_calibration_2026-08-22 `
  --out-dir out/cleanup_sim_v2/layer1_postfix_heavy_merged_2026-08-22 `
  --budgets 1200 2400 3600 7200 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes lawnmower_collect greedy confirmed_route belief_horizon belief_orienteering belief_orienteering_depth1 adaptive_mission oracle_current_physics `
  --seed-start 100 `
  --seeds 30 `
  --fail-on major
```

Merge создает:

- `summary.csv`;
- `summary_enriched.csv`;
- `aggregate_mean_std.csv`;
- `paired_comparisons_by_budget.csv`, если есть `adaptive_mission`;
- `budget_calibration_decision.csv`;
- `budget_decision.json`;
- `validation_issues.csv`;
- `validation_summary.json`;
- `merge_manifest.json`.

## Отдельный adaptive trace

Так как текущий `adaptive_mission` часто вырождается в `belief_horizon`, trace обязателен.

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase trace `
  --budget 1200 `
  --seed-start 100 `
  --seeds 5 `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/layer1_postfix_adaptive_trace_1200_2026-08-22
```

Повторить для `7200`, если heavy run покажет, что adaptive выглядит сильным при длинном бюджете.

## Validation checks

Автоматический validator проверяет:

- полноту матрицы budget/scenario/mode/seed;
- дубликаты;
- обязательные колонки;
- границы `collected_ratio`, AUC, precision/recall;
- `auc_collected_by_path <= collected_ratio`;
- согласованность `done` и полного сбора;
- отсутствие недопустимого `time_budget`;
- `successful_captures == collected`;
- `oracle_current_physics` не хуже non-oracle на тех же seed;
- `regret_to_best_fixed_*` не отрицателен;
- oracle не имеет `regret_to_best_fixed_*`;
- near-zero collection как warning;
- вырождение `adaptive_mission` в `belief_horizon` как warning.

## Что считается успешной подготовкой данных

Данные можно анализировать для статьи только если:

1. `summary.csv` содержит `3840` строк.
2. `validation_summary.json` показывает `has_major_or_blocker = false`.
3. `budget_calibration_decision.csv` сформирован post-fix runner-ом.
4. В `run_manifest.json` один commit и `git_dirty = false`.
5. Нет смешивания с `layer1_budget_calibration_2026-08-21`.
6. Если `adaptive_mission` почти всегда равен `belief_horizon`, это фиксируется как результат, а не скрывается.

## Как интерпретировать следующий результат

Новый heavy run не обязан выбрать один nominal budget. Если gate снова не выберет бюджет, это не провал, а подтверждение, что статья должна строиться как regime-map:

> выбор режима миссии зависит от нормированного дефицита пути, динамики мусора, свежести целей и физической ширины сборщика.

Если один budget пройдет gate, его можно использовать как основной baseline-срез, а остальные бюджеты оставить как sensitivity по ресурсу пути.
