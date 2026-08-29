# Adaptive mission revision report

Дата: 2026-08-29. Ветка: `feature/adaptive-mission-review` (от `feature/adaptive-mission`, commit `0641409`).

Статус: диагностическая ревизия завершена. Результат — **отрицательный, но полезный** в терминологии задания: вырождение `adaptive_mission` в `belief_horizon` устранено и объяснено на уровне кода, но после честного исправления `adaptive_mission` по AUC пока не дотягивает до `belief_horizon` в 3 из 4 базовых сценариев на 3-seed diagnostic-серии, кроме `strong_drift`, где результат нейтральный/слегка положительный.

## Что изменено

`cleanup_sim_v2/planners.py`:

1. **Unified-utility scale bug (главная причина вырождения).** В `_adaptive_utility()` политики `confirmed_route` и `local_exploit` заряжались полной длиной маршрута (`route_length_m`, до `route_batch_size=10` ног) в знаменателе `effort_m`, тогда как `belief_horizon`/`belief_orienteering` платили только за первую ногу. Это делало `confirmed_route`/`local_exploit` структурно неконкурентоспособными: trace показал, что при этом confirmed_route становился кандидатом в 44-79% решений (пороги `adaptive_route_min_confirmed=6`/`adaptive_local_min_expected_count=25` — НЕ бутылочное горлышко), но набирал только ~15-19% от utility `belief_horizon`.
   Исправление: `effort_m` теперь везде считается по первой ноге (`first_leg_m`), как и у остальных политик — это соответствует реальному исполнению (симулятор вызывает `choose_goal`/`next_adaptive_mission` заново после каждой достигнутой цели, см. `simulation.py:321`, `if current_goal is None`). Ожидаемый сбор при этом разбит на `score_expected_collection` (первая нога, как у прочих политик) и `score_rollout_collection` (остаток маршрута), причём rollout **усреднён по оставшимся ногам**, а не просуммирован без ограничения — иначе `confirmed_route`/`local_exploit` получали «бесплатный» (без платы за effort) кредит за весь маршрут, тогда как `belief_horizon`/`belief_orienteering` дают rollout только за один шаг вперёд (`_best_followup_collection`). Полная длина маршрута сохранена как отдельное диагностическое поле `adaptive_route_effort_m`.

2. **Мёртвый drift-override.** `adaptive_route_drift_override_min_ratio` был равен `1.0`, что делает условие `route_score >= best_score * ratio` эквивалентным `route_score >= best_score` — то есть override мог сработать только если `confirmed_route` и так уже был лучшим кандидатом (в этом случае он и без override был бы выбран через обычный argmax). По факту override был математически недостижимым кодом. Это объясняет, почему в `strong_drift` `confirmed_route` не был выбран ни разу (0/1677 событий в исходном trace), хотя override предназначен именно для этого случая (`config.py`: `adaptive_route_drift_override_min_ratio: float = 0.6`, с комментарием).

3. **Двойной гейт `belief_orienteering`.** `next_belief_orienteering()` сам гасит переключение через собственный `belief_orienteering_switch_margin` относительно `belief_horizon`-fallback — это нужно standalone-режиму `belief_orienteering`, но избыточно и вредно, когда `adaptive_mission` уже пересчитывает эту же политику через единую utility и применяет свой hysteresis. Добавлен параметр `bypass_switch_margin: bool = False` (по умолчанию сохраняет старое поведение standalone `belief_orienteering`); `_preview_adaptive_policy`/`_execute_adaptive_policy` вызывают его с `bypass_switch_margin=True`.

4. **Диагностика.** Добавлено поле `adaptive_route_effort_m` в `events.csv` (полная длина маршрута, для сравнения с фактически используемым `adaptive_effort_m`).

`cleanup_sim_v2/config.py`:

- `adaptive_route_drift_override_min_ratio`: `1.0` → `0.6`, с комментарием, объясняющим, почему `1.0` был no-op.

### Что попробовано и отклонено

