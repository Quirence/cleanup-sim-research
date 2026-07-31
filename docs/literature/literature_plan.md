# План изучения литературы для переработки статьи

Дата составления: 2026-07-11

Тема рабочей версии статьи:

> Вероятностное картирование плавающего мусора и адаптивное планирование маршрута автономного надводного робота при шумных и неполных наблюдениях.

Главная идея библиографии: не собирать "всё про дронов", а закрыть четыре научных блока:

1. вероятностное картирование и карты занятости;
2. планирование маршрута для сбора мусора/покрытия акватории;
3. детекция плавающего мусора как источник наблюдений;
4. навигационная архитектура USV/ASV как контекст, но не главный вклад.

## A. Обязательное ядро для статьи

Эти источники надо изучить первыми. Они прямо формируют позиционирование будущей статьи.

### 1. Li Y., Tang C., Yan S., Wang R., Gao D. An Unmanned Vessel Path Planning Method for Floating-Waste Cleaning Based on an Improved Ant Colony Algorithm

- Год: 2025
- Журнал: Journal of Marine Science and Engineering
- DOI: https://doi.org/10.3390/jmse13081579
- Ссылка: https://www.mdpi.com/2077-1312/13/8/1579
- Зачем читать: это ближайший конкурент по теме "USV + floating waste + path planning".
- Что взять:
  - постановку задачи floating-waste-cleaning USV;
  - деление на global patrol path и local cleaning path;
  - TSP-формализацию;
  - метрики эксперимента;
  - то, чем наша работа отличается: у них координаты/цели во многом уже заданы модулем восприятия, у нас акцент на вероятностной карте неопределённых наблюдений.
- Приоритет: максимальный.

### 2. David O., Busoniu L. et al. Active Mapping of Underwater Litter Using Camera and Forward-Looking Sonar

- Год: 2026, свежая работа/preprint или конференционная версия
- Ссылка: https://busoniu.net/files/papers/aqtr26-david.pdf
- Зачем читать: очень близко методологически: Bayesian occupancy map, active mapping, next-best-view, сравнение с lawnmower.
- Что взять:
  - формулировку active mapping;
  - occupancy grid / Bayesian update;
  - exploration vs exploitation;
  - метрики качества карты;
  - baseline lawnmower.
- Чем отличается наша работа:
  - у них underwater litter и UUV/подводные сенсоры;
  - у нас surface floating debris, USV и маршрут сбора.
- Приоритет: максимальный.

### 3. SeaClear system: autonomous detection and collection of marine debris

- Год: 2026
- Журнал/площадка: Applied Soft Computing / ScienceDirect record
- Ссылка: https://www.sciencedirect.com/science/article/pii/S0952197626003751
- PDF/Fraunhofer: https://publica-rest.fraunhofer.de/server/api/core/bitstreams/9df79fcc-7338-4f08-93fe-e4cbf5a931ff/content
- Проект: https://seaclear-project.eu/about-main/about-seaclear
- Зачем читать: это крупная система уровня "роботы ищут, картируют и собирают мусор".
- Что взять:
  - системную архитектуру;
  - связку mapping -> classification -> collection;
  - роль USV как носителя/координатора;
  - аргументацию актуальности автоматизации сбора мусора.
- Чем отличается наша работа:
  - SeaClear в основном про комплексную multi-robot систему и seafloor/underwater litter;
  - у нас более узкий алгоритмический вклад в вероятностное картирование плавающего мусора.
- Приоритет: максимальный.

### 4. Deng T., Xu X., Ding Z., Xiao X., Zhu M., Peng K. Automatic collaborative water surface coverage and cleaning strategy of UAV and USVs

- Год: 2025, опубликовано в Digital Communications and Networks; DOI у страницы ScienceDirect: https://doi.org/10.1016/j.dcan.2022.12.014
- Ссылка: https://www.sciencedirect.com/science/article/pii/S2352864822002826
- Зачем читать: вода, мусор, покрытие поверхности, UAV+USV, task assignment.
- Что взять:
  - coverage path planning;
  - collaborative cleaning;
  - task scheduling для USV;
  - сравнение с нашим вариантом, где UAV пока отсутствует, но есть вероятностная карта.
- Приоритет: высокий.

