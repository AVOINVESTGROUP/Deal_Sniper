# Полный план восстановления Dubai Deal Sniper — R9

Статус: **черновик для единого утверждения владельцем**.
Дата аудита: 1 августа 2026 года, Asia/Dubai.
Код и production по этому документу ещё не изменялись.

Этот документ заменяет как рабочий план все R6–R8.1.3G-документы. Они остаются
историей решений и release evidence, но не являются разрешением продолжать старую
последовательность релизов. Незавершённое исправление G.1 включено в R9.2 и не требует
отдельного микроплана после утверждения R9.

## 1. Итог аудита

Проект нельзя считать целостным работающим production-продуктом. В нём уже есть
существенная полезная реализация — четыре настоящих коллектора, raw snapshots,
Firestore/Cloud Storage, детерминированный финансовый движок, Telegram/TMA/Admin
каркасы, outbox и точная связь Pro → Free. Но фактический production, текущая ветка,
`main`, Hosting, API Gateway, Cloud Run jobs и Terraform описывают разные версии
системы.

Наблюдаемые пользовательские проблемы являются следствием нескольких независимых
дефектов:

- Admin Web не может стабильно обращаться к Admin API;
- периодический publisher не запущен в заявленном режиме;
- подавляющее большинство объявлений не получает достаточное число корректных
  аналогов и честно завершается `INSUFFICIENT_DATA`;
- current-решения могут пережить изменение или истечение исходных доказательств;
- миграция, immutable storage и delivery state machine не обеспечивают безопасный
  повтор;
- Pro entitlement применяется не на всех путях;
- пользовательский поиск, подписка, новости, чат и управление источниками реализуют
  лишь часть заявленного продукта;
- зелёный CI проверяет код, но не доказывает работоспособность live-системы.

Правильный результат R9 — не большое число публикаций любой ценой. Если реально
подходящих автомобилей нет, допустимый результат равен нулю. Недопустимо публиковать
выдуманные объекты, цену `Price on request`, неподтверждённую цену, случайное фото,
ложную прибыль или Free-анонс, для которого ещё нет точной полной карточки в Pro.

## 2. Границы проекта

В R9 входят только автомобили с фиксированной ценой в ОАЭ:

- реальные marketplace/dealer feeds и в дальнейшем чужие публичные Telegram-источники;
- нормализация, дедупликация, verified asking-market и финансовая оценка;
- персональный Telegram-бот и Telegram Mini App;
- Free- и Pro-каналы с точным соответствием одного автомобиля;
- Admin Web для владельца;
- Telegram Stars подписка Pro с коммерческой ценой 100 AED за 30 дней по умолчанию;
- source-backed новости и ответы в связанном Telegram-чате;
- WhatsApp Cloud API только как отдельно включаемая opt-in доставка.

Не входят:

- недвижимость;
- аукционы, ставки и отслеживание торгов;
- автоматическая покупка автомобиля;
- автоматическое общение с продавцом;
- выдуманные или синтетические production-объявления;
- использование LLM для цены, рынка, расходов, прибыли, ROI или решения;
- отдельный тестовый Telegram-канал. Проверка выполняется при выключенной доставке,
  а после отдельного разрешения production deploy — ограниченным smoke в существующих
  каналах.

`irepn.site` не связан с текущим кодом, Hosting или DNS-конфигурацией проекта и не
считается работающим интерфейсом R9. Основной адрес до отдельного решения о домене —
Firebase Hosting проекта `avo-deal-sniper`.

## 3. Проверенная исходная точка

| Область | Фактическое состояние на 01.08.2026 | Вывод |
|---|---|---|
| Git | рабочая ветка `production/deal-sniper-complete`, HEAD `fafcb256`; `main` — `e1848d7`, ветка содержит около 141 отличающегося файла | единый release baseline отсутствует |
| Pull request | большой draft PR с прошедшими checks | зелёный PR не равен выпущенному продукту |
| Локальный gate | Ruff и strict mypy проходят; тесты проходят, 2 интеграционных теста пропущены; coverage около 63% | достаточен для прототипа, недостаточен для cutover |
| Python | CI использует 3.11, активное локальное окружение сообщало 3.13 | локальный результат не полностью воспроизводим |
| CI | порог общего coverage только 45%; зависимости и часть Actions/base image не закреплены immutable digest/version | возможны непроверенные критические ветки и дрейф сборки |
| Production API/publisher | commit `6dd9af`, digest `b6a2…` | не совпадает с Git HEAD |
| Production collectors/migration/replay | commit `851ddaf`, digest `c2e55…` | компоненты production несовместимы по версиям |
| Staging | commit `925597`, digest `48ddd…` | не является rehearsal текущего HEAD |
| Источники | DubiCars, CarSwitch, Cars24 UAE, OpenSooq UAE; registry показывает healthy, но за 24 часа у DubiCars было 344 `KeyError: offers`, а API зарегистрировал 261 ответа 5xx processing из-за временных 429 | текущий health скрывает semantic/retry деградацию |
| Решения Firestore | 1 768 current: 1 678 `INSUFFICIENT_DATA`, 89 `REJECT`, 1 `INSPECT` | основной bottleneck — данные/нормализация/аналоги, а не только Telegram |
| Публикации | единственный допустимый объект уже был отправлен в Pro, Free и personal; outbox: 186 sent, 2 pending, 2 failed | повторять его нельзя; pending/failed требуют reconciliation |
| Telegram-карточки | подтверждены 6 sent `free/v3` с exact sent Pro parent, 10 sent `pro/v1` и 5 парных illustrated news revisions; новых current eligible сверх уже отправленного нет | каналы не полностью пусты, но поток новых объектов фактически исчерпан текущим data gate |
| Publisher | production job запускает `main.py content`; отдельного `main.py publish` каждые 15 минут нет; основной content scheduler paused, weekly остаётся | новые допустимые объекты не гарантированно доходят в каналы |
| Scheduler источников | expressions `0/10`, `2/10`, `4/10`, `6/10` по фактическим executions запускают jobs раз в час, несмотря на имена `every-10m` | freshness существенно хуже заявленной |
| Admin | live Hosting использует старый Gateway и Google Auth=false; большинство новых Admin routes дают 404 без CORS. Checked-in Hosting config, наоборот, направляет Admin в private `run.app`, который отвечает 403 | и live, и следующий непроверенный artifact сломаны разными способами |
| IAM/IaC | документация требует private Run + Gateway; Terraform допускает `allUsers`, общий production namespace и publisher с `DELIVERY_ENABLED=true` | Terraform нельзя применять в текущем виде |
| Firestore | PITR и deletion protection выключены | восстановление production данных не защищено |
| Миграция | версии `1.2.1`, `1.1.0` и `1.0.0` расходятся; completed ledger можно повторно открыть dry-run; последняя staging migration завершилась `blocked_unknown_schema`/FAILED | повторный запуск может повторно инвалидировать данные, а текущий candidate rehearsal не пройден |
| Схема market coverage | из 2 106 comparison keys только 62 имеют не менее пяти записей; это 495 из 3 134 normalized listings | массовый `INSUFFICIENT_DATA` имеет измеримое структурное объяснение |
| News | пять пар Free/Pro имеют одинаковое evidence/изображение и уже отправлены; AI summary не использовался | news pipeline частично работает, но не доказывает актуальность всего продукта |
| Runtime settings | collections runtime configuration/revisions/admin operations пусты; 100 AED, 1 500 Stars, min comparables 5, ROI 10% и profit 5 000 AED фактически берутся из env | видимая Admin «настройка» ещё не управляет production policy |

