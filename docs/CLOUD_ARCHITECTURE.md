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

Telegram webhook -> API Gateway -> Cloud Run API -> Firestore
                                      -> external automotive news RSS (read-only)
                                      -> Telegram Stars subscription / Pro channel membership
Firebase Hosting TMA -> Telegram initData -> Firebase custom token -> Cloud Run API
Firebase Hosting Admin -> Firebase email/password -> Firebase ID token + ADMIN_EMAILS -> Cloud Run API
Firebase Hosting /admin/** rewrite -> public Cloud Run ingress -> application-level Firebase authorization
Secret Manager -> runtime service accounts
Cloud Logging/Monitoring/Billing -> alerts and budget
```

## Компоненты

- `deal-sniper-api`: webhook, task handlers, Application API, admin API, TMA API и `/version`.
- четыре collector Jobs: DubiCars, CarSwitch, Cars24, OpenSooq.
- migration Job: immutable schema migration с dry-run/apply и ledger.
- replay Job: catch-up напрямую в maintenance-режиме либо через очередь.
- content Job: weekly Market Pulse и PublicationEvent.
- Telegram chat router: детерминированные intent/FAQ, персональный поиск и read-only news client.
- `listing-processing`, `telegram-delivery`: rate-limited Cloud Tasks с OIDC.
- Firestore: operational state, immutable evidence/decision/outbox history и current pointers.
- Cloud Storage: raw snapshots, Firestore exports и hosting assets.
- Firebase Hosting/Auth: TMA и Admin Web.

## Данные

Ключевые коллекции: `listings`, вложенные `snapshots`, `listing_current`, `verification_evidence`, `vehicle_identities`, `normalized_vehicles`, `decisions`, `current_decisions`, `delivery_outbox`, `telegram_updates`, `user_settings`, `saved_searches`, `user_actions`, `outcomes`, `publication_events`, `migration_ledger`, `migration_replay_requests`.

Immutable сущности создаются по каноническому ID; operational freshness и leases обновляются отдельно. Старый current pointer не удаляет историю.

Новостная лента не входит в verified market и не может изменять решение. Клиент принимает только HTTPS, ограничивает возраст и число материалов, удаляет дубли и возвращает пользователю provenance. Ошибка внешней ленты изолирована от collection/processing/delivery.

Pro entitlement определяется нативным членством пользователя в приватном платном Telegram-канале. Цена продукта хранится как `100 AED/30 дней`, платёжная цена — отдельным целым числом Stars. Приложение не хранит банковские данные и не создаёт собственный успешный платёж: Telegram является источником истины по подписке и членству.

## Безопасный релиз

Production scheduler/queues/delivery остаются остановленными во время сборки, staging и миграции. Staging восстанавливается из production export в отдельную named Firestore database. Runtime и migration образы фиксируются digest, а не tag. Любое изменение build context после rehearsal создаёт новый RC и требует повторного rehearsal.

Production migration использует тот же migration digest. Catch-up выполняется с `DELIVERY_ENABLED=false` через direct replay, поэтому production delivery queue не включается. Только после merge RC в `main`, deploy того же runtime digest и проверки `/version` разрешён staged resume.

## Права

Collector, API, migration/replay и scheduler имеют отдельные service accounts. Secret accessor выдаётся только runtime, которому нужен конкретный секрет. Public access запрещён для data buckets. Firestore export bucket использует UBLA, public access prevention, versioning и retention.

Terraform описывает desired state, но существующие вручную созданные ресурсы сначала импортируются. Локальный state отсутствует и не является источником истины до import.

## Наблюдаемость

Обязательные сигналы: source success/latency/schema drift, verification reject/error, processing backlog, task retries, outbox unknown/failed, publishable count, Free leakage, stale evidence, API 5xx, cost/budget. Алерт должен содержать project, service/job, revision/digest и correlation ID без токенов и PII.