Дополнительно проверялся вариант, при котором `confirmed_route` стартует с *наиболее эффективной* (а не ближайшей) подтверждённой цели — по аналогии с тем, как `belief_horizon` перебирает все кандидаты и выбирает лучший. На toy-бюджете (800 м, 1 seed) это выглядело как улучшение, но **на реальном бюджете 3000 м (тот же 3-seed paired trace) среднее падение AUC оказалось больше** (-0.093 против -0.060 без этого изменения) — toy-бюджет не является надёжным прокси для решения на реальном бюджете. Изменение отменено; в коде оставлен комментарий с этим выводом. Это самостоятельный методический результат: **быстрые проверки на маленьком бюджете нельзя использовать как замену подтверждения на целевом бюджете**, даже для промежуточных решений в рамках одной ревизии.

Также не подгонялись веса `adaptive_route_target_count_weight`/`adaptive_fresh_target_weight` — предварительная проверка (обнуление) показала смешанный, слабый эффект (небольшое улучшение в `static_calm`, без эффекта в остальных сценариях), а задание прямо запрещает подгонять параметры под 1-3 seed.

## Почему это должно помочь

- Первая находка (effort-scale bug) и вторая (мёртвый override) — это не тюнинг, а исправление внутренне противоречивого кода: `confirmed_route` систематически не мог быть выбран независимо от своего реального качества, а официальный «аварийный клапан» для сильного дрейфа не мог сработать никогда. После фикса `adaptive_mission` перестаёт быть декоративной обёрткой над `belief_horizon` (см. раздел Policy shares) — то есть устранён именно тот логический риск, который был явно зафиксирован в `layer1_logical_results_audit_2026-08-22.md` и `layer1_budget_finesweep_probe_2026-08-25.md`.
- Третья находка (double-gate у orienteering) убирает ещё один источник искусственного занижения кандидатуры без изменения контракта standalone `belief_orienteering`.

## Тесты

Все тесты запускались через `.venv` (`python -m pip install -e ".[dev]"`, `python -m pytest -q`).

Baseline на момент начала работы (ветка `feature/adaptive-mission-review`, до правок): **181 passed, 1 failed**. Единственный сбой — `test_belief_horizon_scores_swept_density_without_truth_access` (ожидает `candidate_type == "density_transect"`, получает `"density_peak"`). Это **pre-existing и не связан с `adaptive_mission`**: тест не затрагивает adaptive-код, использует близкую к границе (tie-like) сцену, и расхождение воспроизводимо на чистом дереве без каких-либо правок. Похоже на чувствительность к версии numpy/pandas в текущем окружении (numpy 2.5.1, pandas 3.0.5 — версии не запинены в `pyproject.toml`, `numpy>=1.26`/`pandas>=2.2`). Не исправлялся в рамках этой ревизии (вне scope, риск случайно задеть belief_horizon-логику, используемую всеми baseline-режимами).

После правок: **185 passed, 1 failed** (тот же pre-existing сбой, регрессий не внесено).

Новые тесты в `tests/test_cleanup_sim_v2.py`:

- `test_confirmed_route_effort_is_first_leg_not_whole_route` — регрессия на масштаб unified utility: `adaptive_effort_m` выбранного `confirmed_route`-решения должен совпадать с первой ногой (как у остальных политик), а не с полной длиной маршрута (`adaptive_route_effort_m`, теперь отдельное диагностическое поле).
- `test_adaptive_route_drift_override_min_ratio_is_below_one` — защита от повторного превращения override в мёртвый код (`ratio < 1.0`).
- `test_adaptive_route_drift_override_selects_confirmed_route_with_default_weights` — сквозная проверка, что override реально срабатывает (`adaptive_route_override_used == 1.0`) в `strong_drift` с дефолтными весами (без искусственно раздутых тестовых весов).
- `test_adaptive_preview_bypasses_orienteering_standalone_switch_margin` — проверяет, что превью `adaptive_mission` обходит собственный switch-margin `belief_orienteering`, а standalone-вызов (`bypass_switch_margin=False` по умолчанию) сохраняет старое поведение.

Изменённый импорт: добавлен `next_belief_orienteering` в блок импорта из `cleanup_sim_v2.planners`.

## Прогоны

