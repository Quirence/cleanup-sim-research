# Этап 2: ремонт экспериментальной базы и подготовка финальной серии

Дата: 2026-07-31

## Цель этапа

Довести симулятор и экспериментальный протокол до состояния, при котором финальная серия `30 seed × сценарии × стратегии` будет научно защищаемой и пригодной для статьи.

Этот этап не про получение красивой таблицы. Он про устранение артефактов baseline-ов, метрик и статистики.

## Основное решение после аудита

Финальную серию запускать все еще рано, но P0-артефакты baseline-ов и метрик закрыты.

Закрыто после P0-ремонта:

- coverage baseline разделен на `lawnmower_sparse` и `lawnmower_dense`;
- greedy baseline больше не залипает на текущей argmax-ячейке;
- метрики карты разделены на `initial_*` и `residual_*`;
- active baseline больше не fallback-ится в `greedy`;
- `hybrid_final_v1` заморожен как final-arm;
- старые draft/result документы помечены как исторические.

Остается до финальной серии:

- часть статистики анти-консервативна для малых n;
- active score зависит от разрешения сетки;
- требуется физическая sensitivity и проверка target precision.

## Блок A. Ремонт baseline-ов

### A1. Coverage baseline

Проблема:

`coverage_spacing_m=22.0` при `collect_radius_m=5.0` дает неполное покрытие.

Решение:

- добавить режим `lawnmower_dense` с spacing около `2 * collect_radius_m`;
- сохранить текущий sparse coverage только если он будет явно назван `lawnmower_sparse`;
- не сравнивать hybrid только с искусственно слабым sparse coverage.

Acceptance:

- закрыто: оба режима реализованы и проходят smoke;
- dense coverage собирает больше sparse в диагностическом smoke;
- в статье нужно ясно указать, какой coverage baseline используется.

### A2. Greedy baseline

Проблема:

Greedy может выбирать текущую argmax-ячейку и залипать.

Решение:

- добавить tabu-маску недавно посещенных целей;
- запретить цель ближе `collect_radius_m`, если после визита сбор не произошел;
- проверить обработку ячейки под роботом в `visible_mask`;
- добавить regression test на отсутствие нулевого пути после старта.

Acceptance:

- закрыто: `greedy` проходит path budget в 5-seed smoke;
- результат greedy можно трактовать как свойство стратегии, а не баг.

## Блок B. Ремонт метрик

### B1. Карта загрязнений

Проблема:

Финальный belief сравнивается с initial occupancy, хотя мусор уже мог быть собран.

Решение:

- хранить `initial_true_occ`;
- считать `residual_true_occ` после завершения миссии;
- добавить метрики:
  - `initial_map_f1`, `initial_map_iou`, `initial_brier_score`;
  - `residual_map_f1`, `residual_map_iou`, `residual_brier_score`;
- старые `map_f1`, `map_iou`, `brier_score` либо оставить как alias с ясным смыслом, либо убрать из финальной таблицы.

Acceptance:

- закрыто: summary содержит `initial_*` и `residual_*`;
- таблица статьи не должна смешивать detection-quality и current-state-quality.

### B2. Path-normalized метрики

Уже исправлено:

- `auc_collected_by_path` считается по `max_path_m`.

Нужно:

- добавить тесты на доли сбора на фиксированных дистанциях;
- в статье сделать AUC и `collected_ratio_at_Xkm` основными метриками.

## Блок C. Ремонт hybrid и active score

### C1. `hybrid_switch_prob`

Статус: закрыто.

Параметр удален из `PlannerConfig` и тестов. Правило hybrid теперь описывается через `hybrid_min_confirmed_targets` и `hybrid_explore_entropy_threshold`.

### C2. Active score normalization

Проблема:

Слагаемые функции полезности зависят от числа видимых ячеек и разрешения сетки.

Решение первой версии:

- нормировать entropy/probability/candidate terms на число видимых ячеек;
- distance penalty оставить в метрах;
- после изменения повторить smoke и ablation.

Осторожность:

Это может изменить поведение всех active/hybrid режимов. После нормировки старые pilot-результаты снова станут историческими.

### C3. Expected information gain

Решение для ближайшей статьи:

- не реализовывать срочно, если цель — РИНЦ/ВАК-основа;
- явно писать “эвристический active score на основе энтропии и вероятности”, а не EIG.

Решение для усиленной ВАК-версии:

- реализовать приближенный EIG отдельным режимом;
- сравнить `active_heuristic` vs `active_eig` vs `hybrid`.

## Блок D. Статистика

Нужно добавить:

- Wilcoxon signed-rank test для paired seed-сравнений;
- effect size;
- число пар, достигших threshold metrics;
- отдельную таблицу reach-rate для `path_to_80_m`, `path_to_95_m`.

Acceptance:

- p-value на 3/5 seed не подается как доказательство;
- финальная статья опирается на 30 seed;
- NaN threshold values не исчезают молча из анализа.

## Блок E. Диагностика `hybrid_final_v1`

Проблема:

В старом pilot у candidate-v2 были `time_budget` завершения при среднем пути меньше 6000 м. После P0-ремонта final-arm зафиксирован как `hybrid_final_v1`.

Нужно:

- запустить диагностический single-run с сохранением series/events;
- проверить частые `target_routed` к близким целям;
- увеличить `tmax_s` для финальных запусков или исправить причину медленного расхода пути.

Acceptance:

- `hybrid_final_v1` доходит до path budget;
- либо в статье явно объясняется, почему используется time budget.

## Финальная серия после ремонта

Минимальный набор стратегий:

- `lawnmower_dense`;
- `lawnmower_sparse`;
- `greedy`;
- `active`;
- `detected_tsp`;
- `hybrid_base`;
- `hybrid_final_v1`.

Сценарии:

- `clustered_base`;
- `clustered_noisy`;
- `uniform_base`.

Seeds:

- минимум 30.

Основные метрики:

- collected_ratio;
- AUC by common path budget;
- collected_ratio_at_2/4/6km;
- path_to_50/80/95 with reach-rate;
- false route visits;
- target precision;
- initial/residual Brier score;
- initial/residual F1/IoU.

## Итоговый критерий закрытия этапа

Этап считается закрытым, когда:

- baseline-ы не содержат известных залипаний;
- coverage baseline не является искусственно слабым;
- карта оценивается по корректным эталонам;
- статистика не удаляет неудачные прогоны молча;
- актуальный confirmatory smoke прошел;
- можно запускать финальные 30 seed без ощущения, что мы уже знаем о системной ошибке.
