# План реализации Dubai Deal Sniper

> Дополнение R7 утверждено владельцем 28 июля 2026 года. Контракт полноценного Control Center и управляемой монетизации находится в `docs/ADMIN_CONTROL_CENTER_PLAN_R7.md`. R7 реализуется поверх production baseline R6 и не разрешает production deploy без отдельного подтверждения после staging.

Статус: кодовая часть RC подготовлена; production остаётся остановлен до прохождения immutable release, staging rehearsal, migration и cutover.

## Правила выполнения

1. Только автомобили с фиксированной ценой в ОАЭ.
2. Сначала обновляется документация и утверждается план, затем создаются проверяемый код и тесты, и только после этого выполняется cloud execution.
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
| 23 | Чужие Telegram sources: MTProto registry, analyzer и evidence tier | только документация | ожидает утверждения плана |
| 24 | Telegram discovery и controlled scaling до 50–200 sources | только документация | после успешного Telegram pilot |
| 25 | Уникальный CTA и кнопка Pro под каждым Free-объявлением | кандидат `1ce36ff` отклонён аудитом | исправленный план R6 и повторная реализация после утверждения |

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

### Free → Pro CTA под каждым объявлением

1. Каждый автомобильный пост Free получает англоязычный CTA и inline-кнопку подписки Pro; публикация без корректной `TELEGRAM_PRO_SUBSCRIPTION_URL` запрещена.
2. CTA создаётся один раз на новый `publication_id`: Gemini получает только уже подтверждённые поля карточки и не создаёт финансовые значения. Fallback — утверждённая библиотека минимум из 30 вариантов.
3. Проверка допускает только короткий английский текст, разрешённые факты и один из продуктовых акцентов: verified market, maximum purchase, costs, expected profit, ROI или risks.
4. `cta_fingerprint` не повторяется до исчерпания пула; соседние публикации всегда имеют разные CTA и button labels. Выбор детерминирован для `publication_id`.
5. `cta_variant_id`, текст, label, target и template/model version сохраняются в `PublicationEvent` и outbox. Retry повторяет исходный вариант без нового вызова Gemini.
6. Тесты проверяют наличие кнопки у 100% Free vehicle posts, отсутствие Pro-данных в teaser, корректность ссылки, разнообразие, fallback, идемпотентность и отсутствие выдуманных чисел.
7. Pilot проверяет не менее 30 последовательных постов, ноль соседних повторов, ноль постов без кнопки и доступную конверсию в членство Pro.

### Корректирующий релиз R6: Admin Web и Free → Pro

Кандидат `1ce36ff` не развёртывается. Его локальные тесты не доказывают соответствие сквозным контрактам. Полный аудит и критерии повторной реализации зафиксированы в `docs/PLAN_REVIEW_2026-07-27-R6.md`.

Порядок релиза после отдельного утверждения владельцем:

```text
R6.1  контракт publication identity и совместимость старых событий/outbox
R6.2  единый Free renderer без цены, рынка, ссылки, ID, прибыли и ROI
R6.3  сохранение CTA + кнопки в одном атомарном publication/outbox контуре
R6.4  диагностика Admin browser path и устранение подтверждённой причины
R6.5  integration/browser tests, CORS/CSP/auth failure matrix
R6.6  immutable image, staging rehearsal и release evidence
R6.7  deploy exact digest, Hosting release и live smoke
```

До завершения R6.1–R6.5 запрещены Cloud Run, Jobs, API Gateway и Firebase Hosting deploy. До R6.6 запрещено включать новые Free-публикации шаблонов v2.

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

### Telegram Sources — чужие публичные каналы и группы

Этот контур не является функцией пользовательского Telegram-бота. Он реализуется отдельным MTProto collector от имени выделенного технического аккаунта и до утверждения данного плана не развёртывается.

1. Admin Web принимает публичный `@username` или `t.me` URL, разрешает стабильный peer ID и запускает ограниченный анализ истории.
2. Для каждого источника сохраняются type, peer identity, access state, status, quality report, cursor, lease и provenance обнаружения. Credentials и session находятся только в Secret Manager.
3. Source Discovery создаёт кандидатов по EN/AR/RU search, forward origin, ссылкам/упоминаниям и cross-post graph. Кандидат не становится включённым источником автоматически.
4. Анализатор группирует media albums, учитывает edits/deletes, классифицирует sale/wanted/rent/parts/auction/discussion/spam и извлекает только присутствующие поля.
5. Gemini разрешён только как fallback для нового неоднозначного content hash. Детерминированный парсер остаётся источником цены, AED, года, пробега, телефона и URL; финансовые решения Gemini запрещены.
6. Quality Gate требует достаточную выборку, минимум 20 продаж, classification precision не ниже 90%, fixed-price coverage не ниже 70%, make/model/year completeness не ниже 80% и price anomaly rate не выше 1%. Иначе источник остаётся `needs_review` или `rejected`.
7. Telegram-only evidence маркируется `seller_stated`, исключается из verified comparable market и не может самостоятельно создать `CONTACT`.
8. Инкрементальный collector работает конечными batch, хранит message cursor и single active lease, уважает FloodWait и не создаёт бесконечный цикл в Cloud Run.
9. Пилот начинается с 10–20 источников на 7 дней и ручной проверки минимум 200 извлечений. Масштабирование до 50–200 включённых источников разрешается только отдельным отчётом.
10. Полный контракт, схема Admin, данные и порядок TG0–TG6 находятся в `docs/TELEGRAM_SOURCES_PLAN.md`.

### Порядок релизов Telegram Sources

```text
TG0  golden dataset и контракты
TG1  MTProto bootstrap/session/connectivity
TG2  Admin registry, backfill и quality report
TG3  extraction, Gemini fallback и evidence tiers
TG4  incremental collector, cursors, edits/deletes и metrics
TG5  multilingual discovery и candidate queue
TG6  staging, 7-day production pilot и решение о масштабировании
```

Каждый этап заканчивается unit/integration/contract tests и обновлением документации. Production delivery не принимает Telegram-derived `CONTACT` до отдельного доказательства отсутствия Telegram-only verified decisions.
# Статус R6

R6 утверждён владельцем и полностью развёрнут в production 27 июля 2026 года. Финальный baseline и результаты pilot зафиксированы в `docs/RELEASE_EVIDENCE_2026-07-27-R6.md`. Следующий этап не изменяет этот baseline: эксплуатационное наблюдение, измерение конверсии Free → Pro и подключение новых источников отдельными проверяемыми адаптерами.
