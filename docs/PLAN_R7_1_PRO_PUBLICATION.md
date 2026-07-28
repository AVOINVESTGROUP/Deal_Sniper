# План R7.1 — восстановление Pro-публикаций и управление ценой

Статус: **утверждён владельцем 28 июля 2026; разрешены реализация и staging, production deploy требует отдельного разрешения**.

Статус реализации: **локальная реализация завершена 28 июля 2026; production не изменён**.

## 1. Подтверждённая проблема

Production настроен на Free и Pro Telegram-каналы, delivery включена, publisher job запускается успешно. При этом Firestore содержит 3 текущих решения `INSPECT`, а история outbox содержит только 5 доставок `pro/v1`.

Причина: периодический `content` job публикует информационный пост и Free `MARKET WATCH`, но не выполняет reconciliation текущих `CONTACT`/`INSPECT` с Pro-каналом. Pro outbox создаётся только в момент обработки новой версии объявления. Если событие было пропущено, delivery была выключена или решение существовало до текущего контура, периодический job его не восстанавливает.

## 2. Уточнённый коммерческий контракт

1. Администратор меняет цену AED и фактическое списание Stars только в разделе **Settings / Pricing** Admin Web.
2. Telegram хранит цену Stars внутри subscription invite link. Поэтому `Apply` автоматически создаёт новую платную ссылку через backend, проверяет её и атомарно переключает active runtime revision. Администратор не создаёт и не вставляет ссылку вручную.
3. Цена AED является коммерческим отображением, Stars — фактическим списанием Telegram. Панель обязана показывать оба значения и итоговую ссылку только в маскированном виде.
4. Поскольку платных пользователей пока нет, staging-smoke допускается выполнить с текущим Pro-каналом при остановленной обычной доставке, лимите в одну тестовую операцию и последующем rollback. Отдельный тестовый канал не требуется.

## 3. Исправление Pro-публикаций

Периодический publisher получает отдельный Pro reconciliation:

1. читает актуальные решения только текущего engine/config;
2. повторно применяет `is_publishable` и допускает только `CONTACT`/`INSPECT`;
3. сортирует по ожидаемой прибыли, ROI и confidence;
4. для каждой пары `decision + Pro recipient + pro/v1` вычисляет стабильные publication/delivery IDs;
5. существующие `sent`, `sending` и `unknown` не дублирует;
6. существующий `pending` разрешает повторно поставить в Cloud Tasks;
7. отсутствующий event атомарно создаёт вместе с outbox;
8. за один запуск публикует не более `CHANNEL_MAX_POSTS_PER_RUN`;
9. Pro-карточка содержит фотографию при наличии, источник, проверенную цену, рынок, max purchase, расходы, прибыль, ROI, confidence, риски и ссылку на объявление;
10. `MARKET WATCH`, `REJECT`, `INSUFFICIENT_DATA` и неподтверждённые цены в Pro не публикуются.

## 4. Управление в Admin Web

В раздел **Publications** добавить:

- число текущих publishable Pro decisions;
- число уже доставленных, pending, unknown и ещё не поставленных в outbox;
- время последнего Pro reconciliation;
- кнопку **Publish Pro now** с preview количества и точным подтверждением;
- результат запуска: selected, created, requeued, skipped, failed.

Кнопка не отправляет Telegram напрямую. Она запускает тот же идемпотентный publisher job. Произвольный recipient или текст из браузера не принимаются.

## 5. Проверки

До production:

- unit: выбор только CONTACT/INSPECT, стабильные IDs, отсутствие дублей, pending requeue, unknown fail-closed, batch limit;
- integration: current decisions → atomic publication event + outbox;
- Admin API/UI: preview и запуск Pro reconciliation;
- staging: delivery disabled, preview counts и создание изолированных test records без Telegram send;
- controlled production smoke при отсутствии платных пользователей: остановить publisher schedule, создать новую Stars-ссылку через Admin, проверить active revision в Admin/bot/TMA/CTA, выполнить rollback, затем запустить Pro reconciliation с лимитом 1;
- проверить реальную карточку в Pro, outbox=`sent`, отсутствие дубля при повторном запуске;
- только после smoke вернуть рабочий batch limit и scheduler.

## 6. Критерии готовности

- цена управляется из Admin без ручной работы со ссылками;
- active runtime revision едина для Admin, bot, TMA и новых Free CTA;
- все текущие publishable CONTACT/INSPECT имеют ровно одну Pro publication revision;
- повтор publisher не создаёт повторных сообщений;
- Pro-канал получает новые подходящие автомобили автоматически;
- Free-канал продолжает публиковать только безопасный teaser/Market Watch;
- production deploy выполняется только после нового immutable build, staging evidence и отдельного разрешения владельца.

## 7. Реализованный кандидат

- periodic `content` job сначала выполняет идемпотентный Pro reconciliation, затем Free/Market Pulse;
- для `decision + Pro recipient + pro/v1` используются стабильные publication и delivery ID;
- `pending` повторно ставится в Cloud Tasks, `sent`, `sending`, `unknown` и `failed` не дублируются;
- отсутствующая пара PublicationEvent/outbox создаётся атомарно, размер запуска ограничен активным `Posts per run`;
- Admin Web показывает покрытие Pro-публикаций и запускает только allowlisted Cloud Run Job `deal-sniper-publisher` после точного подтверждения;
- изменение только цены AED/Stars больше не инвалидирует автомобильные решения; версия финансовой политики меняется только при изменении порогов расчёта;
- локальный gate: 94 теста прошли, 2 условно пропущены; Ruff, strict mypy, ES-module syntax и `git diff --check` прошли.