## 4. Что уже можно сохранить

R9 не переписывает проект с нуля. Сохраняются после усиления контрактов:

- адаптеры DubiCars, CarSwitch, Cars24 UAE и OpenSooq UAE;
- детерминированные Decimal engines и канонические ID;
- запрет mock fallback в production;
- source-bound detail verification как основа, но не текущая мягкая идентификация;
- raw archive и transactional current pointer как концепция;
- transactional outbox как концепция;
- exact Pro-parent → Free teaser invariant;
- source-backed news evidence и парная Free/Pro news delivery;
- Firebase Hosting, Firebase Authentication, Cloud Run, Cloud Tasks, Firestore,
  Cloud Storage, Secret Manager и API Gateway как целевая платформа;
- существующие пользовательские и административные интерфейсы как прототипы UX.

## 5. Полный реестр дефектов

### 5.1 P0 — запрещают новый production cutover

| ID | Дефект | Наблюдаемый риск | Обязательное исправление |
|---|---|---|---|
| P0-01 | API, publisher, collectors, migration, replay, staging, Git branch и `main` работают на разных commit/digest | несовместимые схемы и поведение невозможно воспроизвести | единый release manifest и один runtime digest для API и всех runtime jobs; отдельный migration digest из того же commit |
| P0-02 | live Hosting использует устаревший Gateway, где большинство Admin routes отсутствует; checked-in config выбирает direct private `run.app`; CSP/CORS не совпадают | Admin показывает `Failed to fetch`, а простой Hosting deploy сделает другой нерабочий вариант | только Hosting → Gateway → private Run; все routes, Google Auth flag и CORS в одном versioned Gateway IaC |
| P0-03 | Terraform hardcodes publisher `DELIVERY_ENABLED=true`, production queue и общие имена; image может быть не digest-pinned | staging способен создать production delivery и не является изолированным | отдельные project/database/bucket/queue/job/scheduler names; `delivery=false`; denylist production recipients; только `@sha256` и непустой provenance |
| P0-04 | completed migration можно перезаписать повторным dry-run, затем повторный apply сбрасывает replay requests в `pending` | повторная инвалидация и повторная обработка production | terminal completed epoch, отдельный audit-run, create-once replay request, CAS/checkpoint и regression `apply → dry-run → apply` |
| P0-05 | мигратор не инвентаризирует все collections и принимает любой `*/v2` | часть данных остаётся в неизвестной схеме без checksums | explicit schema registry всех root/nested collections, before/after counts/checksums и unknown-schema STOP |
| P0-06 | Firestore historical snapshots, decisions и evidence допускают overwrite/merge | меняется доказательная база уже отправленного решения | immutable create-once/exact-match documents плюс отдельные mutable current/freshness pointers |
| P0-07 | current decision не всегда инвалидируется при verification reject, semantic change, expiry/reactivation или исчезновении listing | в каналах/боте может остаться устаревшая сделка | listing lifecycle sweeper, dependency graph, transactional retirement и пересчёт всего затронутого cohort |
| P0-08 | publisher выбирает current decision без повторной проверки исходной evidence freshness | stale карточка может быть опубликована | в одной транзакции revalidate listing current, evidence `valid_until`, decision/config/fingerprint и entitlement перед outbox creation/send |
| P0-09 | fail-closed ветки delivery могут оставить outbox `pending`; claim/send не связан immutable attempt; request payload может отличаться от claimed payload | вечные повторы, гонки и отправка изменённого payload | полная CAS state machine, immutable payload из outbox, `attempt_id`, terminal `cancelled/superseded`, lease timeout и reconcile |
| P0-10 | Telegram webhook/internal task auth допускает пустой secret и доверяет заголовку Cloud Tasks | обход служебной аутентификации | fail-fast startup, private Run, OIDC service identity, audience validation и обязательные secrets |
| P0-11 | Pro-проверка отсутствует на `/tma/market-watch`, legacy `/deals` и непосредственно перед personal send | Free пользователь может получить Pro-данные | единый `EntitlementService` на каждом read/delivery path и negative contract tests |
| P0-12 | detail binding использует мягкое совпадение URL/title; один общий `.html` token способен подтвердить чужую страницу; monthly/downpayment может пройти как fixed price; redirect target/IP проверяются недостаточно строго | цена или объект могут принадлежать другой странице; рассрочка может стать ценой покупки; SSRF | exact source/listing ID, final domain/path, markers POR/monthly/downpayment, public-IP pinning, redirect-by-redirect validation и immutable detail response archive |
| P0-13 | scheduled Pro reconciliation не соответствует плану, live publisher выполняет другую команду, а source cron фактически выполняется раз в час | подходящий объект не появляется вовремя в каналах и evidence устаревает | source jobs с доказанным интервалом 10 минут, отдельный idempotent publisher каждые 15 минут и event-driven enqueue после нового current decision |
| P0-14 | PITR/deletion protection выключены, rollback после частичной миграции не формализован | потеря данных или unsafe resume | IaC protection, защищённый export, restore rehearsal и запрет старого runtime после необратимого шага |
| P0-15 | migration отмечает старые решения `active=false`, но Firestore reader продолжает читать их без active/current filter | invalidated данные снова участвуют в replay/publication | единый repository contract `active + current snapshot + fresh evidence` и regression migration/replay |
| P0-16 | current pointer не получает обязательную source sequence/event time | поздний результат способен откатить current на старую revision | server-side compare-and-set по source sequence/observed time с deterministic tie-breaker |
| P0-17 | publication event/outbox и enqueue не полностью атомарны; enqueue может использовать исходный, а не сохранённый payload | orphan event/task и несоответствие отправленного контента | транзакционная запись event+outbox, task только с delivery ID, enqueue строго сохранённой revision |