### 5. Zhang M., Zheng X., Wang J., Pan Z., Che W., Wang H. Trajectory Planning for Cooperative Double Unmanned Surface Vehicles Connected with a Floating Rope for Floating Garbage Cleaning

- Год: 2024
- Журнал: Journal of Marine Science and Engineering
- DOI: https://doi.org/10.3390/jmse12050739
- Ссылка: https://www.mdpi.com/2077-1312/12/5/739
- Зачем читать: планирование траекторий именно для surface garbage cleaning.
- Что взять:
  - TSP-постановку порядка обхода мусора;
  - ограничения кинематики USV;
  - APF/leader-follower подход;
  - описание capture phase.
- Приоритет: высокий.

## B. Детекция плавающего мусора как сенсор высокого уровня

Эти источники нужны, чтобы корректно описать модуль computer vision, но не делать его главным вкладом.

### 6. Cheng Y. et al. FloW: A Dataset and Benchmark for Floating Waste Detection in Inland Waters

- Год: 2021
- Конференция: ICCV 2021
- PDF: https://openaccess.thecvf.com/content/ICCV2021/papers/Cheng_FloW_A_Dataset_and_Benchmark_for_Floating_Waste_Detection_in_ICCV_2021_paper.pdf
- GitHub: https://github.com/ORCA-Uboat/FloW-Dataset
- Зачем читать:
  - первый важный dataset/benchmark для floating waste detection в inland waters;
  - полезен для обоснования, почему детектор можно рассматривать как внешний сенсор.
- Что взять:
  - описание FloW-Img и FloW-RI;
  - проблемы отражений, масштаба, малых объектов;
  - метрики detection benchmark.
- Приоритет: высокий.

### 7. Li Y., Wang R., Gao D., Liu Z. A Floating-Waste-Detection Method for Unmanned Surface Vehicle Based on Feature Fusion and Enhancement

- Год: 2023
- Журнал: Journal of Marine Science and Engineering
- DOI: https://doi.org/10.3390/jmse11122234
- Ссылка: https://www.mdpi.com/2077-1312/11/12/2234
- Зачем читать:
  - USV-based floating-waste detection;
  - dataset FloatingWaste-I;
  - YOLO-Float.
- Что взять:
  - почему визуальная детекция на воде сложна;
  - отражения, солнечные блики, мелкие объекты;
  - AP/mAP как метрики качества сенсорного модуля.
- Приоритет: высокий.

### 8. Water surface garbage detection based on lightweight YOLOv5

- Год: 2024
- Ссылка: https://pmc.ncbi.nlm.nih.gov/articles/PMC10937728/
- Зачем читать:
  - пример lightweight-модели для размещения на unmanned ships;
  - аргумент, что детекция может работать на бортовом вычислителе.
- Приоритет: средний.

### 9. Tharani M. et al. Attention Neural Network for Trash Detection on Water Channels

- Год: 2020
- arXiv: https://arxiv.org/abs/2007.04639
- Зачем читать:
  - ранняя работа по trash detection на водных каналах;
  - полезна для обзора проблем видимого мусора: частичное погружение, деформация, малые размеры.
- Приоритет: средний.

### 10. IWHR_AI_Lable_Floater_V1: Annotated Dataset and Benchmark for Detecting Floating Debris in Inland Waters

- Год: 2025
- Nature Scientific Data: https://www.nature.com/articles/s41597-025-04594-9
- Dataset: https://figshare.com/articles/dataset/IWHR_AI_Lable_Floater_V1_An_annotated_Dataset_and_Benchmark_for_Detecting_Floating_Debris_in_Inland_Waters/27376851
- Зачем читать:
  - свежий набор данных по floating debris;
  - пригоден для обоснования дальнейшего перехода от симуляции к реальным данным.
- Приоритет: средний.

## C. Вероятностное картирование и робототехническая методология

Эти источники нужны для математического фундамента: beta-Bernoulli, occupancy grid, Bayesian update, noisy observations.

### 11. Elfes A. Using Occupancy Grids for Mobile Robot Perception and Navigation

- Год: 1989
- DOI/страница: https://dl.acm.org/doi/abs/10.1109/2.30720
- PDF: https://www.cs.cmu.edu/~motionplanning/papers/sbp_papers/integrated4/elfes_occup_grids.pdf
- Зачем читать:
  - классика occupancy grid mapping;
  - вероятностное представление пространства сеткой.
