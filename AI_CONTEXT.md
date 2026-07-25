# AI Context: Dubai Deal Sniper

## Цель

Production-сервис быстрой монетизации сигналов по недооценённым автомобилям с фиксированной ценой в ОАЭ. Недвижимость и аукционы исключены. Основные каналы: персональный Telegram-бот, Free/Pro Telegram-каналы, TMA и Admin Web. WhatsApp — только официальный opt-in API.

## Обязательные правила

- Python 3.11, type hints, русская документация/коммиты/логи.
- Не коммитить `.env`, токены, credentials или PII.
- Всегда указывать `--project=avo-deal-sniper`; локальный gcloud default не доверять.
- Production delivery fail-closed и остаётся выключенной до финального cutover.
- Не использовать mock fallback в production.
- LLM не определяет финансовые значения.
- Telegram ambiguous send становится `unknown` и не повторяется автоматически.
- WhatsApp без Meta credentials остаётся выключенным и не блокирует Telegram release.

## Реализация

- источники: DubiCars, CarSwitch, Cars24 UAE, OpenSooq UAE;
- exact immutable snapshots и transactional current pointers;
- detail-page verification, immutable semantic evidence и `valid_until` freshness;
- cross-source identity, normalization, robust comparable market;
- deterministic Decimal cost/risk/decision engines;
- market fingerprint и пересчёт затронутого make/model;
- Firestore immutable decisions/current pointers;
- transactional outbox для personal/Free/Pro/WhatsApp;
- Telegram webhook/update leases, user search, saved searches, favorites/outcomes;
- Firebase Auth, Admin/TMA APIs и статические приложения в `web/`;
- repository-backed Market Pulse/engagement content;
- migration schema v2, ledger, checksums, checkpoints и isolated direct replay;
- Terraform, GitHub Actions, pip-audit, Trivy и non-root Python 3.11 Docker image.

## Текущий release state

Ветка: `production/deal-sniper-complete`, база — commit `bc5803a9c7af86bf63f3038430ea547bef83e7ee`. Production был остановлен до начала полной стабилизации: schedules/queues paused, webhook и delivery отключены, STOP export сохранён в защищённом bucket. Существующий draft PR #1 не является baseline и не должен сливаться.

Кодовая часть нового RC проходит Ruff, mypy и 42 теста. До статуса complete остаются immutable build, staging restore/rehearsal, production migration, финальный PR/merge, exact-digest deploy, staged resume и pilot. Источник истины по порядку — `docs/IMPLEMENTATION_PLAN.md`; операции — `docs/OPERATIONS.md`; контракт — `SPEC.md`.

Первый запуск CI выявил только неверный несуществующий pin Trivy Action `0.33.1`; он заменён на официальный release `v0.36.0`. Любой новый commit после этой правки требует новых immutable image digests.

Следующий container scan выявил две HIGH CVE в runtime build-tools `setuptools`/vendored `wheel`; Dockerfile удаляет эти ненужные пакеты после установки runtime dependencies. Digest, собранный до этой правки, недействителен.

После удаления build-tools Trivy не находит исправимых HIGH/CRITICAL. В Debian 13 остаются 23 OS findings без доступного `FixedVersion`; CI использует `ignore-unfixed=true`, но продолжает блокировать любую исправимую HIGH/CRITICAL.

Первый staging replay выявил несовместимость legacy hash с canonical `listing-content/v2`: 100 requests были помечены completed без evidence. Production не затронут. Migration tool повышен до 1.1.0, создаёт canonical snapshot documents и current hashes; direct replay предварительно отклоняет missing/non-current snapshot. Требуется новый RC и полный повтор staging rehearsal.

## Важные команды

```powershell
python main.py collect --source dubicars
python main.py replay --direct --concurrency 10
python -m ruff check src tests main.py
python -m mypy src main.py
python -m pytest --cov=src --cov-fail-under=45
terraform -chdir=infra/terraform validate
```

`replay --direct` разрешён только при `DELIVERY_ENABLED=false` и нужен для migration catch-up без включения production Cloud Tasks.