### 5.2 P1 — не дают продукту правильно работать и монетизироваться

| ID | Дефект | Требуемый результат |
|---|---|---|
| P1-01 | 1 678 из 1 768 current decisions имеют недостаточно аналогов | измеримая funnel по source/stage/reason и рост verified comparable coverage без ослабления достоверности |
| P1-02 | normalization/model/generation/trim/specification неполны | канонический каталог make/model/generation/trim/body/spec с aliases и confidence/unknown quarantine |
| P1-03 | cross-source identity фактически надёжен только при VIN | probabilistic candidate matching с безопасным merge threshold и ручным split/merge audit |
| P1-04 | same-price semantic changes не пересчитывают peers | semantic fingerprint события запускают cohort recalculation независимо от цены |
| P1-05 | listing disappearance/stale/remove/reactivate не реализованы сквозным образом | двухфазный lifecycle с source coverage watermark, grace period и tombstone/current retirement |
| P1-06 | фотографии — внешние hotlinks без гарантированного immutable asset | архивировать реальное source image в GCS с URI, MIME, size, checksum; никакой подмены |
| P1-07 | поисковый parser не извлекает model/body type, TMA отправляет пустые arrays, matching игнорирует body type | make/model/body/budget/year/mileage/spec/profit/ROI end-to-end и экран подтверждения неизвестных параметров |
| P1-08 | чат — keyword router, а не полезный помощник | guided conversational state machine; LLM опционально только для source-grounded языка, без генерации фактов |
| P1-09 | market использует asking prices, но UI говорит просто «market» | везде показывать `verified asking market`, sample, диапазон, возраст данных и provenance |
| P1-10 | year/mileage/trim adjustments и cost assumptions статичны и не откалиброваны | versioned assumptions, backtest на adjudicated sample, scenario label и owner controls с audit |
| P1-11 | confidence не является калиброванной вероятностью | переименовать в data confidence либо откалибровать и описать смысл |
| P1-12 | четыре источника мало для покрытия рынка | после стабилизации подключить минимум 8 независимых marketplace/dealer feeds; каждый через adapter contract/canary, не через произвольный scraping switch |
| P1-13 | Admin умеет динамически добавить только публичный HTTPS JSON feed; обычный HTML marketplace требует код | понятный source registry: installed adapters, JSON feeds, Telegram candidates, test result, enable/pause, run, quarantine и provenance |
| P1-14 | чужие Telegram-каналы/чаты через MTProto только описаны | отдельный collector, source analyzer, sample quality report, manual enable; Telegram price остаётся `seller_stated` до независимой verification |
| P1-15 | news registry часто пуст, generative summary выключен, live/branch components различаются | единый evidence-backed feed, image archive, same evidence во Free/Pro/боте/чате; Vertex summary только из evidence и с source link |
| P1-16 | подписка определяется преимущественно membership канала | собственный subscription/entitlement ledger: purchase, renewal, expiry, refund/cancel, reconciliation и audit |
| P1-17 | изменение Stars price может оставить старую платную ссылку действующей | атомарная ротация: новая versioned price/link, retiring/revocation старой, Admin preview и audit |
| P1-18 | Admin не даёт полного управления бизнесом | Dashboard, Sources, Runs, Listings, Decisions, Publications, Users, Revenue, Errors, Settings с реальными actions и подтверждением опасных операций |
| P1-19 | Admin endpoints сканируют большие collections без cursor pagination | indexes, cursor pagination, bounded filters и export jobs |
| P1-20 | in-memory locks/rate limits работают только в одном instance | Firestore/Redis-style distributed lease, per-source quotas, exponential backoff и circuit breaker |
| P1-21 | dynamic/news fetch защищены не от всех redirect/DNS-rebinding сценариев | единый hardened outbound fetcher с allowlist, IP resolution pinning, limits и audit |
| P1-22 | WhatsApp заявлен, но credentials отсутствуют | в интерфейсе честный `disabled`; включение только после official Cloud API credentials и opt-in smoke |
| P1-23 | язык интерфейсов и каналов неодинаков | английский default; устройство/TMA locale выбирает поддерживаемый язык; каналы имеют фиксированный English content contract |
| P1-24 | Free/Pro exact pairing реализован в ветке, но live работает на другом baseline | один выпуск exact invariant; Free создаётся только после Pro `sent` exact revision и содержит ссылку на неё |
| P1-25 | detail verification хранит checksum, но не гарантирует immutable `source_response_uri` | evidence нельзя независимо воспроизвести | архивировать detail bytes до semantic validation и сохранять URI/checksum/final URL |
| P1-26 | retry contract различается по адаптерам и не хранит единый attempt evidence/Retry-After/jitter/category | health и причина потери данных недостоверны | общий retry policy и append-only attempt events для каждого source |
| P1-27 | source health может показывать success при сотнях parser errors | владелец видит ложное `healthy` | health рассчитывается по HTTP, semantic acceptance, drift, latency, retry и rejection ratios |
| P1-28 | news freshness может жить почти два TTL; RIFF ошибочно принимается за WebP | просроченный/неверный asset допускается к публикации | строгий `valid_until`, сигнатуры MIME и adversarial image tests |
| P1-29 | billing считает `RESTRICTED` активным без обязательного membership | entitlement может быть выдан ошибочно | Telegram status mapping + explicit `is_member`/subscription ledger reconciliation |
| P1-30 | Pro news pairing ограничено сканированием последних 500 записей | старая pending пара может потеряться | индексированный lookup по evidence/publication ID без bounded tail scan |
| P1-31 | dynamic feed test допускает year-only sample, который затем не проходит normalization | Admin обещает рабочий источник, не способный дать данные | test source использует те же mandatory normalization/verification contracts, что production |
| P1-32 | WhatsApp handler существует, но production producer/opt-in E2E отсутствует | интерфейс создаёт впечатление готовой интеграции | либо полный opt-in event→outbox→task→provider E2E, либо честный external-disabled статус |

