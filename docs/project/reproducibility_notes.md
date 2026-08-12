# Воспроизводимость проекта

> **Историческая заметка (2026-08-13):** раздел "Быстрая Проверка" ниже и "Научная Оговорка" написаны под legacy `cleanup_sim` (`hybrid_final_v1`, pre-final smoke) и не отражают текущий `cleanup_sim_v2`. Актуальная быстрая проверка добавлена отдельным блоком ниже; актуальный научный статус — `docs/project/simulator_v2_1_closure_report.md`.

Дата: 2026-07-31

Назначение: дать минимальный воспроизводимый маршрут для коллеги, который поднимает репозиторий с нуля и проверяет, что кодовая база находится в рабочем состоянии.

## Окружение

Поддерживаемая базовая среда:

- Python `3.11` или `3.12`;
- установка через editable package;
- зависимости из `pyproject.toml`.

Рекомендуемая локальная установка:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m pytest
```

Legacy-вариант через `requirements.txt` оставлен для совместимости:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

## Быстрая проверка (актуальная, cleanup_sim_v2)

```powershell
python -m cleanup_sim_v2.run_experiments `
  --seeds 3 `
  --scenarios static_calm weak_drift `
  --modes greedy belief_horizon oracle_current_physics `
  --out-dir out/cleanup_sim_v2/dev_smoke
```

Ожидаемые свойства:

- команда завершается без исключений;
- появляются `summary.csv`, `aggregate_mean_std.csv`, `run_manifest.json`;
- файлы создаются внутри `out/`, который игнорируется git.

## Быстрая проверка (историческая, legacy cleanup_sim)

Минимальный smoke без сохранения тяжелых артефактов в git:

```powershell
python -m cleanup_sim.run_confirmatory `
  --seeds 1 `
  --scenarios clustered_base `
  --out-dir out/cleanup_sim/dev_smoke `
  --max-path-m 1200 `
  --tmax-s 2400
```

Ожидаемые свойства:

- команда завершается без исключений;
- появляются `summary.csv`, `aggregate_mean_std.csv`, `paired_comparisons.csv`;
- файлы создаются внутри `out/`, который игнорируется git.

## CI

GitHub Actions workflow:

`/.github/workflows/tests.yml`

Он выполняет:

- установку Python `3.11` и `3.12`;
- `python -m pip install -e ".[dev]"`;
- `python -m pytest`.

## Что Не Коммитить

Не добавлять в git:

- `out/` с raw результатами запусков;
- `_delete_later/`;
- `.pytest_cache/`;
- локальные PDF/материалы из `Материалы/`;
- большие видео, архивы и временные IDE-файлы.

Исключение: короткие Markdown-отчеты в `docs/article/results/` можно коммитить, если они нужны для научного журнала проекта.

## Научная Оговорка

Воспроизводимость кода не означает готовность к финальному 30-seed прогону. Текущий блокер остается научным: нужно согласовать интерпретацию pre-final smoke и решить, фиксируем ли `hybrid_final_v1` как метод для анализа условий применимости или перерабатываем гибридное правило.
