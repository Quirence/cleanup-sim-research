# Backlog готовности к финальному прогону

Дата: 2026-07-31  
Текущий verdict: **NOT READY**.

Правило: финальный `30 seed` прогон запрещен, пока P0-блокеры не закрыты и P1-проверки не пройдены smoke/confirmatory-прогоном.

## P0: блокеры финального прогона

| ID | Severity | Слой | Проблема | Evidence | Impact | Fix | Acceptance |
|---|---|---|---|---|---|---|---|
| P0-01 | Blocker | algorithm | `greedy` залипает в argmax | `cleanup_sim/planners.py:81`; smoke: `time_budget` во всех проверенных greedy runs | baseline нечестный, вывод “greedy хуже” незащитим | tabu/memory, исключение текущей цели, подавление belief после посещения | `greedy` проходит >=80-90% path budget на `3 scenarios x 5 seeds`, кроме `done` |
| P0-02 | Blocker | algorithm/science | `lawnmower` слишком sparse | `coverage_spacing_m=22`, `collect_radius_m=5` | adaptive/hybrid сравнивается со слабым coverage baseline | добавить `lawnmower_dense` или снизить spacing до `<=10 м`; текущий вариант назвать sparse | в финальном summary есть dense baseline; статья не называет sparse полным покрытием |
| P0-03 | Blocker | metrics | map quality использует исходный true occupancy после сбора | `simulation.py:68`, `metrics.py:60`, `sensors.py:51` | эффективный сбор штрафуется как плохая карта | разделить `initial_true_occ` и `residual_true_occ` | summary содержит `initial_map_*` и `residual_map_*`; result docs объясняют обе группы |
| P0-04 | Blocker | algorithm | active modes fallback-ятся в `greedy` | `planners.py:173-179` | active baseline загрязнен bugged greedy | хранить active goal или выбирать active fallback без greedy | в active series нет planner_mode `greedy`; smoke active не залипает |
| P0-05 | Blocker | reproducibility/science | final hybrid config не заморожен | `hybrid_candidate_v2` пока pilot | риск tuning-on-test | завести явно named final config до 30-seed | config snapshot сохраняется в out; seeds финального прогона определены заранее |
| P0-06 | Blocker | article | черновик статьи содержит устаревшие результаты/заявления | `docs/article/drafts/article_draft_probabilistic_mapping.md` | текст может противоречить текущему коду | пометить старые таблицы obsolete или переписать results section | в черновике нет 30-seed claims до финального run |

## P1: блокеры текста статьи и статистической защиты

| ID | Severity | Слой | Проблема | Evidence | Impact | Fix | Acceptance |
|---|---|---|---|---|---|---|---|
| P1-01 | Major | statistics | normal approximation p-value | `statistics.py:61-70` | p-values могут быть антиконсервативны, особенно на pilot | добавить Wilcoxon signed-rank или permutation test; оставить normal только diagnostic | `paired_comparisons.csv` содержит Wilcoxon/permutation p-value и Holm |
| P1-02 | Major | statistics | NaN threshold metrics молча удаляются | `paired_differences(...).dropna()` | теряется информация о недостижении 80/95% | добавить reach-rate и censored handling | финальные таблицы показывают долю seed, достигших порога |
| P1-03 | Major | science/algorithm | active-score не нормирован | `_score_candidate` суммирует по FOV | веса зависят от сетки/FOV | нормировать или добавить grid sensitivity | есть smoke/sensitivity по `50x50/100x100/200x200` либо честное ограничение |
| P1-04 | Major | targets | target precision низкий | smoke: `target_precision` около `0.06-0.14` для route modes | hybrid может тратить путь на ложные цели | усилить confirmation, suppression, stale policy; добавить sensitivity | target precision и false visits интерпретируемы; false visits не доминируют путь |
| P1-05 | Major | physics | мгновенный сбор радиусом `5 м` | `_collect_nearby`, `collect_radius_m=5` | завышает эффективность всех стратегий | sensitivity по radius; dwell-time или aperture model | финальные результаты сопровождаются physical sensitivity |
| P1-06 | Major | physics | `30 кг` capacity конфликтует с research-USV | BlueBoat/Heron payload меньше | некорректный образ платформы | выбрать reference class или sensitivity `10/30/60 кг` | в статье есть таблица параметров с источниками |
| P1-07 | Major | sensors | camera/radar - абстракция, не real CV/radar | RealSense depth range 0.3-3м; модель camera 28м | риск завышенного заявления | описать visual detector abstraction; radar detection как probabilistic assumption | текст не заявляет реализованную CV/radar детекцию |
| P1-08 | Major | science | нет final 30-seed run | текущие данные pilot/smoke | нет статистической базы | после P0/P1 smoke запустить final 30-seed | `summary.csv`, `aggregate`, `paired`, figures для final run существуют |