### 5.3 P2 — качество сопровождения

| ID | Дефект | Исправление |
|---|---|---|
| P2-01 | `web.py`, `firestore_storage.py` и `storage.py` стали монолитами | разделить по bounded contexts после фиксации контрактов, без изменения внешнего поведения |
| P2-02 | общий coverage gate 45%, критические модули имеют 0–45%, browser/Firestore tests пропускаются | общий минимум 85%, критические state/auth/migration/delivery пути не ниже 95%; обязательные emulator/browser jobs |
| P2-03 | local Python 3.13, CI 3.11, зависимости используют диапазоны | единый Python 3.11, lock/constraints с hashes, воспроизводимый Docker и setup check |
| P2-04 | GitHub Actions и base image не полностью immutable pinned | Actions по commit SHA, base image по digest, SBOM и signed provenance |
| P2-05 | Terraform не создаёт alert policies, log metrics, notification channels и uptime checks | полный monitoring IaC и проверяемые SLO alerts |
| P2-06 | OPERATIONS содержит устаревший тестовый канал и неполный rollback | один актуальный runbook без тестового канала и с явной точкой no-return |
| P2-07 | `IMPLEMENTATION_PLAN`, `AI_CONTEXT`, README и множество R6–R8 планов противоречат live | R9 становится единственным текущим планом; остальные явно historical |
| P2-08 | `main` далеко позади долгоживущей mega-ветки | один reviewable release lineage, fast-forward main только на прошедший exact RC |

### 5.4 Карта проверяемых доказательств

Ключевые выводы привязаны к фактическим участкам проекта:

- migration re-entry, schema inventory и replay reset: `src/migration.py:38`, `:62`,
  `:94`, `:336`, `:367`, `:443`; пробел regression — `tests/test_migration.py:76`;
- Terraform publisher delivery/queue и public access: `infra/terraform/main.tf:135`,
  `:193`, `:557`; immutable variables — `infra/terraform/variables.tf:51`;
- runtime staging guards — `src/config.py:148`; расходящиеся migration versions —
  `src/migration.py:17`, `src/config.py:237`, `infra/terraform/main.tf:226`;
- checked-in Admin routing — `web/runtime-config.json:3`, `web/admin.js:10`; API
  specification — `infra/api-gateway.yaml`;
- fail-open internal/webhook auth — `src/web.py:376`, `:448`, `:572`, `:1866` и
  `src/tasks.py:155`;
- outbox claim/complete races — `src/storage.py:658`, `:782`,
  `src/firestore_storage.py:197`; отправка task payload вместо claimed payload —
  `src/web.py:2446`, `:2540`, `:2725`;
- Pro entitlement gaps — `src/web.py:1846`, `:1988`, `:2351`, `:2447`; корректный
  reference gate — `src/web.py:1634`;
- verification identity/fixed-price gaps — `src/verification.py:287`, `:395` и
  `src/sources/json_feed.py:119`; отсутствие detail URI — `src/verification.py:48`,
  `:223`, `src/domain/models.py:363`;
- SSRF surfaces — `src/sources/json_feed.py:36`, `:65`, `:167`,
  `src/verification.py:93`, `src/news.py:84`, `src/news_evidence.py:89`;
- stale decision/recalculation — `src/service.py:269`, `:345`,
  `src/pro_publication.py:85`, `src/bot.py:34`;
- immutable Firestore gaps — `src/firestore_storage.py:52`, `:183`, `:761`, `:1093`;
  invalidation reader — `src/firestore_storage.py:942`;
- publication atomicity — `src/content_job.py:38`; replay lease — `src/replay.py:33`,
  `:91`;
- no-VIN dedup — `src/domain/normalization.py:87`;
- search/model/body/confirmation — `src/search.py:12`, `:40`, `web/tma.js:44`,
  `src/web.py:540`, `:1784`, `:2020`, `:2286`;
- news TTL/MIME — `src/news_evidence.py:154`, `:275`; bounded pairing scan —
  `src/pro_news.py:130`, `:277`;
- billing membership mapping — `src/billing.py:31`; WhatsApp partial path —
  `src/whatsapp.py:70`, `src/tasks.py:117`, `src/web.py:2725`;
- CI coverage threshold — `.github/workflows/ci.yml:25`.

Live evidence получено read-only из Cloud Run revisions/jobs, Scheduler executions,
Cloud Tasks queue descriptions, Firestore aggregate reads, Gateway route probes,
Hosting assets/runtime config, IAM policies и public Telegram views. Никаких cloud,
Firestore, Telegram или GitHub mutations в ходе аудита не выполнялось.

## 6. Целевая архитектура

```text
Cloud Scheduler / manual Admin run
  -> source-specific Cloud Run Job
  -> hardened fetch + immutable raw/detail/image assets in Cloud Storage
  -> immutable listing_revision + transactional listing_current in Firestore
  -> Cloud Tasks process-listing(listing_id, content_hash)
  -> normalize + entity resolution + verification freshness
  -> verified asking-market + deterministic costs/risk/decision
  -> immutable decision + current_decision pointer
  -> idempotent Pro publication reconciler
  -> Pro outbox -> Telegram delivery -> exact sent message ID
  -> exact Free teaser derived only from sent Pro event

Telegram webhook / TMA / Admin Hosting
  -> API Gateway
  -> private Cloud Run API
  -> Firebase ID token or Telegram initData + central entitlement

News scheduler
  -> approved feeds -> immutable news evidence + source image
  -> paired Pro/Free news outbox

Admin Web
  -> Google Sign-In -> Gateway -> private Admin API
  -> source, run, listing, decision, publication, subscription and settings controls
```

### 6.1 Неизменяемые и операционные сущности

Нельзя смешивать историю с текущим состоянием:

| Неизменяемая сущность | Отдельное изменяемое состояние |
|---|---|
| `raw_snapshot` / `detail_snapshot` / `image_asset` | source cursor, lease, health |
| `listing_revision` | `listing_current`, lifecycle, last_seen |
| `verification_evidence_revision` | `verification_freshness`: last_checked, valid_until, status |
| `vehicle_identity_revision` | current identity pointer / merge review |
| `decision` | `current_decision` / retired reason |
| `publication_event` и payload | outbox delivery state/lease/attempt/provider ID |
| `news_evidence` | feed health/freshness |
| `subscription_event` | current entitlement projection |
| `migration_epoch` completed report | отдельные read-only audit runs |

