# Физические параметры и границы сенсорной модели

> **Историческая заметка (2026-08-13):** документ описывает состояние проекта на legacy `cleanup_sim`, до пивота на `cleanup_sim_v2`. Актуальная таблица параметров — `docs/project/parameter_evidence_matrix.md`. Не использовать как актуальный источник для статьи без сверки с `cleanup_sim_v2`.

Дата: 2026-07-31

Назначение: зафиксировать, как описывать параметры симулятора в статье, чтобы не завысить реалистичность модели малого USV и camera/radar-наблюдений.

## Reference Class

Текущая модель не должна описываться как точная цифровая копия BlueBoat, Heron или WasteShark. Корректная формулировка:

> Симуляция рассматривает малый исследовательский/экспериментальный USV с абстрактным модулем сбора и вероятностной camera/radar-моделью наблюдений. Параметры выбраны в диапазоне, близком к малым USV и роботам очистки поверхности воды, но физическая модель сбора упрощена.

## Платформы-Ориентиры

| Источник | Что использовать в статье | Ограничение для нашей модели |
|---|---|---|
| [Blue Robotics BlueBoat](https://bluerobotics.com/store/boat/blueboat/blueboat/) и [datasheet](https://bluerobotics.com/wp-content/uploads/2023/03/BLUEBOAT-DATASHEET-v1.1-JAN-2025.pdf) | малый USV около 1-2 м; скорость порядка нескольких м/с возможна для исследовательской платформы | `30 кг` мусора требует отдельного класса платформы |
| [Clearpath Heron brochure](https://www.generationrobots.com/media/clearpath_heron_USV_Brochure_2019.pdf) | пример исследовательского USV с умеренной полезной нагрузкой и скоростью | `bin_capacity_kg=30` выше типичного research payload |
| [RanMarine WasteShark Classic](https://www.ranmarine.io/wastesharkclassic/) | cleaning-specific USV с корзиной для мусора; обосновывает саму задачу автономной очистки | нельзя одновременно брать высокую скорость research-USV и большую корзину cleaning-USV без оговорки |

## Параметры Робота

| Параметр | Значение в коде | Как писать | Что проверять sensitivity |
|---|---:|---|---|
| `speed_mps` | `2.0` | верхний исследовательский режим движения, не обязательно режим эффективного сбора | `1.0`, `1.5`, `2.0` |
| `bin_capacity_kg` | `30.0` | допустимо как cleaning-oriented платформа, но не как легкий research-USV | `10`, `30`, `60 кг` |
| `collect_radius_m` | `5.0` | effective collection radius, а не ширина механического ковша | `2.5`, `5.0 м`; future work - aperture/dwell-time model |
| `sensor_period_s` | `10.0` | период mission-level обновления карты, не частота камеры/радара | sensitivity можно добавить позже |

## Сенсорная Модель

| Сенсор | Значение в коде | Корректная интерпретация | Чего не заявлять |
|---|---:|---|---|
| camera range/FOV | `28 м`, `70 deg` | абстрактный RGB/object detector с вероятностной локализацией | не говорить, что это depth range RealSense D435i |
| radar range/FOV | `45 м`, `130 deg` | абстрактный компактный radar-like источник наблюдений | не заявлять доказанную детекцию каждого малого floating debris |
| camera/radar fusion | sequential Bayesian update | условная независимость наблюдений в модели | не выдавать за валидированный sensor fusion pipeline |

Ориентиры по сенсорам:

- [Intel RealSense D435i official specs](https://www.intel.com/content/www/us/en/products/sku/190004/intel-realsense-depth-camera-d435i/specifications.html): depth range существенно меньше `28 м`; поэтому наша camera-модель должна называться RGB/object-detection abstraction.
- [TI IWR6843AOP](https://www.ti.com/product/IWR6843AOP) и [IWR6843AOPEVM](https://www.ti.com/tool/IWR6843AOPEVM): компактный mmWave radar-like источник возможен, но дальность и качество обнаружения малых плавающих объектов зависят от конфигурации, сцены и валидации.

## Формулировка Для Статьи

Защитимо:

> Сенсоры моделируются вероятностно: положительные и отрицательные наблюдения camera/radar обновляют occupancy-belief ячеек по правилу Байеса. Camera/radar в данной работе не являются реализацией конкретной CV- или radar-системы, а задают контролируемые уровни дальности, поля зрения, ложных срабатываний и ошибок локализации.

Не защитимо:

> Реализована реальная компьютерная детекция плавающего мусора камерой и радаром.

## Следствие Для Экспериментов

Для статьи основной результат должен сопровождаться физической sensitivity-серией:

```powershell
python -m cleanup_sim.run_sensitivity `
  --seeds 5 `
  --scenarios clustered_base clustered_noisy uniform_base `
  --components robot `
  --out-dir out/cleanup_sim/physical_sensitivity_prefinal `
  --max-path-m 3000 `
  --tmax-s 6000
```