## P2: улучшения для ВАК-уровня

| ID | Severity | Слой | Проблема | Fix | Acceptance |
|---|---|---|---|---|
| P2-01 | Moderate | science | Нет expected information gain, только current entropy heuristic | либо реализовать approximate EIG, либо назвать метод heuristic | формулировка новизны не сводится к “новый EIG”, если EIG нет |
| P2-02 | Moderate | world | Мусор статичен, нет течений/ветра | добавить future work или отдельный stress scenario | раздел ограничений явно говорит `static debris` |
| P2-03 | Moderate | world | Binary occupancy не отражает count/density | добавить density/count map для анализа | текст различает occupancy и количество объектов |
| P2-04 | Moderate | reproducibility | Нет CI | добавить GitHub Actions pytest | pull/push прогоняет tests |
| P2-05 | Moderate | reproducibility | Нет lock/pyproject | добавить `pyproject.toml` или pinned env notes | коллега воспроизводит tests и smoke с чистой установки |
| P2-06 | Moderate | article | Недостаточно таблицы параметров с внешними источниками | собрать platform/sensor parameter table | методология имеет отдельную таблицу реалистичности |
| P2-07 | Moderate | experiment | Candidate-v2 выбран на pilot | pre-register final config и final seeds | result docs отделяют tuning и confirmatory |
| P2-08 | Moderate | plots | Нет финальных publication figures после ремонта | перегенерировать после final run | минимум 3 графика: curves, maps, trajectories/bar |

## P3: future work без блокировки текущей статьи

| ID | Severity | Слой | Тема | Комментарий |
|---|---|---|---|---|
| P3-01 | Minor | navigation | SLAM/NMHE/NMPC | Оставить как внешний слой и будущую интеграцию, не вклад статьи. |
| P3-02 | Minor | simulation | ROS/Gazebo | Не нужен для первой статьи, но полезен для диссертационного продолжения. |
| P3-03 | Minor | perception | Реальная CV-модель | Можно добавить позже на dataset floating waste. |
| P3-04 | Minor | physics | Волны/течение/дрейф мусора | Хороший следующий этап после базовой статьи. |
| P3-05 | Minor | robotics | Манипулятор/механизм сбора | Для инженерной статьи или второй работы. |

## Минимальный маршрут до READY

1. Исправить `greedy`, active fallback и `hybrid_switch_prob`.
2. Добавить dense lawnmower baseline.
3. Разделить map metrics на initial/residual.
4. Добавить статистику Wilcoxon/permutation + reach-rate.
5. Добавить физическую sensitivity: `collect_radius_m`, `bin_capacity_kg`, `speed_mps`.
6. Обновить README/results docs: старые pilot данные не финальные.
7. Выполнить smoke:

```powershell
python -m cleanup_sim.run_experiments `
  --seeds 5 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --modes lawnmower_sparse lawnmower_dense greedy active detected_tsp hybrid `
  --out-dir out/cleanup_sim/pre_final_smoke `
  --max-path-m 3000 `
  --tmax-s 6000
```

8. Если smoke чистый, запустить final:

```powershell
python -m cleanup_sim.run_experiments `
  --seeds 30 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --modes lawnmower_sparse lawnmower_dense greedy active detected_tsp hybrid `
  --out-dir out/cleanup_sim/final_30seed `
  --plot-examples
```

## READY criteria

Проект можно считать готовым к финальному прогону, когда:

- все P0 закрыты;
- P1-01, P1-02, P1-05, P1-06 закрыты или явно отражены в методологии/sensitivity;
- smoke на 5 seed показывает отсутствие залипаний;
- все strategies имеют сопоставимый path/time budget;
- старые result docs не используются как финальные;
- итоговые таблицы и графики строятся из одного final output directory;
- команда `python -m pytest -q` проходит.