Create-once операция разрешает только два результата: новый документ либо точное
совпадение уже существующего canonical payload. Любое различие под тем же ID —
integrity error и STOP, а не overwrite.

### 6.2 Обязательные state machines

- Listing: `discovered → active → stale → removed`, дополнительно `reactivated` как
  новая revision; отсутствие на одной неполной странице не означает removal.
- Evidence freshness: `active → expired → active` меняет только operational state,
  не semantic evidence ID.
- Decision pointer: `current → retired/superseded`; historical decision неизменяем.
- Outbox: `pending → sending → sent | failed | unknown | cancelled | superseded`.
  `unknown` не повторяется автоматически.
- Subscription: `pending → active → grace → expired | cancelled | refunded`.
- Migration: `planned → dry_run_complete → applying → completed | failed`; `completed`
  terminal навсегда, повторные audits живут в других документах.

## 7. Порядок реализации

Утверждение R9 разрешает выполнить R9.0–R9.11, собрать immutable candidate и провести
delivery-off staging rehearsal из R9.12 как один согласованный объём без новых
микроутверждений. Новое согласование требуется только при изменении границ/архитектуры.
Production deploy остаётся отдельным разрешением после полного R9.12 staging evidence.

### R9.0 — единая истина и release freeze

Результат: невозможно спутать код, конфигурацию и live-версию.

1. Зафиксировать machine-readable inventory API, jobs, schedulers, queues, Gateway,
   Hosting, Firestore databases/buckets и Telegram recipients.
2. Ввести schema для `release-manifest.json` и заполнить factual inventory: commit,
   schema/tool/config versions, Gateway/Hosting/job/scheduler/database IDs. Поля image
   digests на этом этапе остаются явно `not_built`; подписанный final manifest создаётся
   только после immutable build R9.12.
3. Пометить R6–R8 документы historical; README перестаёт называть систему production-ready.
4. Запретить feature work до закрытия P0; исправления идут только по R9.
5. Не останавливать текущий production на всё время разработки; его delivery меняется
   только в bounded cutover.

Gate R9.0:

- один inventory сравнивает Git, desired state и live state и показывает все drift;
- неизвестный commit/digest/config делает release gate красным;
- документация не содержит двух «текущих» планов.

### R9.1 — безопасность, окружения и Infrastructure as Code

Результат: staging физически не способен отправить сообщение production-получателю,
а браузер использует единственный поддерживаемый маршрут.

1. Отдельные Terraform stacks/variables для staging и production.
2. Cloud Run остаётся IAM-private без `allUsers`; ingress выбирается совместимым с API
   Gateway и прямыми Google service-to-service OIDC вызовами.
3. API Gateway полностью описывается IaC и содержит только browser/bot/TMA/Admin public
   application routes. Internal Cloud Tasks handlers не публикуются в Gateway.
4. Hosting runtime-config выбирает только Gateway; CSP и exact CORS origins генерируются
   из того же release config.
5. Firebase Google provider/authorized domains/Admin email allowlist проверяются browser test.
6. Internal tasks вызывают IAM-protected Cloud Run напрямую с OIDC audience/service
   account; пустые обязательные auth secrets запрещают startup.
7. Staging имеет отдельные database, bucket, queue, jobs и schedulers; delivery
   hard-disabled. Telegram/Meta provider secrets и production recipients отсутствуют,
   production chat/channel IDs присутствуют только в denylist safety config.
8. Images принимаются только `repository@sha256`; commit/digest/version не допускают
   `unknown`.
9. Firestore PITR, deletion protection, backup bucket retention/versioning и access
   prevention входят в Terraform.
10. Единый hardened outbound fetcher закрывает SSRF/redirect/DNS rebinding.

Gate R9.1:

- Terraform plan не содержит production recipients в staging;
- direct `run.app` недоступен, Gateway health/API работает;
- authenticated browser проходит все Admin routes без CORS/CSP ошибок;
- negative OIDC/Firebase/Telegram auth tests возвращают 401/403;
- no-public-access и Firestore protection подтверждены read-only queries.

### R9.2 — immutable data model и безопасная миграция

Результат: любой retry безвреден, история доказуема, current state можно восстановить.

1. Исправить G.1: completed migration не изменяется dry-run; replay request create-once.
2. Свести migration tool version в коде/config/Terraform/manifest.
3. Ввести explicit registry всех collections, nested groups и допустимых schema versions.
4. Добавить before/after counts, canonical checksums, unknown-doc sample и invariant report.
5. Разделить immutable revision и operational pointer/freshness для listings, evidence,
   identity, decisions, news и publications.
6. Все readers применяют один контракт `active + exact current snapshot + fresh evidence`;
   migration invalidation не может быть проигнорирована старым query.
7. Current pointer принимает только более новую source sequence/observed event time и
   использует deterministic tie-breaker при равенстве.
8. Добавить listing lifecycle и decision retirement.
9. Расширить outbox terminal states, immutable claimed payload, lease/attempt CAS.
10. Создать subscription event ledger, единую entitlement projection и центральный
   `EntitlementService`; все существующие bot/TMA/API/read/send пути fail-closed используют
   его до продолжения feature work. Добавить отрицательные Free/expired tests.
11. Мигратор поддерживает checkpoint/resume только до terminal completed; новый запуск —
   новый epoch, а не перезапись старого.
12. Подготовить compensating migration/restore path до build RC.

Gate R9.2:

- `apply → completed → dry-run → apply` даёт 0 writes и не меняет report/replay;
- повторные, конкурентные и out-of-order операции дают тот же итог;
- create-once mismatch останавливает операцию;
- emulator test восстанавливает current projections только из immutable history;
- unknown schema и checksum mismatch блокируют продолжение.

### R9.3 — надёжный ingestion и evidence

Результат: каждое поле карточки можно связать с сохранённым ответом источника.

1. Для каждого installed adapter: search contract, exact detail contract, parser fixtures,
   live canary, quota/backoff/circuit breaker и source health categories.
