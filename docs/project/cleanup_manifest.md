# Cleanup manifest

> **Историческая заметка (2026-08-13):** документ описывает состояние проекта на legacy `cleanup_sim`, до пивота на `cleanup_sim_v2`. Актуальное состояние — `docs/project/current_state.md`.

Дата: 2026-07-31

## Что сделано

Рабочие каталоги очищены от устаревших raw-результатов, smoke-запусков, кэшей и legacy-архива.

Из-за политики выполнения команд рекурсивное физическое удаление через `Remove-Item -Recurse` было заблокировано. Поэтому устаревшие данные не удалены с диска, а вынесены из рабочего дерева в карантин:

`_delete_later/`

Размер карантина после перемещения:

```text
685.48 MB, 4980 files
```

## Вынесено в карантин

- `.pytest_cache`;
- `cleanup_sim/__pycache__`;
- `tests/__pycache__`;
- `archive`;
- `out/legacy_runs`;
- `out/cleanup_sim/experiments`;
- `out/cleanup_sim/experiments_smoke`;
- `out/cleanup_sim/pilot_ablation_v1`;
- `out/cleanup_sim/pilot_hybrid_v1`;
- `out/cleanup_sim/pilot_hybrid_v2_suppression`;
- `out/cleanup_sim/confirmatory_hybrid_v2_pilot`;
- `out/cleanup_sim/confirmatory_hybrid_v2_pilot_fixed_auc`;
- все старые `out/cleanup_sim/smoke*` каталоги.

## Почему это больше не рабочие данные

Эти результаты были получены до одной или нескольких важных правок:

- исправление AUC по общему бюджету пути;
- повторяющийся `lawnmower`;
- появление `confirmatory_hybrid_v2_pilot_fixed_auc_lawnmower`;
- актуализация научной интерпретации после внешнего аудита.

Их нельзя использовать как таблицы для статьи.

## Что осталось актуальным

В `out/cleanup_sim/` оставлены:

- `confirmatory_hybrid_v2_pilot_fixed_auc_lawnmower`;
- `sensitivity_ofat_v1`.

Важное уточнение:

`sensitivity_ofat_v1` оставлен как малый диагностический артефакт, но AUC-числа в нем считаются историческими после исправления методики. Для статьи использовать только после повторного запуска sensitivity на актуальном коде.

## Как физически удалить карантин

Команда для ручного удаления из корня проекта:

```powershell
Remove-Item -LiteralPath .\_delete_later -Recurse -Force
```

Перед удалением убедиться, что внутри нет файлов, которые пользователь хочет сохранить вне текущего проекта статьи.
