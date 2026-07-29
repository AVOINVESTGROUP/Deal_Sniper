# Release evidence R7.3 — staging-кандидат

Статус: **локальный gate, GitHub CI, immutable build, Gateway и publisher staging smoke пройдены. UI smoke ожидает повторной авторизации Firebase CLI. Production не изменён**.

## Зафиксированные версии

- ветка: `production/deal-sniper-complete`;
- реализация R7.3: `48e3132f12fa2b4fa7f7ad8fdb6cf747543d3cbb`;
- evidence commit, из которого собран образ: `c6c283667a889f030581fe3adcc6814d52d8f9cd`;
- Draft PR: `https://github.com/AVOINVESTGROUP/Deal_Sniper/pull/3`;
- GitHub Actions реализации: `30387369703` и `30387367900` — success;
- GitHub Actions evidence commit: `30387653569` и `30387651492` — success;
- production baseline остаётся R6: `851ddaf26852aaaa0547df1b60e222d7f74b5d9a` / `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`.

## Пройденные проверки

- 105 тестов прошли, 2 условно пропущены, coverage 58,82%;
- Ruff и strict mypy — success;
- JavaScript ES-module syntax — success;
- dependency audit — известных уязвимостей нет;
- Terraform format/validate — success;
- GitHub container build и Trivy — success;
- `git diff --check` — success.

## Immutable build и staging

- Cloud Build: `46d3f002-8073-4ebb-8cf7-3faefa507831` — success;
- image: `me-central1-docker.pkg.dev/avo-deal-sniper/deal-sniper/app:r73-c6c2836`;
- immutable digest: `sha256:d52c10aae8b19afad46ef380d47887e5ecdcf8d30136a245fdbf05b16cda50f5`;
- Cloud Run staging revision: `deal-sniper-api-staging-00038-f2j`;
- staging publisher generation: `4`;
- staging использует `deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false`, `WHATSAPP_ENABLED=false` и фиктивного Pro recipient;
- `/health`, `/ready` и `/version` подтверждают commit `c6c2836`, exact digest и schema `2`;
- активирована immutable runtime revision `r73-stage-c6c2836`, сохранившая прежние цены и финансовые пороги и включившая `pro_deals_enabled=true`, `pro_news_enabled=true`, лимит 2 материала и интервал 6 часов;
- staging API Gateway config `r73-c6c2836` находится в состоянии ACTIVE и назначен gateway `deal-sniper-r6-staging`;
- системные endpoints через Gateway возвращают HTTP 200; CORS preflight нового `/admin/news-feeds` возвращает HTTP 200 и явный разрешённый origin.
- создана изолированная очередь `telegram-delivery-staging`; во время теста она оставалась в состоянии PAUSED и не могла вызвать Telegram delivery;
- два последовательных выполнения publisher — `deal-sniper-publisher-staging-gj6jk` и `deal-sniper-publisher-staging-twgxd` — завершились успешно;
- первый прогон создал один `pending` outbox `pro-news/v1` для фиктивного получателя `staging-pro-preview` с двумя source-backed материалами; второй прогон сохранил тот же delivery ID `1d47608f…573b2` и ту же task ID `1d47608f…573b`, то есть дубль не возник;
- после проверки единственная тестовая задача удалена по точному ID; staging-очередь остаётся PAUSED и содержит 0 задач. Production queue не изменялась.

## Оставшиеся staging-проверки

- Новый Hosting Preview R7.3 не опубликован: Firebase CLI потребовал `firebase login --reauth`. Production Hosting не изменялся.
- До восстановления Google-сессий запрещено считать staging полностью закрытым и запрещён production deploy R7.3.

## Следующая граница

Повторно авторизовать Firebase CLI, опубликовать Hosting Preview, выполнить authenticated UI smoke и дополнить этот evidence Preview URL. Production deploy, production publisher и Telegram-доставка не разрешены этим документом.