2. Архивировать search response до parsing и exact detail response до semantic validation.
3. Проверять final source domain, listing ID/path, MIME, body, currency, fixed price,
   make/model/year и расхождение search/detail.
4. Архивировать настоящее source photo в GCS с checksum; не использовать generative image.
5. Ввести distributed source lease и global/per-source request budget.
6. Сохранять last-seen coverage watermark и запускать lifecycle sweeper.
7. Daily contract canary обнаруживает schema drift до массового повреждения данных.
8. Dynamic JSON feed проходит тот же evidence contract; arbitrary HTML source не
   включается без versioned adapter/test fixtures.
9. Каждый HTTP/semantic attempt сохраняет одинаковые category, number, latency,
   `Retry-After`, archived response URI и final result; source `healthy` учитывает
   acceptance, drift, retries и rejection ratio, а не только завершение job.

Gate R9.3:

- по три последовательных live delivery-off цикла каждого источника без schema error;
- 100% выбранной audit-выборки имеет raw search, exact detail и source photo checksum;
- wrong object, redirect, private IP, POR, currency/price mismatch уходят в quarantine;
- transient retry не создаёт дубликаты или ложный сигнал.

### R9.4 — нормализация, identity и verified asking-market

Результат: отсутствие публикаций объясняется рынком, а не поломанными aliases/cohorts.

1. Versioned automotive taxonomy: make, model, generation, trim, body, year,
   specification, mileage, fuel/transmission и UAE/GCC attributes.
2. Alias dictionaries строятся из реальных quarantined samples; unknown остаётся unknown.
3. Cross-source identity использует VIN, затем безопасный weighted match; merge/split
   сохраняют audit и не склеивают неоднозначные машины.
4. Comparable cohort требует compatible model/generation/body/spec; одна физическая машина
   учитывается один раз.
5. Freshness, source diversity, mileage/year adjustment и robust outlier removal versioned.
6. UI везде называет результат `Verified asking market`, показывает число аналогов,
   sample age, lower/median/upper и ограничения.
7. Cost/risk assumptions становятся versioned scenarios с owner controls и audit.
8. Выполнить ручную adjudication выборку не менее 200 listings разных ценовых сегментов;
   измерить parse accuracy, identity precision, comparable acceptance и false positives.
9. По funnel `fetched → normalized → verified → comparable → decided → publishable`
   устранить причины массового `INSUFFICIENT_DATA`; минимальный порог аналогов не снижать
   без подтверждённой методики.

Gate R9.4:

- цена/объект/detail совпадают в 100% release audit sample;
- normalization accuracy не ниже 98% для обязательных полей audit sample;
- unsafe cross-source merges — 0; duplicate rate измерен и ограничен;
- для каждой `INSUFFICIENT_DATA` есть машинный reason и Admin drill-down;
- financial decision воспроизводится из сохранённых inputs и config version.

### R9.5 — decisions, publications и каналы

Результат: каждый реальный допустимый автомобиль появляется ровно один раз в Pro,
после чего тот же объект может появиться во Free.

1. Любое semantic/freshness/lifecycle/config изменение создаёт dependency event и
   пересчитывает affected cohort.
2. Старый current decision retire в той же транзакции, где новый pointer принимается.
3. Publisher работает event-driven и reconciliation каждые 15 минут.
4. Candidate повторно проверяется по current listing/evidence/decision/config/image.
5. Pro publication event и outbox создаются атомарно; task содержит только delivery ID,
   отправитель читает immutable stored payload; provider message ID сохраняется через CAS.
6. Free teaser создаётся только из exact Pro `sent` с теми же decision/listing/content
   IDs и неизменяемым parent; кнопка ведёт на это Pro message и отдельно на подписку.
7. Free не раскрывает цену, ссылку, ID, market, profit и ROI согласно SPEC.
8. CTA может варьироваться, но создаётся один раз из утверждённых templates либо
   source-grounded LLM и не придумывает числа/срочность.
9. Все non-current, expired, rejected и insufficient события terminalize outbox как
   `cancelled/superseded`, а не остаются pending.
10. Admin показывает полный funnel и безопасные actions: retry one, mark sent/failed,
    cancel/supersede; опасные массовые операции требуют preview.

Gate R9.5:

- property/concurrency tests доказывают at-most-once creation и controlled unknown;
- 100% Free object events имеют существующий exact Pro sent parent;
- ни один Pro field не доступен Free пользователю/API;
- один controlled delivery-off replay создаёт ожидаемые previews без Cloud Tasks;
- при отсутствии допустимых candidates результат честно равен нулю.

### R9.6 — рабочий Admin Control Center

Результат: владелец управляет продуктом в обычном браузере через Google Sign-In, а не
slash-команды Telegram.

Разделы и действия:

- Dashboard: funnel, source health, queues, eligible/current/sent, subscribers/revenue,
  SLO и активная release version;
- Sources: installed adapters, JSON feeds и Telegram candidates; test, sample, enable,
  pause, run, quarantine, delete dynamic config;
- Runs: scheduler/job execution, duration, counts, retry/error category, exact logs;
- Listings: filters, raw/detail/photo provenance, lifecycle, duplicates и quarantine;
- Decisions: inputs, comparables, assumptions, fingerprint, reasons и reproduce action;
- Publications: Pro/Free parent pair, preview, outbox state, provider IDs и reconcile;
- Users: user profile, searches, entitlement и audit без показа секретов;
- Revenue: commercial AED price, Stars billing price, active/renewal/expiry/refund counts;
- Errors: grouped actionable failures и runbook link;
- Settings: versioned business thresholds, schedules, channel/content switches и
  immutable audit; secrets только как presence/status, никогда как значения.

Gate R9.6:

- реальный authenticated Chrome smoke открывает каждый раздел и выполняет безопасные
  create/update/run/pause/preview действия в staging;
- API использует cursor pagination и exact authorization;
- browser console имеет 0 CORS/CSP/network/auth errors;
- Admin UI явно различает current live data, stale data и unavailable backend.

### R9.7 — пользовательский бот и Mini App

Результат: новый пользователь без знания команд создаёт подбор и получает только
доступные ему данные.

1. English default; поддерживаемая локаль определяется Telegram/device и может быть
   изменена в Settings.
2. Home: Find a car, Deals, Market, Favorites, My searches, Pro, News, Help.
3. Guided search и natural text проходят один parser: make/model/body, budget, year,
   mileage, spec, min profit/ROI.
