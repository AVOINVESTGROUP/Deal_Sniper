# План R8.1.3 — восстановление публикации автомобильных объявлений

Статус: **R8.1.3G source candidate и GitHub Actions успешны, но immutable build остановлен
до утверждения дополнения R8.1.3G.1 об идемпотентности completed migration epoch;
production не изменён**.

## 0. Статус реализации 31 июля 2026 года

Реализованы этапы R8.1.3A–R8.1.3F: исправлены десятиминутные расписания,
устойчивый разбор DubiCars, ограничение нагрузки и `Retry-After`, tiered comparable
selector, двухволновая обработка «верификация → перерасчёт рынка», отдельный
идемпотентный publisher каждые 15 минут и наблюдаемая воронка Admin Web.

Admin Web обращается непосредственно к Cloud Run API с Firebase ID token и загружает
разделы с ограниченной параллельностью, чтобы один временно недоступный endpoint не
обрушал всю панель. Google-вход включён в hosting runtime configuration.

Финальный локальный gate: Ruff, strict mypy, 153 passed / 2 skipped, coverage 62,44%,
dependency audit, Terraform, JavaScript и Docker успешны. Commit `925597043f35` прошёл
оба GitHub Actions запуска; Cloud Build создал immutable digest `sha256:48ddd19e…22323`.
Три delivery-off staging-цикла каждого из четырёх источников завершились `12/12`
успешно в отдельной database/bucket/PAUSED queue. Production deploy, replay и
Telegram-доставка требуют отдельного разрешения владельца.

## 1. Подтверждённая проблема

29 июля 2026 года выполнена read-only проверка production-конвейера от сборщиков до двух Telegram-каналов.

Доставка в Telegram не является главным дефектом. Очередь `telegram-delivery` работает, ранее созданные сообщения имеют состояние `sent`, а последняя доказанная пара одного автомобиля существует в обоих каналах: сначала полная Pro-карточка, затем связанный с ней Free-анонс.

Главная причина отсутствия новых публикаций — конвейер почти не создаёт новых допустимых кандидатов:

| Показатель production | Значение |
|---|---:|
| Актуальные решения | 1 690 |
| `INSUFFICIENT_DATA` | 1 608 |
| `REJECT` | 81 |
| `INSPECT` | 1 |
| `CONTACT` | 0 |
| Решения с рассчитанным рынком | 82 |
| Допустимые Pro-кандидаты | 1 |

Цифры повторно подтверждены read-only аудитом 30 июля 2026 года после R8.1.2.1. Единственный
допустимый кандидат `opensooq:284587230` уже опубликован в Pro как Telegram message ID `35`.
Его стабильный delivery `25e83ef6…08155` имеет terminal-состояние `sent`. Идемпотентность
правильно запрещает отправлять его повторно, поэтому новый запуск publisher создаёт `0`
автомобильных карточек.

Дополнительно подтверждены шесть дефектов:

1. Расписания `0/10`, `2/10`, `4/10` и `6/10` выполняются Cloud Scheduler один раз в час, а не каждые 10 минут.
2. Структура JSON-LD DubiCars изменилась: часть карточек не содержит ожидаемого `offers`, из-за чего возникают `KeyError`.
3. Detail-page verification новых DubiCars объявлений получает `ReadTimeout`; обработка корректно прекращается fail-closed, но объявления не доходят до решения.
4. Полные Pro-карточки сверяются только плановым publisher раз в шесть часов. Даже новый допустимый объект может ждать публикации до следующего запуска.
5. Все четыре production collector jobs используют старый image
   `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`, тогда как API и
   publishers R8.1.2.1 работают на `sha256:b6a2e5cb…de75f4`. Сквозной runtime не является
   единым immutable release.
6. За последние два часа processing зарегистрировал 136 временных отказов detail verification
   с HTTP `429`. Повторы происходят, но без source-aware ограничения скорости и не приводят к
   новым решениям.

