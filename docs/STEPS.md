# Журнал реализации

## 25 июля 2026 — полный production candidate

- Production остановлен: schedules и Cloud Tasks paused, delivery/webhook выключены.
- Создан защищённый STOP Firestore export и зафиксирован watermark.
- Реализованы canonical IDs, immutable snapshots/evidence/decisions и current pointers.
- Исправлена обработка out-of-order версий и блокировка доставки старого snapshot.
- Реализована source-bound detail verification; `Price on request` и неподтверждённая цена не допускаются.
- Freshness отделена от immutable evidence: `last_checked_at`, `valid_until`, `freshness_status`.
- Реализованы deterministic Comparable, Cost, Risk и Decision Engines с Decimal.
- Добавлены cross-source identity/dedup, market fingerprint и controlled recalculation.
- Реализован transactional outbox personal/Free/Pro/WhatsApp и ручной reconcile `unknown`.
- Реализованы Telegram update leases, RU/EN поиск, saved searches, favorites и outcomes.
- Добавлены Free teaser без финансовых утечек и полная Pro-карточка.
- Добавлены Firebase Auth, Admin Web, TMA и content pipeline.
- Добавлен официальный WhatsApp opt-in adapter, fail-closed без credentials.
- Реализованы migration tool v1.0/schema v2, ledger, checksums, checkpoints и replay requests.
- Добавлен direct migration replay с `DELIVERY_ENABLED=false` без включения очередей.
- Terraform расширен Cloud Run Jobs/Tasks/Scheduler, Firebase, IAM, secrets, monitoring и budget.
- CI использует Python 3.11, Ruff, mypy, pytest coverage, pip-audit, Terraform, Docker и Trivy.
- Локальный gate: Ruff — green; mypy — green; 42 теста — green; coverage 46,81%; Terraform validate — green.
- Документация приведена к фактической реализации; добавлен release/cutover/rollback runbook.
- Исправлен CI pin Trivy Action на существующий официальный release `v0.36.0`.
- Runtime image очищен от ненужных build-пакетов `setuptools` и `wheel`, найденных Trivy; прежний RC digest аннулирован.
- Trivy подтверждает отсутствие исправимых HIGH/CRITICAL; 23 findings Debian 13 без `FixedVersion` сохраняются в отчёте и не блокируют gate через `ignore-unfixed`.
- Staging replay обнаружил несовместимость legacy content hash; migration tool 1.1 rekey создаёт canonical v2 snapshots, переводит current pointer и отклоняет missing/non-current replay вместо ложного `completed`.

## Следующая обязательная операция

Сформировать immutable RC commit и image digests; восстановить STOP export в staging named database; выполнить migration rehearsal и full catch-up с delivery disabled. Только затем разрешены production migration, merge в `main`, exact-digest deploy и staged resume.

## Ограничения

- Существующий draft PR #1 не сливать и не использовать как production baseline.
- Terraform apply до import существующих ресурсов запрещён.
- WhatsApp включать только после внешних Meta credentials/template approval/opt-in.
- Любое изменение build context после staging rehearsal требует нового RC и повторного rehearsal.
