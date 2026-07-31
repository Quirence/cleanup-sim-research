# Глубокое резюме 4 статей для переработки статьи и будущей симуляции

Дата: 2026-07-11

Папка с материалами:

`C:\Users\Quirence\PycharmProjects\Education\01_Учебные_дисциплины\datascience\Материалы`

Извлечённый текст:

`out/literature_text`

Цель этого документа: сохранить не общий пересказ, а рабочие элементы, которые понадобятся для новой версии статьи и для реализации симулятора:

- постановки задач;
- модели среды;
- модели сенсоров;
- вероятностные карты;
- алгоритмы маршрутизации;
- baseline-ы;
- метрики;
- ограничения;
- идеи, которые можно аккуратно перенести в нашу работу.

## Общий вывод по 4 статьям

В мировой литературе тема автономного сбора мусора уже развивается в нескольких направлениях:

1. **Маршрутизация USV для сбора плавающего мусора**, когда координаты целей известны или получены модулем восприятия.
2. **Активное вероятностное картирование**, когда робот сам выбирает следующие точки наблюдения, чтобы быстрее найти объекты при неопределённых сенсорных данных.
3. **UAV+USV collaborative cleaning**, где UAV выполняет быстрый осмотр поверхности, а USV собирают мусор.
4. **Комплексные multi-robot системы**, такие как SeaClear, где есть обнаружение, картирование, навигация, сбор и реальные полевые эксперименты.

Для нашей статьи наиболее сильная ниша:

> перенести логику active probabilistic mapping на задачу **плавающего мусора на поверхности воды** и связать её с адаптивным маршрутом **одного надводного робота** в 2D-симуляции.

Это отличается от:

- чистой TSP/ACO-маршрутизации, где цели уже известны;
- чистой CV-детекции, где нет карты и планирования;
- underwater litter mapping, где другая среда и сенсоры;
- больших multi-robot систем, где вклад распылён между многими подсистемами.

---

# 1. Li et al. 2025 — USV path planning for floating-waste cleaning based on IACO

Файл:

`Материалы/jmse-13-01579.pdf`

Полное название:

**An Unmanned Vessel Path Planning Method for Floating-Waste Cleaning Based on an Improved Ant Colony Algorithm**

Журнал:

Journal of Marine Science and Engineering, 2025, 13, 1579.

DOI:

https://doi.org/10.3390/jmse13081579

## Главная идея

Авторы предлагают интегрированную схему планирования пути для USV, который собирает плавающий мусор. Система делится на два уровня:

1. **Global patrol path planning** — глобальный патрульный маршрут по точкам покрытия акватории.
2. **Local cleaning path planning** — локальный маршрут сбора обнаруженных целей.

Обе задачи сводятся к **Traveling Salesman Problem (TSP)**, а решаются улучшенным ant colony optimization algorithm (**IACO**).

## Что важно для нашей статьи

Это ближайшая работа-конкурент. Её нужно обязательно цитировать и от неё отстраиваться.

Их вклад:

- строят global patrol points по карте акватории;
- используют perception module для получения координат floating waste;
- после обнаружения целей решают TSP локального сбора;
- используют radar + camera fusion;
- разворачивают алгоритмы как ROS nodes на Jetson Xavier NX;
- проверяют IACO на TSPLIB и на прикладных сценариях.

Наше отличие:

- у нас не просто TSP по уже известным точкам мусора;
- у нас мусор представлен как **вероятностное поле/карта**, уточняемая по мере движения;
- планирование должно учитывать **неопределённость** и неполные наблюдения;
- локальные цели не считаются полностью известными заранее.

## Модель задачи у авторов

### Глобальная задача

Акватория разбивается на точки патрулирования. В статье точкам соответствуют координаты, полученные с satellite map. Затем они переводятся в TSP.

Смысл:

- задан набор патрульных точек;
- нужно построить кратчайший маршрут обхода;
- маршрут возвращается к стартовой точке.

