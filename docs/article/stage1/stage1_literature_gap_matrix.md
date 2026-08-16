# Этап 1. Сравнительная матрица литературы и научный зазор

Дата фиксации: 2026-07-11

Статус на 2026-08-16: матрица полезна как литературная база, но формулировки
научного зазора нужно сверять с актуальной постановкой
`stage1_reframing_after_prefinal_2026-08-16.md`.

Цель документа: зафиксировать, что уже происходит в мировой и российской научной среде, и показать, где находится зазор для статьи о гибридном вероятностном планировании поиска и сбора плавающего мусора.

## Ближайшие работы

| Источник | Задача | Платформа | Карта неопределенности | Сенсоры | Планирование | Сбор | Эксперимент | Отличие нашей работы |
|---|---|---|---|---|---|---|---|---|
| Li et al., 2025, floating-waste-cleaning USV, IACO | Патрулирование и локальный сбор плавающего мусора | USV | Не является центральным объектом | Camera + radar fusion | TSP/IACO по патрульным и обнаруженным точкам | Да | TSPLIB и прикладные сценарии | У них основной акцент на маршрутизации по точкам; у нас цели возникают из вероятностной карты и шумных наблюдений |
| David et al., Active Mapping of Underwater Litter | Активное построение карты мусора | Подводный робот | Bayesian occupancy map | Camera + sonar | Next-best-view по энтропии/utility | Скорее обнаружение/картирование, не физический сбор | Симуляция, сравнение с lawnmower | У них underwater active mapping; у нас surface debris и задача маршрута сбора |
| Ilioudi et al., SeaClear system, 2026 | Автономное обнаружение и сбор морского мусора со дна | Multi-robot: USV, UAV, ROV | Mapping pipeline | Camera, sonar, navigation sensors | Survey, safe path, local search | Да | Симуляция и полевые испытания | Системная multi-robot работа; у нас узкий алгоритмический слой для single-USV surface cleanup |
| Deng et al., UAV+USV collaborative cleaning | Совместное покрытие и очистка поверхности | UAV + несколько USV | Не основной акцент | UAV/USV perception | Coverage, task assignment, clearance planning | Да | Симуляция multi-agent | У них координация нескольких аппаратов; у нас planning under uncertainty для одного USV |
| Zhang et al., 2024, double USV with floating rope | Траектория двух USV для сбора крупного мусора | Два USV с тросом | Нет | Не центральный вклад | Trajectory planning, APF/constraints | Да | Сценарии с препятствиями | У них механика кооперативного захвата; у нас probabilistic search-and-collection |

## Расширенная матрица источников

