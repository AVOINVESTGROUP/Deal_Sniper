# Проверка кандидата `1ce36ff` и корректирующий план R6

Статус: **утверждён владельцем 27 июля 2026; R6.7 разрешён, но production cutover
остановлен на обязательном Chrome gate; готовится новый RC**.

## 1. Проверенный контур

Проверены `SPEC.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/CLOUD_ARCHITECTURE.md`, `docs/OPERATIONS.md`, `README.md`, `AI_CONTEXT.md`, `firebase.json`, API Gateway OpenAPI, Admin Web, Firebase authentication, CORS middleware, publication/outbox identity, Free/Pro renderers, content Job, SQLite/Firestore repositories и тесты кандидата.

Production доступен на commit `12bdee56c6b299132f55d1afedc0d25e4918ac82` и runtime digest `sha256:561814a852339e454dca7a362d41bc68e27ffe3359fc02e5eedbe6a31597aa3e`. Кандидат `1ce36ff` находится в GitHub, но не развёрнут.

## 2. Блокеры кандидата

### B1. Исправление Admin Web не устанавливает причину отказа

`retry`, обновление ID token и `Promise.allSettled` улучшают поведение при временном отказе, но не доказывают исправление наблюдаемого `Failed to fetch`. Тест проверяет наличие строк в JavaScript, а не реальный браузерный путь.

До изменения нужны воспроизводимые результаты для каждого запроса Admin:

```text
Firebase sign-in
  -> Firebase ID token
  -> browser preflight OPTIONS
  -> API Gateway
  -> X-Forwarded-Authorization
  -> backend Firebase verification
  -> response CORS headers
```

Матрица обязана покрывать `200`, `401`, `403`, `429`, `5xx`, expired token, preflight и частичный отказ одного раздела. Причина должна быть привязана к конкретному слою и trace ID.

### B2. Firebase Hosting содержит противоречивые маршруты

Архитектура и runtime-config требуют Gateway-only browser path, но `firebase.json` продолжает объявлять rewrites `/admin/**`, `/tma/**`, `/content/**`, `/version` и `/health` в приватный Cloud Run. Эти rewrites уже давали `403` и не должны сосуществовать с заявленным контрактом без явного назначения и теста.

### B3. Free Market Watch раскрывает запрещённые данные

`SPEC.md` запрещает Free teaser раскрывать цену, ссылку, ID, рынок, прибыль и ROI. `format_market_watch_card` публикует цену, verified market и прямую ссылку. Добавление CTA к такому сообщению закрепляет утечку вместо её устранения.

Должен существовать один Free renderer/validator. Любой автомобильный target Free проходит автоматическую проверку отсутствия запрещённых полей до создания outbox.

### B4. Immutable PublicationEvent несовместим с CTA upgrade

`publication_event_id` не содержит template version. Существующая запись создаётся через Firestore `create` либо SQLite `INSERT OR IGNORE`. При повторной обработке прежнего decision/event ID новые CTA-поля не сохраняются, хотя outbox нового шаблона может быть создан. Возникает несогласованность immutable event и доставки.

До кода требуется выбрать и зафиксировать один вариант:

1. новый event type/version участвует в identity; либо
2. создаётся отдельный immutable CTA/publication revision с родительским subject event.

Изменять существующий immutable event запрещено.

### B5. PublicationEvent, CTA assignment и outbox не имеют доказанного атомарного контракта

Текущий allocator, сохранение события и запись outbox выполняются отдельными операциями. Нужно определить допустимые crash points, идемпотентное восстановление и reconciliation. Тест обязан симулировать сбой после каждого шага и доказать, что retry не меняет CTA и не создаёт публикацию без кнопки.

### B6. Проверки недостаточны для разрешения релиза

71 unit-тест не включает:

- браузерный Firebase/Gateway/CORS smoke;
- Firestore emulator/integration для конкурентной CTA-ротации;
- upgrade старых publication events;
- 100% Free-target leakage test;
- Telegram caption/button contract;
- staging replay и живую публикацию 30 последовательных CTA.

### B7. Релизный процесс не пройден

Прямой Hosting или Cloud Run deploy запрещён. Требуются clean commit, Python 3.11 gate, audit/scan, один immutable runtime digest, staging rehearsal, evidence и только затем exact-digest production deploy.

## 3. Исправленный контракт

1. Free vehicle publication содержит только безопасный teaser, CTA и прямую Pro-кнопку.
2. Pro publication сохраняет полный audit trail.
3. Любой Free renderer проходит общий leakage validator до outbox.
4. CTA revision является immutable и однозначно связана с конкретной publication revision.
5. CTA assignment, publication payload и outbox восстанавливаются идемпотентно после любого допустимого сбоя.
6. Невалидная подписная ссылка блокирует только Free target и создаёт наблюдаемую операционную ошибку; она не создаёт ложный `sent` или неполный event.
7. Admin Web использует один документированный browser path. Ошибки каждого слоя диагностируются отдельно и отображаются без технического дампа пользователю.
8. Production не меняется до полного R6 evidence.

## 4. Последовательность реализации после утверждения

### R6.1 — identity и migration contract

- утвердить identity новой publication/CTA revision;
- описать совместимость существующих `publication_events` и outbox;
- добавить golden vectors и crash/retry сценарии;
- определить, требуется ли migration ledger или достаточно новых immutable revisions.

### R6.2 — единый Free policy

- выделить общий Free renderer и leakage validator;
- исключить цену, рынок, ссылку, ID, прибыль и ROI из Market Watch Free;
- запретить обход валидатора любым channel/content path;
- сохранить полные данные только в Pro и персональном разрешённом контуре.

