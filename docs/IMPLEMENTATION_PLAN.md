# План реализации Dubai Deal Sniper

Статус: кодовая часть RC подготовлена; production остаётся остановлен до прохождения immutable release, staging rehearsal, migration и cutover.

## Правила выполнения

1. Только автомобили с фиксированной ценой в ОАЭ.
2. Сначала проверяемый код и тесты, затем документация, затем cloud execution.
3. Ни один этап не разрешает delivery до финального cutover.
4. Любое изменение после фиксации RC digest аннулирует rehearsal.
5. WhatsApp не блокирует основной релиз, если единственная причина — отсутствующие внешние Meta credentials.

## Матрица реализации

| № | Результат | Код | Cloud evidence |
|---:|---|---|---|
| 1 | Production STOP, watermark и защищённый export | не применяется | подтверждено оператором; повторная проверка перед migration |
| 2 | Canonical IDs и golden vectors | реализовано, тесты | ожидает RC |
| 3 | Exact snapshot/current CAS/out-of-order | реализовано, тесты | ожидает staging |
| 4 | Source-bound verification и operational freshness | реализовано, тесты | ожидает live rehearsal |
| 5 | Identity, normalization, verified market | реализовано, тесты | ожидает staging data |
| 6 | Deterministic cost/risk/decision engines | реализовано, тесты | ожидает pilot |
| 7 | Current market fingerprint и controlled recalculation | реализовано, тесты | ожидает catch-up |
| 8 | Transactional delivery outbox и unknown reconcile | реализовано, тесты | ожидает staging smoke |
| 9 | Telegram update lease/idempotency | реализовано, тесты | ожидает webhook smoke |
| 10 | RU/EN personal search, saved searches, favorites | реализовано, тесты | ожидает TMA/bot smoke |
| 11 | Free/Pro split без утечки данных | реализовано, тесты/preview | ожидает channel pilot |
| 12 | Admin Web и Firebase Auth | реализовано, тесты | ожидает Hosting/Auth |
| 13 | TMA feed, filters, favorites, outcomes | реализовано | ожидает Hosting/BotFather |
| 14 | Естественный Telegram-диалог и новости авторынка Дубая | production, 57 тестов | наблюдение pilot |
| 15 | Pro 100 AED: Telegram Stars, платная ссылка, entitlement и CTA | реализовано, 58 тестов | production smoke |
| 14 | Market Pulse и engagement content | реализовано, тесты | включается после pilot |
| 15 | WhatsApp official opt-in adapter | реализовано fail-closed | ожидает внешние credentials |
| 16 | Schema migration tool/ledger/checkpoints/checksums | реализовано | ожидает staging rehearsal |
| 17 | Isolated direct replay с delivery=false | реализовано | ожидает staging/production |
| 18 | Terraform desired state/IAM/alerts/budget | реализовано, validate | ожидает import/apply |
| 19 | CI/CD security gates и non-root Python 3.11 image | реализовано | ожидает GitHub Actions/registry |
| 20 | Immutable RC build и manifest | готово к выполнению | ожидает digest |
| 21 | Staging restore/migration/full rehearsal | готово к выполнению | ожидает execution |
| 22 | Production migration, merge, cutover и pilot | запрещено до 21 | ожидает execution |

## Порядок оставшегося execution

### 0.11RC — immutable candidate

- green Ruff, mypy, pytest/coverage, pip-audit, Terraform и container scan;
- clean commit;
- runtime/migration images, связанные с commit и SHA-256 digests;
- manifest без секретов.

### 0.11S — staging rehearsal

- restore STOP export в named Firestore staging database;
- exact migration digest dry-run/apply;
- exact runtime digest с delivery disabled;
- direct replay и сверка counts/checksums/provenance;
- smoke источников, поиска, Admin/TMA и delivery preview/reconcile;
- ноль реальных исходящих сообщений.

### 0.11M — production migration

- подтверждённый STOP и новый export;
- тот же migration digest;
- dry-run/apply, isolated direct replay, reconciliation;
- collectors/queues/webhook/delivery остаются остановленными.

### 0.11D — baseline и staged resume

- `main` равен проверенному RC commit;
- deploy exact runtime digest;
- `/version` подтверждает commit/digest/schema;
- resume: collectors → processing → Telegram delivery;
- Firebase Hosting/Admin/TMA;
- content после успешного пилота.

### 0.11P — production pilot

Для 100–300 обработанных объявлений подтверждаются:

- цена совпадает с актуальной detail page;
- отсутствуют `Price on request` и price parsing anomalies;
- рынок использует только current/fresh/verified/deduplicated аналоги;
- публикация проходит profit/ROI/max-purchase gates;
- Free teaser не раскрывает Pro-данные;
- нет автоматических повторов `unknown`;
- outbox/provider IDs и source health доступны администратору.

После пилота формируется `docs/RELEASE_EVIDENCE.md` с commit, digests, cloud revisions, migration IDs, counts, checksums, smoke/pilot результатами и оставшимся внешним blocker WhatsApp, если он существует.

## Рабочая браузерная Admin Panel

1. `/admin.html` открывается в обычном desktop-браузере без Telegram-контекста.
2. Firebase email/password sign-in включён; пароль хранится только в Firebase Authentication, а backend принимает Firebase ID token только для email из `ADMIN_EMAILS`.
3. Административная роль определяется allowlist `ADMIN_EMAILS`, а не Telegram ID.
4. Браузерные запросы Admin Web идут через защищённый API Gateway: Firebase Hosting rewrite в приватный Cloud Run запрещён организационной политикой `allUsers`. Backend всё равно проверяет Firebase ID token и `ADMIN_EMAILS`.
4. Интерфейс содержит разделы Dashboard, Sources, Runs, Listings, Decisions, Publications, Users & subscriptions, Revenue & referrals, Errors и Settings.
5. Технические JSON/provenance/stack traces скрыты за подробностями; основной экран показывает человекочитаемые статусы и действия.
6. Collector получает минимальный доступ чтения/записи raw bucket; API получает read-only роли для Scheduler, Tasks и Run.
7. Ошибка обязательного этапа делает source run неуспешным; противоречие `success=true` вместе с `error` запрещено тестом.
8. Telegram используется для клиентского продукта и кратких owner alerts, но не как обязательная оболочка панели.

### Управление источниками

1. Раздел Sources содержит действие `Add source`, а не только переключатели предустановленных адаптеров.
2. Без изменения кода можно подключить структурированный JSON feed по HTTPS. Минимальные поля записи: стабильный ID, URL объявления, название и фиксированная цена в AED. Поля марки, модели, года, пробега и фотографий рекомендуются.
3. Перед сохранением backend сам загружает образец, проверяет HTTP/JSON, распознаёт записи и отклоняет пустой feed, `Price on request`, нулевые/аномально низкие цены и записи не об автомобилях.
4. Новый источник создаётся выключенным. Администратор видит результат теста и отдельно включает его после проверки.
5. Обычный marketplace HTML, антибот-защита или нестабильная закрытая схема требуют отдельного протестированного адаптера. Панель регистрирует такой источник как `Adapter required`, но не выдаёт его за работающий collector.
6. Конфигурация динамического feed хранится в Firestore/SQLite, доступна всем экземплярам API и collector, не содержит ключей или токенов и удаляется без удаления уже собранной истории.
7. Ручной `Run now` для динамического feed запускает общий Cloud Run collector с override имени источника; предустановленные источники продолжают использовать отдельные jobs.