### Локальная задача

Во время патруля USV обнаруживает мусор через perception module. Обнаруженные цели получают координаты. После этого строится локальный маршрут сбора, тоже как TSP.

Важное отличие от нас: если detection module выдал цель, дальше она становится точкой маршрута. Вероятностная неопределённость карты почти не рассматривается.

## Формализация TSP

У авторов:

- `n` — число патрульных или целевых точек;
- `D_ij` — расстояние между точками `i` и `j`;
- `x_ij` — бинарная переменная перехода из `i` в `j`;
- минимизируется суммарная длина маршрута.

Для нашей реализации это можно использовать как baseline:

```text
min sum_i sum_j D_ij x_ij
```

С ограничениями:

- каждая точка посещается один раз;
- устраняются подциклы;
- маршрут замкнут для глобального патруля или может быть незамкнут для локального сбора.

## Система восприятия

Авторы используют radar + camera fusion:

- vision sensor даёт цвет/текстуру и bounding boxes;
- radar устойчивее к помехам и даёт пространственную информацию;
- fusion нужен для локализации плавающего мусора.

В статье упоминается:

- Texas Instruments 77 GHz radar;
- максимальная sensing distance около **14.7 m**;
- YOLO-Float;
- FloW-RI dataset;
- метрики `mAP`, `mAP50`, `mAP75`, `mAR`, `FPS`;
- локализационные метрики fusion: `Edeg`, `Edis`, `Eloc`, `Loss`.

Для нашей симуляции это можно упростить:

- задать дальность сенсора `R`;
- задать вероятность детекции `p_det(d, angle)`;
- задать false positive rate;
- добавить ошибку локализации обнаруженной цели;
- позднее заменить на реальные вероятности из CV-модуля.

## Экспериментальные метрики у авторов

Для path planning:

- mean path length;
- min path length;
- variance;
- confidence bound;
- p-values для сравнения.

Для perception:

- mAP;
- mAP50;
- mAP75;
- mAR;
- параметрический размер модели;
- FPS;
- errors локализации после fusion.

Для нашей статьи лучше взять:

- средняя длина пути;
- время до сбора 50%, 80%, 95% мусора;
- доля собранного мусора за фиксированное время;
- число пройденных метров на один собранный объект;
- стабильность по seed-ам;
- качество карты: IoU/F1/MAE/Brier score по сетке.

## Что перенести в симулятор

Минимально:

1. Baseline `TSP-greedy` или `ACO/TSP` по известным целям.
2. Разделение на:
   - глобальное покрытие;
   - локальный сбор.
3. Модель detection module как источника координат мусора с ошибкой.
4. Таблицу сравнения с:
   - lawnmower;
   - greedy;
   - active probabilistic planner;
   - optional TSP/ACO по oracle-целям.

## Ограничение статьи, полезное для нашей новизны

У Li et al. основная неопределённость сенсорного обнаружения не превращается в карту вероятностей, которая управляет следующим наблюдением. Это и есть наша ниша.

---

# 2. David et al. — Active Mapping of Underwater Litter Using Camera-Sonar Fusion

Файл:

`Материалы/aqtr26-david.pdf`

Полное название:

**Active Mapping of Underwater Litter Using Camera-Sonar Fusion**

## Главная идея

Робот строит **Bayesian occupancy map** мусора и сам выбирает следующую точку обзора (**next-best-view**), чтобы быстрее найти объекты. Используются:

- camera;
- forward-looking sonar;
- shared probabilistic occupancy map;
- utility function = exploration + exploitation;
- сравнение с lawnmower pattern.

Это самая важная методологическая статья для нас.

## Почему она критична для нашей работы

Она почти напрямую даёт математическую основу:

- карта вероятностей;
- энтропия ячеек;
- активный выбор следующей точки;
- баланс исследования неизвестных областей и уточнения вероятных объектов;
- оценка "objects detected vs distance traveled";
- baseline `lawnmower`.

