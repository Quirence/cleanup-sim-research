# Задание для ревью и доработки `adaptive_mission`

Дата: 2026-08-29.

Цель документа: дать коллеге воспроизводимое задание по текущему направлению статьи и симулятора. Работа ведется вокруг `cleanup_sim_v2`, без использования legacy-результатов как финальных.

## Короткий контекст

Текущая тема статьи:

> Планирование миссии надводного робота для поиска и сбора плавающего мусора при неполной, шумной и устаревающей информации о положении целей.

Научный фокус сейчас не в том, чтобы объявить один алгоритм абсолютным победителем. Более сильная и честная постановка: построить методику анализа режимов миссии и понять, когда оправданы:

- равномерное физическое покрытие;
- жадное движение к текущим целям;
- вероятностное планирование по density/count-map;
- короткий маршрутный горизонт;
- маршрутизация по подтвержденным целям;
- адаптивное переключение между этими режимами.

Текущий риск: `adaptive_mission` часто совпадает с `belief_horizon` или уступает ему. Поэтому основная полезная задача для ревью - не просто запустить еще одну таблицу, а выяснить, можно ли сделать `adaptive_mission` содержательно отличимым и полезным.

## Откуда начинать

Рекомендуемая базовая ветка:

```powershell
git fetch origin
git checkout feature/adaptive-mission
git pull
git checkout -b feature/adaptive-mission-review
```

Текущий известный commit с тяжелым post-fix прогоном:

```text
601b4cf Add post-fix layer1 heavy run results
```

Перед работой:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
```

Ожидаемое состояние на момент подготовки задания: все тесты должны проходить.

## Что прочитать в первую очередь

Минимальный набор документов:

- `docs/project/mission_regime_analysis_direction_2026-08-16.md` - актуальная научная рамка.
- `docs/project/adaptive_mission_initial_report_2026-08-16.md` - первая реализация и ранние ограничения adaptive-переключателя.
- `docs/project/layer1_logical_results_audit_2026-08-22.md` - логические риски результатов и проблема копирования `belief_horizon`.
- `docs/project/layer1_postfix_heavy_run_protocol_2026-08-22.md` - протокол тяжелого post-fix прогона.
- `docs/project/layer1_budget_finesweep_probe_2026-08-25.md` - проверка промежуточного бюджета и кандидат `3000 м`.
- `docs/project/parameter_evidence_matrix.md` - параметры симулятора и ограничения заявлений.

Важно: старые результаты до v2.1 и pre-fix calibration не использовать как финальные доказательства.

## Карта кода

Основные файлы:

- `cleanup_sim_v2/config.py`
  - `PlannerMode`;
  - `PlannerConfig`;
  - `scenario_config()`;
  - параметры `adaptive_*`, `belief_*`, `target_*`.

- `cleanup_sim_v2/planners.py`
  - `next_belief_horizon()`;
  - `next_belief_orienteering()`;
  - `_next_confirmed_route_decision()`;
  - `_next_local_exploit_decision()`;
  - `_preview_adaptive_policy()`;
  - `_adaptive_utility()`;
  - `next_adaptive_mission()`;
  - `choose_goal()`.

- `cleanup_sim_v2/layer1.py`
  - наборы режимов `LAYER1_MODES`;
  - расчет `collection_coverage_ratio`, `drift_per_update_width`, `camera_capture_uncertainty_ratio`, `oracle_gap`;
  - `evaluate_budget_calibration()`;
  - `adaptive_policy_shares()`.

- `cleanup_sim_v2/run_layer1.py`
  - основной runner для budget calibration, baseline и trace.

- `cleanup_sim_v2/layer1_validation.py`
  - проверки полноты матрицы, stop reasons, oracle-gap, near-zero collection, совпадения `adaptive_mission` с `belief_horizon`.

- `tests/test_cleanup_sim_v2.py`
  - основная масса unit/regression-тестов для планировщиков.

- `tests/test_cleanup_sim_v2_layer1.py`, `tests/test_cleanup_sim_v2_layer1_validation.py`
  - тесты layer1-логики и validation.

## Основная задача

Нужно провести ревизию текущего `adaptive_mission` и ответить на вопрос:

> Можно ли сделать адаптивное переключение между режимами миссии содержательно лучше или хотя бы устойчиво не хуже `belief_horizon`, не используя oracle-доступ и не подгоняя параметры симулятора?

Ревизия должна быть научной, а не косметической. Нельзя просто подобрать веса под один seed или один сценарий.

## Рабочая гипотеза

Текущий `adaptive_mission` слаб не потому, что идея переключения бессмысленна, а потому что:

- selector слишком часто выбирает `belief_horizon`;
- `confirmed_route` редко проходит пороги включения;
- `local_exploit` включается редко и не всегда повышает AUC;
- `belief_orienteering` может проигрывать из-за стоимости маршрута и устаревания целей;
- разные политики сравниваются через unified utility, но признаки состояния могут быть недостаточно сильными для реального переключения;
- AUC по пути и итоговая доля сбора иногда рекомендуют разные поведения.

Эту гипотезу нужно проверить trace-логами и малой серией, а не большой финальной таблицей.

## Запреты

Нельзя:

- использовать истинные координаты мусора, `field`, `source_index` или oracle-данные в non-oracle режимах;
- менять физику симулятора, сенсоры, дрейф, число объектов и карту мира ради улучшения `adaptive_mission`;
- запускать финальные seed `100-129` для tuning;
- коммитить весь `out/` через `git add out`;
- трактовать 1-3 seed как доказательство;
- заявлять, что `oracle_current_physics` является математическим optimum;
- заявлять SLAM/NMHE/NMPC/CV/radar hardware validation.

## Этап 1. Воспроизвести текущую проблему

Сначала выполнить короткий trace при бюджете-кандидате `3000 м`.

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase trace `
  --budget 3000 `
  --seed-start 300 `
  --seeds 3 `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/colleague_adaptive_trace_3000_2026-08-29
```

