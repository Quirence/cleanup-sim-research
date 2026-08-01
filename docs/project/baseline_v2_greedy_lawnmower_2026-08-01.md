# Baseline v2: greedy and lawnmower

Дата: 2026-08-01.

Цель: получить первые воспроизводимые baseline-метрики для `cleanup_sim_v2` после отказа от мгновенного кругового сбора. Это не финальный эксперимент статьи, а базовая серия для ревью и дальнейшей разработки алгоритмов.

## Методическое решение

В v2 нельзя оставлять один безымянный `coverage`, потому что "lawnmower" может означать разные физические действия:

- `lawnmower_survey` - систематический галсовый маршрут для сенсорного обследования. Шаг между галсами задается по эффективной ширине camera-наблюдения, а сбор происходит только если объект физически попал в узкую переднюю полосу захвата.
- `lawnmower_collect` - физически плотное "траление" с шагом `0.8 * collection_width_m`. Это честная, но очень дорогая стратегия сбора при ширине захвата около 1 м.
- `greedy` - движение к максимуму текущей density-map без доступа к ground truth. Пустые цели теперь считаются для него так же, как для остальных стратегий.

Такое разделение важно для статьи: нельзя сравнивать адаптивные алгоритмы с произвольным "lawnmower", не указав, покрывает он сенсорную область или физическую полосу сборщика.

## Команда

```powershell
python -m cleanup_sim_v2.run_experiments `
  --baseline-only `
  --seeds 10 `
  --scenarios static_calm weak_drift strong_drift robot_disturbed `
  --profile nominal `
  --max-path-m 3600 `
  --tmax-s 9000 `
  --out-dir out\cleanup_sim_v2\baseline_v2_10seeds_2026-08-01
```

Все 120 прогонов завершились по `path_budget`. Среднее время выполнения: около 6.4 секунды на прогон.

## Основные метрики

| scenario | mode | collected ratio, mean | std | AUC path, mean | std | empty goals, mean | wasted path, mean, m |
|---|---:|---:|---:|---:|---:|---:|---:|
| robot_disturbed | greedy | 0.264 | 0.085 | 0.155 | 0.062 | 177.5 | 3270.24 |
| robot_disturbed | lawnmower_collect | 0.013 | 0.012 | 0.010 | 0.010 | 35.3 | 3155.76 |
| robot_disturbed | lawnmower_survey | 0.030 | 0.012 | 0.022 | 0.010 | 29.5 | 2879.82 |
| static_calm | greedy | 0.482 | 0.070 | 0.270 | 0.062 | 186.1 | 2726.88 |
| static_calm | lawnmower_collect | 0.045 | 0.038 | 0.019 | 0.019 | 32.5 | 2631.60 |
| static_calm | lawnmower_survey | 0.072 | 0.022 | 0.045 | 0.017 | 26.6 | 2302.26 |
| strong_drift | greedy | 0.493 | 0.080 | 0.296 | 0.055 | 164.0 | 3229.38 |
| strong_drift | lawnmower_collect | 0.009 | 0.006 | 0.008 | 0.006 | 35.9 | 3268.08 |
| strong_drift | lawnmower_survey | 0.010 | 0.011 | 0.009 | 0.009 | 31.8 | 3293.04 |
| weak_drift | greedy | 0.323 | 0.159 | 0.174 | 0.077 | 174.2 | 3096.36 |
| weak_drift | lawnmower_collect | 0.022 | 0.017 | 0.016 | 0.011 | 34.2 | 2968.50 |
| weak_drift | lawnmower_survey | 0.059 | 0.026 | 0.041 | 0.018 | 27.3 | 2520.00 |

Сырые данные:

- `out/cleanup_sim_v2/baseline_v2_10seeds_2026-08-01/summary.csv`
- `out/cleanup_sim_v2/baseline_v2_10seeds_2026-08-01/aggregate_mean_std.csv`

## Первичная интерпретация

- `greedy` стал сильным baseline-ом на v2: он заметно превосходит оба lawnmower-режима по доле сбора и AUC.
- У `greedy` много пустых целей. Это больше не скрытый артефакт: `empty_goal_arrivals` и `wasted_path_to_empty_goals` теперь прямо показывают цену жадной эксплуатации карты.
- `lawnmower_collect` показывает, насколько плохо масштабируется чистое физическое траление при ширине сбора около 1 м и бюджете 3600 м.
- `lawnmower_survey` полезен как baseline обследования, но не как сильная стратегия сбора: он покрывает сенсорную область галсами, однако физический сбор остается узким.
- Эти результаты поддерживают научную постановку: для сборщика с узким рабочим органом нужен не просто равномерный маршрут, а стратегия, связывающая обнаружение, подтверждение, целевое наведение и физический захват.

## Ограничения

- 10 seed достаточно для baseline-рецензии, но не для финальной статистики статьи.
- Параметры сенсоров и захвата пока не прошли полную calibration/sensitivity серию.
- Алгоритмы `active` и будущий гибрид должны разрабатываться уже после принятия этих baseline-режимов.
- `lawnmower_collect` не является "плохим baseline"; он демонстрирует физическую цену полной зачистки узкой полосой.

## Источниковая опора

- Coverage/lawnmower как классический маршрут систематического покрытия: [Choset, "Coverage for robotics - A survey of recent results"](https://link.springer.com/article/10.1023/A%3A1016639210559).
- Более поздние обзоры CPP определяют coverage path planning как построение пути, проходящего через всю область интереса: [Galceran and Carreras, "A survey on coverage path planning for robotics"](https://www.sciencedirect.com/science/article/abs/pii/S092188901300167X).
- USV coverage planning использует lawnmower-like галсы как стандартный шаблон для обследования акватории; пример современной USV-CPP постановки: [MDPI JMSE 2023, "Complete Coverage Path Planning for Unmanned Surface Vehicle Based on Deep Reinforcement Learning"](https://www.mdpi.com/2077-1312/11/3/645).
- Для v2 мы разделяем сенсорное покрытие и физическую полосу сбора, потому что у реального мусоросборщика это разные ограничения.
