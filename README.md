# Cleanup Simulation Research Project

Проект для статьи о планировании миссии поиска и сбора плавающего мусора автономным надводным роботом при неполной, шумной и устаревающей информации о целях.

Текущий научный вектор: **режимный анализ планирования миссии**. Цель работы не сводится к поиску алгоритма, который "побеждает все baseline-ы". Статья должна показать, как параметры робота, сенсоров, мусорного поля, дрейфа и физического сборщика определяют рациональный режим поведения: разведку, вероятностное планирование, короткий маршрутный горизонт, маршрутизацию по подтвержденным целям или локальную работу с найденной областью.

## Содержимое

- `cleanup_sim_v2/` - актуальный 2D Python-симулятор (density/count-map, лагранжев дрейф, физический swept-aperture сбор, `belief_horizon`/`belief_orienteering` планировщики). Основа текущей работы над статьёй.
- `cleanup_sim/` - legacy-симулятор (occupancy grid, `hybrid`/`graph_mst`/`hybrid_mst`). Не использовать для финальных результатов статьи; сохранён ради воспроизводимости старых экспериментов и как источник идей (MST-маршрутизация уже перенесена в план `cleanup_sim_v2` как baseline-слой).
- `tests/` - regression/unit tests для обоих симуляторов.
- `docs/project/` - актуальное состояние проекта, ревью репозитория, планы исправлений и научное направление.
- `docs/article/stage1/`, `docs/article/stage2/` - научная постановка и вклад; актуальный ориентир после pre-final результатов: `docs/article/stage1/stage1_reframing_after_prefinal_2026-08-16.md`. Более старые stage1/stage2 документы сохранены для traceability и помечены как частично исторические.
- `docs/article/results/` - Markdown-отчёты по pilot-результатам.

Главный ориентир по текущему состоянию проекта: `docs/project/current_state.md`.

Контекст восстановлен и проверен 2026-09-05: [сводка для продолжения работы](docs/project/project_memory_snapshot_2026-09-05.md), [разбор работы коллеги из PR #4](docs/project/adaptive_mission_revision_review_2026-09-05.md). Изменения коллеги, пять серий CSV и ограничения их интерпретации закреплены в рабочей ветке `feature/adaptive-mission-review`. Состояние этой ветки следует отличать от `main`.

Ближайший шаг: закрыть расхождение контрольного повтора с CSV коллеги и согласовать оценку маршрута с длительностью его исполнения. Бюджет `3000 м` остается диагностическим кандидатом. Seed-ы `100-129` уже использованы в тяжелой calibration-серии и не являются нетронутой финальной выборкой.

Главный ориентир по научному направлению: `docs/project/mission_regime_analysis_direction_2026-08-16.md`.

## Проверка

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

Проверенное окружение, число тестов и статус воспроизводимости указаны в [текущем состоянии](docs/project/current_state.md). Успешные unit tests не заменяют воспроизведение экспериментальных CSV.

Legacy-вариант через `requirements.txt` оставлен для совместимости:

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

## Запуск симулятора

```powershell
python -m cleanup_sim_v2.run_once --scenario weak_drift --mode greedy --seed 0 --out-dir out/cleanup_sim_v2/run_once
python -m cleanup_sim_v2.run_experiments --seeds 3 --modes greedy belief_horizon oracle_current_physics --out-dir out/cleanup_sim_v2/smoke
```

Подробности - в `docs/project/simulator_v2_implementation_notes.md`.

## Важное ограничение

Финальные confirmatory-результаты для статьи ещё не заморожены. `cleanup_sim_v2` готов для разработки и анализа режимов миссии (`READY FOR REGIME ANALYSIS`), но не для финального прогона (`NOT READY FOR FINAL CONFIRMATORY RUN`) - подробности в `docs/project/simulator_v2_1_closure_report.md`.

Не трактовать текущие baseline-ы как случайный турнир алгоритмов. Каждый режим должен отвечать на отдельный исследовательский вопрос: что дает равномерное покрытие, жадная эксплуатация карты, вероятностная разведка, короткий маршрутный горизонт, маршрутизация по подтвержденным целям и адаптивное переключение.

Не использовать старые raw-результаты из `out/` (особенно из `cleanup_sim`, до v2.1) как финальные таблицы статьи.

Подробный маршрут воспроизводимости: `docs/project/reproducibility_notes.md`.
