# Рабочая структура проекта

Дата обновления: 2026-07-31

## Главный рабочий путь

1. `docs/article/stage1/`
   - научная постановка;
   - матрица литературы;
   - готовые формулировки для статьи.

2. `docs/article/drafts/`
   - Markdown-черновики статьи.

3. `docs/article/audits/`
   - критика и аудит старой/новой статьи.

4. `docs/literature/`
   - план литературы;
   - глубокие резюме загруженных статей.

5. `Материалы/`
   - исходные PDF-статьи.

6. `cleanup_sim/`
   - актуальная исследовательская Python-реализация симулятора.

7. `tests/`
   - тесты для `cleanup_sim`.

8. `out/cleanup_sim/`
   - только актуальные или диагностически важные результаты симулятора.

## Текущая документация состояния

Главная сводка проекта:

`docs/project/current_state.md`

План ремонта экспериментальной базы:

`docs/article/stage2/stage2_repair_and_final_experiment_plan.md`

Актуальный диагностический pre-final smoke после закрытия P0/P1:

`docs/article/results/p1_prefinal_confirmatory_smoke_5seed.md`

Разбор внешнего аудита:

`docs/article/drafts/2026-07-31_audit_triage_after_current_fixes.md`

## Текущий научный вектор

Рабочая тема:

> гибридное вероятностное планирование поиска и сбора плавающего мусора автономным надводным роботом при шумных и неполных наблюдениях.

Главный файл для продолжения:

`docs/article/stage1/stage1_scientific_positioning.md`

Следующий научно-технический этап:

> согласовать интерпретацию pre-final smoke: фиксировать `hybrid_final_v1` как метод для анализа условий применимости, перерабатывать hybrid-правило или смещать вклад статьи на протокол сравнения и trade-off analysis.

Быстрая проверка симулятора:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
python -m cleanup_sim.run_confirmatory --seeds 1 --scenarios clustered_base --out-dir out/cleanup_sim/dev_smoke --max-path-m 1200 --tmax-s 2400
```

Подробные инструкции по воспроизводимости:

`docs/project/reproducibility_notes.md`