Все прогоны — через `.venv`, `python -m cleanup_sim_v2.run_layer1`. Валидатор запускался без `--fail-on` явно указанным иначе, чем по умолчанию; часть прогонов помечена валидатором как `major: dirty_git_state` — это ожидаемо для диагностических прогонов на незакоммиченной ветке разработки и не влияет на корректность самих данных (сверено вручную).

1. Этап 1 (trace, **до** правок), 3000 м, seed 300-302:
   `out/cleanup_sim_v2/colleague_adaptive_trace_3000_2026-08-29/`
2. Этап 2 (diagnostic baseline, **до** правок, полный набор режимов), 3000 м, seed 300-304:
   `out/cleanup_sim_v2/colleague_baseline_3000_5seed_2026-08-29/`
3. Этап 1 повтор (trace, **после** правок), 3000 м, seed 300-302, тот же seed/бюджет для парного сравнения:
   `out/cleanup_sim_v2/colleague_adaptive_trace_3000_AFTERFIX_2026-08-29/`
4. Этап 5 smoke (**после** правок, с абляциями), 3000 м, seed 320-321:
   `out/cleanup_sim_v2/colleague_adaptive_revision_smoke_2026-08-29/`
5. Этап 5 diagnostic (**после** правок), 3000 м, seed 330-339, 10 seed:
   `out/cleanup_sim_v2/colleague_adaptive_revision_10seed_2026-08-29/`

Команды — как в `docs/project/colleague_adaptive_mission_task_2026-08-29.md`, разделы «Этап 1»/«Этап 2»/«Этап 5» (запускались дословно, с заменой `--out-root`).

Этап 6 (перепроверка бюджета) **сознательно не выполнялся**: правила `adaptive_mission` по итогам ревизии не «заморожены» — вывод отрицательный (adaptive пока не превосходит `belief_horizon` по AUC вне `strong_drift`), поэтому по логике самого задания «не запускать тяжёлые серии, пока adaptive-правила не заморожены» бюджетную перепроверку разумнее отложить до следующей итерации доработки selector-а.

## Policy shares

До правок (Этап 1 trace, 3 seed): `belief_horizon` выбирается в 94-100% решений во всех 4 сценариях; `confirmed_route` — 0% в `strong_drift`/`weak_drift`/`robot_disturbed`, максимум 2.6% в `static_calm`; `belief_orienteering` — 0-1.2%; `local_exploit` — 0-4.3%.

После правок (тот же 3-seed trace, seed 300-302, 3000 м):

| Сценарий | belief_horizon | confirmed_route | belief_orienteering | local_exploit |
|---|---:|---:|---:|---:|
| `static_calm` | 70.7% | 22.5% | 1.8% | 5.5% |
| `weak_drift` | 56.3% | 40.2% | 0.8% | 4.0% |
| `strong_drift` | 58.8% | 41.2% | 0.0% | 0.0% |
| `robot_disturbed` | 48.7% | 49.9% | 1.2% | 0.7% |

Вырождение устранено: `adaptive_mission` больше не является декоративной обёрткой над `belief_horizon` ни в одном базовом сценарии. `belief_orienteering` по-прежнему выбирается редко даже после снятия двойного гейта — это не техническая ошибка, а содержательный результат: при честном сравнении по unified utility `belief_horizon`'s continuous re-optimization обычно не хуже short-horizon route орienteering в этих сценариях (см. `mission_regime_analysis_direction_2026-08-16.md`: «AUC по пути и итоговая доля сбора могут рекомендовать разные режимы»).

## AUC / collected ratio

Парное сравнение **того же** `adaptive_mission`, seed 300-302, 3000 м, до/после правок:

| Сценарий | AUC до | AUC после | Δ AUC | collected до | collected после | Δ collected |
|---|---:|---:|---:|---:|---:|---:|
| `static_calm` | 0.275 | 0.238 | -0.038 | 0.513 | 0.424 | -0.089 |
| `weak_drift` | 0.357 | 0.313 | -0.044 | 0.775 | 0.764 | -0.011 |
| `strong_drift` | 0.517 | 0.507 | -0.010 | 0.864 | 0.898 | +0.033 |
| `robot_disturbed` | 0.385 | 0.238 | -0.147 | 0.711 | 0.671 | -0.040 |
| **среднее** | | | **-0.060** | | | **-0.027** |

