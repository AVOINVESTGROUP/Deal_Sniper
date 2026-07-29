# Release evidence R8.1.1 — целостность Free → Pro

Дата выпуска: 29 июля 2026 года.

## Результат

R8.1.1 развёрнут в production. Объектная публикация Free теперь возможна только после
подтверждённой доставки точной Pro revision. Независимые объектные шаблоны `free/v2` и
`market-watch/v2` заблокированы в delivery handler.

## Неизменяемый кандидат

- source commit: `308545a43a3b06d32f984e5d8d5d18294750f87a`;
- GitHub Actions: `30437458699` и `30437468879`, все jobs успешны;
- Cloud Build: `ec0856ca-59c3-4b37-b804-382f6e17150c`;
- image digest: `sha256:7a8ed30227434bfe6411e3d457a76b550c5ba39d9dd877560c4fed05223af897`;
- Python: 3.11 в CI и runtime;
- локальный gate: 126 passed, 2 skipped, coverage 60,18%, Ruff, strict mypy,
  pip-audit, Terraform validate и JavaScript ES-module syntax успешны.

## Staging

- API revision: `deal-sniper-api-staging-00044-crz`;
- тот же immutable digest и commit;
- `/health`, `/ready`, `/version` успешны;
- `DELIVERY_ENABLED=false`;
- очередь `telegram-delivery-staging` оставалась `PAUSED` и пустой до и после publisher;
- reconciliation preview: `total=0`, `unsafe=0`.

## Production cutover

- на время cutover были остановлены только `deal-sniper-content-every-6h` и очередь
  `telegram-delivery`; collectors и processing не останавливались;
- API revision: `deal-sniper-api-00062-s79`;
- publisher использует тот же immutable digest и штатную команду `python main.py content`;
- `/health`, `/ready`, `/version` успешны; schema version `2`;
- предварительный legacy preview: `total=75`, `matched=0`, `unsafe=75`;
- удалены ровно 75 недоказуемых legacy Free message ID, `already_absent=0`, `blocked=0`;
- повторный preview: `total=0`, `unsafe=0`;
- временный доступ publisher service account к Telegram secret удалён после reconciliation;
- content scheduler снова `ENABLED`, delivery queue снова `RUNNING` и пуста.

## Доказательство точной пары

Production integrity preview после доставки:

```text
pro_candidates=1
eligible=1
sent=1
blocked_no_pro=0
blocked_not_sent=0
blocked_revision_mismatch=0
failures=0
legacy_sent=0
legacy_unmatched=0
legacy_manual_review=0
```

Публичная страница Free-канала подтверждает новую пару:

- Free message ID: `163`;
- точная кнопка объекта: `https://t.me/c/4319276577/27`;
- Pro message ID: `27`.

Повторный publisher cycle не создал Pro- или news-дубль, а очередь после обработки осталась
пустой.

## Admin Web

Firebase Hosting live version: `2d5e57e0df831daa`. Страница
`https://avo-deal-sniper.web.app/admin.html` отвечает HTTP 200 и содержит блок
`Free → exact Pro integrity`.

## Rollback

Предыдущий production baseline:

- API revision: `deal-sniper-api-00061-tlq`;
- publisher generation: `41`;
- digest: `sha256:0efbc0699d8a79f9c8e4802a15f274debb1b25843d5c19cdc3b47d910c73fd0b`;
- source commit: `aa261129415065b63d4be85f098cd0e255966ab1`.

Откат runtime не восстанавливает удалённые недоказуемые Free-посты: их удаление намеренно и
зафиксировано append-only audit events `free_publication_withdrawn`.
