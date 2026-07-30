# Release evidence R8.1.2 — единый доказуемый контур новостей

Дата проверки: 29 июля 2026 года.

## Результат

R8.1.2 реализован, прошёл полный quality/security/IaC gate и delivery-off staging.
Production не изменён. Выпуск в существующие Telegram-каналы требует отдельного явного
разрешения владельца.

## Неизменяемый кандидат

- source commit: `946db4e175fbe3c46f4ce155660bafb2656b9f7f`;
- GitHub Actions: `30478854454` и `30478850873`, все jobs успешны;
- Cloud Build: `91fa7335-18b4-4bf9-a0fe-bfa7154521c3`;
- image digest: `sha256:6d6d44e29a9512819460c46b648bc037716614d78af9148a76fbcde07e7745aa`;
- локальный gate: Ruff, strict mypy, 130 passed / 2 skipped, dependency audit,
  Terraform validate и JavaScript syntax успешны;
- CI дополнительно подтвердил Python 3.11, Docker build и Trivy.

## Staging runtime

- Firestore database: `deal-sniper-stage-rc2`;
- API revision: `deal-sniper-api-staging-00047-k42`;
- publisher generation: `16`;
- финальный publisher execution: `deal-sniper-publisher-staging-stg5t`;
- `/health` вернул `ok`;
- `/version` вернул точные source commit и image digest, schema `2`;
- `DELIVERY_ENABLED=false`, `WHATSAPP_ENABLED=false`;
- очередь `telegram-delivery-staging` осталась `PAUSED`, задач до и после smoke — `0`;
- publisher service account получил bucket-level `roles/storage.objectUser` для
  `news-assets/{sha256}`; доступ ограничен raw bucket.

## Реальные news evidence и изображения

Live DubiCars ingestion принял 5 из 5 материалов. Все пять имеют:

- `publisher_name=DubiCars`;
- canonical HTTPS URL на `www.dubicars.com`;
- source-backed JPEG/WebP;
- MIME, размер и SHA-256;
- immutable объект в `gs://avo-deal-sniper-raw-snapshots/news-assets/`.

Примеры проверенных evidence:

- `e6a2f24b933565aed01219a08cede7ded8eb8ba619c6de7d380452f63adaf43f`,
  image SHA `9d92c20b1af02e183dc46bc96e9d9d8e6968a73df249bce9e0ac22652d45f438`;
- `de880e49311f1d76fa67fdd581e689beb22ea4f8c00b72dec0e8e7090eb09742`,
  image SHA `07344abd6acccfcc6cc02746f21a2122bd66d057495e4daec5852e8d25f4859d`.

## Free / Pro целостность

Для двух статей созданы четыре изолированные preview-записи:

| Template | Delivery ID | Evidence ID | Image SHA |
|---|---|---|---|
| `free-news/v1` | `4028c467…14da9` | `e6a2f24b…af43f` | `9d92c20b…45f438` |
| `pro-news/v2` | `9e18edea…568a0` | `e6a2f24b…af43f` | `9d92c20b…45f438` |
| `free-news/v1` | `7a58aac6…e5918` | `de880e49…09742` | `07344abd…4859d` |
| `pro-news/v2` | `aafa315e…8ec1e` | `de880e49…09742` | `07344abd…4859d` |

Recipients — только `staging-free-preview` и `staging-pro-preview`. Повторные publisher
executions сохранили те же четыре delivery ID и не создали Cloud Tasks. Контрактная
проверка Telegram подтверждает только `sendPhoto`; text fallback запрещён.

## Двухлентовый и отказоустойчивый сценарий

Regression fixture подтверждает:

- `accepted` считается отдельно для каждой ленты, а не накапливается между feeds;
- временный `httpx.ReadTimeout` записывается в source health;
- уже сохранённая evidence остаётся доступной, пока `valid_until > now`;
- неподтверждённый redirect image domain блокируется;
- отсутствие допустимого изображения не создаёт канальную публикацию.

## Административная наблюдаемость

Staging OpenAPI содержит `/admin/news-evidence`. Control Center получает thumbnail,
publisher, article/image provenance, MIME, размер, SHA-256 и отдельные состояния Free/Pro.
Все пользовательские пути новостей читают `news_evidence`, а не выполняют независимый fetch.

## Промежуточные кандидаты

Digests `sha256:0e27a52f…f977`, `sha256:f51b0a16…4435` и
`sha256:6a0f6e41…1c19` аннулированы после найденных до production пробелов и не являются
release candidate. Во время очистки исключительно staging fixture были удалены точные
preview outbox/publication events и три audit-записи rehearsal; production данные и
Telegram сообщения не изменялись.

## Следующий разрешённый шаг

Только после отдельной команды владельца:

1. backup и read-only аудит ошибочных legacy `pro-news/v1`;
2. delivery-off production deploy exact digest;
3. bounded publication в существующие Free и Pro каналы;
4. сверка Telegram message ID, publisher, URL, image SHA и ответа чата;
5. возврат штатного content schedule либо rollback.

## Неуспешный production cutover 30 июля 2026

Владелец отдельно разрешил production deploy. До мутаций создан защищённый Firestore export
`gs://avo-deal-sniper-firestore-exports/r812-production-20260730-100157`. Delivery-off
revision `deal-sniper-api-00063-cq4`, publisher execution `deal-sniper-publisher-z9pxk` и
Gateway config `r812-946db4e` подтвердили пять production evidence/assets и одну точную
pending Free/Pro пару.

Контролируемая постановка задач выявила новый блокер: publisher поставил только Free news
задачу, оставил Pro news `pending` и отдельно поставил legacy `content/v1`. Queue оставалась
PAUSED; обе задачи удалены при `dispatchCount=0`, Telegram сообщений не создано.

Выполнен полный rollback:

- API revision `deal-sniper-api-00064-9sk` снова использует R8.1.1 digest
  `sha256:7a8ed302…af897`;
- publisher generation `55` использует тот же R8.1.1 digest;
- Gateway возвращён на `deal-sniper-config-source-12bdee5`;
- `telegram-delivery` — `RUNNING` и пуста;
- `deal-sniper-content-every-6h` — `ENABLED`;
- `/health=ok`, `/version` снова показывает commit `308545a…f87a`;
- отправок в Free/Pro во время cutover не было.

Пять immutable `news_evidence`, проверенная registry entry `environment-default` и pending
Free/Pro outbox-пара намеренно сохранены как доказательство и вход для следующего
идемпотентного rehearsal. R8.1.1 их не публикует; связанных Cloud Tasks нет.

Digest R8.1.2 больше не допускается к production. Исправление описано в
`docs/PLAN_R8_1_2_1_PAIRED_NEWS_DELIVERY.md` и требует отдельного утверждения до изменения
кода.
