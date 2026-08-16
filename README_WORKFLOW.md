# Рабочая структура проекта

Дата обновления: 2026-08-13

## Главный рабочий путь

1. `docs/article/stage1/`
   - научная постановка, матрица литературы, готовые формулировки для статьи;
   - актуальный ориентир после pre-final результатов: `docs/article/stage1/stage1_reframing_after_prefinal_2026-08-16.md`;
   - более ранние файлы сохранены для traceability и могут содержать pre-v2/pre-final формулировки.

2. `docs/article/drafts/`
   - Markdown-черновики статьи.

3. `docs/article/audits/`
   - критика и аудит старой/новой статьи.

4. `docs/literature/`
   - план литературы;
   - глубокие резюме загруженных статей, включая `algorithm_literature_directions_2026-08-02.md` (выбор направлений алгоритмов для `cleanup_sim_v2`).

5. `Материалы/`
   - исходные PDF-статьи.

6. `cleanup_sim_v2/`
   - актуальная исследовательская Python-реализация симулятора (density/count-map, лагранжев дрейф, физический сбор, `belief_horizon`/`belief_orienteering`).
   - `cleanup_sim/` - legacy-версия (occupancy grid, `hybrid`/`graph_mst`/`hybrid_mst`), не для финальных результатов статьи.

7. `tests/`
   - тесты для `cleanup_sim_v2` и `cleanup_sim`.

8. `out/cleanup_sim_v2/`, `out/cleanup_sim/`
   - только актуальные или диагностически важные результаты симулятора.

## Текущая документация состояния

Главная сводка проекта:

`docs/project/current_state.md`

Статус симулятора v2.1 и что закрыто перед разработкой алгоритма:

`docs/project/simulator_v2_1_closure_report.md`

Выбор направлений алгоритма и порядок реализации:

`docs/project/algorithm_literature_directions_2026-08-02.md`, `docs/project/algorithm_implementation_roadmap_2026-08-02.md`

Ревью репозитория и план исправлений:

`docs/project/repository_review_2026-08-12.md`, `docs/project/repository_review_fix_plan_2026-08-13.md`

## Текущий научный вектор

Рабочая тема:

> адаптивное планирование миссии поиска и сбора плавающего мусора автономным надводным роботом при неполной, шумной и устаревающей информации о целях, физически ограниченном сборе и дрейфе объектов.

Текущий научный статус: `cleanup_sim_v2` готов для разработки алгоритма (`READY FOR ALGORITHM DESIGN`), но не для финального confirmatory-прогона - нужны sensitivity-серия, заморозка параметров и paired-seed сравнение против `greedy`/`confirmed_route`/`oracle_current_physics` на достаточном числе seed (см. `docs/project/parameter_evidence_matrix.md`).

Быстрая проверка симулятора:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m cleanup_sim_v2.run_experiments --seeds 3 --modes greedy belief_horizon oracle_current_physics --out-dir out/cleanup_sim_v2/dev_smoke
```

Подробные инструкции по воспроизводимости:

`docs/project/reproducibility_notes.md`