Наша адаптация:

- вместо 3D underwater voxel grid использовать 2D surface grid;
- вместо camera+sonar использовать camera/radar или camera-only;
- вместо UUV использовать USV;
- вместо seabed litter — floating surface debris;
- добавить возможность дрейфа мусора в будущих версиях.

## Occupancy-grid mapping

Авторы представляют среду как 3D occupancy grid:

- ячейки/voxels индексируются `i`;
- у каждой ячейки есть вероятность занятости `b_i ∈ [0, 1]`;
- истинная карта `m_i ∈ {0, 1}`;
- `m_i = 1` означает, что в ячейке есть объект.

Для нашей статьи:

```text
Акватория Ω ⊂ R² дискретизируется на сетку G = {g_i}.
Каждая ячейка имеет скрытое состояние m_i ∈ {0,1}.
Вероятность наличия мусора задаётся b_i = P(m_i = 1).
```

## Энтропия карты

Авторы используют entropy ячейки как меру неопределённости:

```text
h_i = - b_i log(b_i) - (1 - b_i) log(1 - b_i)
```

Интерпретация:

- `b_i ≈ 0.5` — высокая неопределённость;
- `b_i ≈ 0` или `b_i ≈ 1` — низкая неопределённость.

Для нашей симуляции это прямо нужно реализовать.

## Sensor model

Важный элемент: вероятность детекции зависит от геометрии наблюдения:

- distance/range;
- bearing/angle;
- sensor field of view;
- true positive probability;
- false alarm probability.

Авторы строят probability tables по данным симуляции:

- target-present runs для true positive;
- target-absent runs для false alarms;
- отдельные модели для sonar и camera;
- затем fusion выполняется последовательными Bayesian updates.

Для нашей реализации:

```python
p_det = sigmoid((R0 - d) / kappa) * angle_weight(phi)
p_false = const or function of glare/noise
```

Более реалистичный вариант:

- таблица `P(z=1 | m=1, d, phi)`;
- таблица `P(z=1 | m=0, d, phi)`;
- обновление `b_i` через Байеса или log-odds.

## Active planner: next-best-view

У авторов есть множество waypoint-ов `W`. На каждом шаге выбирается следующий waypoint:

```text
w_{k+1} = argmax_{w∈W} sum_{i∈φ(w)} ( h_i + α I(b_i ∈ [b_lower, b_upper]) )
```

Где:

- `φ(w)` — множество ячеек, попадающих в поле зрения сенсоров из waypoint `w`;
- `h_i` — энтропия ячейки, exploration;
- `I(b_i ∈ [b_lower, b_upper])` — indicator likely object candidate, exploitation;
- `α` — вес exploitation;
- `[b_lower, b_upper]` задаёт диапазон вероятных, но ещё не полностью подтверждённых объектов.

Это можно почти напрямую перенести в наш симулятор.

## Как адаптировать objective function для нашей задачи

Нужно добавить стоимость перемещения:

```text
score(w) =
    Σ_{i∈FOV(w)} [ H(b_i) + α · I(b_low < b_i < b_high) ]
    - λ · dist(x_robot, w)
```

Или нормировать:

```text
score(w) = information_gain(w) / (dist(x_robot,w) + ε)
```

Почему это важно:

- у underwater paper цель — быстрее найти объекты;
- у нас цель — ещё и эффективно собрать мусор;
- без штрафа на расстояние робот может прыгать между удалёнными областями.

## Эксперимент у авторов

Сравнение:

- active mapping;
- lawnmower coverage.

Метрика:

- objects detected vs distance traveled.

В одном эксперименте active search находит все объекты примерно за **60 m**, а lawnmower требует около **110 m**.

Отдельно сравнивают:

- dual-sensor active search;
- sonar-only;
- camera-only.

Вывод:

