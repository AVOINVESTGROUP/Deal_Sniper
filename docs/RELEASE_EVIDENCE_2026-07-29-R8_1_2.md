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
`docs/PLAN_R8_1_2_1_PAIRED_NEWS_DELIVERY.md`; план отдельно утверждён владельцем до
изменения кода.

## Реализация R8.1.2.1

Владелец утвердил план 30 июля 2026 года. Локально реализованы:

- группировка pending news по `news_evidence_id`;
- точная валидация двух сторон по recipient/template/publisher/URL/fingerprint/image SHA;
- стабильная постановка Pro и Free с маркером `news_pair_ready` только после обеих задач;
- delivery pair-gate и обязательная последовательность Pro `sent` → Free;
- `news_pair_blocked` при неполной паре, terminal state или ошибке постановки;
- отдельный news-only entrypoint, Cloud Run Job и Scheduler без `content/v1` и сделок;
- Admin-счётчики `paired_pending`, `paired_enqueued`, `blocked_pair`;
- закрепление container base на `python:3.11.15-slim-bookworm`.

Локальные проверки: Ruff, strict mypy, 136 passed / 2 skipped, покрытие 61,5%, dependency
audit без известных уязвимостей, Terraform fmt/init/validate. Отдельные тесты подтверждают,
что отказ второй постановки не открывает delivery gate, повтор не добавляет задач, а Free
не отправляется до точного Telegram message ID Pro. GitHub Python 3.11, container/Trivy и
Terraform gates должны пройти до нового immutable build. Production не изменён.

## Security gate R8.1.2.1

После публикации commit `6596ae85730ee948b1036799ee8e91378201e43a` Trivy заблокировал container job из-за
`CVE-2026-23949` и `CVE-2026-24049` во встроенных vendored-пакетах базового `setuptools`.
Владелец утвердил отдельное дополнение к плану. Runtime переведён на multi-stage и очищен от
`pip`, `setuptools`, `wheel` и `ensurepip`; зависимости приложения переносятся из builder stage.

Локальная сборка `deal-sniper:r8121-security` подтвердила:

- успешный импорт `src.web:app`;
- отсутствие импортируемых `pip`, `setuptools` и `wheel`;
- ноль исправляемых HIGH/CRITICAL в Trivy для Debian 12.15 и Python-пакетов;
- успешные 136 тестов, Ruff, strict mypy, pip-audit, Terraform и JavaScript syntax.

CI дополнен читаемым блокирующим table scan и отдельным SARIF artifact без ослабления security gate.

## Финальный release candidate R8.1.2.1

- source/implementation commit: `6dd9af358772f9c37ed006632c0202b19d91fd5a`;
- GitHub Actions: push `30542429343`, PR `30542431711`, все jobs успешны;
- Cloud Build: `623817ea-787f-45ec-af4d-9765ed44dbcd`;
- immutable image:
  `me-central1-docker.pkg.dev/avo-deal-sniper/deal-sniper/app@sha256:b6a2e5cb9ae7de2c14e2e26bc141c077292d78e16c1e23ffee1f1f6573de75f4`;
- staging API revision: `deal-sniper-api-staging-00048-bxv`;
- staging Firestore database: `deal-sniper-stage-rc2`;
- staging queue: `telegram-delivery-staging`, состояние во время проверки — `PAUSED`.

Exact-digest runtime smoke и registry-mode Trivy подтвердили импорт приложения, отсутствие
импортируемых `pip`, `setuptools`, `wheel` и ноль исправляемых HIGH/CRITICAL.

### Парный staging rehearsal

Первый delivery-off execution `deal-sniper-publisher-staging-9g44c` завершился успешно и не
создал Cloud Tasks. Для контролируемой проверки постановки очередь оставалась `PAUSED`, а
получатели были фиктивными: `staging-pro-preview` и `staging-free-preview`.

Fail-closed execution `deal-sniper-publisher-staging-4vxj6` ожидаемо остановился до доступа к
данным: отсутствовали обязательные staging `PUBLISHER_JOB_NAME` и allowlist production recipients.
После добавления только этих staging-параметров, без ослабления guard и без изменения production,
execution `deal-sniper-publisher-staging-qx9nb` дал:

```text
News: selected=1, created=0, requeued=2, paired=1, blocked=0, failed=0
```

В очереди появились ровно две задачи на `/tasks/deliver-content`:

1. `pro-news/v2`, task `25d7dd1b053f2f328935ed79be829841b4e270c2711cfbe866b0071a5a1fd96`;
2. `free-news/v1`, task `5e9217c6bac15cb361e761be04cda4b0299c87dc69e76196504bcef7c82dde5`.

Pro была поставлена на 656 мс раньше Free. У обеих задач совпали:

- `news_evidence_id=de880e49311f1d76fa67fdd581e689beb22ea4f8c00b72dec0e8e7090eb09742`;
- source URL `https://www.dubicars.com/news/uae-car-market-recovery-2026.html`;
- fingerprint `9738230f4f0c295087a0395353a3a94dca39abfb919733521b834c7dc076c374`;
- image SHA-256 `07344abd6acccfcc6cc02746f21a2122bd66d057495e4daec5852e8d25f4859d`.

