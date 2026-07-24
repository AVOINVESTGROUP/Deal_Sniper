# Протокол проверки плана от 24.07.2026

Статус: замечания включены в draft-документацию; план не утверждён, PR #1 не сливать.

## Подтверждённый контекст

- `main` остаётся legacy и не воспроизводит временно развёрнутый Google Cloud контур.
- PR #1 является крупным монолитным изменением кода, Terraform и документации.
- Зелёные Ruff, mypy, pytest и Terraform checks не доказывают целостность Firestore, экономическую корректность, изоляцию пользователей и качество плана.
- Кодовые дефекты предыдущего аудита не исправлялись документальными коммитами.

## Блокирующие требования второй проверки

1. Немедленный, отдельно подтверждаемый владельцем containment `0.11-STOP`.
2. Версионированная миграция production-данных `0.11M` с backup, dry run и reconciliation.
3. Полный `decision_id` и пересчёт affected targets при изменении verified market.
4. `delivery_id` на основе decision ID и полноценный reconciliation состояния `unknown`.
5. Owner-scoped `/deals`, push и watchlist уже в `0.11A`.
6. Единственное текущее решение; старые решения superseded и не выдаются.
7. Verification TTL, extractor version, cache, rate limits и circuit breaker.
8. Одна каноническая финансовая формула без двойного risk reserve.
9. Серверный порядок current pointer, а не только application `observed_at`.
10. Версионированные identity merge/split и audit trail.
11. Устранение противоречий README, AI_CONTEXT, STEPS, SPEC и CLOUD_ARCHITECTURE.
12. Docs CI, tracking issues и минимум одно approving review не от автора.
13. Защита Free teaser от прямых идентификаторов с признанием остаточной discoverability.
14. Generic outbox в `0.11A`, `PublicationEvent` в `0.12`, WhatsApp только как adapter в `0.16`.
15. Повтор официального пилота после `0.11D`; прежние результаты считаются диагностическими.

## Внесённые документальные изменения

- добавлены `0.11-STOP` и `0.11M`;
- расширены критерии `0.11A–0.11D`;
- синхронизированы decision, delivery, verification, lifecycle и identity contracts;
- синхронизирована финансовая формула в SPEC и плане;
- документация разделяет current verified state и historical/superseded утверждения;
- README ограничивает использование временно развёрнутого candidate-контура;
- текущий порядок работ в SPEC ссылается на канонический implementation plan.

Все перечисленные пункты являются изменениями проекта документации и критериев
приёмки. Docs CI, tracking issues, independent review, миграция и стабилизационный
код ещё не реализованы и не должны отмечаться как фактически завершённые.

## Открытые решения владельца

- разрешение и окно выполнения `0.11-STOP`;
- ответственный оператор;
- GitHub username независимого reviewer;
- окно миграции и retention старых данных;
- SLA для `unknown` delivery;
- финансовые коэффициенты после утверждения формулы.

До закрытия этих пунктов статус остаётся Draft.