Последний часовой цикл при этом действительно получил реальные данные: DubiCars — 143 записи,
19 новых и 2 изменения; CarSwitch — 120; Cars24 — 125; OpenSooq — 141, включая одну новую и
одно изменение. Отсутствие публикаций вызвано не пустыми источниками и не Telegram, а потерей
объектов на verification/market/decision gates.

## 2. Непереговорные правила

1. Не публиковать выдуманные автомобили, цены, характеристики, новости, рыночные диапазоны или прибыль.
2. LLM не рассчитывает цену, рынок, расходы, прибыль, ROI и решение.
3. Не снижать `TARGET_PROFIT_AED`, `MIN_ROI_PERCENT` и минимальную цену ради искусственного наполнения каналов.
4. Объект Free-канала существует только после состояния `sent` полной карточки **того же автомобиля и той же semantic revision** в Pro-канале.
5. Кнопка `Open this exact car in Pro` ведёт на точное Pro-сообщение этого автомобиля, а не на общий канал.
6. Ошибка источника или отсутствие аналогов дают явное состояние ошибки/недостаточности, но не подменяются mock-данными.
7. Повторный запуск не создаёт дубликаты публикаций.
8. В scope входят только автомобили с фиксированной подтверждённой ценой; аукционы и недвижимость исключены.

## 3. Целевой production-поток

```text
4 независимых scheduler каждые 10 минут
    -> collector source adapter
    -> raw snapshot + detail evidence
    -> normalize + cross-source identity
    -> tiered deterministic comparable selection
    -> market / costs / risks / decision
    -> eligible publication event
    -> exact full card in Pro
    -> confirmed Telegram message_id
    -> exact linked teaser in Free

scheduled reconciler каждые 15 минут
    -> восстанавливает только пропущенные idempotent deliveries
```

## 4. Этапы реализации

### R8.1.3A — починить фактическую частоту сбора

- собрать один новый immutable release image и развернуть **тот же digest** в API, всех четырёх
  collectors, processing handlers и publishers; смешанные runtime digests блокируют staging и
  production resume;
- заменить неоднозначные cron-выражения на явные минуты:
  - DubiCars: `0,10,20,30,40,50 * * * *`;
  - CarSwitch: `2,12,22,32,42,52 * * * *`;
  - Cars24: `4,14,24,34,44,54 * * * *`;
  - OpenSooq: `6,16,26,36,46,56 * * * *`;
- показывать в Admin Web не только статус scheduler, но и `last run`, `next run`, фактический интервал, fetched/new/changed/error;
- сигнализировать, если фактический интервал превышает 15 минут.

### R8.1.3B — восстановить адаптеры и detail verification

- адаптер DubiCars должен поддерживать текущие допустимые варианты JSON-LD без обращения к обязательному `offers`;
- цена принимается только из явно распознанного fixed-price поля; `Price on request`, рассрочка, месячный платёж и placeholder отклоняются;
- добавить source-aware rate limiter, ограничение concurrency и bounded retry с `Retry-After`,
  backoff и jitter для `429`, timeout и временных detail-page ошибок;
- запретить одновременный retry storm одной и той же source/detail revision; task ID и
  verification key остаются стабильными;
- сохранять категорию ошибки: schema drift, timeout, blocked, missing price, invalid vehicle;
- добавить contract fixtures для всех четырёх источников и тесты на изменение схемы;
- ошибка одной карточки не прерывает обработку остальных карточек источника.

### R8.1.3C — увеличить доказуемое покрытие рынка

Текущий поиск читает только точное `make|model`, после чего одновременно требует год ±2, пробег ±50 000 км, совместимые generation/specification/trim, свежесть 14 дней и минимум аналогов. В production это оставляет рынок только для 65 из 1 643 решений.

Новый детерминированный selector вводит версионируемые уровни:

