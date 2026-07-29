# Release evidence R8.1 — production

Статус: **R8.1 активирован в существующем production Pro-канале. Дополнительный тестовый канал не создавался**.

## Immutable-версия

- source commit: `aa261129415065b63d4be85f098cd0e255966ab1`;
- Draft PR: `https://github.com/AVOINVESTGROUP/Deal_Sniper/pull/3`;
- GitHub Actions: push `30431337917`, PR `30431341429` — успешно;
- Cloud Build: `2ff0f1e7-6828-4e0f-a06a-35503cf1d328` — успешно;
- API/publisher digest: `sha256:0efbc0699d8a79f9c8e4802a15f274debb1b25843d5c19cdc3b47d910c73fd0b`.

Локальный gate: 114 тестов прошли, 2 условно пропущены; Ruff, strict mypy, pip-audit,
Terraform fmt/validate и проверка diff завершились успешно.

## Исправление качества новостей

Во время production preflight обнаружено ложное совпадение: подстрока `car` в фамилии
`Pogacar` ошибочно проходила automotive relevance gate. Проверка заменена на поиск целых
автомобильных терминов, добавлен регрессионный тест. В production настроена прямая лента
`https://www.dubicars.com/news/feed` с актуальными материалами автомобильного рынка ОАЭ.

## Staging

- API revision: `deal-sniper-api-staging-00042-w8f`;
- publisher generation: `6`;
- publisher execution: `deal-sniper-publisher-staging-g5ggx` — завершён;
- Firestore: `deal-sniper-stage-rc2`;
- очередь `telegram-delivery-staging` осталась остановленной и пустой;
- delivery и WhatsApp были выключены;
- `/health`, `/ready` и `/version` подтвердили готовность, schema `2`, commit и exact digest.

## Ограниченный production cutover

Перед переключением был остановлен только scheduler публикаций. Collectors, processing,
личный Telegram-бот и Free-канал не останавливались.

- production API revision: `deal-sniper-api-00061-tlq`;
- production publisher generation: `41`;
- `DELIVERY_ENABLED=true`, `PRO_DEALS_ENABLED=true`, `PRO_NEWS_ENABLED=true`;
- `PRO_NEWS_MAX_ITEMS=1`, интервал новостей — 6 часов;
- Vertex AI summary выключен: финансовые расчёты и публикация не зависят от модели;
- первый bounded run: `deal-sniper-publisher-mpxs7` — завершён;
- второй idempotency run: `deal-sniper-publisher-r6ll5` — завершён.

Первый запуск выбрал одну новость, создал один outbox и доставил её в существующий канал
`Dubai Auto Deals Pro` (`-1004319276577`). Зафиксировано:

- outbox: `eaeed9dd00603e3f92cafb675fb0b10a8fdb8c95e512645f6f0daf8c6e8140ad`;
- состояние: `sent`;
- Telegram message ID: `29`;
- время подтверждения: `2026-07-29T07:32:07.851448Z`.

Второй запуск не создал повторную новость. На момент cutover новой сделки, одновременно
проходящей quality, profit и ROI gates, не было; система корректно не создала фиктивное
объявление. Следующая подходящая сделка будет опубликована плановым запуском.

## Рабочее состояние

- scheduler `deal-sniper-content-every-6h` снова включён, расписание `15 */6 * * *`;
- production queue `telegram-delivery` работает;
- Telegram webhook направлен на production Gateway, ошибок нет, pending updates — 0;
- бот `@DubaiDealSniper111_bot` доступен;
- `/health`, `/ready` и `/version` production API успешны;
- Admin Auth и WhatsApp в рамках R8.1 не изменялись.

## Rollback

- предыдущий commit: `851ddaf26852aaaa0547df1b60e222d7f74b5d9a`;
- предыдущий digest: `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`;
- API revision: `deal-sniper-api-00060-kkc`;
- publisher generation: `40`.

Rollback не требует миграции данных. Автоматический повтор сообщений в состоянии `unknown`
не выполняется.
