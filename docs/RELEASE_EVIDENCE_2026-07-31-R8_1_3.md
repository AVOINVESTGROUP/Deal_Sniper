# Release evidence R8.1.3F — восстановление автомобильного контура

Дата проверки: 31 июля 2026 года.

## Результат

Дополнение R8.1.3F реализовано и прошло полный локальный gate, GitHub Actions,
immutable build и повторный delivery-off staging. Три последовательных цикла каждого
из четырёх реальных источников завершились успешно: `12/12` executions. Staging не
отправлял сообщения в Telegram и не записывал raw evidence в production bucket.

Production не развёртывался. Следующий шаг требует отдельной явной команды владельца
на production deploy R8.1.3.

## Неизменяемый кандидат

- source commit: `925597043f3596c1296723a668337dc474e8495a`;
- GitHub Actions push: `30619171198`, все jobs успешны;
- GitHub Actions Draft PR: `30619176067`, все jobs успешны;
- Cloud Build: `44381975-eca8-4165-b692-a3452fcfab7a`;
- image tag: `r813f-925597043f35`;
- image digest:
  `sha256:48ddd19e9f0abe8a93240045f0d51e9dbfb283a32d7265ddaf06df026be22323`;
- registry describe, pull и запуск exact digest успешны;
- runtime импортирует приложение под Python 3.11 и не содержит импортируемых
  `pip`, `setuptools` или `wheel`.

Локальный gate: Ruff, strict mypy по 42 source-файлам, `153 passed / 2 skipped`,
coverage `62,44%`, dependency audit без известных уязвимостей, Terraform
fmt/init/validate, JavaScript ES-module syntax и Docker runtime/import.

## Изоляция staging

- Firestore database: `deal-sniper-stage-rc2`;
- API revision: `deal-sniper-api-staging-00052-82s`;
- raw bucket: `gs://avo-deal-sniper-raw-snapshots-staging`;
- bucket location: `ME-CENTRAL1`;
- uniform bucket-level access включён;
- public access prevention установлен в `enforced`;
- семидневный soft delete включён; object versioning не включался;
- staging collector service account имеет только требуемый bucket-level
  `roles/storage.objectCreator`;
- очередь `telegram-delivery-staging` всё время оставалась `PAUSED` и пустой;
- `DELIVERY_ENABLED=false`, `WHATSAPP_ENABLED=false`;
- `TELEGRAM_BOT_TOKEN` и `INTERNAL_TASK_SECRET` отсутствуют в staging API и jobs.

Read-back всех runtime-параметров подтвердил точные commit, digest, database, bucket,
schema `2` и staging environment. `/health=ok`, `/ready=ready`, `/version` вернул
commit `925597043f3596c1296723a668337dc474e8495a`, exact digest, API `1.1.0`, engine
`3.2.0` и schema `2`.

## Исправленные staging jobs

Перед rehearsal устранены два staging-конфигурационных разрыва, production при этом
не изменялся:

- publisher args исправлены с одного значения `main.py publish` на два значения
  `main.py`, `publish`;
- все rehearsal collectors и publisher переведены с production raw bucket на отдельный
  `avo-deal-sniper-raw-snapshots-staging`.

Read-back подтвердил exact digest и корректные args у пяти jobs:

- `deal-sniper-publisher-staging`, generation `25`;
- `deal-sniper-rehearsal-dubicars-staging`, generation `3`;
- `deal-sniper-rehearsal-carswitch-staging`, generation `3`;
- `deal-sniper-rehearsal-cars24-staging`, generation `3`;
- `deal-sniper-rehearsal-opensooq-staging`, generation `3`.

## Три последовательных цикла источников

| Цикл | DubiCars | CarSwitch | Cars24 | OpenSooq |
|---|---|---|---|---|
| 1 | `8x9r4` | `2fdzg` | `cn6cd` | `b8r6r` |
| 2 | `55s59` | `74srd` | `slbnw` | `ttxc4` |
| 3 | `cgqsp` | `m5g4q` | `m7fkn` | `f4snq` |

Во всех строках полное имя имеет префикс соответствующего
`deal-sniper-rehearsal-{source}-staging-`. Все `12/12` executions завершились
успешно, staging delivery queue оставалась пустой до, между и после циклов.

