# Production release evidence — 25 июля 2026

Статус: production running; WhatsApp disabled до внешних Meta credentials.

## Подтверждённые контуры

- `/health`, `/ready` и `/version` через API Gateway возвращают успешный ответ, schema 2 и engine 3.1.0.
- CORS разрешён только для Firebase Hosting; Admin без Firebase token и TMA с неверным `initData` получают `401`.
- Полный smoke `Telegram initData → Firebase custom token → Firebase ID token → TMA feed → Admin overview` успешен.
- Telegram webhook обработал production `/status`; pending updates равны нулю, webhook error отсутствует.
- Бот имеет статус administrator в обоих Telegram-каналах.
- Все четыре per-source Cloud Run Jobs успешно выполнены; общий legacy collector schedule остаётся paused.
- `listing-processing` и `telegram-delivery` находятся в состоянии RUNNING.
- Free/Pro delivery использует transactional outbox; старые pending записи остановленного периода закрыты как superseded.

## Качество данных на cutover

- detail-page verified evidence: 1 177;
- permanent invalid: 1 671;
- temporary verification error: 4;
- current decisions: 1 137;
- publishable CONTACT/INSPECT: 0;
- текущие решения: 1 091 `INSUFFICIENT_DATA`, 46 `REJECT`.

Отсутствие публикаций автомобилей на этом срезе является корректным результатом: система не заменяет недостаток аналогов выдуманной рыночной ценой и не публикует `Price on request`.

## Восстановление

До миграции созданы защищённые Firestore exports STOP и cutover. Rollback выполняется по `docs/OPERATIONS.md`: delivery выключается первой, затем ставятся на паузу очереди и schedules, после чего восстанавливается подтверждённый export и предыдущий immutable digest.
