# Cleanup Simulation Research Project

Проект для статьи о гибридном вероятностном планировании поиска и сбора плавающего мусора автономным надводным роботом при шумных и неполных наблюдениях.

## Содержимое

- `cleanup_sim/` - модульный 2D Python-симулятор.
- `tests/` - regression/unit tests.
- `docs/project/` - актуальное состояние проекта и manifest уборки.
- `docs/article/stage1/` - научная постановка и вклад.
- `docs/article/stage2/` - план ремонта экспериментальной базы перед финальной серией.
- `docs/article/results/` - Markdown-отчеты по pilot-результатам.

## Проверка

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

Текущее ожидаемое состояние:

```text
51 passed
```

Legacy-вариант через `requirements.txt` оставлен для совместимости:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

## Важное ограничение

Финальные 30-seed результаты для статьи пока не заморожены. Перед ними нужно закрыть блокеры из:

`docs/article/stage2/stage2_repair_and_final_experiment_plan.md`

Главная текущая причина паузы: pre-final smoke показал, что `hybrid_final_v1` не является универсальным победителем, поэтому перед финальным прогоном нужно согласовать научную интерпретацию.

Не использовать старые raw-результаты из `out/` как финальные таблицы статьи.

Подробный маршрут воспроизводимости:

`docs/project/reproducibility_notes.md`
