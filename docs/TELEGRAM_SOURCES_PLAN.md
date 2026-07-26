# План Telegram Sources: чужие каналы и чаты

Статус: проект документации для утверждения. Реализация и production-настройки не начаты.

## 1. Цель

Добавить массовый сбор автомобильных объявлений из чужих публичных Telegram-каналов и публичных групп ОАЭ. Система должна сама находить потенциальные источники, оценивать пригодность их сообщений для корректного извлечения данных и подключать постоянный сбор только после проверки администратором.

Целевой масштаб первого production-пилота:

- не менее 200 обнаруженных кандидатов;
- не менее 50 проанализированных источников;
- 10–20 включённых источников в семидневном пилоте;
- расширение до 50–200 включённых источников только после подтверждения качества, лимитов и стоимости.

Недвижимость, аукционы, ставки, аренда, запчасти и объявления о покупке не входят в автомобильный deal pipeline и классифицируются как нерелевантные.

## 2. Почему нужен MTProto

Telegram Bot API остаётся пользовательским интерфейсом продукта и не используется для чтения истории чужих источников. Отдельный Telegram Source Collector работает через MTProto от имени выделенного Telegram-аккаунта.

Доступность источников:

| Источник | Доступ |
|---|---|
| Публичный канал | история и новые публикации доступны MTProto-аккаунту |
| Публичная группа или супергруппа | история и новые сообщения доступны в пределах доступа аккаунта |
| Приватный источник, куда аккаунт приглашён | доступен после успешного вступления |
| Приватный источник без приглашения | недоступен и не добавляется |
| Секретный чат | не поддерживается |

Для подключения создаётся отдельное Telegram API application и отдельный технический аккаунт. `api_id`, `api_hash`, номер, session и одноразовые коды не передаются через Admin Web, не пишутся в Firestore, логи или Git и хранятся в Secret Manager. Первичная интерактивная авторизация выполняется отдельной bootstrap-командой оператора.

## 3. Пользовательский сценарий Admin Web

В Sources появляются вкладки:

- `Installed` — работающие marketplace, JSON и Telegram sources;
- `Candidates` — автоматически найденные каналы и группы;
- `Analyze source` — добавление `@username`, `t.me` URL или Telegram peer;
- `Discovery settings` — языки, ключевые запросы и лимиты;
- `Telegram collector` — состояние session, rate limits, очереди и последнего успешного sync без показа секретов.

Сценарий подключения:

1. Администратор вводит публичный `@username` или ссылку либо выбирает кандидата Discovery.
2. Backend разрешает peer, фиксирует стабильный Telegram peer ID и проверяет доступ.
3. Collector загружает ограниченную выборку истории: до 1 000 последних сообщений, но не старше 30 дней.
4. Сообщения сохраняются как raw evidence; альбомы и подписи объединяются.
5. Анализатор строит отчёт пригодности и показывает реальные распознанные/отклонённые примеры.
6. Источник получает статус `ready`, `needs_review`, `rejected` или `inaccessible`.
7. Только `ready` или вручную подтверждённый `needs_review` можно включить.
8. Включённый источник обрабатывается инкрементально от сохранённого message cursor.

## 4. Discovery чужих источников

Discovery создаёт кандидатов, но не включает сбор автоматически. Используются четыре независимых сигнала:

1. Telegram search по ограниченному словарю автомобильных запросов на английском, арабском и русском языках.
2. Источники пересланных автомобильных публикаций.
3. Публичные `t.me` ссылки и упоминания, найденные в уже подключённых источниках.
4. Cross-post graph: каналы, из которых регулярно появляются дубли известных автомобильных объявлений.

Каждый кандидат имеет provenance: каким запросом, сообщением или пересылкой он найден. Повторные находки повышают discovery score, но не quality score. Поиск ограничивается rate limit, дневным бюджетом запросов и backoff на Telegram FloodWait.

## 5. Контракт Telegram-сообщения

Raw-событие содержит:

- стабильный `peer_id`, `message_id` и дату;
- текст или caption без изменения;
- список media IDs и метаданные альбома;
- reply/thread и forward origin, если Telegram их предоставляет;
- edit date, deletion marker и ingest timestamps;
- hash содержимого и correlation ID;
- ссылку на публичное исходное сообщение, если она существует.

Ключ идемпотентности: `telegram:{peer_id}:{message_id}:{content_hash}`. Редактирование создаёт новую immutable revision, а current pointer меняется отдельно. Удаление не стирает историю и переводит объявление в `removed`.

## 6. Анализ пригодности и извлечение

Pipeline анализа:

```text
raw message / media group
    -> language and content classification
    -> sale / wanted / rent / parts / auction / discussion / spam
    -> deterministic field extraction
    -> optional Gemini extraction for ambiguous text
    -> fixed-price and anomaly validation
    -> cross-message and cross-source deduplication
    -> source quality report
```

Обязательные извлекаемые поля: цена и валюта, марка, модель, год, пробег, контакт, местоположение, фотографии и исходная ссылка. Неизвестное поле остаётся `null`.