Последний source-health read-back:

| Источник | Получено | Новых | Изменено | Время, с |
|---|---:|---:|---:|---:|
| DubiCars | 23 | 5 | 2 | 4,705 |
| CarSwitch | 24 | 0 | 0 | 4,654 |
| Cars24 | 25 | 0 | 0 | 4,455 |
| OpenSooq | 30 | 0 | 0 | 3,694 |

## Evidence семантических попыток CarSwitch

Три live-цикла CarSwitch создали три отдельных append-only события
`raw_snapshot_attempt`. Каждый live-ответ был валидным с первой попытки, поэтому у
каждого события `attempt_number=1`; события имеют разные `fetched_at`, но один и тот же
checksum и один физический content-addressed raw object:

- MIME: `text/html`;
- размер: `6 798 976` байт;
- checksum: `b43ceb49…7046`;
- storage URI находится только в staging bucket.

Ветка восстановления `пустой HTTP 200 -> валидный ItemList` и ветка исчерпания трёх
попыток не воспроизводились искусственно на live-сайте. Они покрыты локальными
регрессионными тестами. Тест трёх одинаковых пустых ответов подтверждает один физический
payload, три capture-события с номерами `1–3`, terminal
`semantic_empty_response` и отсутствие listings/decisions.

## Воронка staging

После трёх циклов read-only отчёт показал:

- fetched: `6137`;
- verified: `1538`;
- normalized: `2819`;
- market: `106`;
- current decisions: `1196`;
- eligible: `1`;
- Pro sent: `0`;
- Free sent: `0`.

Распределение решений: `CONTACT=0`, `WATCH=1`, `INSPECT=1`, `REJECT=104`,
`INSUFFICIENT_DATA=325`, `unclassified_legacy=765`; сумма равна `1196`.
Legacy-записи показаны отдельно и не считаются допустимыми публикациями. Числа отражают
накопленную staging-базу и не являются обещанием числа новых production-предложений.

## Delivery-off publisher rehearsal

Два последовательных execution завершились успешно:

- `deal-sniper-publisher-staging-rrhsx`;
- `deal-sniper-publisher-staging-zqfln`.

Оба вернули:

```text
Deals: Pro selected=0, created=0, requeued=0, skipped=0, failed=0;
Free eligible=0, created=0, requeued=0, blocked=0, failed=0
```

Outbox сохранил `11 pending`, остальные состояния — `0`; publisher не создал и не
переочередил карточки, потому что в этих циклах не появилось новой допустимой revision.
Это ожидаемый fail-closed результат: проект не создаёт вымышленные предложения для
демонстрации. Telegram queue до и после обоих запусков пуста.

## Сверка production до/после

Контрольные снимки сняты в `2026-07-31T09:22Z` и `2026-07-31T10:04:48Z`.
Нормализованное сравнение подтвердило:

- API generation `66`, revision `deal-sniper-api-00066-lcf` и digest
  `sha256:b6a2e5cb9ae7de2c14e2e26bc141c077292d78e16c1e23ffee1f1f6573de75f4`
  не изменились;
- specs и generations всех девяти production Cloud Run jobs не изменились;
- все production Scheduler specs не изменились;
- очереди `listing-processing` и `telegram-delivery` не изменились.

Три регулярно запускаемых collector jobs получили новые служебные `resourceVersion`,
не меняя generation или spec. В API-ответе также появилось явное представление
неявного default traffic `latestRevision=true, percent=100`; revision, generation,
resourceVersion и image остались прежними. Эти operational/API-normalization поля не
являются production-конфигурационной мутацией.

## Следующий разрешённый шаг

Только после отдельной команды владельца `Разрешаю production deploy R8.1.3`:

1. защищённый Firestore export и повторный production preflight;
2. остановка только согласованных scheduler/delivery контуров;
3. delivery-off deploy exact digest и read-back всех API/jobs;
4. bounded replay с отчётом воронки без ослабления financial/evidence gates;
5. staged resume collectors -> processing -> Pro -> exact linked Free;
6. Telegram smoke только на новом реальном допустимом автомобиле либо честный результат
   «новых доказуемых предложений нет»;