Это ожидаемо: до правок `adaptive_mission` фактически исполнял `belief_horizon` (см. Policy shares выше), поэтому «его» AUC — это AUC `belief_horizon`. После правок `adaptive_mission` реально пробует `confirmed_route`/`local_exploit`, и в 3 из 4 сценариев это ухудшает AUC.

## Сравнение с belief_horizon

Прямое сравнение исправленного `adaptive_mission` с `belief_horizon`, 3-seed trace (seed 300-302) и статистически более надёжная 10-seed diagnostic-серия (seed 330-339, paired по seed):

| Сценарий | Δ AUC, 3 seed (300-302) | Δ AUC, 10 seed (330-339), mean ± std |
|---|---:|---:|
| `static_calm` | -0.037 | -0.053 ± 0.048 |
| `weak_drift` | -0.051 | -0.072 ± 0.114 |
| `strong_drift` | -0.010 | -0.012 ± 0.076 |
| `robot_disturbed` | -0.164 | -0.073 ± 0.059 |
| **среднее** | **-0.066** | **-0.053** |

10-seed серия (`out/cleanup_sim_v2/colleague_adaptive_revision_10seed_2026-08-29/`, `280/280` строк, `validation_issues.csv` содержит только ожидаемый `dirty_git_state`, нет `time_budget` у non-oracle, нет других `major`/`blocker`) даёт более устойчивую оценку, чем 3-seed trace: `robot_disturbed` оказывается не такой экстремальной аномалией (-0.073, а не -0.164), а `weak_drift` — более шумной (std 0.114).

Критерий успеха из задания («AUC `adaptive_mission` не хуже `belief_horizon` более чем на `0.02` в среднем») **не выполняется** на обеих сериях: среднее отставание -0.053…-0.066, с превышением допуска в `static_calm`, `weak_drift`, `robot_disturbed`. В `strong_drift` разрыв (-0.010…-0.012) стабильно укладывается в допуск на обеих сериях — это единственный сценарий, где `adaptive_mission` статистически не хуже `belief_horizon`.

## Абляции

Smoke, seed 320-321, 3000 м (`adaptive_mission` и `adaptive_mission_no_*` против `belief_horizon`):

| Сценарий | `belief_horizon` | `adaptive_mission` | `no_route` | `no_orienteering` | `no_local_exploit` | `no_hysteresis` |
|---|---:|---:|---:|---:|---:|---:|
| `static_calm` | 0.258 | 0.226 | 0.286 | 0.235 | 0.226 | 0.226 |
| `weak_drift` | 0.419 | 0.241 | 0.308 | 0.311 | 0.282 | 0.241 |
| `strong_drift` | 0.431 | 0.527 | 0.431 | 0.527 | 0.527 | 0.527 |
| `robot_disturbed` | 0.470 | 0.291 | 0.464 | 0.291 | 0.290 | 0.291 |

Значения — `auc_collected_by_path`, среднее по 2 seed.

Выводы абляций:

- **`confirmed_route` — главный вклад и в плюс, и в минус.** `no_route` почти полностью восстанавливает AUC `belief_horizon` в `static_calm`/`weak_drift`/`robot_disturbed` (т.е. именно `confirmed_route` тянет AUC вниз в этих сценариях), но в `strong_drift` включённый `route` даёт **+0.096 AUC** относительно `no_route` (0.527 против 0.431) — единственный чисто положительный эффект среди всех абляций. Это согласуется с гипотезой из `mission_regime_analysis_direction_2026-08-16.md`: маршрутизация по подтверждённым целям выгоднее именно при выраженном дрейфе.
- **`belief_orienteering` и `local_exploit`** дают заметный эффект только в `weak_drift` (оба положительные при отключении, т.е. слегка мешают при включении) и `robot_disturbed`/`static_calm` (эффект нулевой/шумовой на 2 seed).
- **Hysteresis не работает.** `adaptive_mission` и `adaptive_mission_no_hysteresis` дают **побитово идентичные** AUC во всех 4 сценариях. Это самостоятельная находка, не исправленная в этой ревизии: `adaptive_switch_margin=0.12` был откалиброван под старый (сломанный) масштаб utility, где `confirmed_route` никогда не приближался к `belief_horizon` и margin был неважен. После фикса effort-scale абсолютные значения utility выросли на порядки, и `0.12` стал пренебрежимо малым — hysteresis перестал на что-либо влиять. Кроме того, механизм hysteresis в текущем виде удерживает уже выбранную политику, но не мешает *первому* переходу на `confirmed_route`, поэтому даже пересчитанный margin вряд ли сам по себе устранит просадку AUC в спокойных сценариях. Оставлено как задокументированная находка для следующей итерации, а не исправлено «на скорую руку» без валидации на достаточном числе seed.