4. Перед сохранением показывается подтверждение; unknown terms не активируют поиск.
5. Результаты разделены: verified market objects, eligible deals и insufficient data;
   Free не видит Pro economics.
6. Favorites/watch, price-change notifications, saved-search pause/edit/delete и outcomes
   работают через owner-scoped API.
7. Фотографии загружаются из immutable source asset; карточка показывает source/time.
8. Slash-команды остаются только совместимостью, основной путь — buttons/TMA/dialog.
9. Admin и user кабинеты физически/навигационно разделены.

Gate R9.7:

- browser/TMA и Telegram webhook E2E проходят для нового Free, active Pro, expired Pro
  и admin пользователей;
- make/model/body query создаёт точный фильтр после подтверждения;
- unsupported phrase задаёт уточняющий вопрос и не создаёт поиск;
- все owner resources изолированы; locale и фото проверены на desktop/mobile Telegram.

### R9.8 — монетизация Pro

Результат: цена управляется в Admin, доступ выдаётся и отзывается автоматически и
доказуемо.

1. Использовать уже обязательный центральный `EntitlementService` из R9.2; этот этап
   добавляет коммерческий lifecycle, но не откладывает устранение Pro leakage.
2. Commercial default — 100 AED / 30 дней. Отдельное поле Stars — фактическая цена
   Telegram purchase; UI не выдаёт Stars за фиксированный AED exchange rate.
3. Изменение цены создаёт новую config version и preview; после подтверждения backend
   создаёт новую paid subscription link и retiring/revoke старую.
4. Webhook/Telegram reconciliation пишет subscription events: purchase, renewal,
   cancellation, refund, expiry и membership mismatch.
5. Entitlement projection использует явный membership, а не только Telegram status
   `RESTRICTED`, и проверяется bot/TMA/API/delivery непосредственно перед read/send.
6. Admin показывает active, trial/grace при наличии, renewals, churn, refunds, MRR-equivalent
   в AED как коммерческую метрику и Stars receipts отдельно.
7. Free CTA ведёт сначала на актуальную purchase/subscription flow; устаревшая link version
   запрещена validator-ом.

Gate R9.8:

- staging fixtures и controlled Telegram test-user flow покрывают purchase/renew/expire/
  cancel/refund/price rotation;
- старая ссылка после ротации не выдаётся ни в одном новом payload;
- expired/refunded пользователь немедленно теряет Pro API и новые delivery;
- Admin audit связывает изменение цены с actor, old/new version и Telegram link status.

### R9.9 — новости и поддерживающий интерес чат

Результат: канал остаётся полезным между редкими сделками, но не подменяет рынок
выдуманным контентом.

1. Approved RSS/Atom/feed registry с publisher/article/image domains и freshness SLA.
2. Каждая новость содержит immutable evidence, publisher, date, canonical URL,
   source image checksum и archived asset.
3. Free и Pro получают одну evidence revision; бот и связанный чат читают её же.
4. Vertex/Gemini разрешён для краткого английского summary/CTA только из полей evidence.
   Prompt/output/fingerprint сохраняются; числа и утверждения, которых нет в evidence,
   validator блокирует.
5. При отсутствии свежего evidence система честно сообщает об этом и ничего не invent.
6. Chat отвечает на продукт, подбор, verified market и latest news через retrieval;
   непонятный вопрос уточняется либо передаётся владельцу как feedback.
7. Market Pulse строится только из verified internal aggregates и содержит период/sample.
8. `valid_until` вычисляется один раз от evidence creation/refresh без двойного TTL;
   MIME определяется по строгой сигнатуре, RIFF без WEBP marker отклоняется.

Gate R9.9:

- news card всегда имеет source-backed illustration и link;
- Free/Pro/bot/chat evidence IDs и factual fields совпадают;
- adversarial grounding tests не допускают invented fact/number;
- news/engagement не влияет на Deal Engine inputs.

### R9.10 — расширение источников и внешние доставки

Результат: покрытие рынка расширяется управляемо, а не числом неподконтрольных parser-ов.

1. Приоритизировать новые UAE marketplace/dealer feeds по объёму, fixed-price rate,
   detail stability, required fields, freshness и duplicate contribution.
2. Довести installed verified adapters/feeds минимум до 8; каждый проходит R9.3 contract,
   canary и quality score до включения в market.
3. Реализовать MTProto collector чужих публичных Telegram sources отдельно от Bot API:
   discovery, backfill sample, edits/deletes, media groups, cursor/lease и source analyzer.
4. Admin показывает parseability, fixed-price rate, mandatory-field coverage, duplicate
   rate и expected contribution; включение только вручную после sample review.
5. Telegram listing сначала `seller_stated`; verified decision возможен только после
   independent marketplace/detail evidence.
6. WhatsApp остаётся disabled до наличия Meta credentials и opt-in template/recipient;
   его отсутствие не блокирует Telegram product.

Gate R9.10:

- source count не используется как vanity metric: по каждому есть coverage contribution;
- плохой источник изолируется без остановки остальных;
- Telegram edit/delete корректно меняет lifecycle, но не переписывает history;
- WhatsApp disabled path создаёт 0 tasks и понятный Admin status.

### R9.11 — наблюдаемость, производительность и release gate

Результат: неисправность видна до жалобы пользователя.

1. Log-based metrics: fetch/detail/parse/quarantine/freshness/comparable/decision/outbox/
   Telegram/provider/auth/admin latency and failures.
2. SLO dashboards и alerts: source freshness, processing age, eligible-to-Pro latency,
   Pro-to-Free latency, queue oldest task, outbox pending/unknown, Admin availability,
   subscription reconciliation и news freshness.
3. Uptime checks для Gateway health/version и Hosting/Admin/TMA assets.
4. Budget alerts и quotas; per-source cost/requests и Vertex token budget.
5. Cursor pagination/indexes, bounded batch jobs и load tests для ожидаемого объёма.
6. Рефакторинг монолитов только после green characterization tests.
7. Python 3.11 reproducible environment, locked hashes, immutable Actions/base image,
   SBOM, vulnerability scan и release provenance.

Gate R9.11:

- overall coverage ≥85%; критические migration/state/auth/entitlement/delivery paths ≥95%;
- Firestore emulator и authenticated browser suites не skipped;
- Ruff, strict mypy, pytest, dependency audit, Terraform fmt/validate/plan, Docker,
  Trivy, JS tests и load tests green;