Обе задачи имели `dispatchCount=0` и `responseCount=0`; legacy `content/v1` отсутствовал. После
проверки удалены только эти две staging-задачи. Delivery возвращён в `false`, повторный execution
`deal-sniper-publisher-staging-kf8lh` завершился с `requeued=0`, staging queue осталась `PAUSED` и пуста.

Production не изменялся: API `deal-sniper-api-00064-9sk`, publisher generation `55` и digest
`sha256:7a8ed30227434bfe6411e3d457a76b550c5ba39d9dd877560c4fed05223af897` сохранены;
production queue `telegram-delivery` остаётся `RUNNING`.

R8.1.2.1 готов к отдельному разрешению production deploy. Текущее разрешение на production для
аннулированного R8.1.2 не переносится на новый commit/digest автоматически.

## Production cutover R8.1.2.1 — 30 июля 2026

Владелец отдельно разрешил deploy фразой `Разрешаю production deploy R8.1.2.1`.

Перед изменением остановлены только content scheduler и `telegram-delivery`. Collectors и
processing не отключались. Создан новый Firestore export:

`gs://avo-deal-sniper-firestore-exports/r8121-production-20260730-144413`

Export завершился успешно (`completedWork=106534`). Затем exact immutable image развёрнут в
delivery-off режиме:

- API revision `deal-sniper-api-00065-5s5`, после включения delivery — `deal-sniper-api-00066-lcf`;
- `deal-sniper-publisher`, args `main.py content`;
- `deal-sniper-news-publisher`, args `main.py news`;
- implementation commit `6dd9af358772f9c37ed006632c0202b19d91fd5a`;
- digest `sha256:b6a2e5cb9ae7de2c14e2e26bc141c077292d78e16c1e23ffee1f1f6573de75f4`;
- `/health=ok`, `/version` вернул тот же commit/digest и schema `2`.

Первый execution нового job был остановлен самим Cloud Run до данных и delivery из-за ошибочно
переданного единого аргумента `main.py news`. Args исправлены на два значения `main.py`, `news`;
задач и Telegram-сообщений ошибочный execution не создал. Delivery-off execution
`deal-sniper-news-publisher-nnhhk` завершился успешно с пустой очередью.

### Контролируемая production-пара

При PAUSED queue один delivery-enabled execution поставил ровно две задачи:

1. Pro task `eaee8feb6d31664d4c79538d25c7c18942348548681c51f24b65400e865a14b`,
   delivery `fd8ea4cd0e9528acb6bf3874fd529833c8e3a6fa30ac01b1df9897312d24db6b`;
2. Free task `a4d712ce828322cd59f000541ce0f0ed56aef82076595fb1ea6313b3e5e42a4`,
   delivery `6d7a8475b57c7e6c86ef073aa138194121698877db16590e876b72d03d736369`.

Pro была запланирована раньше Free. Обе задачи имели `dispatchCount=0`, `responseCount=0`, один
evidence `de880e49311f1d76fa67fdd581e689beb22ea4f8c00b72dec0e8e7090eb09742`, publisher
`DubiCars`, URL `https://www.dubicars.com/news/uae-car-market-recovery-2026.html`, fingerprint
`9738230f4f0c295087a0395353a3a94dca39abfb919733521b834c7dc076c374` и image SHA-256
`07344abd6acccfcc6cc02746f21a2122bd66d057495e4daec5852e8d25f4859d`. `content/v1`
отсутствовал.

После включения API delivery и resume queue получены два terminal результата `sent`:

- существующий Pro-канал `-1004319276577`: Telegram message ID `37`;
- существующий Free-канал `@Dubai_Auto_Invest`: Telegram message ID `171`.

Публичная Free-страница `https://t.me/Dubai_Auto_Invest/171` возвращает HTTP 200 и содержит
исходную DubiCars статью с source-backed изображением.

### Повторный bounded run и штатный режим

Повторный ручной execution `deal-sniper-news-publisher-ts4jg` не повторил уже отправленную
evidence: он выбрал следующую ещё не опубликованную фактическую DubiCars статью
`https://www.dubicars.com/news/top-5-readily-available-evs-uae.html`. Получена новая точная
пара Pro message `38` → Free message `172` с общим fingerprint
`bf91e748ad63286193194ad1177f5d21d41562e86906b91bb8f5f871047abe3b`; первая статья не
дублировалась. `https://t.me/Dubai_Auto_Invest/172` возвращает HTTP 200.

Финальное состояние:

- API `deal-sniper-api-00066-lcf`, exact commit/digest/schema подтверждены через Gateway;
- оба Cloud Run Job используют тот же digest, корректные args и `DELIVERY_ENABLED=true`;
- `deal-sniper-news-every-6h` — `ENABLED`, `0 */6 * * *`, `Asia/Dubai`;
- `deal-sniper-weekly-market-pulse` — `ENABLED`, `0 10 * * 6`, `Asia/Dubai`;
- legacy `deal-sniper-content-every-6h` — `PAUSED`, чтобы не конкурировать с разделёнными
  расписаниями;
- `telegram-delivery` — `RUNNING`, лимиты 5 concurrent/10 per second, очередь пуста;
- `listing-processing` — пуста.

R8.1.2.1 активен в production. Для rollback сохранены свежий export, предыдущий API revision
`deal-sniper-api-00064-9sk` и предыдущий digest
`sha256:7a8ed30227434bfe6411e3d457a76b550c5ba39d9dd877560c4fed05223af897`.
