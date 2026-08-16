# Таблица параметров платформы и сенсоров для статьи

Дата: 2026-07-31

Статус на 2026-08-16: использовать только после сверки с
`cleanup_sim_v2/config.py` и `docs/project/parameter_evidence_matrix.md`.
Часть формулировок относится к pre-v2 модели и не должна переноситься в статью
без проверки.

Назначение: подготовить переносимый в методологию статьи блок, который обосновывает численные параметры симулятора и одновременно фиксирует границы их интерпретации.

## Источники-Ориентиры

| Источник | Что подтверждает | Как использовать |
|---|---|---|
| [Blue Robotics BlueBoat datasheet](https://bluerobotics.com/wp-content/uploads/2023/03/BLUEBOAT-DATASHEET-v1.1-JAN-2025.pdf) | малый research/survey USV: скорость до `3 м/с` без нагрузки, payload+batteries до `15 кг` | обосновывает порядок скорости `2 м/с`, но не емкость мусорного бункера `30 кг` |
| [Clearpath Heron portal](https://www.clearpathrobotics.com/assets/ClearpathPortalv2.html), [Heron user manual](https://oceanai.mit.edu/herons/docs/Heron_USV_UserManual.pdf) и [ROS Robots Heron](https://robots.ros.org/clearpath-heron-usv/) | research USV около `1.3 м`, payload порядка `10 кг`, скорость около `1.7 м/с`; есть payload bay, GPS/IMU и ROS-контекст | показывает, что исследовательские USV этого класса несут сенсоры, но не большой мусорный бункер |
| [RanMarine WasteShark+](https://www.ranmarine.io/wasteshark/) | cleaning-oriented USV с корзиной `160 л` и грузоподъемностью корзины `60 кг` | обосновывает, что емкость десятки килограммов реалистична для cleaning-класса, но не для легкого research-USV |
| [RanMarine WasteShark Classic](https://www.ranmarine.io/wastesharkclassic/) | cleaning USV со скоростью около `3 км/ч` и дальностью около `12 км` | показывает, что режим эффективной очистки может быть медленнее, чем research/survey режим |
| [RealSense D435i official specs](https://realsenseai.com/products/depth-camera-d435i/) и [Intel D435 specs](https://www.intel.com/content/www/us/en/products/sku/128255/intel-realsense-depth-camera-d435/specifications.html) | depth-camera class: FOV около `85-87 x 58 deg`, ideal/operating depth range около `0.3-3 м` | наша camera range `28 м` не должна называться RealSense depth range; это RGB/object-detector abstraction |
| [TI IWR6843AOPEVM](https://www.ti.com/tool/IWR6843AOPEVM) | компактный `60-64 GHz` mmWave radar-like модуль, `4 RX / 3 TX`, широкий FoV порядка `120 deg` | обосновывает radar-like FoV, но не валидирует обнаружение малого плавающего мусора на `45 м` |
| [u-blox ZED-F9P](https://www.u-blox.com/en/product/zed-f9p-module) | RTK GNSS-модуль с centimeter-level positioning как возможный навигационный компонент | использовать только как навигационный контекст; текущая статья не моделирует GNSS/SLAM/NMHE |

## Параметры Симулятора И Интерпретация

| Параметр | Значение в коде | Реалистичная интерпретация | Ограничение | Что делать в статье |
|---|---:|---|---|---|
| Акватория | `200 x 200 м` | небольшой портовый/лабораторный участок | не вся портовая зона | описывать как ограниченную тестовую акваторию |
| Сетка | `100 x 100`, ячейка `2 x 2 м` | mission-level карта, не пиксельная CV-карта | occupancy теряет count/density при нескольких объектах в ячейке | указать occupancy-map; count-map только diagnostic |
| Число объектов | `150` | плотное загрязнение на малой акватории | не моделирует приток/дрейф мусора | писать static debris field |
| Скорость | `2.0 м/с` | верхний research/survey режим; близко к BlueBoat, выше WasteShark Classic cleaning speed | сбор на такой скорости может быть оптимистичным | сопровождать sensitivity `1.0/1.5/2.0 м/с` |
| Емкость | `30 кг` | cleaning-oriented малый USV, между research payload и WasteShark+ basket capacity | нельзя приписывать BlueBoat/Heron без оговорки | писать как абстрактный cleaning module; sensitivity `10/30/60 кг` |
| Радиус сбора | `5 м` | effective collection radius в 2D-модели | не равен физической ширине корзины/ковша; завышает сбор | явно назвать effective radius; sensitivity `2.5/5 м` |
| Шаг динамики | `1 с` | mission-level дискретизация движения | нет маневренности, инерции и ограничений курса | не заявлять динамическую модель судна |
| Период сенсоров | `10 с` | период обновления карты планировщиком | не частота камеры/радара | писать mission-level update period |
| Camera range/FOV | `28 м`, `70 deg` | RGB/object-detector abstraction | не depth range RealSense D435i | не заявлять реальную CV-детекцию |
| Radar range/FOV | `45 м`, `130 deg` | radar-like probabilistic observation source | обнаружение мусора радаром не валидировано натурно | писать probabilistic radar-like sensor model |

## Формулировка Для Раздела Методологии

Готовый фрагмент:

> Параметры симулятора выбраны для малого экспериментального надводного робота в ограниченной спокойной акватории. Значения скорости и габаритного класса сопоставимы с research/survey USV, тогда как емкость бункера относится скорее к cleaning-oriented платформам. Поэтому модель не рассматривается как цифровой двойник конкретного аппарата. Сенсорные параметры camera/radar задают вероятностные уровни дальности, поля зрения, ложных срабатываний и ошибок локализации; они не являются реализацией конкретной RealSense- или radar-системы. Для контроля физической чувствительности предусмотрены серии по скорости, емкости бункера и эффективному радиусу сбора.

## Формулировка Для Ограничений

Готовый фрагмент:

> В текущей версии мусор считается статичным, а процесс сбора упрощен до мгновенного удаления объектов внутри эффективного радиуса. Вероятностная карта является occupancy-map и описывает вероятность наличия хотя бы одного объекта в ячейке, но не оценивает плотность или количество объектов. Для анализа этой потери информации сохраняется диагностическая count-map, однако она не используется планировщиками и не дает алгоритмам доступа к истинному распределению мусора.

## Итог По P2-06

Параметры можно защищать как baseline simulation для малого experimental/cleaning-oriented USV, если в статье будут явно указаны:

- это не цифровой двойник конкретного BlueBoat/Heron/WasteShark;
- `2 м/с`, `30 кг`, `5 м` являются исследуемыми параметрами, а не доказанными характеристиками будущего прототипа;
- camera/radar являются вероятностными абстракциями;
- физическая sensitivity является обязательным сопровождающим результатом.