- deliberate source, queue, auth и Telegram faults вызывают нужный alert и recovery;
- никакой secret/PII не попадает в manifest, logs или Admin payload.

### R9.12 — immutable staging, production cutover и pilot

Этот этап начинается только после R9.0–R9.11 и не изменяет код после сборки RC.

#### Immutable candidate

1. Clean commit на текущей recovery-ветке.
2. Runtime и migration images строятся из exact git archive.
3. Digests, SBOM, test evidence и release manifest подписываются/сохраняются.
4. Любое изменение build context аннулирует candidate.

#### Полный staging rehearsal

1. Новая disposable database, bucket и queues; delivery выключена, queue paused;
   Telegram/Meta provider secrets и production recipients отсутствуют.
2. Restore production export.
3. Exact migration digest: inventory, dry-run, apply, повторный dry-run/apply no-op.
4. Exact runtime digest: full replay, lifecycle/freshness reconciliation и publishers.
5. Три цикла каждого источника, Admin Chrome, TMA, bot webhook, subscription fixtures,
   news and publication previews.
6. Staging Telegram/WhatsApp sends = 0; production recipients отсутствуют.
7. Counts/checksums/funnel/unknown/pending/failed сверены с ожидаемыми.
8. Три последовательных фактических интервала source jobs близки к 10 минутам, а
   publisher — к 15 минутам; проверяются execution timestamps, не имена Scheduler.

#### Разрешение production deploy

После успешного rehearsal владельцу предоставляется один release evidence document.
Только отдельная команда `Разрешаю production deploy R9` разрешает следующие действия.

#### Production cutover

1. Снять точный preflight inventory и включить maintenance flags.
2. Поставить publisher/delivery, processing и collectors на паузу в этом порядке;
   сохранить watermark и новый защищённый export.
3. Проверить PITR/delete protection и rollback restore.
4. Fast-forward `main` на exact RC commit без изменения дерева.
5. Deploy exact Gateway/Hosting/runtime/migration digests/config из manifest.
6. Выполнить migration и replay при `delivery=false`; reconciliation до нулевой
   необъяснимой разницы.
7. Проверить `/version` API и каждого job: один commit/runtime digest/schema/config.
8. Resume: collectors → processing → publisher. Delivery остаётся выключенной до
   проверки новых candidates/outbox preview.
9. Выполнить bounded real smoke в существующих Pro/Free каналах на одном настоящем
   eligible object/news pair, если такой candidate существует. Тестовый объект не создавать.
10. Включить delivery и schedulers; проверить provider message IDs и exact Pro→Free parent.
11. Наблюдать pilot 100–300 обработанных объявлений либо 7 дней, что наступит позже.

Если после необратимой миграции старый runtime не совместим, его нельзя возобновлять.
Разрешены только проверенный restore всего набора либо roll-forward тем же утверждённым
candidate. Частичный rollback отдельных компонентов запрещён.

## 8. Definition of Done — что означает «проект работает»

R9 завершён только когда одновременно выполнены все пункты:

1. `main`, release manifest, API, все jobs, Gateway и Hosting указывают на один
   утверждённый release; drift = 0.
2. Cloud Run private; Admin работает через Google Sign-In и Gateway, console errors = 0.
3. Firestore PITR/deletion protection/export/restore проверены.
4. Не менее 8 включённых verified adapters/feeds проходят contract canary и contribution
   gate; каждый объект имеет immutable raw/detail/photo provenance.
5. Цена в карточке совпадает с exact current detail page; POR/foreign currency/wrong page
   не публикуются.
6. Verified asking market содержит только fresh/current/verified/deduplicated comparables;
   UI показывает sample и ограничения.
7. Старые/expired/removed decisions retired; все processing/outbox записи terminal или
   имеют объяснимый active lease.
8. Каждый Pro объект настоящий, current и проходит max-purchase/profit/ROI/risk gates.
9. Каждый Free объект имеет exact уже отправленный Pro parent и не раскрывает Pro fields.
10. Если eligible objects = 0, каналы не получают выдуманных автомобилей; Admin показывает
    причины и funnel.
11. Пользователь через buttons/TMA создаёт подтверждённый поиск по make/model/body/budget/
    year/mileage/spec и получает owner-isolated результаты.
12. English работает по умолчанию; поддерживаемая device locale выбирается корректно.
13. Цена 100 AED и Stars price меняются в Admin через versioned workflow; purchase,
    renewal, expiry, cancel/refund и old-link retirement проверены.
14. News во Free/Pro имеет реальную иллюстрацию и source link; бот/чат не придумывает факты.
15. Dashboards и alerts показывают sources, funnel, queues, publications, errors,
    subscribers/revenue и release version.
16. Повтор любого job/task/migration не создаёт дубль, не меняет immutable history и не
    отправляет сообщение повторно.
17. Pilot проходит без ложной цены, Free leakage, orphan teaser, необъяснимого pending,
    автоматического retry `unknown` и несогласованной версии компонента.

Работающий технический продукт не гарантирует наличие выгодных автомобилей или платных
пользователей. Он гарантирует достоверный сбор, объяснимое решение, корректную доставку,
управление, оплату и честное отображение нулевого результата.

## 9. Артефакты, которые должны быть переданы владельцу

- утверждённый этот план и актуализированные SPEC/architecture/operations/README;
- defect traceability matrix `ID → code → test → staging evidence → release`;
- release manifest с commit/digests/configs без секретов;
- migration inventory/checksums/report и restore evidence;
- data-quality funnel и adjudication report;
- browser/TMA/bot/channel/subscription/news E2E evidence;
- production cutover/rollback protocol;
- pilot report с реальными counts, provider IDs, ошибками и остаточными ограничениями;
- инструкция владельца: Admin URL, вход Google, управление ценой, источниками, запуском,
  публикациями, пользователями и ошибками;
- инструкция пользователя: бот, Mini App, поиск, подписка, избранное и настройки.

## 10. Решение владельца

Для единого разрешения реализации всего R9 достаточно одной фразы:

```text
План R9 утверждаю
```

Она разрешает изменения кода, тесты, immutable build и delivery-off staging по этому
плану. Она не разрешает production deploy. После полного staging evidence будет нужен
только один отдельный production gate, а не новая серия микропланов.
