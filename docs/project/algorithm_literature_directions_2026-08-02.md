# Algorithm Literature Directions for `cleanup_sim_v2`

Дата: 2026-08-02.

Цель документа: выбрать направления алгоритмов для реализации поверх `cleanup_sim_v2.1`. Симулятор уже стал достаточно строгим физически, поэтому следующий вклад должен быть не “еще одна эвристика маршрута”, а алгоритм, который осмысленно работает с неполной картой, ложными наблюдениями, дрейфом мусора и физической ценой сбора.

## Текущая постановка

Задача в v2.1 не сводится к TSP. Робот не знает истинную карту мусора, получает шумные object-level наблюдения camera/radar, строит density/count-map, едет с ограниченной скоростью, собирает только в передней swept-aperture зоне, может промахиваться при захвате, имеет ограниченную емкость и работает при дрейфе мусора.

Следовательно, алгоритм должен решать конфликт:

```text
исследовать неизвестные области
vs
ехать к вероятным кластерам
vs
проверять подтвержденные цели
vs
физически собирать по траектории, а не точечно
vs
не тратить путь на ложные/устаревшие цели
```

## Что показала ветка `dev`

Коллега проверил `graph_mst` и `hybrid_mst` на старом `cleanup_sim`. Вывод полезный, но переносить результаты в статью нельзя, потому что они получены до v2.1.

Главный научный урок:

- MST улучшает порядок объезда уже подтвержденных целей относительно nearest-neighbor.
- MST почти не решает проблему поиска новых целей.
- Route-only методы структурно ограничены: они работают только с тем, что уже обнаружено и подтверждено.
- Поэтому MST/2-opt/ACO/TSP полезны как baseline routing layer, но не как основной вклад статьи.

## Литературные кластеры

| Кластер | Ключевые источники | Что дают нам | Решение |
|---|---|---|---|
| Floating-waste USV routing | Li et al. 2025, JMSE; SeaClear; DRL plastic-waste ASV paper | подтверждают актуальность search/collection, но часто работают с уже заданными целями или multi-robot схемой | использовать в обзоре и для baseline-позиционирования |
| Coverage path planning | Galceran & Carreras 2013; CPP для ASV/Dubins | честные baseline для обследования/траления | оставить `lawnmower_survey` и `lawnmower_collect` |
| Informative path planning | Hollinger & Sukhatme 2014; Binney & Sukhatme 2012; Singh et al. AUV IPP; Marchant & Ramos 2014 | планирование пути ради информации при бюджете | взять как математическую основу, но адаптировать под сбор |
| Orienteering / prize-collecting | Bottarelli et al. 2019; Yu/Schwager/Rus COP; Best & Fitch probabilistic set cover | выбор ограниченного маршрута по полезным точкам | главный мост к нашей задаче: reward = expected collection + information |
| POMDP / belief-space search | POMCP; OO-POMDP multi-object search; multi-resolution POMDP | строгий язык для частично наблюдаемого поиска | использовать как теоретическую рамку, но не делать полный POMDP solver первым |
| Pareto / multi-objective planning | Pareto MCTS for multi-objective informative planning; multi-objective orienteering | позволяет не прятать конфликт целей в один вес | перспективно для второго алгоритма/абляции |
| Learning-based / DRL | Robotic Learning for IPP survey; DeepIG; plastic-waste DRL ASV | высокий потолок, но тяжелая валидация и слабая интерпретируемость | future work, не первая реализация для ВАК-статьи |
| Drift / marine debris transport | OpenDrift; van Sebille et al.; Dobler et al. | оправдывает belief prediction step и drift scenarios | использовать для модели среды и ограничений |

## Матрица отбора направлений

Оценка: `1` - слабо, `5` - сильно. Это не публикационная статистика, а инженерно-научная матрица для выбора первого алгоритма.

| Направление | Шанс обойти `greedy` | Научная новизна для нашей задачи | Реализуемость в v2.1 | Интерпретируемость для ВАК | Риск подгонки | Итог |
|---|---:|---:|---:|---:|---:|---|
| MST/2-opt/ACO routing | 2 | 1 | 5 | 5 | 2 | baseline, не вклад |
| Adaptive coverage / density sweep | 3 | 2 | 4 | 5 | 2 | сильный baseline |
| Receding-horizon prize-collecting belief planner | 4 | 4 | 4 | 4 | 3 | основной кандидат |
| Pareto / multi-objective horizon | 4 | 5 | 3 | 4 | 3 | второй кандидат |
| POMCP / full POMDP | 5 | 5 | 2 | 3 | 4 | future work или отдельная статья |
| Learning-based / DRL | 4 | 4 | 2 | 2 | 5 | future work |
| Gaussian-process active mapping | 3 | 3 | 3 | 4 | 3 | полезно для карты, но не закрывает сбор |

