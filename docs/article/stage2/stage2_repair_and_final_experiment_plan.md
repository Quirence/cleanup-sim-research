# Этап 2: ремонт экспериментальной базы и подготовка финальной серии

Дата: 2026-07-31

Статус на 2026-08-16: исторический план ремонта старой экспериментальной
базы. Для `cleanup_sim_v2` использовать вместе с
`docs/project/simulator_v2_1_closure_report.md`,
`docs/project/repository_review_followup_2026-08-16.md` и актуальной
постановкой `../stage1/stage1_reframing_after_prefinal_2026-08-16.md`.

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

Закрыто дополнительно после P1-статистики:

- paired comparisons используют sign-flip permutation p-value как основной `p_value`;
- normal approximation оставлен только как diagnostic `p_normal_approx`;
- добавлены `cohen_dz`, `rank_biserial` и Holm correction;
- threshold metrics имеют reach-rate/censored accounting.
- active score получил area-normalized FOV terms и regression-тест на устойчивость при смене разрешения сетки.
- route-цели требуют мультисенсорного подтверждения, а target success учитывает сбор рядом с route goal по пути.
- sensitivity runner теперь поддерживает `robot` cases для `collect_radius_m`, `bin_capacity_kg`, `speed_mps` вокруг `hybrid_final_v1`.

Остается до финальной серии:

- требуется научное решение по pre-final smoke: `hybrid_final_v1` использовать как метод для анализа условий применимости или переработать hybrid-правило.

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

Статус: закрыто.

Реализовано:

- entropy/probability/candidate FOV terms нормируются через `cell_area / active_reference_cell_area_m2`;
- на базовой сетке `100 x 100` с ячейкой `2 x 2 м` масштаб score сохраняется;
- добавлен regression-тест на близость score для `100 x 100` и `50 x 50` сеток.

Ограничение:

Метод остается эвристическим active score, а не expected information gain.

### C3. Expected information gain

Решение для ближайшей статьи:

- не реализовывать срочно, если цель — РИНЦ/ВАК-основа;
- явно писать “эвристический active score на основе энтропии и вероятности”, а не EIG.

Решение для усиленной ВАК-версии:

- реализовать приближенный EIG отдельным режимом;
- сравнить `active_heuristic` vs `active_eig` vs `hybrid`.

## Блок D. Статистика

Статус: базово закрыто.

Реализовано:

- paired sign-flip permutation test для paired seed-сравнений;
- effect sizes `cohen_dz` и `rank_biserial`;
- число пар, достигших threshold metrics;
- reach-rate для `path_to_50/80/95` и `time_to_50/80/95`;
- censored pair accounting в `paired_comparisons.csv`.

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

Статус перед финальной серией:

- pre-final 5-seed smoke выполнен: `docs/article/results/p1_prefinal_confirmatory_smoke_5seed.md`;
- технических залипаний нет, все 105 запусков дошли до `path_budget`;
- `hybrid_final_v1` не является универсальным победителем относительно `greedy` и `lawnmower_dense`.

Финальную 30-seed серию запускать только после согласования интерпретации этого результата.

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

Физическая sensitivity-серия:

```powershell
python -m cleanup_sim.run_sensitivity `
  --seeds 5 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --components robot `
  --out-dir out/cleanup_sim/physical_sensitivity_prefinal `
  --max-path-m 3000 `
  --tmax-s 6000
```

## Итоговый критерий закрытия этапа

Этап считается закрытым, когда:

- baseline-ы не содержат известных залипаний;
- coverage baseline не является искусственно слабым;
- карта оценивается по корректным эталонам;
- статистика не удаляет неудачные прогоны молча;
- актуальный confirmatory smoke прошел;
- можно запускать финальные 30 seed без ощущения, что мы уже знаем о системной ошибке.