- Что взять:
  - идею разбиения среды на ячейки;
  - стохастическую оценку состояния ячейки;
  - связь восприятия и планирования.
- Приоритет: высокий.

### 12. Thrun S., Burgard W., Fox D. Probabilistic Robotics

- Год: 2005
- MIT Press: https://mitpress.mit.edu/9780262303804/probabilistic-robotics/
- Зачем читать:
  - основной источник по вероятностной робототехнике;
  - Bayesian filtering, occupancy grid mapping, localization.
- Что взять:
  - стандартную нотацию;
  - аккуратное описание неопределённости;
  - терминологию для статьи.
- Приоритет: высокий.

### 13. Moravec H., Elfes A. High Resolution Maps from Wide Angle Sonar

- Год: 1985
- Semantic Scholar: https://www.semanticscholar.org/paper/High-resolution-maps-from-wide-angle-sonar-Moravec-Elfes/d1ec836351c0e89f5834957953d9a040dab56985
- Зачем читать:
  - исток occupancy grid mapping.
- Приоритет: дополнительный, можно цитировать через Elfes/Thrun.

### 14. Meyer-Delius D., Beinhofer M., Burgard W. Occupancy Grid Models for Robot Mapping in Changing Environments

- Год: 2012
- PDF: https://ais.informatik.uni-freiburg.de/publications/papers/meyerdelius12aaai.pdf
- Зачем читать:
  - карты в изменяющейся среде;
  - полезно для будущего развития модели, где мусор дрейфует.
- Приоритет: средний.

### 15. A Simulator and First Reinforcement Learning Results for Underwater Mapping / informative path planning

- Ссылка: https://pmc.ncbi.nlm.nih.gov/articles/PMC9322081/
- Зачем читать:
  - simulation environment для underwater mapping;
  - long-horizon informative path planning.
- Приоритет: дополнительный.

## D. USV/ASV навигация, SLAM, NMPC как архитектурный контекст

Эти источники нужны не как основной вклад, а чтобы правильно описать навигационный слой и не исказить Roboat II.

### 16. Wang W. et al. Roboat II: A Novel Autonomous Surface Vessel for Urban Environments

- Год: 2020
- IROS / arXiv
- DOI: https://doi.org/10.1109/IROS45743.2020.9340712
- arXiv: https://arxiv.org/abs/2007.10220
- Зачем читать:
  - основной технический референс по ASV-архитектуре;
  - LiDAR+IMU+GPS factor graph SLAM;
  - NMPC/NMHE для управления и оценки состояния.
- Что взять:
  - архитектуру sensor fusion;
  - корректное использование LiDAR: инфраструктурные ориентиры, не водная поверхность;
  - iSAM2/factor graph как зрелую SLAM-базу.
- Приоритет: высокий.

### 17. Kaess M. et al. iSAM2: Incremental Smoothing and Mapping Using the Bayes Tree

- Год: 2012
- IJRR/SAGE: https://journals.sagepub.com/doi/10.1177/0278364911430419
- PDF: https://www.cs.cmu.edu/~kaess/pub/Kaess11icra.pdf
- Зачем читать:
  - основа factor graph SLAM, на которую опирается Roboat II.
- Приоритет: средний, если в статье останется блок про SLAM.

### 18. Wang W. et al. Roboat III: An Autonomous Surface Vessel for Urban Transportation

- Год: 2023
- PDF: https://senseable.mit.edu/papers/pdf/20230901_Wang_Roboat-3_JournalFieldRobotics.pdf
- Зачем читать:
  - развитие Roboat-платформы;
  - полезно для архитектурного обзора ASV.
- Приоритет: средний.

### 19. Social Trajectory Planning for Urban Autonomous Surface Vessels

- PDF: https://autonomousrobots.nl/assets/files/publications/20-park-TRO.pdf
- Зачем читать:
  - планирование движения ASV в городской среде;
  - полезно, если статья будет затрагивать городскую акваторию, препятствия, суда.
- Приоритет: дополнительный.

## E. Российский и ВАК-контекст

Эти источники нужны, чтобы статья не выглядела оторванной от российской научной среды.

### 20. Теплухин Р. Г., Фархадов М. П. О., Лычков И. И., Санько А. О. Современные методы автономной навигации беспилотных надводных аппаратов