Вывод матрицы: первый реализуемый вклад должен быть между orienteering/informative path planning и частично наблюдаемым поиском, но без тяжелого полного POMDP. Поэтому выбран `belief_horizon`: receding-horizon, ожидаемый reward, beam search, явное логирование компонентов score.

## Почему не начинать с полного POMDP или DRL

Полный POMDP теоретически красив: состояние включает карту мусора, положение робота, бункер, дрейф и наблюдения. Но даже в нашей 2D-сетке пространство состояний быстро становится слишком большим. Для первой статьи лучше использовать POMDP как язык постановки, а не как solver.

DRL близок к теме: свежие работы уже применяют deep reinforcement learning к plastic-waste collection с ASV. Но для нашей ближайшей статьи это опасно:

- понадобится отдельная среда обучения и тысячи прогонов;
- придется доказывать отсутствие переобучения на сценарии;
- сложнее объяснить, почему алгоритм принял конкретное решение;
- рецензенту ВАК проще защитить интерпретируемый model-based planner.

## Почему `belief_horizon` может быть научно сильнее MST

MST, TSP и ACO отвечают на вопрос:

```text
В каком порядке объехать известные цели?
```

Наша задача задает другой вопрос:

```text
Куда ехать, если цели известны неполно, карта шумная, мусор дрейфует,
а физический сбор происходит вдоль полосы движения?
```

Поэтому MST нужен, но только как контрольный route-baseline. Научный вклад должен быть в функции полезности, которая объединяет:

- ожидаемый физический сбор по swept-aperture;
- информационный выигрыш от сенсорного обзора;
- вероятность подтверждения цели;
- риск ложного визита;
- устаревание карты из-за дрейфа;
- цену пути, времени и возврата на базу.

## Источники для обязательного чтения

1. Roboat II: A Novel Autonomous Surface Vessel for Urban Environments.  
   https://arxiv.org/abs/2007.10220

2. A Receding Horizon Multi-Objective Planner for Autonomous Surface Vehicles in Urban Waterways.  
   https://arxiv.org/abs/2007.08362

3. SeaClear project overview.  
   https://seaclear-project.eu/about-main/about-seaclear

4. The SeaClear system: An intelligent multi-robot solution for autonomous cleanup of marine debris on the seabed.  
   https://publica-rest.fraunhofer.de/server/api/core/bitstreams/9df79fcc-7338-4f08-93fe-e4cbf5a931ff/content

5. Active Mapping of Underwater Litter Using Camera-Based Detection and Gaussian Processes.  
   https://busoniu.net/files/papers/aqtr26-david.pdf

6. An Unmanned Vessel Path Planning Method for Floating-Waste Cleaning Based on TSP/ACO.  
   https://www.mdpi.com/2077-1312/13/8/1579

7. FloW: A Dataset and Benchmark for Floating Waste Detection in Inland Waters.  
   https://openaccess.thecvf.com/content/ICCV2021/papers/Cheng_FloW_A_Dataset_and_Benchmark_for_Floating_Waste_Detection_in_ICCV_2021_paper.pdf

8. A survey on coverage path planning for robotics.  
   https://www.sciencedirect.com/science/article/abs/pii/S092188901300167X

9. Sampling-based robotic information gathering algorithms.  
   https://journals.sagepub.com/doi/abs/10.1177/0278364914533443

10. Branch and Bound for Informative Path Planning.  
    https://uscresl.org/publication/branch-and-bound-for-informative-path-planning/

11. Informative Path Planning for an Autonomous Underwater Vehicle.  
    https://authors.library.caltech.edu/records/19ext-ajr84/files/05509714.pdf

12. Bayesian Optimisation for Informative Continuous Path Planning.  
    https://fabioramos.github.io/Publications_files/Roman_ICRA14.pdf

13. Orienteering-based informative path planning for environmental monitoring.  
    https://www.sciencedirect.com/science/article/abs/pii/S095219761830201X

14. Correlated Orienteering Problem and its Application to Informative Path Planning for Persistent Monitoring Tasks.  
    https://arxiv.org/abs/1402.1896