Нужно изучить:

- `adaptive_policy_shares.csv`;
- `runs/*_events.csv`;
- долю выбора `belief_horizon`, `belief_orienteering`, `confirmed_route`, `local_exploit`;
- совпадение `adaptive_mission` с `belief_horizon` по AUC и collected ratio;
- случаи, где adaptive выбирает не `belief_horizon`, но результат хуже.

Минимальный Python-сниппет для быстрой проверки:

```powershell
python - <<'PY'
import pandas as pd
from pathlib import Path

base = Path("out/cleanup_sim_v2/colleague_adaptive_trace_3000_2026-08-29/layer1_postfix_adaptive_trace_2026-08-22")
shares = pd.read_csv(base / "adaptive_policy_shares.csv")
print(shares.groupby(["scenario", "adaptive_selected_policy"])["share"].mean().unstack(fill_value=0).round(3))
summary = pd.read_csv(base / "summary_enriched.csv")
print(summary[["scenario", "seed", "auc_collected_by_path", "collected_ratio", "stop_reason"]].to_string(index=False))
PY
```

Если shell не поддерживает heredoc, можно сохранить этот фрагмент в временный локальный `.py` вне коммита.

## Этап 2. Диагностический baseline при `3000 м`

Запустить небольшой сравнительный прогон. Это не финальная статистика, а диагностика.

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase baseline `
  --budget 3000 `
  --seed-start 300 `
  --seeds 5 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes lawnmower_collect greedy confirmed_route belief_horizon belief_orienteering belief_orienteering_depth1 adaptive_mission oracle_current_physics `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/colleague_baseline_3000_5seed_2026-08-29
```

Смотреть в первую очередь:

- `auc_collected_by_path`;
- `collected_ratio`;
- `oracle_gap_auc_collected_by_path`;
- `empty_goal_arrivals_per_km`;
- `wasted_path_ratio`;
- `goal_success_rate`;
- `stop_reason`;
- `paired_comparisons_by_budget.csv`.

Если `adaptive_mission` снова совпадает с `belief_horizon`, это нужно фиксировать как результат диагностики.

## Этап 3. Ревизия алгоритма

Работать в `cleanup_sim_v2/planners.py` и `cleanup_sim_v2/config.py`.

Приоритетные направления:

1. Проверить пороги включения `confirmed_route`.
   - Сейчас `adaptive_route_min_confirmed = 6`.
   - Нужно понять, не слишком ли поздно включается маршрут по подтвержденным целям.
   - Нельзя просто снизить порог без проверки роста пустых визитов и ухудшения AUC.

2. Проверить `local_exploit`.
   - Сейчас `adaptive_local_min_expected_count = 25.0`.
   - Возможно, порог слишком высокий для локального прохода через найденное пятно.
   - Нужно сравнивать не только collected ratio, но и AUC: поздний добор мусора может ухудшать миссионную эффективность.

3. Проверить hysteresis.
   - `adaptive_switch_margin = 0.12`.
   - Слишком сильный hysteresis может удерживать старый режим.
   - Слишком слабый может вызвать частые переключения и шум.

4. Усилить decision rules через измеримые признаки состояния.
   - Не полагаться только на итоговую utility.
   - Добавить понятные gates: свежесть целей, плотность подтверждений, drift-risk, expected collection per meter, empty-visit pressure.
   - Каждое правило должно попадать в `events.csv` как диагностическое поле.

5. Разделить выбор по целям AUC и итогового сбора.
   - Если режим дает больше итогового сбора, но хуже AUC, это не всегда улучшение.
   - Для статьи primary metric сейчас `auc_collected_by_path`.

Рекомендуемый безопасный подход: не добавлять новый основной режим сразу. Сначала доработать `adaptive_mission` в ветке и сохранить абляции `adaptive_mission_no_*`.

Если изменение сильно экспериментальное, допустимо временно добавить режим `adaptive_mission_candidate`, но тогда нужны CLI, config и тесты. Перед merge нужно решить, заменяет ли он основной `adaptive_mission`.

## Этап 4. Тесты после изменений

Минимум:

```powershell
python -m pytest -q
```

Добавить или обновить тесты, если менялась логика selector-а:

- adaptive выбирает `belief_horizon`, когда нет надежных целей;
- adaptive выбирает `confirmed_route`, когда есть достаточно свежих подтвержденных целей и маршрутная польза выше;
- adaptive выбирает `local_exploit`, когда есть плотное локальное пятно и ожидаемый сбор на метр выше;
- hysteresis не подавляет явно лучший режим;
- preview не мутирует `PlannerState` и `TargetQueue`;
- non-oracle режим не получает доступ к истинному полю мусора;
- новые диагностические поля пишутся в `events.csv`.

## Этап 5. Проверка улучшенной версии

Сначала smoke на 2 seed:

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase baseline `
  --budget 3000 `
  --seed-start 320 `
  --seeds 2 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes belief_horizon adaptive_mission adaptive_mission_no_route adaptive_mission_no_orienteering adaptive_mission_no_local_exploit adaptive_mission_no_hysteresis oracle_current_physics `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/colleague_adaptive_revision_smoke_2026-08-29
```