1. точные make/model/generation/specification/trim;
2. make/model/generation с поправками за год, пробег, specification и тип продавца;
3. make/model с годом ±2 только при достаточном числе независимых автомобилей и ограниченной дисперсии.

Для каждого аналога сохраняются source evidence, причина включения, все поправки и уровень когорты. Межсайтовые дубли считаются одним автомобилем. Если после robust outlier filter доказательств недостаточно, результат остаётся `INSUFFICIENT_DATA`.

После изменения selector/normalization создаются новые версии engine и adjustment policy. Все 1 643 текущих подтверждённых snapshots переоцениваются идемпотентным bounded replay; старые решения не переписываются.

### R8.1.3D — публикация сразу после нового решения

- после сохранения нового допустимого `CONTACT`/`INSPECT` решения создавать стабильный Pro publication event и задачу доставки;
- после подтверждённого Pro `sent` создавать Free teaser для той же revision;
- publisher job оставить как reconciliation/backstop и запускать каждые 15 минут, а не раз в шесть часов;
- terminal `sent` не переотправлять; `pending` безопасно восстанавливать; `unknown` и `failed` оставлять для явной reconciliation;
- новости остаются отдельным типом контента и не могут считаться автомобильной публикацией.

### R8.1.3E — понятное управление в Admin Web

Добавить раздел `Listing pipeline`:

- воронка `fetched -> verified -> normalized -> market -> decision -> Pro sent -> Free sent`;
- распределение решений и причин `INSUFFICIENT_DATA`/`REJECT`;
- список текущих допустимых кандидатов и уже опубликованных revision;
- ошибки источников с понятной категорией, временем и числом повторов;
- кнопки `Run collector`, `Run reconciliation`, `Retry temporary failures` с аудитом;
- запрет ручной публикации решения, не прошедшего финансовые и evidence-фильтры.

## 5. Проверка и выпуск

1. Unit/contract/integration tests для адаптеров, уровней аналогов, outlier filter, event IDs и exact Pro→Free linkage.
2. Полный локальный quality gate и GitHub Actions.
3. Immutable image из утверждённого commit.
4. Delivery-off staging: реальные read-only страницы источников, отдельная база и очередь, никакой отправки в Telegram.
5. Dry-run replay текущих данных с отчётом `до/после` по каждому gate: fetched, detail verified,
   normalized, market, decision, eligible. Владелец проверяет выборку аналогов и расчётов.
6. После отдельного разрешения production deploy — тот же digest, bounded replay, затем staged resume collectors → processing → Pro delivery → Free delivery.
7. Smoke выполняется в существующих production-каналах только на новом реальном допустимом объекте. Дополнительный тестовый канал не создаётся.

## 6. Критерии приёмки

- каждый источник действительно запускается шесть раз в час;
- API, collectors, processing и publishers показывают один утверждённый commit и один immutable
  image digest;
- три последовательных цикла каждого источника проходят без необработанного schema exception;
- три последовательных цикла не создают retry storm: `429` либо восстанавливается в bounded
  budget, либо получает наблюдаемое terminal processing outcome;
- временный timeout либо восстанавливается retry, либо виден как отдельная ошибка и не создаёт решение;
- все новые/изменённые объявления получают terminal processing outcome;
- отчёт replay показывает причины результата для каждого объекта и полный список использованных аналогов;
- новый допустимый объект ставится в Pro delivery не позднее пяти минут после решения;
- Free teaser появляется только после Pro `sent` и ведёт на exact Pro message;
- для каждой Free-карточки существует соответствующая Pro-карточка, а для каждой новой Pro object-card создаётся соответствующая Free-карточка;
- ни один `REJECT`, `INSUFFICIENT_DATA`, placeholder или объект выше допустимой цены покупки не публикуется как сделка;
- повторный collector, replay, publisher и delivery не создают дублей;
- Admin Web объясняет отсутствие публикаций конкретным числом на каждом gate, а не пустым экраном.

