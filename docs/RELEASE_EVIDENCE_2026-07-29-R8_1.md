# Release evidence R8.1 — изолированный staging-кандидат

Статус: **immutable build и delivery-off staging прошли; реальный Telegram smoke ожидает отдельный тестовый канал. Production не изменён**.

## Версии

- source commit: `4e3f67e4d9f5b9a46ca224c045f0e596a5514201`;
- Draft PR: `https://github.com/AVOINVESTGROUP/Deal_Sniper/pull/3`;
- финальные CI: push `30429306501`, PR `30429308524` — success;
- Cloud Build: `63ce516a-2ba4-4af7-82bb-7df6b51f7a0e` — success;
- image digest: `sha256:928ddb983b793e9f77a5248dd5dec4cd2a542b55b08510523857b9bc62f18649`.

## Staging

- API revision: `deal-sniper-api-staging-00041-vp6`;
- publisher generation: `5`;
- Firestore: `deal-sniper-stage-rc2`;
- delivery queue: `telegram-delivery-staging`, состояние `PAUSED`, задач нет;
- `DEPLOYMENT_ENVIRONMENT=staging`, `DELIVERY_ENABLED=false`, `WHATSAPP_ENABLED=false`;
- `/health` вернул `ok`;
- `/version` подтвердил source commit, exact digest, schema `2`, API `1.1.0` и engine `3.1.0`.

Два последовательных publisher execution `deal-sniper-publisher-staging-k85vj` и
`deal-sniper-publisher-staging-fcxbg` завершились успешно. Оба нашли ту же news publication:
первый и второй запуск показали `created=0`, `requeued=1`; новый outbox не создан.
При выключенной delivery ни один запуск не создал Cloud Task.

## Незакрытый критерий

Владелец отменил требование отдельного тестового канала и потребовал завершить ограниченный smoke
в существующем production Pro-канале. Во время preflight найден и исправлен дефект relevance:
подстрока `car` внутри фамилии `Pogacar` ошибочно проходила automotive gate. Новый source commit,
CI и immutable digest должны быть зафиксированы до bounded production cutover.
