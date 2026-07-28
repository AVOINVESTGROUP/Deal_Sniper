# План R7 — полноценный Control Center и управляемая монетизация

Статус: утверждён владельцем 28 июля 2026 года. Этот документ является обязательным контрактом реализации R7.

## 1. Цель

R7 превращает существующую read-mostly Admin Web в рабочий центр управления продуктом. Администратор должен менять коммерческую цену Pro, управлять установленными источниками и расписаниями, видеть объявления, решения, пользователей, публикации и ошибки без редактирования `.env`, ручных команд и просмотра JSON.

Пользовательская TMA и Telegram-бот остаются отдельным клиентским продуктом. Административный интерфейс доступен только в обычном браузере по Firebase Authentication и серверному allowlist `ADMIN_EMAILS`.

## 2. Подтверждённые недостатки baseline R6

1. `PRO_PRICE_AED`, `PRO_PRICE_STARS`, финансовые пороги и URL подписки загружаются один раз из окружения; раздел Subscriptions показывает их без возможности изменения.
2. Реальная цена Telegram Stars зашита в subscription invite link. Существующую ссылку нельзя безопасно считать изменённой после изменения только отображаемой суммы AED.
3. В интерфейсе есть только Dashboard, Sources, Cloud runtime, Publications и Subscriptions, хотя утверждённая документация требует также Runs, Listings, Decisions, Users, Revenue, Errors и Settings.
4. Publications объединяет `unknown` и исторические `failed`, но backend разрешает reconcile только для `unknown`; интерфейс предлагает заведомо неработающие действия.
5. Cloud runtime и database operations в основном read-only и местами выводят технические структуры вместо понятных действий и показателей.
6. Изменения параметров не имеют preview, версии, подтверждения, audit trail и rollback.

## 3. Границы R7

В R7 входят:

- версионированная operational/commercial configuration в Firestore с локальной SQLite-реализацией для тестов;
- изменение коммерческой цены AED и фактической цены Stars из Admin Web;
- создание новой Telegram subscription invite link, проверка результата и атомарное переключение активной версии;
- использование активной версии цены и ссылки в боте, TMA и новых Free CTA без redeploy;
- разделы Dashboard, Sources, Runs, Listings, Decisions, Publications, Users, Revenue, Errors и Settings;
- фильтры, ограниченная пагинация, человекочитаемые состояния и подтверждение опасных операций;
- журнал административных изменений и возможность отката на ранее созданную валидную конфигурацию;
- управление установленными источниками и их ручным запуском;
- управление разрешёнными scheduler jobs через allowlist: запуск, пауза и возобновление;
- исправление reconciliation: действия доступны только для `unknown`, `failed` остаются диагностической историей.

Не входят хранение или показ секретов, произвольное создание облачных ресурсов, автоматическая отмена старых платных ссылок и production deploy без отдельного разрешения владельца после staging evidence.

## 4. Модель конфигурации

Активный документ `runtime_configuration/active` содержит только несекретные значения:

```text
version
state: active | archived
pro_price_aed
pro_price_stars
pro_subscription_url
subscription_period_seconds = 2592000
target_profit_aed
min_roi_percent
min_comparables_count
channel_max_posts_per_run
created_at
created_by
previous_version
telegram_link_name
```

Каждая версия неизменяема и дополнительно хранится как `runtime_configuration_revisions/{version}`. Переключение active pointer выполняется транзакционно. Токен бота, webhook secret, Firebase credentials, WhatsApp token и MTProto session в эту модель не входят.

Если active-документ отсутствует или невалиден, runtime fail-safe использует утверждённые значения окружения R6. Ошибка чтения динамической конфигурации не должна останавливать сбор и расчёт.

## 5. Смена цены Pro

Форма показывает отдельно коммерческую цену AED и фактическое списание Telegram Stars. Период фиксирован: 30 дней.

1. `Preview` проверяет AED, Stars, доступность Pro channel и отличие от текущей версии; ничего не меняет.
2. `Apply` требует точную строку подтверждения и idempotency key.
3. Backend создаёт новую subscription invite link через Telegram Bot API с периодом 2 592 000 секунд и ценой 1–10 000 Stars.
4. Backend проверяет полученную ссылку и сохраняет immutable revision.
5. Active pointer переключается одной транзакцией; старая версия архивируется, но её ссылка не отзывается автоматически.
6. Бот, TMA, CTA и Admin читают одну active revision. Новые публикации используют новую ссылку; retry старого outbox сохраняет исходный payload.
7. Audit event содержит actor, operation ID, old/new version и изменённые несекретные поля.

Rollback создаёт новую active revision на основе выбранной архивной версии. Недействующая архивная Telegram-ссылка заменяется новой ссылкой с той же ценой Stars.

## 6. Разделы интерфейса

- **Dashboard:** здоровье источников, свежесть сбора, очереди, delivery, current decisions, active Pro, публикации и ошибки.
- **Sources:** состояние, последний запуск, fetched/new/changed, Enable/Pause/Run now и проверяемое добавление JSON feed.
- **Runs:** последние source/content/delivery runs, длительность, correlation ID, результат и краткая ошибка.
- **Listings:** current listings, цена, verification/freshness/quarantine, время проверки и ссылка.
- **Decisions:** действие, цена, рынок, max purchase, прибыль, ROI, confidence, аналоги и версии engine/config.
- **Publications:** Free/Pro preview и outbox. Только `unknown` имеет `mark sent`, `mark failed`, `retry once`; `failed` — история без ложных кнопок.
- **Users:** Free/Pro status, язык, saved searches, favorites и последняя активность без лишних персональных данных.
- **Revenue:** цена AED/Stars, active Pro, referrals, Star balance и история версий цены.
- **Errors:** ошибки источников, quarantine, failed/unknown delivery и недоступные Cloud dependencies.
- **Settings:** preview/apply/rollback несекретных параметров, allowlisted schedules и audit history.

## 7. API

Все маршруты требуют Firebase ID token и `ADMIN_EMAILS`:

```text
GET  /admin/overview
GET  /admin/runs
GET  /admin/listings
GET  /admin/decisions
GET  /admin/users
GET  /admin/errors
GET  /admin/settings
POST /admin/settings/preview
POST /admin/settings/apply
POST /admin/settings/rollback
POST /admin/schedulers/{job_name}/action
GET  /admin/outbox?state=...
POST /admin/outbox/{delivery_id}/reconcile
```

Mutating endpoints требуют `operation_id`, проверяют допустимые поля, пишут audit event и являются идемпотентными. API Gateway содержит явный `OPTIONS` для каждого браузерного маршрута.

## 8. Проверки и выпуск

Локальный gate включает unit/integration/API/auth/CORS/browser tests, Telegram Bot API mock, Ruff, strict mypy, pytest/coverage, dependency audit, Terraform validate и container scan.

Staging проверяет immutable image и Hosting preview, Firebase Auth, смену тестовой цены в тестовом Pro channel, единую active revision в bot/TMA/Admin/CTA, rollback и все десять разделов без production-сообщений и платежей.

После staging формируется `docs/RELEASE_EVIDENCE_2026-07-28-R7.md`. Production deploy выполняется только после отдельной явной команды владельца.