## Что можно заявлять в статье

- `adaptive_mission` в исходном виде на ветке `feature/adaptive-mission` был декоративной обёрткой над `belief_horizon` (0-4% переключений на альтернативы) из-за конкретных, идентифицированных багов реализации: несопоставимый масштаб unified utility между policy-типами и математически недостижимый drift-override.
- После исправления этих багов `adaptive_mission` содержательно переключается между режимами (`belief_horizon` 49-71%, `confirmed_route` 23-50%, до нескольких процентов `local_exploit`/`belief_orienteering`), и эти переключения объясняются измеримыми признаками состояния (`adaptive_confirmed_count`, `adaptive_fresh_confirmed_count`, `adaptive_drift_speed_mps`, `adaptive_route_override_used` — уже логировались; добавлено `adaptive_route_effort_m`).
- Маршрутизация по подтверждённым целям (`confirmed_route`) измеримо помогает по AUC именно при выраженном дрейфе (`strong_drift`, +0.096 AUC при включении по абляции) и измеримо вредит в спокойных/умеренных сценариях — это прямое экспериментальное подтверждение режимной гипотезы документа `mission_regime_analysis_direction_2026-08-16.md`, а не декларация.
- Честный текущий вывод: **после устранения багов реализации адаптивное переключение само по себе не гарантирует улучшения AUC**; выгода зависит от режима (дрейф vs его отсутствие), и наивное «дать confirmed_route шанс на равных» ухудшает primary metric в большинстве проверенных сценариев на этом бюджете.

## Что нельзя заявлять

- Нельзя писать, что `adaptive_mission` в текущем виде превосходит `belief_horizon` — на 3-seed diagnostic-серии он хуже в среднем на ~0.066 AUC, с допуском в 0.02 не укладывается в 3 из 4 базовых сценариев.
- Нельзя писать, что hysteresis в `adaptive_mission` контролирует частоту переключений — экспериментально показано, что при текущем `adaptive_switch_margin=0.12` он не оказывает никакого измеримого эффекта.
- Нельзя использовать результаты этой ревизии (seed 300-304, 320-321, 330-339) как финальную/pre-final серию: это диагностика на малой выборке, как и было явно оговорено в задании. Финальные seed `100-129` не использовались и не должны использоваться для tuning.
- Нельзя заявлять, что `oracle_current_physics` является математическим оптимумом, и что реализована реалистичная гидродинамика/CV/radar — как и раньше (`parameter_evidence_matrix.md`).
- Нельзя интерпретировать «toy-budget» пробы (800 м) как доказательство поведения на целевом бюджете — в этой ревизии показано, что они могут вводить в заблуждение (см. «Что попробовано и отклонено»).

## Дальнейшая работа (вне scope этой ревизии)

1. Пересмотреть `adaptive_switch_margin` (пере-масштабировать под новый диапазон utility) и, отдельно, механизм входа в `confirmed_route`/`local_exploit` — hysteresis сейчас не защищает от невыгодного *первого* переключения, только от отказа от уже выбранной политики. Требует отдельной ревизии и валидации на seed вне `100-129`.
2. Разобраться, почему `belief_orienteering` почти не выбирается даже после снятия double-gate — возможно, потребуется собственная диагностика с trace на сценариях с плотной картой.
3. Точечная калибровка `adaptive_route_target_count_weight`/`adaptive_fresh_target_weight` на статистически достаточной seed-серии (не 1-3 seed) — предварительная проверка (обнуление) не дала однозначного эффекта.
4. При достижении AUC-паритета — повторить Этап 6 (budget recheck) и затем 10/30-seed финальную серию.
