# План исправления находок ревью от 2026-08-12

Дата: 2026-08-13

Источник: [docs/project/repository_review_2026-08-12.md](repository_review_2026-08-12.md).
🔴 Critical (тесты абляций `belief_*`) уже закрыт коммитом `912d45a`.
Этот план закрывает 🟠 Important и 🟡 Minor.

Принцип выполнения: маленькие независимые коммиты, после каждого —
`pytest -q`. Пункты упорядочены от безопасных/механических к более крупным
рефакторам с реальным риском регрессии.

## Волна 1 — безопасные точечные фиксы (этот проход)

- [x] 1. `next_active` тихо использует одноразовый `PlatformConfig()`/`PlannerState()`
      на fallback-пути вместо реальных `platform`/`state`, которые уже есть в
      обоих вызывающих местах. Добавить параметры `platform`, `state` в сигнатуру,
      прокинуть их из `next_belief_horizon` (строка ~602) и `choose_goal`'s
      `active`-ветки (строка ~1526). Прямых тестов на `cleanup_sim_v2.next_active`
      нет (у `test_hybrid.py` — другая, legacy-функция), так что сигнатуру можно
      менять без риска сломать тесты; добавить один новый тест, что fallback
      использует переданный `platform`/`state`, а не дефолтный.
      (`cleanup_sim_v2/planners.py:139-160,602,1526`)
      **Готово** (`1b50b3e`, mutation-verified).

- [x] 2. Магические веса `0.35` (дважды в `belief_cluster_route`-скоринге) и `0.2`
      (в `_orienteering_leg_components` для target-кандидатов) — вынести в именованные
      поля `PlannerConfig` с сохранением текущих значений (без изменения поведения),
      снять двусмысленность "баг или задумано" явным именем/комментарием, а не
      гадать. Не трогать отдельный `belief_orienteering_density_prior_weight`
      (это уже именованный, другой концептуально путь — additive для density_peak).
      (`cleanup_sim_v2/planners.py:767,952,1209`, `cleanup_sim_v2/config.py`)
      **Готово** (`e2ed2d6`).

- [x] 3. Добавить `dev` в триггеры CI (`.github/workflows/tests.yml`), чтобы
      активная ветка разработки тоже проверялась, не только `main`.
      **Готово** (`1a9e0f2`).

- [x] 4. Обновить `README.md` и `README_WORKFLOW.md`: упомянуть `cleanup_sim_v2`
      как актуальный симулятор, `cleanup_sim` как legacy, актуализировать
      команду проверки и число тестов, убрать ссылки на устаревший
      `docs/article/stage2/stage2_repair_and_final_experiment_plan.md` как
      единственный источник истины.
      **Готово** (`f6f9d7d`).

- [x] 5. Ужесточить рыхлые assert-ы в `tests/test_cleanup_sim_v2.py`, отмеченные
      ревью (`in {"density_peak", "density_transect", "entropy_peak"}` и
      `"provisional_target" in kinds or "provisional_target_transect" in kinds`)
      — заменить на точное ожидаемое значение там, где сценарий уже это
      гарантирует.
      **Готово** (`3c3cd24`).

Волна 1 полностью закрыта. Полный набор тестов после волны 1: 123 passed.

## Волна 2 — новые тесты на непокрытые модули cleanup_sim_v2 (закрыта)

- [x] 6. `cleanup_sim_v2/metrics.py` — прямые тесты (`occupancy_from_count`,
      `map_quality`, `auc_by_path`, `value_at_path`, `sensor_metrics`); сейчас
      покрыт только косвенно через `np.isfinite(...)` в smoke-тестах.
      **Готово** (`30c43d0`, `tests/test_cleanup_sim_v2_metrics.py`).
- [x] 7. `cleanup_sim_v2/mapping.py` — прямые тесты `predict_density_map`,
      `update_density_map`, `entropy`, `visible_cell_mask`, `suppress_collected_area`.
      **Готово** (`f7c2bb3`, `tests/test_cleanup_sim_v2_mapping.py`).
