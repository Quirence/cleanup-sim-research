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

## Волна 3 — рефакторинг с реальным риском регрессии

- [x] 11. Вынести общую scoring-формулу (`benefit/effort - risk`) из
      belief-планировщиков в один переиспользуемый хелпер — была скопирована
      вручную в 7 местах и уже разошлась (см. пункт 2).
      **Готово** (`2b4c82d`). Проверено full suite (161/161) + численным
      diff'ом 12-строчного sweep (`belief_horizon`/`belief_orienteering`/
      `belief_cluster_route` x `weak_drift`/`strong_drift`, 2 seed) до/после
      через `git stash` — максимальное расхождение по всем 63 числовым
      колонкам `summary.csv`: `0.0`.
- [~] 12. Разбить `run_simulation` (432 строки, ~25 локальных аккумуляторов) на
      именованные шаги: sensing/track-update, goal-completion/suppression,
      сборка summary. **Частично готово** (`3008575`): вынесена сборка
      summary (~60 строк, чистая агрегация в конце функции, без
      loop-order побочных эффектов) в `_build_summary(...)`. Проверено
      full suite (161/161) + численным diff'ом 48-строчного sweep (6 режимов
      x 4 сценария x 2 seed) до/после через `git stash` — расхождение по
      всем 69 числовым колонкам: `0.0`.
      Два более рискованных блока (sensing/track-update и
      goal-completion/suppression, строки ~186-234 и ~404-489) **сознательно
      не тронуты** — они мутируют общее состояние внутри цикла с RNG-вызовами
      и зависят от порядка выполнения; извлекать их безопасно — отдельная,
      более осторожная задача, не блок в конце уже большой сессии.
- [~] 13. Ослабить связность `belief_cluster_route`/`belief_orienteering`,
      которые вызывают `next_belief_horizon` как fallback. **Пересмотрено
      после разбора кода — это не совсем баг.** `next_belief_horizon` внутри
      `next_belief_cluster_route`/`next_belief_orienteering` даёт не просто
      "запасной вариант на случай ошибки", а обязательный baseline-скор,
      с которым сравнивается специализированный маршрут/beam-search — это и
      есть механизм "receding-horizon с opportunity cost", ради которого эти
      режимы вообще существуют (см. `belief_orienteering_switch_margin`,
      `belief_orienteering_opportunity_cost_weight`). Убрать эту зависимость
      "чтобы легче тестировалось" — значит менять научное поведение
      алгоритма, а не рефакторить код; это решение не мне принимать
      односторонне в проходе по чистке репозитория. Что можно сделать
      безопасно (не сделано, кандидат на будущее): переименовать возвращаемое
      `fallback.mode`, когда `next_belief_cluster_route`/`next_belief_orienteering`
      реально отдают его как есть — сейчас в такие моменты `GoalDecision.mode`
      остаётся `"belief_horizon"`, а не `"belief_cluster_route"`/`"belief_orienteering"`,
      что может путать при чтении логов, но менять это без проверки, что
      никто не полагается на текущее значение в `events.csv`/метриках, тоже
      требует отдельной проверки, а не мгновенной правки.
      **Follow-up 2026-08-16:** безопасная часть закрыта: когда
      `belief_cluster_route` действительно выбирает собственный route/transect,
      события и `GoalDecision.mode` теперь пишут `belief_cluster_route`, а общая
      физика belief-целей явно поддерживает этот mode. Концептуальная зависимость
      от `next_belief_horizon` как opportunity-cost baseline остается осознанным
      архитектурным решением.
- [~] 14. `PlannerConfig` (71 поле, 55 `belief_*`) — рассмотреть вложенные
      суб-датаклассы. Инвазивный рефакторинг — по плану делать только если
      реально мешает, не превентивно. **Сознательно не делается.**
      **Follow-up 2026-08-16:** подтверждено как maintainability debt, не
      ошибка корректности и не блокер статьи/экспериментов.
- [x] 15. `GoalDecision.expected_value` — рассмотрено вместе с пунктом 11.
      **Решение: не переименовывать.** `simulation.py` пишет тот же ключ
      `"expected_value"` в события (persisted output column) — переименование
      только датакласс-поля развело бы одно и то же понятие на два имени, а
      переименование колонки — это изменение схемы вывода за рамками этого
      пункта. Вместо этого добавлена docstring-заметка на поле, поясняющая
      двойную семантику (заглушка для oracle/coverage/route, реальный
      mode-relative скор для belief_*) — второй вариант, который сама находка
      ревью и предлагала.
- [x] 16. `docs/article/stage1/`, `docs/article/stage2/` — решить: переписать под
      архитектуру v2.1 или явно пометить как "будет пересобрано после заморозки
      алгоритма". Это решение о содержании статьи, не инженерная правка — нужен
      отдельный разговор с пользователем, не будет сделано автоматически.
      **Готово follow-up 2026-08-16:** добавлен актуальный reframing
      `docs/article/stage1/stage1_reframing_after_prefinal_2026-08-16.md`;
      старые stage1/stage2 документы помечены как исторические/частично
      устаревшие и больше не являются источником истины для `cleanup_sim_v2`.
- [x] 17. `docs/project/` — расставлены пометки "historical" на файлах,
      которые описывают до-v2 состояние (`full_project_audit_2026-07-31.md`,
      `static_debris_and_density_scope.md`, `platform_sensor_parameter_notes.md`,
      `final_run_readiness_backlog.md`, `cleanup_manifest.md`); в
      `reproducibility_notes.md` дополнительно добавлена актуальная
      `cleanup_sim_v2`-команда рядом со старой (файл активно линкуется из
      README, просто пометкой не обойтись).
      **Готово** (`d915f60`).

Полный набор тестов после волны 3: 161 passed (без изменений количества —
эта волна не добавляла новых тестов, только рефакторинг), без изменений
численных результатов симуляции относительно волны 2 (проверено дважды
численным diff'ом реальных прогонов до/после через `git stash`).

Итог волны 3: пункты 11, 15, 17 закрыты; пункт 12 закрыт частично (самый
безопасный кусок); пункты 13 и 14 сознательно не делаются — 13 после
разбора кода оказался не багом, а решением об архитектуре, 14 явно
помечен "только если мешает".

## Не в плане

- `out/` 258 МБ локально — не проблема git-репозитория, локальная гигиена,
  оставить пользователю.
- Дублированный test-boilerplate в `test_cleanup_sim_v2.py` (~100-150 строк) —
  включить в волну 2 по мере добавления новых тестов на непокрытые модули,
  не выносить отдельным проходом ради самого рефакторинга.