- fusion быстрее, чем отдельные сенсоры;
- активный поиск лучше фиксированного покрытия.

## Что перенести в нашу статью

1. Формулу entropy.
2. Next-best-view objective.
3. Baseline lawnmower.
4. Метрику `objects detected / collected vs distance traveled`.
5. Сравнение single-sensor vs fused-sensor в будущем.
6. Идею sensor reliability tables.

## Что перенести в симуляцию

### Минимальная версия

- 2D grid;
- `b_i` probability map;
- entropy map;
- candidate waypoints;
- FOV;
- detection probability by range;
- false positives;
- active planner;
- lawnmower baseline.

### Следующая версия

- camera + radar как два сенсора;
- разная дальность и FOV;
- последовательное Bayesian update;
- сравнение camera-only, radar-only, fusion.

### Продвинутая версия

- дрейф мусора;
- non-myopic planner;
- планирование не только наблюдения, но и сбора.

---

# 3. Deng et al. 2025 — UAV + USVs collaborative water surface coverage and cleaning

Файл:

`Материалы/1-s2.0-S2352864822002826-main.pdf`

Полное название:

**Automatic collaborative water surface coverage and cleaning strategy of UAV and USVs**

Журнал:

Digital Communications and Networks, 2025.

DOI страницы ScienceDirect:

https://doi.org/10.1016/j.dcan.2022.12.014

## Главная идея

Авторы предлагают систему:

- один UAV выполняет быстрый осмотр поверхности воды;
- несколько USV собирают мусор;
- CCV обеспечивает координацию и зарядку UAV;
- задачи распределяются между USV;
- USV строят маршруты с obstacle avoidance.

## Что важно для нашей статьи

Эта работа показывает, что разделение задач "поиск" и "сбор" является устойчивым направлением:

- UAV хорошо покрывает большую площадь;
- USV хорошо выполняет сбор благодаря грузоподъёмности;
- одновременное inspection + cleaning эффективнее последовательного процесса.

Мы пока не делаем UAV, но можем указать:

- наш симулятор рассматривает single-USV вариант;
- в будущем карта вероятностей может обновляться и с UAV-наблюдений;
- архитектура совместима с multi-agent расширением.

## Предположения модели

Авторы явно задают:

1. Границы акватории известны.
2. UAV и USV используют общую систему координат.
3. Водная поверхность рассматривается как 2D-плоскость.
4. UAV имеет ограничения дальности связи и энергии.
5. Communication delay и processing delay игнорируются.
6. UAV при разряде садится на CCV для замены батареи.

Для нашей статьи можно использовать похожий набор предположений, но адаптировать:

1. Границы акватории известны.
2. Движение рассматривается в локальной 2D-системе координат.
3. Положение робота считается известным с заданной ошибкой локализации.
4. Сенсор имеет ограниченную дальность, FOV, false positives и misses.
5. Динамика мусора в базовой версии не учитывается.

## Coverage path planning

UAV покрывает акваторию по подзонам. Внутри подзоны применяется reciprocating/serpentine coverage.

Для нашей работы это полезно как baseline:

- `lawnmower`;
- `serpentine coverage`;
- равномерное покрытие всей акватории.

## Task assignment для USV

Авторы формализуют назначение мусорных целей нескольким USV:

- есть `n` USV;
- есть `m` garbage tasks;
- `ε_ij = 1`, если задача `j` назначена USV `i`;
- минимизируется суммарная стоимость назначения.

Для нас это пока резерв. Но если позже расширять симуляцию до нескольких USV, можно использовать:

```text
min Σ_i f(u_i)
```

с учётом:

- расстояния до задач;
- текущей загрузки контейнера;
- баланса между аппаратами.

## Clearance path planning

После назначения задач USV строит маршрут обхода garbage nodes.

Авторы используют:

- graph representation;
- grid model;
- ACO-based obstacle avoidance;
- path cost с учётом расстояния до цели и расстояния до препятствий.