7. итоговая сверка message IDs, exact Pro/Free linkage, очередей и rollback markers.

## Дополнительный preflight после разрешения deploy

Владелец разрешил production deploy R8.1.3, но production не был изменён: обязательная
проверка полного replay выявила неполное покрытие старого migration epoch. Из `4 179`
текущих revisions старый request set может обработать только `2 326`; все `1 757`
current decisions остаются на engine `3.1.0`, а release требует `3.2.0`.

Дополнительный full staging replay старого epoch завершился успешно на exact digest:

- bounded execution `deal-sniper-replay-staging-7ppl8`: `293 completed`, `0 failed`,
  `7 skipped`;
- full execution `deal-sniper-replay-staging-l2rtd`: `2 390 completed`, `0 failed`,
  `389 skipped`, длительность `27m34s`;
- publisher `deal-sniper-publisher-staging-fkmts` завершился успешно;
- staging queue осталась `PAUSED` и пустой, реальных Telegram send не было;
- стабильная воронка после replay: fetched `6 137`, verified `2 033`, normalized `2 819`,
  market `124`, current decisions `1 198`, eligible `0`.

Regulated migration dry-run `deal-sniper-migration-staging-2wm9j` был запущен на том же
digest и корректно остановился **до apply**: migration tool `1.2.0` не признаёт одиннадцать
фактически используемых `publication-event/v3`, хотя writer release сохраняет именно этот
контракт. Production API/jobs, schedulers, queues, Firestore и Telegram не изменены.
Read-only production schema audit обнаружил `129` таких v3 событий из `177`; остальные
`48` используют разрешённый v1. Других неизвестных schema versions во всех коллекциях
migrator и вложенных snapshots нет.

Исправление описано в дополнении R8.1.3G. Оно меняет код и digest, поэтому текущий release
candidate остановлен; production deploy нового build запрещён до утверждения R8.1.3G,
нового immutable build, полного staging migration/replay evidence и нового отдельного
разрешения владельца.

Независимый review дополнительно установил: простого добавления v3 в allowlist недостаточно,
поскольку generic top-level upgrade затем переписал бы native `publication-event/v3` в
общую schema `"2"`. R8.1.3G поэтому также ограничивает write только legacy `None`/`"1"` и
обязует apply-тестом доказать неизменность всех уже валидированных native contracts.
Rollback уточнён без ложного обещания in-place restore: Firestore import выполняет merge;
staging clone при ошибке создаётся заново, а production остаётся STOP/delivery-off до
компенсирующей процедуры и полной сверки export/ledger.

## Локальное evidence R8.1.3G

После явного утверждения владельцем реализована только согласованная compatibility-правка:
точный allowlist `publication-event/v3`, legacy-only generic upgrade и migration tool
`1.2.1`. Validation по-прежнему fail-closed для произвольных `/v3` и v4.

Локальный gate завершён успешно:

- Ruff — без ошибок;
- strict mypy — 42 source-файла без ошибок;
- Pytest — `156 passed / 2 skipped`, coverage `63%`;
- pip-audit — известных уязвимостей нет;
- Terraform fmt/init/validate — успешно;
- JavaScript ES-module syntax — успешно;
- Docker Python 3.11 — приложение импортируется, build tooling отсутствует;
- container read-back — `MIGRATION_TOOL_VERSION=1.2.1`.

Локальный Trivy в среде не установлен, поэтому GitHub Actions container scan остаётся
обязательным блокирующим gate. Новый commit, digest, migration ID и staging ledger будут
добавлены только после CI/build/rehearsal. Production на этом этапе не изменён.

## STOP перед immutable build: completed epoch safety

Source commit `d881224` прошёл оба GitHub Actions запуска: `quality`, `terraform` и
блокирующий `container`/Trivy зелёные. Immutable image из него не собирался.

Финальный read-only review обнаружил, что повторный dry-run после completed apply способен
перезаписать неизменяемый ledger статусом `dry_run_complete`; последующий apply может
повторно выполнить invalidation и вернуть requests того же epoch в pending. Облачные
ресурсы, staging database и production не изменялись.

Исправление и regression gate описаны в R8.1.3G.1. До явного утверждения дополнения source
commit `d881224` не является build candidate.