| N | Источник | Блок | Что дает статье | Ограничение для нашей задачи | Как использовать |
|---:|---|---|---|---|---|
| 1 | Li Y. et al. An Unmanned Vessel Path Planning Method for Floating-Waste Cleaning Based on an Improved Ant Colony Algorithm. JMSE, 2025. DOI: 10.3390/jmse13081579 | Floating waste path planning | Ближайший конкурент: USV, floating waste, camera/radar, TSP/IACO | Не фокусируется на апостериорной карте неопределенности | Главный target-routing baseline и источник для обсуждения Li et al. |
| 2 | David O., Busoniu L. et al. Active Mapping of Underwater Litter Using Camera and Forward-Looking Sonar | Active mapping | Occupancy grid, entropy, next-best-view, sensor fusion | Подводная среда; цель больше про карту/обнаружение, чем сбор | Методологическая основа active exploration |
| 3 | Ilioudi A. et al. The SeaClear system: An intelligent multi-robot solution for autonomous cleanup of marine debris on the seabed. Engineering Applications of AI, 2026. DOI: 10.1016/j.engappai.2026.114094 | System architecture | Полная цепочка detection -> mapping -> planning -> collection | Multi-robot и seabed debris, не single-USV surface debris | Архитектурный ориентир и мотивация |
| 4 | Deng T. et al. Automatic collaborative water surface coverage and cleaning strategy of UAV and USVs. Digital Communications and Networks, 2025. DOI: 10.1016/j.dcan.2022.12.014 | Surface coverage/cleaning | Разделение осмотра и очистки, coverage baseline, task assignment | UAV+multi-USV; неопределенность карты не главный объект | Обоснование coverage/lawnmower и water-surface cleaning |
| 5 | Zhang M. et al. Trajectory Planning for Cooperative Double USVs Connected with a Floating Rope for Floating Garbage Cleaning. JMSE, 2024. DOI: 10.3390/jmse12050739 | Cooperative cleanup | Физическая задача сбора мусора USV, ограничения траектории | Нет вероятностного картирования | Контекст работ по surface garbage cleaning |
| 6 | Cheng Y. et al. FloW: A Dataset and Benchmark for Floating Waste Detection in Inland Waters. ICCV, 2021 | Detection dataset | Реальные проблемы visual/radar detection плавающего мусора | Не решает planning/collection | Обоснование вероятностной сенсорной модели |
| 7 | Li Y. et al. A Floating-Waste-Detection Method for USV Based on Feature Fusion and Enhancement. JMSE, 2023. DOI: 10.3390/jmse11122234 | Detection | YOLO-Float, dataset, feature fusion | Только detection, нет маршрутизации | Показать, что CV-модуль является внешним сенсором |
| 8 | Water surface garbage detection based on lightweight YOLOv5, 2024 | Detection | Легковесная детекция для размещения на борту | Нет вероятностного planning | Поддержка выбора camera как сенсора |
| 9 | Tharani M. et al. Attention Neural Network for Trash Detection on Water Channels, 2020 | Detection | Сложности визуальной детекции в каналах | Не решает сбор и карту | Дополнительный источник по perception |
| 10 | IWHR_AI_Lable_Floater_V1 dataset, Scientific Data, 2025 | Detection dataset | Свежий датасет floating debris | Не решает planning | Для future work с реальными данными |
| 11 | Elfes A. Using Occupancy Grids for Mobile Robot Perception and Navigation. Computer, 1989. DOI: 10.1109/2.30720 | Occupancy grid | Классическая вероятностная сетка | Общая методология, не про мусор | Математический фундамент карты |
| 12 | Thrun S., Burgard W., Fox D. Probabilistic Robotics. MIT Press, 2005 | Probabilistic robotics | Bayesian filtering, sensor models, occupancy maps | Учебная монография, не прикладной аналог | Терминология и формулы |
| 13 | Moravec H., Elfes A. High Resolution Maps from Wide Angle Sonar, 1985 | Occupancy grid history | Истоки grid mapping | Исторический источник | Можно цитировать при необходимости |
| 14 | Meyer-Delius D. et al. Occupancy Grid Models for Robot Mapping in Changing Environments, 2012 | Dynamic maps | Карты изменяющейся среды | Для базовой статьи мусор статичен | Future work: дрейф мусора |
| 15 | Simulator/RL results for underwater mapping, 2022 | Informative mapping | Симуляционная среда для mapping/IPP | Подводная область и RL | Обоснование симуляционного этапа |
| 16 | Taylor A. T., Berrueta T. A., Murphey T. D. Active Learning in Robotics: A Review of Control Principles. Mechatronics, 2021. DOI: 10.1016/j.mechatronics.2021.102576 | Active learning | Обзор information measures and action generation | Широкий обзор, не про мусор | Показать, что entropy/IPP сами по себе известны |
| 17 | Wang W. et al. Roboat II: A Novel Autonomous Surface Vessel for Urban Environments. IROS, 2020. DOI: 10.1109/IROS45743.2020.9340712 | ASV navigation | ASV architecture, SLAM, NMPC/NMHE | Не про debris mapping/collection | Навигационный контекст, не основной вклад |
| 18 | Kaess M. et al. iSAM2: Incremental Smoothing and Mapping Using the Bayes Tree, 2012 | SLAM | Factor graph SLAM foundation | Не требуется для нашей симуляции | Только если остается раздел о навигации |
| 19 | Wang W. et al. Roboat III: An Autonomous Surface Vessel for Urban Transportation, 2023 | ASV platform | Развитие Roboat-платформы | Транспортная задача, не мусор | Дополнительный ASV-контекст |
| 20 | Теплухин Р. Г. и др. Современные методы автономной навигации беспилотных надводных аппаратов. Управление большими системами, 2025. DOI: 10.25728/ubs.2025.118.7 | Российский БНА-контекст | Свежий российский обзор автономной навигации БНА | Навигация, не вероятностный сбор мусора | Закрывает российскую терминологию и ВАК-контекст |
| 21 | Построение эпюр расходов воды на малых водотоках посредством надводного беспилотного аппарата | Российские применения БНА | Пример БНА для мониторинга водных объектов | Не про мусор и planning under uncertainty | Локальный пример экологического мониторинга |
| 22 | Росгидромет. Обзор состояния и загрязнения окружающей среды в РФ за 2023 год | Актуальность | Экологический фон и загрязнение водных объектов | Не робототехника | Введение и мотивация |