Полезно для нас:

- добавить препятствия в будущую 2D-среду;
- использовать grid-based motion;
- учитывать obstacle penalty.

## Метрики

В статье важны:

- total cleaning time;
- path cost;
- workload balance;
- convergence curves;
- сравнение single/multiple USV strategies;
- сравнение PSO task assignment и greedy assignment.

Для нашей статьи:

- если остаёмся с одним USV, не берём task assignment;
- берём `cleaning time`, `path length`, `coverage completion`, `collected debris ratio`.

## Что перенести в симулятор

На первом этапе:

- `lawnmower/serpentine coverage` как baseline.
- Разделение режима:
  - exploration/coverage;
  - exploitation/cleaning.

На втором этапе:

- obstacles;
- grid-based obstacle avoidance;
- multi-USV task assignment.

## Чем наша работа отличается

Deng et al. решают multi-agent координацию UAV+USV. Наша работа решает вероятностное принятие решений одним USV при неопределённой карте мусора.

---

# 4. Ilioudi et al. 2026 — The SeaClear system

Файл:

`Материалы/1-s2.0-S0952197626003751-main.pdf`

Полное название:

**The SeaClear system: An intelligent multi-robot solution for autonomous cleanup of marine debris on the seabed**

Журнал:

Engineering Applications of Artificial Intelligence, 2026.

## Главная идея

SeaClear — комплексная multi-robot система для автономного обнаружения, картирования и сбора мусора со дна. Система включает:

- USV SeaCat;
- collection basket;
- Observation ROV;
- Collection ROV;
- UAV;
- YOLO для детекции;
- mapping pipeline;
- navigation and control;
- field experiments.

## Почему статья важна

Это системный ориентир: как выглядит полноценная робототехническая система уровня публикации в серьёзном журнале.

Для нас важно не копировать подводную систему, а взять структуру:

```text
survey -> detection -> mapping -> planning -> collection -> validation
```

И показать, что наша работа реализует один алгоритмический слой этой цепочки для surface debris.

## Архитектура SeaClear

Система состоит из пяти компонентов:

1. **USV** сканирует морское дно и служит надводной платформой.
2. **Collection basket** хранит собранный мусор.
3. **Observation ROV** ищет мусор под водой.
4. **Collection ROV** собирает мусор.
5. **UAV** ищет мусор с воздуха и помогает с situational awareness.

Для нашей архитектуры можно упростить:

```text
USV + camera/radar/GNSS/IMU
    -> detection
    -> probability map
    -> active route planner
    -> trajectory follower
```

## Сенсоры и навигация

USV SeaCat имеет:

- multibeam echosounder;
- DGPS/RTK GPS;
- gyrocompass;
- onboard interfaces.

ROV имеют:

- cameras;
- sonar;
- AHRS/IMU;
- depth sensors;
- acoustic positioning.

Для нашей статьи:

- не нужно тащить весь набор сенсоров;
- важно указать, что реальная робототехническая система требует связки локализации, восприятия и карты;
- для поверхности воды основными сенсорами мусора являются camera/radar, а LiDAR/sonar/RTK — навигационный и вспомогательный слой.

## Detection metrics

SeaClear использует YOLO и оценивает:

- Precision;
- Recall;
- F1;
- mAP;
- AP at IoU thresholds.

Они сообщают высокую результативность YOLO для trash detection в их датасете, включая `mAP@0.5`.

Для нашей статьи:

- если CV не реализован, не заявлять собственную mAP;
- использовать detection module как вероятностный сенсор;
- в симуляции задавать `P_D`, `P_FA`, localization noise;
- в будущем заменить вероятности на реальные output confidence детектора.

## Mapping pipeline

В SeaClear мусор, обнаруженный UAV/ROV, регистрируется в 2D/3D карте:

- UAV detections can be registered in a 2D occupancy grid;
- ROV camera/sonar detections are projected into map;
- mapping uses transformations between sensor and world frames.