Количество реальных выгодных автомобилей заранее не фиксируется: система не имеет права создавать публикации при отсутствии доказуемых сделок. Частота контента увеличивается за счёт корректного сбора, нормализации и сопоставления реальных данных, а не за счёт ослабления достоверности.

## 7. Граница разрешения

Утверждение этого документа разрешает реализацию кода и delivery-off staging R8.1.3. Оно **не разрешает production deploy, bounded replay production или отправку новых Telegram-сообщений**. Для них после staging evidence требуется отдельная явная команда владельца.

## 8. Дополнение R8.1.3F — семантически пустой HTTP 200 CarSwitch

### Подтверждённый диагноз

31 июля 2026 immutable staging digest
`sha256:4ecc211ff5d5e32f3ba58610a77775249ea80200276f737ee6fd0b5ca2188d22`
прошёл первый реальный цикл всех четырёх источников. Во втором цикле DubiCars, Cars24
и OpenSooq завершились успешно, а CarSwitch execution
`deal-sniper-rehearsal-carswitch-staging-qnd8s` завершился ошибкой отсутствующего
`ItemList`.

Это не даёт права ослабить parser. Raw evidence содержит HTTP-ответ CarSwitch с SHA-256
пустого тела `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
и размером `0` байт. Текущий `_get_with_retry` повторяет timeout, network error и
допустимые HTTP-коды, но возвращает пустой HTTP 200 как успешный результат. Ошибка
структуры возникает позже в `parse_carswitch_page` и поэтому обходит bounded retry.

### Граница исправления

1. CarSwitch обязан считать пустое тело, неподходящий content type и отсутствие
   распознаваемого `ItemList` семантически неуспешной попыткой получения страницы.
2. Каждая такая попытка сохраняется как raw evidence, но не создаёт listing, market,
   decision или публикацию.
3. Семантический transient получает тот же bounded budget: не более трёх попыток с
   backoff. Если следующая попытка возвращает валидный `ItemList`, цикл продолжается.
4. После исчерпания бюджета source run получает наблюдаемую terminal-категорию
   `semantic_empty_response`; старые данные не выдаются за свежий результат.
5. Parser не принимает placeholder, request-price или данные, отсутствующие в
   фактическом ответе.

### Тесты и повтор релизного gate

- unit: `empty HTTP 200 -> valid ItemList` восстанавливается ровно в пределах budget;
- unit: три пустых HTTP 200 завершаются `semantic_empty_response` без snapshots и решений;
- regression: валидный CarSwitch ItemList остаётся совместимым;
- полный локальный gate, GitHub Actions и новый immutable commit-labelled digest;
- заново выполнить три последовательных delivery-off staging-цикла 4/4 источников;
- staging Telegram queue всё время остаётся `PAUSED`, `DELIVERY_ENABLED=false`;
- digest `sha256:4ecc211f…8d22` после изменения кода не может продвигаться в production.

Это дополнение изменяет код и поэтому требует отдельного явного утверждения владельца.
Production deploy по-прежнему требует ещё одного отдельного разрешения только после
успешного повторного staging evidence.

### Статус реализации R8.1.3F — 31 июля 2026

Дополнение утверждено владельцем и реализовано. CarSwitch проверяет нормализованный MIME
(`text/html` или `application/xhtml+xml`), непустое тело и распознаваемый `ItemList`
внутри общего трёхпопыточного retry. Повторяется только специальная семантическая ошибка
CarSwitch; постоянные ошибки будущего parser-контракта не маскируются как transient.

Каждый HTTP 200 перед проверкой передаётся в immutable raw archive. Payload-объект остаётся
content-addressed и одинаковые тела могут физически разделять один объект по checksum, но
**каждый вызов** обязан дополнительно создавать отдельное append-only событие
`raw_snapshot_attempt`. Событие содержит номер попытки, `fetched_at`, source URL, checksum,
storage URI, content type и размер. Поэтому три одинаковых пустых ответа имеют один
неизменяемый payload и три различимых capture-события. Итоговые `attempts` и
`error_category=semantic_empty_response` дополнительно сохраняются в source health и
показываются в Admin Sources и Runs. При исчерпании budget snapshots и decisions не
создаются.

Append-only capture-события реализованы без изменения schema version: используется
существующий audit trail, а content-addressed payload сохраняет прежний immutable URI.
Regression-тест подтверждает один физический пустой payload и три события с номерами 1–3.
Полный повторный локальный gate успешен: Ruff, strict mypy по 42 source-файлам,
`153 passed / 2 skipped`, coverage `62,44%`, dependency audit без известных уязвимостей,
Terraform fmt/init/validate, JavaScript ES-module syntax и Docker Python 3.11 runtime/import
без `pip`, `setuptools` и `wheel`. Далее разрешены commit, GitHub Actions, новый
commit-labelled immutable digest и повтор трёх delivery-off staging-циклов 4/4 источников.

### Статус staging R8.1.3F — 31 июля 2026

Commit `925597043f3596c1296723a668337dc474e8495a` прошёл оба GitHub Actions запуска.
Cloud Build `44381975-eca8-4165-b692-a3452fcfab7a` создал immutable digest
`sha256:48ddd19e9f0abe8a93240045f0d51e9dbfb283a32d7265ddaf06df026be22323`.

Staging использует отдельный защищённый raw bucket, отдельную Firestore database и PAUSED
пустую Telegram queue. API и пять jobs прошли read-back commit/digest/environment; delivery и
WhatsApp выключены, Telegram secrets отсутствуют. Три последовательных цикла четырёх реальных
источников завершились `12/12` успешно. Два publisher rehearsal не создали задач или
публикаций при отсутствии новой допустимой revision. Это корректный fail-closed результат,
а не основание создавать демонстрационный объект.

Production revision/digest, job specs/generations, Scheduler и очереди по нормализованному
снимку до/после не изменились. Полное evidence зафиксировано в
`docs/RELEASE_EVIDENCE_2026-07-31-R8_1_3.md`. Реализация и staging завершены; production deploy,
bounded replay и Telegram smoke всё ещё требуют отдельной явной команды владельца.

## 9. Дополнение R8.1.3G — совместимость migration dry-run с PublicationEvent v3

### Подтверждённый диагноз

После разрешения production deploy повторный сквозной preflight обнаружил, что старый
набор `migration_replay_requests` не покрывает текущие revisions. В production существуют
`4 179` текущих revisions, а старый набор может реально обработать только `2 326`; все
`1 757` current decisions используют engine `3.1.0`, тогда как R8.1.3 требует `3.2.0`.
Поэтому новый migration epoch и полный delivery-off replay обязательны, а не являются
оптимизацией.

Exact staging migration dry-run на digest `sha256:48ddd19e…22323` корректно остановился до
apply: одиннадцать уже существующих `publication_events` имеют актуальный контракт
`publication-event/v3`, но `KNOWN_SCHEMA_VERSIONS` migration tool `1.2.0` явно знает только
`publication-event/v1` и общий суффикс `/v2`. При этом production writer в
`src/firestore_storage.py` сам сохраняет `publication-event/v3`. Таким образом, это
несогласованность allowlist мигратора с фактическим неизменяемым контрактом, а не
неизвестные или повреждённые данные.

Отдельный read-only аудит production подтвердил `177` publication events:
`48` с `publication-event/v1` и `129` с `publication-event/v3`. Полный проход по всем
коллекциям migrator и вложенным snapshots не нашёл других неизвестных schema versions.
Следовательно, граница исправления точная и не требует общего ослабления schema gate.

Production не изменён: schedulers, queues, API/jobs, Firestore и Telegram остались на
предыдущем baseline. Неуспешный dry-run был только в изолированной staging database и не
выполнял apply.

### Граница исправления

1. Явно добавить `publication-event/v3` в `KNOWN_SCHEMA_VERSIONS`; не вводить общий допуск
   произвольных `/v3` и не ослаблять fail-closed проверку будущих контрактов.
2. Исправить generic top-level upgrade: он обновляет в schema `2` только legacy документы
   со значением `None` или `"1"`. Любой уже валидированный native contract, включая
   `verification-evidence/v1`, `saved-search/v1`, `outcome/v1`,
   `publication-event/v1`, `publication-event/v3`, `audit-event/v1`,
   `migration-replay-request/v1` и контракты `/v2`, сохраняется без write. Validation
   выполняется раньше и продолжает блокировать любой неизвестный контракт.
3. Поднять `MIGRATION_TOOL_VERSION` с `1.2.0` до `1.2.1`, чтобы provenance и migration ID
   однозначно связывались с исправленным allowlist.
4. Не менять структуру `PublicationEvent`, схему Firestore, финансовые расчёты, parser,
   delivery, публикации или существующие immutable события.
5. Не создавать replay-запросы ручным скриптом. Их формирует только утверждённый migration
   apply с новым `cutover_at` и `export_watermark`.

### Тесты и релизный порядок

1. Regression-тест подтверждает, что `publication-event/v3` принят, а произвольный
   `publication-event/v4` и неизвестный `/v3` по-прежнему блокируются. Apply-тест с fake
   Firestore batch доказывает отсутствие write для всех валидированных native contracts и
   наличие write только для legacy `None`/`"1"`.
2. Повторить полный локальный gate и GitHub Actions; собрать новый commit-labelled immutable
   digest. Старый digest `sha256:48ddd19e…22323` после изменения кода не продвигается.
3. Перед staging apply создать новый staging export. На отдельной database выполнить exact
   migration dry-run, затем apply с tool `1.2.1` и новым watermark.
4. Проверить новый replay epoch: один request на каждую текущую revision. Выполнить bounded
   direct replay, полный catch-up и второй controlled recalculation при
   `DELIVERY_ENABLED=false`.
5. Повторить delivery-off publisher rehearsal; staging Telegram queue остаётся `PAUSED`,
   задач и реальных исходящих сообщений нет.
6. Только после нового staging evidence запросить отдельное разрешение владельца на
   production deploy нового digest. Предыдущее разрешение относилось к digest
   `sha256:48ddd19e…22323` и не разрешает изменённый build.
7. Production cutover остаётся прежним: STOP → свежий защищённый export → exact migration
   dry-run/apply → полный replay/reconciliation при выключенной delivery → merge exact RC →
   deploy/read-back → staged resume collectors → processing → Pro → exact linked Free.

### Rollback

- до production никакого rollback не требуется: текущий production baseline не меняется;
- staging apply выполняется только на disposable database, восстановленной из export; при
  ошибке эта database не восстанавливается import поверх себя, а отбрасывается и создаётся
  заново из исходного export;
- Firestore import имеет merge-семантику и не является in-place rollback частично
  выполненных apply/invalidation/replay writes;
- при production-инциденте schedulers/queues немедленно останавливаются, delivery остаётся
  выключенной. Предыдущий runtime digest допускается только как maintenance rollback;
  production resume запрещён до подтверждённой компенсирующей миграции или rollback-reader
  процедуры и полной сверки с защищённым export и migration ledger. `unknown` delivery
  автоматически не повторяется.

### Статус реализации R8.1.3G — 31 июля 2026

Владелец явно утвердил план. Реализована только согласованная граница:

- `publication-event/v3` добавлен в точный allowlist без общего допуска `/v3`;
- generic top-level migration пишет только legacy `None` и строку `"1"`;
- валидированные native v1/v2/v3 остаются без write;
- migration tool и provenance подняты до `1.2.1`.

Regression-тесты проходят через реальный validation path, отдельно доказывают блокировку
неизвестных v3/v4 и используют commit-aware fake batch в двух коллекциях. Проверены точные
пути трёх legacy writes, `merge=true`, schema `"2"`, tool `1.2.1`, два commit и нулевые
writes для native contracts.

Полный локальный gate успешен: Ruff, strict mypy по 42 source-файлам,
`156 passed / 2 skipped`, coverage `63%`, dependency audit без известных уязвимостей,
Terraform fmt/init/validate, JavaScript ES-module syntax, Docker Python 3.11 import и
отсутствие `pip`, `setuptools`, `wheel` в runtime. Внутри локального образа подтверждён
`MIGRATION_TOOL_VERSION=1.2.1`. Локальный Trivy отсутствует; блокирующий container scan
остаётся обязательным GitHub Actions gate.

Следующий разрешённый этап: commit, GitHub Actions, новый commit-labelled immutable digest
и полный migration/replay rehearsal только на disposable staging clone при выключенной
delivery. Старый digest `sha256:48ddd19e…22323` не продвигается. Production не изменён;
предыдущее разрешение deploy не распространяется на новый digest.

## 10. Дополнение R8.1.3G.1 — completed migration epoch нельзя открывать повторно

### Подтверждённый диагноз

Финальный review перед immutable build обнаружил отдельный safety-дефект в
`FirestoreMigrator.run`. Existing ledger со статусом `completed` возвращается без действий
только для повторного apply. Повторный `--dry-run` с теми же `cutover_at` и watermark
создаёт тот же migration ID, но продолжает выполнение и в `_finish` перезаписывает ledger
статусом `dry_run_complete`. Следующий apply больше не видит completed epoch, повторно
инвалидирует derived state и `merge=false` возвращает replay requests этого epoch в
`pending`.

Это противоречит контракту класса «повторный запуск безопасен», требованию SPEC об
идемпотентных Jobs и неизменяемости завершённого migration ledger. Ошибка обнаружена
локально при read-only review. После commit `d881224` GitHub Actions полностью зелёные,
но immutable build намеренно не запускался; staging и production не изменены.

### Граница исправления

1. Для existing ledger со статусом `completed` немедленно возвращать сохранённый
   `MigrationReport` независимо от запрошенного режима dry-run/apply.
2. Не выполнять inventory, validation, writes, invalidation, replay preparation или
   `_finish` для завершённого epoch.
3. Новый `cutover_at` или watermark по-прежнему создаёт новый migration ID и проходит
   полный dry-run/apply; общий schema gate не ослабляется.
4. `MIGRATION_TOOL_VERSION` остаётся `1.2.1`: версия ещё не была собрана в immutable image
   и не проходила staging; исправление войдёт в единственный новый source candidate.
5. Не менять финансовые engines, publication contracts, replay semantics, delivery или
   production configuration.

### Тесты, риски и релизный порядок

1. Regression-тест выполняет оба повторных режима после completed ledger и доказывает
   возврат сохранённого отчёта без batch commit, ledger write и открытия epoch.
2. Снова выполнить полный local gate и GitHub Actions. Commit `d881224` не собирать и не
   продвигать; создать новый commit-labelled digest только из исправленного source commit.
3. Staging runbook сохраняется, но после apply дополнительно выполняется safe repeat-read
   того же completed epoch и проверяется, что ledger, request states и attempts не изменены.
4. Далее выполнить только disposable-clone delivery-off migration/replay rehearsal,
   описанный в R8.1.3G. Production по-прежнему требует нового отдельного разрешения после
   полного evidence.

Риск возврата сохранённого отчёта приемлем: completed epoch является неизменяемым фактом.
Для проверки нового среза оператор обязан использовать новый watermark/cutover, который
даёт новый migration ID. Мутаций и миграции данных это дополнение не требует.

Код дополнения запрещён до отдельного явного утверждения владельцем:
`Дополнение R8.1.3G.1 утверждаю`.