Если smoke не выявил регрессий, diagnostic на 10 seed:

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase baseline `
  --budget 3000 `
  --seed-start 330 `
  --seeds 10 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes greedy confirmed_route belief_horizon belief_orienteering belief_orienteering_depth1 adaptive_mission oracle_current_physics `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/colleague_adaptive_revision_10seed_2026-08-29
```

Этот прогон уже можно использовать для решения, стоит ли делать 30-seed серию.

## Этап 6. Подтверждение бюджета без больших вычислений

Если после ревизии adaptive меняется поведение, бюджет `3000 м` нужно перепроверить на малой сетке:

```powershell
python -m cleanup_sim_v2.run_layer1 `
  --phase calibration `
  --budgets 2400 3000 3600 `
  --seed-start 350 `
  --seeds 5 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --modes lawnmower_collect greedy confirmed_route belief_horizon belief_orienteering belief_orienteering_depth1 adaptive_mission oracle_current_physics `
  --checkpoint `
  --fail-on major `
  --out-root out/cleanup_sim_v2/colleague_budget_check_after_adaptive_2026-08-29
```

Не запускать 30 seed для бюджета, пока не ясно, что adaptive-правила заморожены.

## Критерии успеха

Минимальный успешный результат:

- тесты проходят;
- trace показывает, что `adaptive_mission` не является почти полным клоном `belief_horizon`;
- нет `major` и `blocker` в validation;
- нет роста `time_budget`;
- нет oracle-доступа;
- AUC `adaptive_mission` не хуже `belief_horizon` более чем на `0.02` в среднем по базовым сценариям на diagnostic-серии;
- хотя бы в одном сценарии adaptive снижает regret к лучшему fixed mode или к oracle-gap без ухудшения stop reasons.

Сильный результат:

- adaptive имеет понятные режимные переключения;
- улучшение AUC наблюдается не на одном seed, а на paired-серии;
- абляции показывают, какой компонент реально дает эффект;
- результаты можно объяснить через drift, свежесть целей, плотность карты и пустые визиты.

Отрицательный, но полезный результат:

- adaptive после честной ревизии все равно не лучше `belief_horizon`;
- trace показывает, почему именно: нет надежных условий для включения route/local/orienteering или переключение ухудшает AUC;
- тогда в статью идет не “наш adaptive победил”, а методический вывод о границе полезности переключения.

## Что отдать в конце

В pull request желательно приложить:

- краткое описание изменений в `cleanup_sim_v2/planners.py` и `cleanup_sim_v2/config.py`;
- список новых/измененных тестов;
- команды запусков;
- путь к локальным `out/...` результатам;
- файл `docs/project/adaptive_mission_revision_report_YYYY-MM-DD.md`.

Шаблон отчета:

```markdown
# Adaptive mission revision report

## Что изменено

## Почему это должно помочь

## Тесты

## Прогоны

## Policy shares

## AUC / collected ratio

## Сравнение с belief_horizon

## Абляции

## Что можно заявлять в статье

## Что нельзя заявлять
```

## Git hygiene

Перед commit:

```powershell
git status --short --branch --untracked-files=normal
git diff --stat
python -m pytest -q
```

Не делать:

```powershell
git add out
git add .
```

Если нужно закоммитить результаты, добавлять только явно выбранные итоговые артефакты:

- `summary.csv`;
- `summary_enriched.csv`;
- `aggregate_mean_std.csv`;
- `paired_comparisons_by_budget.csv`;
- `validation_issues.csv`;
- `validation_summary.json`;
- `run_manifest.json`;
- отчет `.md`.

Partial-файлы, прерванные probe-папки и старые локальные `out/` результаты не коммитить без отдельного решения.

## Рекомендуемый порядок работы

1. Поднять ветку и прогнать тесты.
2. Прочитать документы из раздела "Что прочитать".
3. Запустить `trace` на `3000 м`, `3 seed`.
4. Запустить diagnostic baseline на `3000 м`, `5 seed`.
5. Сформулировать причину вырождения adaptive в `belief_horizon`.
6. Только после этого менять selector.
7. Добавить тесты под измененную логику.
8. Запустить smoke на `2 seed`.
9. Если smoke нормальный, запустить diagnostic на `10 seed`.
10. Написать отчет и открыть PR.
