# Архитектура Google Cloud

## Контур

```text
Cloud Scheduler -> Cloud Run collector Jobs -> Cloud Storage raw
                                         \-> Firestore snapshot/current
                                             -> Cloud Tasks processing
                                             -> Cloud Run API/worker
                                                -> verification/evidence
                                                -> identity/normalization
                                                -> market/cost/risk/decision
                                                -> transactional outbox
                                                -> Cloud Tasks delivery
                                                -> Telegram / WhatsApp opt-in

Cloud Scheduler -> Telegram MTProto collector/discovery Jobs
                    -> Secret Manager session (single active lease)
                    -> Firestore source registry/cursors/candidates/reports
                    -> Cloud Storage raw message batches
                    -> Cloud Tasks telegram-source-analysis
                    -> classification/extraction/evidence tier
                    -> existing identity/processing pipeline

Telegram webhook -> API Gateway -> Cloud Run API -> Firestore
                                      -> external automotive news RSS (read-only)
                                      -> Telegram Stars subscription / Pro channel membership
Firebase Hosting TMA -> Telegram initData -> Firebase custom token -> Cloud Run API
Firebase Hosting Admin -> Firebase Auth provider -> Firebase ID token
                       -> API Gateway -> private Cloud Run API -> ADMIN_EMAILS
Secret Manager -> runtime service accounts
Cloud Logging/Monitoring/Billing -> alerts and budget
```

## Компоненты

- `deal-sniper-api`: webhook, task handlers, Application API, admin API, TMA API и `/version`.
- четыре collector Jobs: DubiCars, CarSwitch, Cars24, OpenSooq.
- планируемые MTProto Jobs: `deal-sniper-telegram-collector` для ограниченного backfill/incremental sync и `deal-sniper-telegram-discovery` для поиска чужих публичных источников. Они не входят в production до утверждения `docs/TELEGRAM_SOURCES_PLAN.md` и прохождения TG0–TG6.
- migration Job: immutable schema migration с dry-run/apply и ledger.
- replay Job: catch-up напрямую в maintenance-режиме либо через очередь.
- content Job: агрегированный Market Pulse, Pro reconciliation и Free reconciler.
- Telegram chat router: детерминированные intent/FAQ, персональный поиск и чтение общего активного `news_evidence` без независимого live-fetch.
- News ingestion: управляемый registry → publisher/domain/relevance gate → source-backed image gate → immutable `news-assets/{sha256}` в Cloud Storage → Firestore `news_evidence` → парные `free-news/v1`/`pro-news/v2` outbox-карточки.
- Service account publisher Job имеет `roles/storage.objectUser` только на raw bucket: именно publisher сохраняет и повторно читает immutable `news-assets/{sha256}`; одного доступа API runtime для этого недостаточно.
- `listing-processing`, `telegram-delivery`: rate-limited Cloud Tasks с OIDC.
- Firestore: operational state, immutable evidence/decision/outbox history и current pointers.
- Cloud Storage: raw snapshots, Firestore exports и hosting assets.
- Firebase Hosting/Auth: TMA и Admin Web.

## Независимые контуры выпуска

- Data Plane: collectors, verification, market и decision engines.
- Product Delivery Plane: content publisher, transactional outbox, Cloud Tasks и Telegram.
- Control Plane: Admin Web, Firebase Authentication, API Gateway и Admin API.

Недоступность Control Plane не останавливает Data Plane или уже настроенный Product
Delivery Plane. Google Sign-In и Pro publisher имеют разные release gates. Для каждого
deployable component release manifest фиксирует commit, digest, schema и совместимые
template versions.

## Инвариант публикации Free → Pro

Объектная Free-публикация не создаётся непосредственно из решения или Market Pulse.
Сначала transactional Pro outbox той же `decision_id + listing_id + content_hash`
доставляется в Telegram и получает состояние `sent` и `telegram_message_id`. Только после
этого Free reconciler создаёт immutable `free/v3` с `parent_pro_delivery_id`, точной ссылкой
на Pro-сообщение и тем же content hash. Delivery handler повторяет проверку перед отправкой.
Legacy-шаблоны `free/v2` и объектный `market-watch/v2` заблокированы на входе delivery.