## Сформулированный научный зазор

В существующей литературе можно выделить три хорошо развитые линии:

1. **Маршрутизация по известным или обнаруженным целям.** Работы по floating-waste-cleaning USV, TSP, ACO и cooperative USV хорошо решают задачу построения маршрута, когда набор целей уже задан или считается достаточно надежным.

2. **Активное картирование и informative path planning.** Эти работы уменьшают неопределенность карты, выбирая следующие точки наблюдения, но часто не связывают критерий планирования с физическим сбором объектов и очередью подтвержденных целей.

3. **Системные multi-robot решения.** SeaClear и UAV+USV системы демонстрируют полную цепочку обнаружения, картирования и сбора, но их вклад распределен между платформами, сенсорами, координацией и полевыми испытаниями.

Зазор для нашей статьи:

> недостаточно исследована задача планирования одиночного надводного робота, который должен одновременно уточнять вероятностную карту плавающего мусора и принимать решения о сборе уже подтвержденных объектов при шумных и неполных наблюдениях.

## Рабочая ниша статьи

Наша работа должна занять позицию между active mapping и target routing:

```text
шумные наблюдения -> вероятностная карта -> active exploration
                                      -> confirmed target queue -> routing/collection
                                      -> adaptive switching
```

Такой сюжет позволяет не конкурировать напрямую с полноценными системами SeaClear и не заявлять новый SLAM. Вместо этого статья исследует алгоритмический уровень экологической миссии.

## Источники, обязательные для первой версии статьи

Минимальный обязательный набор:

1. Li et al., 2025, floating-waste-cleaning USV, IACO.
2. David et al., Active Mapping of Underwater Litter.
3. Ilioudi et al., SeaClear system.
4. Deng et al., UAV+USV collaborative cleaning.
5. Zhang et al., cooperative double USV garbage cleaning.
6. Cheng et al., FloW dataset.
7. Li et al., YOLO-Float / FloatingWaste-I.
8. Elfes, occupancy grids.
9. Thrun, Burgard, Fox, Probabilistic Robotics.
10. Taylor et al., Active Learning in Robotics.
11. Wang et al., Roboat II.
12. Теплухин и др., обзор автономной навигации БНА.
13. Росгидромет, обзор загрязнения окружающей среды.

Для ВАК-версии список нужно расширить до 25-40 источников, но для закрытия этапа научной постановки текущей матрицы достаточно.

## Риск близкого совпадения

Риск: в литературе могут существовать работы по hybrid active search / target routing для других доменов, например наземных роботов, БПЛА, AUV или search-and-rescue.

Как снизить риск:

- не заявлять универсально новый класс методов;
- формулировать вклад как адаптацию и исследование гибридной стратегии для surface floating debris cleanup;
- в дальнейшем добавить раздел related work по informative path planning, orienteering, Bayesian search и POMDP;
- экспериментально показать условия применимости, а не только среднее превосходство.

## Вывод

Научная среда подтверждает релевантность темы: есть работы по USV-сбору мусора, active mapping, floating waste detection и комплексным robotic cleanup systems. Однако между probabilistic active mapping и practical target routing остается защищаемый зазор. Именно его должна занять новая статья.
