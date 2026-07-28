# Release evidence R7.1 — staging

Статус: **immutable build и безопасное staging-развёртывание выполнены; production не изменён**.

## Зафиксированные версии

- ветка: `production/deal-sniper-complete`;
- реализация R7.1: `07e89b79e3a46deade619a87b115157d3df4209a`;
- Draft PR: `https://github.com/AVOINVESTGROUP/Deal_Sniper/pull/3`;
- GitHub Actions: `30344706101` и `30344746180` — success;
- Cloud Build: `18c2f73a-d5e5-4ec4-84dc-e948c7f9b706`;
- immutable digest: `sha256:d1fa347b8b4a528b89ba93ad6ab0a3ca11c86813ad514c44097cf8300d92998c`;
- staging Cloud Run revision: `deal-sniper-api-staging-00035-gst`;
- staging Gateway config: `r71-07e89b7`;
- Hosting Preview version: `06e7b909a8895569`;
- Hosting Preview: `https://avo-deal-sniper--r7-02fcb6f-gswik35m.web.app`.

## Пройденные проверки

- локально: 94 passed, 2 skipped, Ruff, strict mypy, JavaScript ES-module syntax и `git diff --check`;
- два независимых GitHub Actions запуска: quality, container/Trivy и Terraform — success;
- образ собран только из `git archive` точного commit, без локальных `.env`, кэшей и незакоммиченных файлов;
- exact digest развёрнут только в `deal-sniper-api-staging`;
- `/version` подтвердил commit, digest, API/engine и schema `2`;
- `/health` и `/ready` успешны;
- staging сохраняет отдельную Firestore database `deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false` и `WHATSAPP_ENABLED=false`;
- staging Gateway активен на `r71-07e89b7`; новый `/admin/pro-publications` без Firebase-сессии возвращает 401, а CORS preflight для Preview origin — 200;
- Hosting Preview содержит вызовы preview/run R7.1 и направлен только на staging Gateway;
- production API, Gateway, publisher и live Hosting остались на R6.

## Оставшаяся ручная проверка

Автоматический authenticated smoke нового Admin-раздела не выполнен: у операторской учётной записи нет `iam.serviceAccounts.signBlob`, а локальные Application Default Credentials требуют повторной авторизации. Временная Firebase account не была создана. Владелец может проверить раздел **Publications** своей существующей Firebase-сессией в Hosting Preview.

До отдельного разрешения запрещены production deploy, запуск production publisher и Telegram-доставка из staging.
