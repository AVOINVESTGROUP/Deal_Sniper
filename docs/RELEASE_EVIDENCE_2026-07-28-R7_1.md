# Release evidence R7.1 — staging

Статус: **финальный immutable-кандидат успешно проверен в изолированном staging; требуется только ручная проверка Admin Web владельцем. Production не изменён**.

## Зафиксированные версии

- ветка: `production/deal-sniper-complete`;
- финальный код R7.1: `4aaf252c47e1c7d1f60e839fcf7cac6c019fd07c`;
- Draft PR: `https://github.com/AVOINVESTGROUP/Deal_Sniper/pull/3`;
- GitHub Actions: `30347621234` и `30347621827` — success;
- Cloud Build: `977cb039-a9b4-4234-9803-cd09a1037e77`;
- immutable digest: `sha256:41b04c0ed5f1e7fd5a3e738f34dbb7121d60e4c3c02cc28300d2002ab11caa99`;
- staging Cloud Run revision: `deal-sniper-api-staging-00036-87b`;
- staging publisher Job: `deal-sniper-publisher-staging`;
- staging Gateway config: `r71-07e89b7`;
- Hosting Preview version: `06e7b909a8895569`;
- Hosting Preview: `https://avo-deal-sniper--r7-02fcb6f-gswik35m.web.app`.

Предыдущий кандидат `07e89b7` / `sha256:d1fa347b8b4a528b89ba93ad6ab0a3ca11c86813ad514c44097cf8300d92998c` аннулирован: проверка обнаружила жёсткую связь staging Admin с production publisher Job. Он не является релизным кандидатом.

## Пройденные проверки

- локально: 95 passed, 2 skipped, Ruff, strict mypy, JavaScript ES-module syntax и `git diff --check`;
- оба GitHub Actions запуска успешно выполнили quality, container build, Trivy и Terraform;
- образ собран только из `git archive` точного commit, без локальных `.env`, кэшей и незакоммиченных файлов;
- exact digest развёрнут только в staging API и отдельном staging publisher;
- `/version` подтвердил точные commit/digest, API `1.1.0`, engine `3.1.0` и schema `2`;
- `/health`, `/ready`, защищённые Gateway routes и CORS preflight успешны;
- staging использует Firestore `deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false`, `WHATSAPP_ENABLED=false`, `PUBLISHER_JOB_NAME=deal-sniper-publisher-staging` и фиктивный recipient `staging-pro-preview`;
- точный allowlist допускает только `deal-sniper-publisher` и `deal-sniper-publisher-staging`, произвольные имена Job отклоняются;
- Hosting Preview направлен только на staging Gateway и содержит оба Admin-вызова R7.1;
- staging publisher execution `deal-sniper-publisher-staging-jrf2n` успешно завершился без кандидатов;
- изолированный Firestore smoke создал один тестовый текущий `INSPECT`, после чего execution `deal-sniper-publisher-staging-xfjlp` показал `selected=1, created=1, failed=0`;
- проверены стабильные publication/delivery IDs, атомарно созданные PublicationEvent и pending outbox с recipient `staging-pro-preview`;
- тестовые listing, snapshot, decision, pointer, PublicationEvent и outbox удалены по точным идентификаторам; тестовой Cloud Task в очереди больше нет;
- фактическая Telegram/WhatsApp-доставка из staging не выполнялась.

## Production baseline не изменён

- commit: `851ddaf26852aaaa0547df1b60e222d7f74b5d9a`;
- digest: `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`;
- API revision: `deal-sniper-api-00060-kkc`;
- production publisher использует тот же R6 digest и Firestore `(default)`;
- Gateway config: `deal-sniper-config-source-12bdee5`;
- live Hosting version: `c110b289b2855e7f`.

## Оставшаяся ручная проверка

Автоматический authenticated browser smoke не выполнялся: у операторской учётной записи нет `iam.serviceAccounts.signBlob`, а временная Firebase account не создавалась. Владелец должен войти своей существующей Firebase-сессией в Hosting Preview, открыть раздел **Publications** и убедиться, что отображается блок **Pro publication coverage** и кнопка **Publish Pro now**. При `missing=0` кнопка закономерно неактивна.

До отдельного явного разрешения запрещены production deploy, запуск production publisher и Telegram-доставка из staging.