### R6.3 — CTA publication transaction

- создать CTA revision по утверждённой identity;
- резервировать вариант без повторов полного цикла;
- сохранять CTA и outbox с доказанной идемпотентностью;
- передавать одну inline-кнопку из серверной subscription URL;
- сохранить стабильность payload при retry/reconcile.

### R6.4 — Admin root-cause fix

- воспроизвести отказ в обычном Chrome с trace/network evidence;
- проверить Hosting CSP и исключить неиспользуемые rewrites;
- проверить preflight и ответы Gateway для всех Admin endpoints;
- исправить только подтверждённый слой;
- сохранить частичный рендер как UX-защиту, но не считать его root-cause fix.

### R6.5 — обязательные проверки

- Ruff, mypy, pytest/coverage, pip-audit;
- Python 3.11 container build;
- Firestore integration/emulator и конкурентная ротация;
- browser test Firebase login → все Admin endpoints;
- CORS/CSP negative matrix;
- Free leakage test для каждого target/template;
- 30 CTA без соседних повторов, 100% кнопок, стабильный retry.

### R6.6 — staging

- clean RC commit и immutable digest;
- staging с `DELIVERY_ENABLED=false`;
- replay старых и новых publication scenarios;
- Admin browser smoke;
- Telegram payload preview без реальной доставки;
- release evidence с commit, digest, counts и результатами.

### R6.7 — production

- отдельное разрешение владельца;
- deploy exact staging digest и Hosting version;
- `/version` подтверждает commit/digest/schema;
- staged resume согласно `docs/OPERATIONS.md`;
- пилот 30 Free CTA и 100–300 объявлений;
- ноль утечек Free, пропущенных кнопок, дублей и автоматических retry для `unknown`.

## 5. Критерий утверждения плана

Владелец явно подтверждает этот документ. Только после этого разрешён R6.1. Любое изменение контракта identity, Free/Pro данных, Admin transport или release sequence возвращает работу на стадию документации и повторного утверждения.

## 6. Текущее выполнение

После явного сообщения владельца «План R6 утверждаю» реализован локальный кандидат
R6.1–R6.4:

- новая immutable publication revision включает subject, recipient, event type и template;
- старые subject events сохраняются как parent и не переписываются;
- PublicationEvent и outbox фиксируются одной транзакцией в SQLite и Firestore;
- повторная обработка возвращает тот же payload и тот же CTA, а противоречивое частичное
  состояние блокируется;
- все автомобильные Free-пути используют общий teaser и leakage validator;
- legacy publisher больше не подменяет отсутствующий Pro-канал бесплатным каналом;
- Firebase Hosting использует только Gateway browser path без конфликтующих rewrites;
- Admin Web отдельно сообщает об истёкшей Firebase-сессии и сохраняет частичный рендер.

Локальный gate: Ruff, mypy, 80 pytest, coverage 56%, pip-audit без известных
уязвимостей, Terraform fmt/validate успешно. GitHub Actions для кандидата `f1bd8fd`
подтвердил Python 3.11, повторный quality gate, Docker build и Trivy без блокирующих
HIGH/CRITICAL. Firestore integration, browser smoke и staging rehearsal относятся к
незавершённым R6.5–R6.6. Реальный integration-тест в named database
`deal-sniper-stage-rc2` выявил contention при стандартных пяти попытках Firestore
transaction; publication/CTA retry budget адресно повышен до 20. Повторный тест с 12
конкурентными reservations, атомарным event+outbox, стабильным retry и очисткой test IDs
прошёл успешно. Незавершёнными остаются browser smoke и staging rehearsal. Production
остаётся на прежнем digest.

Authenticated browser smoke затем выполнен в headless Chrome через отдельный staging
API Gateway: `/admin/overview`, `/content/market-pulse`, `/admin/preview` и два состояния
`/admin/outbox` вернули 200 при настоящем browser CORS с Hosting-origin. Live CSP ожидаемо
блокировал незаявленный staging hostname; тестовый route добавлял его только в изолированный
ответ Chrome, не меняя production Hosting. R6.5 завершён.

Финальный R6.6 выполнен на чистом RC commit
`2a42735d57af6e3549af1d5fa0a975cee120a76f`. GitHub Actions `30278152829` успешен;
commit-labelled image имеет digest
`sha256:abd5cf8b368e2fffa5cc9fc70023ac68baf4572202942634092dc61bef145d8a` и развёрнут
только в staging revision `deal-sniper-api-staging-00020-mgd`. Конфигурация использует
`deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false`, `WHATSAPP_ENABLED=false`; `/health` и
`/version` успешны. Повторный реальный Firestore integration и authenticated browser smoke
прошли. Telegram payload проверен через Admin preview без фактической доставки. Production
остаётся на прежнем commit/digest до отдельного разрешения владельца на R6.7.

После отдельного разрешения R6.7 был выполнен STOP и защищённый Firestore export. RC
`2a42735` развёрнут с delivery off, Hosting опубликован, collector и processing smoke
успешны. Production Chrome gate обнаружил `504` только у `/admin/overview`, поэтому
delivery и content не возобновлялись. Диагностика доказала production-only bottleneck:
последовательные Cloud API waits и потоковое чтение Firestore counts превышали Gateway
deadline. Исправление ограничено этим слоем: Cloud status и агрегаты выполняются
параллельно, dashboard counts используют Firestore aggregation. Изменение требует нового
commit/digest и полного повторения R6.5–R6.6 перед продолжением разрешённого R6.7.