15. Probabilistic Maximum Set Cover with Path Constraints for Informative Path Planning.  
    https://www.araa.asn.au/acra/acra2016/papers/pap141s1.pdf

16. Path Planning With Spatiotemporal Optimal Stopping for Stochastic Mission Monitoring.  
    https://ieeexplore.ieee.org/document/7859467/

17. Pareto Monte Carlo Tree Search for Multi-Objective Informative Planning.  
    https://arxiv.org/pdf/2111.01825

18. Online Monte-Carlo Planning in Large POMDPs.  
    https://papers.nips.cc/paper_files/paper/2010/file/edfbe1afcf9246bb0d40eb4d8027d90f-Paper.pdf

19. Multi-Object Search using Object-Oriented POMDPs.  
    https://par.nsf.gov/servlets/purl/10146415

20. Multi-Resolution POMDP Planning for Multi-Object Search in 3D.  
    https://irl.cs.brown.edu/pubs/multires_3dsearch.pdf

21. Robotic Learning for Informative Path Planning.  
    https://arxiv.org/html/2404.06940v2

22. Optimizing Plastic Waste Collection in Water Bodies Using Heterogeneous Autonomous Surface Vehicles with Deep Reinforcement Learning.  
    https://arxiv.org/abs/2412.02316

23. The physical oceanography of the transport of floating marine debris.  
    https://ora.ox.ac.uk/objects/uuid%3A5a358dea-f895-4c36-9aed-d2c2b984244c

24. On the Fate of Floating Marine Debris Carried to the Sea through the Main Rivers of Indonesia.  
    https://cnrs.hal.science/hal-04960072v1/file/jmse-10-01009-v2.pdf

## Выбранные направления реализации

### Направление A: Drift-Aware Receding-Horizon Prize-Collecting Planner

Рабочее имя: `belief_horizon`.

Это основной кандидат для статьи.

Идея: на каждом шаге строить набор возможных действий и выбирать не ближайшую “горячую” ячейку, а короткий план на горизонт `H`, максимизирующий ожидаемую полезность:

```text
U = expected_collected_mass
  + beta_info * expected_information_gain
  + beta_confirm * expected_target_confirmation
  - lambda_path * travel_cost
  - lambda_empty * empty_goal_risk
  - lambda_stale * stale_target_risk
  - lambda_return * capacity_return_penalty
```

Кандидаты действий:

- confirmed targets;
- локальные максимумы density-map;
- точки с высокой энтропией;
- короткие collection-transects через вероятные кластеры;
- depot/return action;
- продолжение coverage-route как fallback.

Почему это сильнее текущего `greedy`:

- `greedy` выбирает один максимум карты и не видит, что рядом может быть кластер/полоса сбора.
- `belief_horizon` может предпочесть точку чуть хуже по карте, но лучше по ожидаемому сбору вдоль пути.
- Алгоритм может учитывать дрейф, устаревание целей, вероятность пустого визита и емкость бункера.

Научная ценность:

- это не просто “эвристика entropy”;
- постановка ближе к prize-collecting / informative orienteering under uncertainty;
- можно честно сравнивать oracle-gap;
- хорошо объясняется в статье на русском языке.

Сложность: средняя. Реалистично сделать первым.

### Направление B: Pareto / Multi-Objective Receding-Horizon Planner

Рабочее имя: `pareto_horizon` или `pareto_mcts`.

Идея: не сводить все цели к одному весовому коэффициенту, а строить Pareto-набор действий по нескольким критериям:

- ожидаемый сбор;
- информационный выигрыш;
- риск пустого визита;
- путь/время;
- риск устаревания цели;
- необходимость возврата на базу.

Преимущество:

- для статьи это может быть сильнее, чем один hand-tuned score;
- можно показать trade-off surfaces и условия применимости;
- хорошо объясняет, почему разные стратегии выигрывают в разных сценариях.

Риск:

- труднее реализовать и интерпретировать;
- нужно аккуратно выбирать правило выбора из Pareto-front;
- может быть вторым этапом после `belief_horizon`.

### Направление C: Graph/MST/2-opt Routing как baseline, а не вклад

Рабочие режимы: `graph_mst_v2`, `route_2opt_v2`.

Идея: перенести полезные части из ветки `dev` в `cleanup_sim_v2.1`, но только как route baseline.

Что переносить:

- MST/preorder route для confirmed targets;
- invalidation route при появлении новой цели;
- тесты, что маршрут отличается от nearest-neighbor;
- сравнение с `confirmed_route`.