Детерминированные правила первыми распознают цену, AED, год, пробег, телефон, URL и явные маркеры `price on request`, аренды, покупки, запчастей и аукциона. Gemini вызывается только для нового content hash и только для неоднозначного автомобильного текста. Gemini не определяет рыночную цену, прибыль, ROI или решение и не исправляет отсутствующую цену догадкой.

## 7. Quality Gate

Отчёт источника содержит:

- объём выборки и период;
- долю автомобильных сообщений;
- долю объявлений о продаже;
- долю фиксированных цен;
- полноту make/model/year/mileage;
- наличие фотографий и публичных ссылок;
- распределение языков;
- duplicate/spam/edit/delete rates;
- количество price anomalies;
- 20 примеров accepted и 20 rejected;
- причину итогового статуса.

Автоматический статус `ready` разрешён, если одновременно:

- проанализировано не менее 100 сообщений или вся доступная выборка, если её меньше;
- найдено не менее 20 объявлений о продаже автомобилей;
- precision классификации на проверочной выборке не ниже 90%;
- фиксированная валидная цена присутствует минимум у 70% найденных продаж;
- make, model и year заполнены минимум у 80% найденных продаж;
- price anomaly rate не превышает 1%;
- источник не состоит преимущественно из дублей, аренды, запчастей или объявлений о покупке.

При недостаточной выборке источник остаётся `needs_review`. Любая цена 99/999 AED, `Price on request` или конфликт валюты блокирует конкретное объявление, а не преобразуется в фиктивную цену.

## 8. Достоверность и использование в расчётах

Telegram evidence получает уровень `seller_stated`, а не `verified_listing`. Сообщение может использоваться для обнаружения автомобиля и уведомления `WATCH/INSPECT`, но не входит в verified comparable market и не получает `CONTACT` только на основании текста Telegram.

Повышение до `verified_listing` возможно только после одного из событий:

- сообщение содержит внешнюю detail URL, и source-bound verifier подтвердил на ней автомобиль и текущую фиксированную цену;
- тот же автомобиль найден на независимом проверяемом marketplace и cross-source identity подтверждён;
- оператор выполнил отдельную ручную проверку с записанным provenance.

Публичная карточка всегда показывает `Telegram seller-stated price` либо `Verified price`; эти статусы нельзя смешивать.

## 9. Google Cloud архитектура

Новые компоненты:

- `deal-sniper-telegram-collector` — Cloud Run Job для backfill и incremental sync;
- `deal-sniper-telegram-discovery` — Cloud Run Job с ограниченным поиском кандидатов;
- `telegram-source-analysis` — Cloud Tasks queue;
- Secret Manager: MTProto app credentials и encrypted session;
- Firestore: `telegram_sources`, `telegram_source_candidates`, `telegram_messages`, `telegram_source_reports`, cursor/leases;
- Cloud Storage: immutable raw message batches и media metadata; загрузка бинарных media выполняется только для сообщений-кандидатов.

Одновременно session использует только один активный collector lease. Jobs завершаются после ограниченного batch и не работают бесконечным процессом. Scheduler запускает incremental sync; FloodWait переносит `next_allowed_at`, а не создаёт агрессивный retry storm.

## 10. Этапы реализации

### TG0 — контракт и golden dataset

- модели source/message/revision/report;
- 100–200 обезличенных golden сообщений EN/AR/RU;
- ожидаемые классификации и поля;
- тесты ценовых аномалий, альбомов, edits/deletes и дублей.

### TG1 — MTProto bootstrap и connectivity

- отдельные credentials и технический аккаунт;
- bootstrap session вне Web UI;
- Secret Manager, rotation/revoke процедура;
- read-only probe публичного тестового канала;
- отсутствие credentials/session в логах и Firestore.

### TG2 — реестр и ручной анализ

- Admin `Analyze source`;
- resolve peer, backfill sample, raw archive;
- quality report, examples и статусы;
- approve/pause/remove без удаления истории.

### TG3 — extractor и evidence tiers

- classification и deterministic extraction;
- Gemini fallback с content-hash cache;
- `seller_stated`/`verified_listing` provenance;
- запрет Telegram-only evidence в verified market и `CONTACT`.

### TG4 — incremental collector

- per-source cursor, lease, edit/delete handling;
- media-group assembly;
- Cloud Tasks processing;
- rate limit, FloodWait, retry/backoff и metrics.

### TG5 — Discovery

- multilingual query dictionary;
- forward/link/cross-post discovery;
- candidate scoring и deduplication;
- дневные лимиты и Admin candidate queue.

### TG6 — staging и production pilot

- staging с отдельной session и delivery disabled;
- replay golden dataset и live probe;
- 10–20 источников, 7 дней, ручной аудит минимум 200 извлечений;
- ноль Telegram-only `verified`/`CONTACT`;
- после отчёта — разрешение масштабирования до 50–200 источников.

## 11. Критерий завершения

Функция считается работающей только когда администратор может добавить чужой публичный канал, получить понятный quality report, включить его, увидеть новые сообщения и фотографии, а система корректно отделяет продажу от шума и не выдаёт заявленную Telegram-цену за проверенный рынок. Количество зарегистрированных источников само по себе не является результатом без подтверждённого качества.