Это очень важно для нас:

```text
image detection -> camera/radar projection -> world coordinates -> map update
```

Даже если мы пока не делаем real camera projection, в статье стоит показать эту цепочку.

## Planning и collection

SeaClear применяет:

- lawnmower trajectory для обследования;
- safe path planning к litter location;
- local spiral search для reacquiring litter;
- visual servoing при захвате.

Для нашей работы:

- lawnmower как baseline;
- spiral/local search можно использовать в будущей версии, если координаты цели неточны;
- если вероятность высокой ячейки есть, но точное положение не подтверждено, робот может выполнять локальный search pattern.

## Simulation и field validation

SeaClear использует:

- Gazebo/UUVsim-based simulation;
- realistic sensors, kinematics, environments;
- field tests in Hamburg and Dubrovnik.

Сильный урок для нас:

- симуляция должна быть честно описана как этап до полевых испытаний;
- нужно явно перечислять ограничения симуляции;
- после Python-2D следующим шагом логично указать ROS2/Gazebo.

## Future work у SeaClear

Полезные направления:

- uncertainty-aware strategies to weight sensor measurements;
- Bayesian fusion from cameras and sonars;
- better self-localization and mapping;
- improving visual/camera-based environmental representations.

Это почти напрямую поддерживает нашу тему. Мы можем писать, что наша работа движется именно в сторону uncertainty-aware probabilistic mapping.

## Что перенести в симулятор

Минимально:

- pipeline detection -> projection -> map update;
- lawnmower baseline;
- local reacquisition/search near probable target;
- detection confidence as measurement probability.

Позже:

- ROS2/Gazebo;
- camera model;
- real detection outputs;
- uncertainty-aware fusion.

---

# Сводка: что именно реализовать в новой симуляции

## 1. Среда

2D-акватория:

- прямоугольная или polygonal boundary;
- сетка `Nx × Ny`;
- мусор задаётся точками или распределением;
- мусор может быть кластерным;
- в базовой версии мусор статичен;
- в расширенной версии мусор дрейфует.

## 2. Истинная карта

```text
m_i ∈ {0,1}
```

или плотность мусора:

```text
ρ_i ≥ 0
```

Для первой статьи проще:

- бинарная occupancy grid;
- в каждой ячейке есть/нет мусор.

## 3. Вероятностная карта

```text
b_i = P(m_i = 1)
```

Возможные реализации:

1. beta-Bernoulli:

```text
b_i = α_i / (α_i + β_i)
```

2. log-odds occupancy grid:

```text
L_i = log(b_i / (1 - b_i))
```

Для статьи beta-Bernoulli проще объяснять, log-odds ближе к robotics literature.

## 4. Энтропия карты

```text
H_i = -b_i log(b_i) - (1-b_i) log(1-b_i)
```

Использовать для active exploration.

## 5. Сенсорная модель

Базовая:

```text
P(z=1 | m=1, d) = sigmoid((R0 - d)/κ)
P(z=1 | m=0, d) = p_false
```

Улучшенная:

```text
P(z=1 | m=1, d, φ)
P(z=1 | m=0, d, φ)
```

где:

- `d` — расстояние;
- `φ` — bearing angle;
- FOV задаёт видимые ячейки;
- разные сенсоры имеют разные `R`, `FOV`, `noise`, `false_positive`.

## 6. Bayesian update

Для каждой видимой ячейки обновлять вероятность по измерению.

Через beta-Bernoulli:

```text
α_i ← α_i + z_i
β_i ← β_i + 1 - z_i
```

Через вероятностную модель:

```text
P(m_i=1 | z_i) ∝ P(z_i | m_i=1) P(m_i=1)
```

Для научной строгости лучше постепенно перейти ко второму варианту, потому что он учитывает false positives и false negatives.

## 7. Candidate waypoints