- Год: 2025
- Журнал: Управление большими системами, выпуск 118, с. 132-207
- DOI: 10.25728/ubs.2025.118.7
- Math-Net: https://www.mathnet.ru/ubs1335
- CyberLeninka: https://cyberleninka.ru/article/n/sovremennye-metody-avtonomnoy-navigatsii-bespilotnyh-nadvodnyh-apparatov
- PDF: https://ubs.mtas.ru/upload/library/UBS11807.pdf
- Зачем читать:
  - свежий российский обзор по БНА;
  - удобно цитировать в разделе обзора навигации;
  - закрывает российскую терминологию: БНА/USV/ASV.
- Приоритет: высокий.

### 21. Построение эпюр расходов воды на малых водотоках посредством надводного беспилотного аппарата

- Ссылка: https://vestnik.astu.org/ru/nauka/article/88410/view
- Зачем читать:
  - пример российского применения надводного беспилотного аппарата в мониторинге водных объектов.
- Приоритет: средний.

### 22. Росгидромет. Обзор состояния и загрязнения окружающей среды в Российской Федерации за 2023 год

- Год: 2024
- PDF: https://downloads.igce.ru/publications/reviews/review2023.pdf
- Зачем читать:
  - статистика и актуальность экологического мониторинга в РФ;
  - источник для введения.
- Приоритет: высокий.

## F. Источники, которые можно оставить в резерве

### 23. U*: GA-based path planning algorithm for surface floating garbage cleaning robots

- Ссылка: https://journals.sagepub.com/doi/abs/10.3233/JIFS-232137
- Зачем читать:
  - ещё один пример path planning для surface garbage cleaning.
- Приоритет: резерв.

### 24. Cross-attention PPO-based task allocation for single USV debris cleaning

- Ссылка: https://link.springer.com/article/10.1007/s44295-026-00102-w
- Зачем читать:
  - свежая линия с reinforcement learning и debris flow prediction.
- Приоритет: резерв, если будем добавлять раздел "перспективные RL-подходы".

### 25. Research on Hull Design and Path Planning of Unmanned Garbage Collection Vessel

- Ссылка: https://icj-e.org/index.php/ojs/article/view/232
- Зачем читать:
  - прикладная статья про корпус и coverage path planning.
- Приоритет: резерв.

## Минимальный набор для первой переработки статьи

Если времени мало, сначала читать:

1. Li et al. 2025, Improved Ant Colony for floating-waste-cleaning USV.
2. David/Busoniu et al., Active Mapping of Underwater Litter.
3. SeaClear system.
4. FloW dataset, ICCV 2021.
5. YOLO-Float / FloatingWaste-I.
6. Elfes, occupancy grids.
7. Thrun, Burgard, Fox, Probabilistic Robotics.
8. Roboat II.
9. Теплухин и др., Современные методы автономной навигации БНА.
10. Росгидромет 2023.

## Как использовать источники в новой статье

### Во введении

- Росгидромет;
- SeaClear;
- floating-waste-cleaning USV papers;
- FloW / YOLO-Float для сложности детекции.

### В обзоре литературы

- ASV/USV navigation: Roboat II, российский обзор Теплухина и др.;
- detection: FloW, YOLO-Float, lightweight YOLOv5;
- mapping: Elfes, Probabilistic Robotics, Active Mapping of Underwater Litter;
- planning: Li et al. 2025, Zhang et al. 2024, Deng et al. 2025.

### В методологии

- occupancy grid и beta-Bernoulli обновление: Elfes + Thrun;
- routing baseline: lawnmower из active mapping / coverage literature;
- greedy / TSP / ACO: Li et al. 2025, Zhang et al. 2024.

### В обсуждении

- отличие от работ, где координаты мусора считаются известными;
- отличие от чистых детекторов;
- отличие от underwater litter mapping;
- ограничения симуляции и путь к ROS/Gazebo/натурным испытаниям.

## Предупреждение по индексированию

Перед финальной отправкой в журнал нужно отдельно проверить, какие источники действительно находятся в Scopus/Web of Science на момент подачи. Статус журналов и индексация могут меняться. Для ВАК-статьи это не запрещает цитировать важные источники, но лучше, чтобы значимая часть списка литературы была из Scopus/WoS/IEEE/Springer/Elsevier/MDPI-журналов с проверяемыми DOI.