Что не заявлять:

- что MST является новым методом;
- что MST решает search/collection;
- что dev-результаты применимы к v2.1.

Научная роль:

- честный baseline для утверждения: “мы не просто сравнили с ближайшим соседом”.

### Направление D: Adaptive Coverage / Swept-Aperture Coverage Baseline

Рабочее имя: `adaptive_lawnmower` или `density_sweep`.

Идея: построить более честный coverage baseline, который изменяет плотность проходов в зависимости от density-map, но не делает сложного belief planning.

Почему нужно:

- `lawnmower_survey` и `lawnmower_collect` сейчас задают крайности;
- между ними нужен baseline: “покрытие плотнее там, где карта обещает больше мусора”.

Научная роль:

- сильный baseline, который может отобрать у нас легкие победы;
- если `belief_horizon` выигрывает и у него, результат становится намного убедительнее.

### Направление E: DRL / Learning-Based Planner

Рабочий статус: future work.

Почему не первым:

- нужна среда обучения, reward shaping, много прогонов, контроль переобучения;
- сложнее объяснить ВАК-рецензенту, почему именно сеть сделала правильное решение;
- хуже воспроизводимость при малых ресурсах.

Почему держать в обзоре:

- есть близкая работа по heterogeneous ASV для plastic-waste collection;
- можно использовать как аргумент, что наша первая статья сознательно делает интерпретируемый model-based planner.

## Рекомендуемый порядок работ

1. Перенести MST/2-opt из `dev` в v2.1 как baseline, но не как научный центр.
2. Реализовать `belief_horizon` с детерминированным expected rollout.
3. Сделать smoke: `3 seeds x 4 scenarios x modes`.
4. Если `belief_horizon` не улучшает `greedy`, не подгонять веса вслепую, а смотреть decomposition метрик:
   - где теряется путь;
   - где растут пустые визиты;
   - где карта устаревает;
   - где сбор не происходит из-за физики.
5. После устойчивого результата добавить `adaptive_lawnmower`.
6. Только затем рассматривать `pareto_horizon` / `pareto_mcts`.

## Минимальная спецификация `belief_horizon`

Публичный режим:

```text
--mode belief_horizon
```

Основные параметры:

```text
planner.horizon_depth = 3
planner.rollout_branching = 8
planner.belief_horizon_candidate_count = 30
planner.expected_collection_weight = 1.0
planner.information_gain_weight = 0.25
planner.target_confirmation_weight = 0.35
planner.path_cost_weight = 0.01
planner.empty_goal_risk_weight = 0.7
planner.stale_target_risk_weight = 0.3
```

Внутренние шаги:

1. Сформировать кандидаты из confirmed targets, density peaks, entropy peaks, short transects и depot.
2. Для каждого кандидата оценить:
   - ожидаемую массу/число объектов в swept-aperture по текущей density-map;
   - ожидаемый sensor gain в FOV;
   - риск пустого визита;
   - стоимость пути/времени с учетом cruise/collection speed;
   - влияние дрейфа на карту за время пути.
3. Выполнить beam search на глубину `H`.
4. Вернуть первый waypoint/primitive лучшего плана.
5. Логировать причину выбора и компоненты score в `events`.

## Критерии научного успеха

`belief_horizon` имеет смысл как главный алгоритм только если на pre-final `10 seeds`:

- снижает oracle-gap относительно `greedy` хотя бы в части сценариев;
- улучшает `auc_collected_by_path` или `collected_ratio_at_3km` относительно `greedy` с paired-seed анализом;
- не выигрывает только за счет одного случайного seed;
- снижает `empty_goal_arrivals_per_km` или `wasted_path_ratio`;
- сохраняет честность: без доступа к истинной карте и `source_index`.

Если `belief_horizon` не выигрывает у `greedy`, публикационная постановка должна сместиться:

- либо к анализу пределов route/exploration методов при ложных наблюдениях;
- либо к multi-objective/Pareto версии;
- либо к stronger adaptive coverage baseline.

## Вердикт

Основное направление на реализацию: **Drift-Aware Receding-Horizon Prize-Collecting Planner**.

Второе направление: **Pareto/MCTS multi-objective planner**.

Обязательный baseline: **MST/2-opt routing по подтвержденным целям**, перенесенный из `dev` в v2.1.

DRL и полный POMDP оставляем в обзоре и future work. Они теоретически сильные, но сейчас слишком тяжелые и менее интерпретируемые для ближайшей ВАК-ориентированной статьи.