Сгенерировать сетку возможных следующей точек:

```text
W = {w_1, ..., w_K}
```

Для каждого `w` вычислить:

- какие ячейки попадут в FOV;
- expected information/exploitation score;
- расстояние от текущей позиции.

## 8. Active planner

Базовая objective function из David et al.:

```text
score(w) =
Σ_{i∈FOV(w)} [ H_i + α · I(b_low < b_i < b_high) ]
```

Адаптация для USV:

```text
score(w) =
Σ_{i∈FOV(w)} [ H_i + α · I(b_low < b_i < b_high) + μ · b_i ]
- λ · dist(x_robot, w)
```

Где:

- `H_i` — explore uncertainty;
- `I(...)` — refine likely object candidates;
- `b_i` — prefer high-probability trash cells;
- `dist` — штраф за путь;
- `α`, `μ`, `λ` — веса.

## 9. Collection model

Если робот проходит ближе `r_collect` к мусору:

```text
collected = True
```

Дополнительно:

- bin capacity;
- return-to-base;
- unload events.

## 10. Baseline-ы

Обязательно:

1. `lawnmower` / serpentine coverage.
2. `greedy` по максимальной вероятности `b_i`.
3. `active entropy + exploitation`.

Желательно:

4. `oracle TSP` по истинным координатам мусора — верхняя граница.
5. `detected-target TSP` по подтверждённым целям — аналог Li et al.

## 11. Метрики

Для статьи:

- percent collected by time;
- percent collected by path length;
- time to 50%, 80%, 95% collection;
- path length to 50%, 80%, 95%;
- total path length;
- number of turns или smoothness;
- number of false target visits;
- map F1 / IoU;
- Brier score по вероятностной карте;
- entropy reduction;
- classifier/detector precision, recall, F1, если моделируем детектор.

## 12. Серии экспериментов

Нужно не менее:

- 20-50 random seeds;
- 3-4 стратегии;
- 3 уровня sensor noise;
- 2-3 плотности мусора;
- 2 типа распределения:
  - uniform;
  - clustered.

Итоговые таблицы:

```text
mean ± std
```

Для path length, collection ratio, time-to-threshold, map quality.

---

# Как использовать эти статьи в новой статье

## Во введении

Цитировать:

- SeaClear — автоматизация обнаружения/сбора marine debris;
- Deng et al. — surface cleaning как collaborative UAV/USV task;
- Li et al. — floating-waste-cleaning USV path planning;
- David et al. — active probabilistic mapping.

## В обзоре литературы

Разделить:

1. Detection of floating/marine debris.
2. Path planning for surface cleaning robots.
3. Probabilistic/active mapping.
4. ASV/USV navigation architecture.

## В методологии

Главная опора:

- David et al. для occupancy grid, entropy, next-best-view.
- Li et al. для TSP/local cleaning baseline.
- Deng et al. для coverage/lawnmower и cleaning-time metrics.
- SeaClear для system pipeline detection -> mapping -> planning -> collection.

## В обсуждении новизны

Формулировка:

> В отличие от работ, в которых маршрут сбора строится по уже известному набору координат мусора, предлагаемая модель рассматривает обнаружения как зашумленные наблюдения и формирует апостериорную карту вероятности загрязнения. Планирование маршрута выполняется на основе этой карты, что позволяет совмещать исследование неизвестных областей и уточнение вероятных скоплений мусора.

## В ограничениях

Честно указать:

- пока 2D simulation;
- нет реального CV;
- нет реального SLAM/NMHE;
- мусор статичен;
- простая кинематика USV;
- нет волн, течений и ветра;
- не учитывается взаимодействие корпуса с мусором.

## В будущей работе

- camera/radar fusion;
- ROS2/Gazebo;
- реалистичная модель течений и ветра;
- дрейф мусора;
- multi-USV;
- интеграция с SLAM/NMHE;
- натурные эксперименты.