- [x] 8. `cleanup_sim_v2/sensors.py` — прямые тесты `detect_with_suite`,
      `in_sensor_fov` (включая wrap на ±180°), `detection_probability`, `_sample_clutter`.
      **Готово** (`9f15cf5`, `tests/test_cleanup_sim_v2_sensors.py`).
- [x] 9. `cleanup_sim_v2/io.py` — тесты `git_commit`, `git_dirty`, `save_run`
      (сейчас покрыт только `config_hash`).
      **Готово** (`59864d2`, `tests/test_cleanup_sim_v2_io.py`; git_commit/git_dirty
      fallback-путь проверен реальным запуском вне git-репозитория, без mock).
- [x] 10. `cleanup_sim_v2/run_once.py` и реальный прогон `run_experiments()`
      (включая `--checkpoint`/`--resume`) — сейчас у `run_experiments` тестируется
      только argparse-поверхность.
      **Готово** (`503a673`, `tests/test_cleanup_sim_v2_cli_execution.py`).

Волна 2 полностью закрыта. Полный набор тестов после волны 2: 161 passed
(было 123 после волны 1; +10 metrics, +8 mapping, +10 sensors, +6 io,
+4 CLI execution = +38, финальное число подтверждено `pytest -q`).

## Волна 3 — рефакторинг с реальным риском регрессии (отдельный проход, не начинать без явного запроса)

- [ ] 11. Вынести общую scoring-формулу (`benefit/effort - risk`) из трёх
      belief-планировщиков в один переиспользуемый хелпер — сейчас
      скопирована вручную в 4+ местах и уже разошлась (см. пункт 2).
- [ ] 12. Разбить `run_simulation` (432 строки, ~25 локальных аккумуляторов) на
      именованные шаги: sensing/track-update, goal-completion/suppression,
      сборка summary.
- [ ] 13. Ослабить связность `belief_cluster_route`/`belief_orienteering`,
      которые вызывают `next_belief_horizon` как fallback — сейчас невозможно
      юнит-тестировать один режим в изоляции от другого.
- [ ] 14. `PlannerConfig` (71 поле, 55 `belief_*`) — рассмотреть вложенные
      суб-датаклассы (`BeliefHorizonConfig`, `OrienteeringConfig`,
      `ClusterRouteConfig`). Инвазивный рефакторинг, трогает много call sites —
      делать только если реально мешает, не превентивно.
- [ ] 15. `GoalDecision.expected_value` — переименовать/задокументировать (для
      oracle-режимов это заглушка `0.0`/`1.0`, для belief-режимов — реальный
      скор в произвольных единицах). Затрагивает `simulation.py` (логирование)
      и все `next_belief_*` — сделать вместе с пунктом 11, а не отдельно.
- [ ] 16. `docs/article/stage1/`, `docs/article/stage2/` — решить: переписать под
      архитектуру v2.1 (density/count-map, `belief_horizon`/`belief_orienteering`)
      или явно пометить как "будет пересобрано после заморозки алгоритма".
      Это решение о содержании статьи, не инженерная правка — нужен отдельный
      разговор с пользователем, не будет сделано автоматически в рамках этого плана.
- [ ] 17. `docs/project/` — расставить пометки "historical/superseded" на файлах,
      которые описывают до-v2 состояние (`full_project_audit_2026-07-31.md`,
      `static_debris_and_density_scope.md`, `platform_sensor_parameter_notes.md`,
      `reproducibility_notes.md`), аналогично уже помеченным
      `cleanup_manifest.md`/`final_run_readiness_backlog.md`.

## Не в плане

- `out/` 258 МБ локально — не проблема git-репозитория, локальная гигиена,
  оставить пользователю.
- Дублированный test-boilerplate в `test_cleanup_sim_v2.py` (~100-150 строк) —
  включить в волну 2 по мере добавления новых тестов на непокрытые модули,
  не выносить отдельным проходом ради самого рефакторинга.