## Данные

Ключевые коллекции: `listings`, вложенные `snapshots`, `listing_current`, `verification_evidence`, `vehicle_identities`, `normalized_vehicles`, `decisions`, `current_decisions`, `delivery_outbox`, `telegram_updates`, `user_settings`, `saved_searches`, `user_actions`, `outcomes`, `publication_events`, `migration_ledger`, `migration_replay_requests`. R7 добавляет `runtime_configuration/active`, неизменяемые `runtime_configuration_revisions`, идемпотентные `admin_operations` и административный audit trail. Telegram Sources добавляет `telegram_sources`, `telegram_source_candidates`, `telegram_messages`, `telegram_source_reports` и отдельные cursor/lease records.

Immutable сущности создаются по каноническому ID; operational freshness и leases обновляются отдельно. Старый current pointer не удаляет историю.

Новостная лента не входит в verified market и не может изменять решение. Клиент принимает только HTTPS, ограничивает возраст и число материалов, удаляет дубли и возвращает пользователю provenance. Ошибка внешней ленты изолирована от collection/processing/delivery.

Telegram MTProto raw messages также не входят в verified market автоматически. Они создают evidence tier `seller_stated`; только source-bound внешняя проверка, независимый verified marketplace listing или ручная проверка с provenance повышает evidence до `verified_listing`.

Pro entitlement определяется нативным членством пользователя в приватном платном Telegram-канале. Коммерческая цена AED, платёжная цена Stars и активная subscription link читаются из единой версионированной runtime-конфигурации; переменные окружения являются только fallback baseline. Смена Stars создаёт новую Telegram subscription link, после чего активная версия переключается транзакционно. Приложение не хранит банковские данные и не создаёт собственный успешный платёж: Telegram является источником истины по подписке и членству.

## Безопасный релиз

Production scheduler/queues/delivery остаются неизменными во время сборки и staging. При production migration останавливаются только затрагиваемые компоненты. Staging восстанавливается из production export в отдельную named Firestore database и использует отдельные publisher Job, Telegram recipient и delivery queue. Runtime и migration образы фиксируются digest, а не tag. Любое изменение build context после rehearsal создаёт новый RC и требует повторного rehearsal.

`DELIVERY_ENABLED=false` запрещает создание Cloud Task, но не запрещает идемпотентно
сохранить `pending` outbox. Включённый publisher может переочередить этот record только в
очередь своего окружения. Совпадение staging recipient/queue/database с production
считается ошибкой конфигурации и блокирует запуск.

Production migration использует тот же migration digest. Catch-up выполняется с `DELIVERY_ENABLED=false` через direct replay, поэтому production delivery queue не включается. Только после merge RC в `main`, deploy того же runtime digest и проверки `/version` разрешён staged resume.

## Права

Collector, API, migration/replay и scheduler имеют отдельные service accounts. Secret accessor выдаётся только runtime, которому нужен конкретный секрет. Public access запрещён для data buckets. Firestore export bucket использует UBLA, public access prevention, versioning и retention.

Terraform описывает desired state, но существующие вручную созданные ресурсы сначала импортируются. Локальный state отсутствует и не является источником истины до import.

## Наблюдаемость

Обязательные сигналы: source success/latency/schema drift, verification reject/error, processing backlog, task retries, outbox unknown/failed, publishable count, Free leakage, stale evidence, API 5xx, cost/budget. Для MTProto дополнительно контролируются session health, active lease, FloodWait/`next_allowed_at`, message lag, candidate backlog, quality rejection rate, extraction completeness и ошибочные price anomalies. Алерт должен содержать project, service/job, revision/digest и correlation ID без токенов, session и PII.
