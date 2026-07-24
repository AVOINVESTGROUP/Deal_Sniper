# Протокол третьей проверки плана от 24.07.2026

Статус: замечания включены в draft-документацию; план не утверждён, `0.11-STOP`
не выполнять, PR #1 не сливать.

## Блокирующие замечания проверки

1. Утверждение архитектурного плана было смешано с execution gates поздних релизов.
2. Приёмка `0.11A` зависела от полного `decision_id`, определяемого только в `0.11B`.
3. Replacement PR, issues, reviewer и защита `main` создавались слишком поздно.
4. Firestore export выполнялся до согласованной остановки writers и direct publisher.
5. Миграция не имела export watermark, restore rehearsal, raw replay и catch-up.
6. Составные ID были описаны неоднозначной конкатенацией строк.
7. Переключение current/superseded decision не было атомарным.
8. Единицы liquidity discount, Decimal precision и rounding не были определены.
9. Пилот был расположен до стабилизации, хотя выполнялся после неё.
10. SPEC не повторял требования защиты изображения Free-тизера.

## Внесённые изменения документации

- архитектурное approval отделено от execution approvals для `0.11-STOP/R/A/B/M/D`;
- добавлен предварительный repository gate `0.11R`;
- `0.11A` использует непрозрачный `decision_id`, а его полный состав принимается в `0.11B`;
- STOP-последовательность сначала блокирует side effects, publisher, schedulers, queues и in-flight operations, затем фиксирует единый watermark и export;
- `0.11M` включает test restore в изолированную среду, migration rehearsal, raw replay и catch-up reconciliation;
- verification, market, decision, delivery, operation и task IDs используют версионированный canonical JSON и SHA-256;
- current decision переключается Firestore transaction с precondition и отдельным pointer;
- liquidity discount определён как rate `0..1`; зафиксированы Decimal, rounding и отрицательная максимальная цена;
- официальный пилот перенесён после `0.11D` как релиз `0.11P`;
- SPEC требует защищённое Free-изображение и признаёт остаточную discoverability.

## Открытые execution decisions

Они не блокируют утверждение архитектурного документа целиком, но каждый блокирует
только свой релиз:

- `0.11-STOP`: окно, оператор и kill switch;
- `0.11R`: PR strategy и GitHub username независимого reviewer;
- `0.11A`: SLA `unknown`;
- `0.11B`: финансовые коэффициенты;
- `0.11M`: окно, retention, export location и irreversible checkpoint;
- `0.11D`: cutover и rollback decision.

Код, production, IAM, Scheduler, Cloud Tasks и данные этой редакцией не изменялись.
