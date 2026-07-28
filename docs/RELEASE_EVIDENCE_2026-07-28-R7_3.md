# Release evidence R7.3 — staging-кандидат

Статус: **локальный gate и GitHub CI пройдены; immutable build и staging ещё не выполнены. Production не изменён**.

## Зафиксированные версии

- ветка: `production/deal-sniper-complete`;
- реализация R7.3: `48e3132f12fa2b4fa7f7ad8fdb6cf747543d3cbb`;
- Draft PR: `https://github.com/AVOINVESTGROUP/Deal_Sniper/pull/3`;
- GitHub Actions: `30387369703` и `30387367900` — success;
- production baseline остаётся R6: `851ddaf26852aaaa0547df1b60e222d7f74b5d9a` / `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`.

## Пройденные проверки

- 105 тестов прошли, 2 условно пропущены, coverage 58,82%;
- Ruff и strict mypy — success;
- JavaScript ES-module syntax — success;
- dependency audit — известных уязвимостей нет;
- Terraform format/validate — success;
- GitHub container build и Trivy — success;
- `git diff --check` — success.

## Следующая граница

Собрать новый immutable image только из точного evidence commit, развернуть exact digest в `deal-sniper-api-staging` и `deal-sniper-publisher-staging`, сохранить `FIRESTORE_DATABASE=deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false`, `WHATSAPP_ENABLED=false` и фиктивный Pro recipient. Production deploy, production publisher и Telegram-доставка не разрешены этим документом.
