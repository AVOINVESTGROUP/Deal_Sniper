# Release evidence R6 — 27 июля 2026

## Идентичность релиза

- Git commit: `851ddaf26852aaaa0547df1b60e222d7f74b5d9a`.
- Container digest: `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`.
- Cloud Build: `5e074858-42a8-4fb1-9782-176329323455`.
- GitHub Actions: `30282317974`, все jobs успешны.
- Production API revision: `deal-sniper-api-00060-kkc`.
- Staging revision: `deal-sniper-api-staging-00021-lvq`.
- Firebase Hosting version: `c110b289b2855e7f`.

## Резервная копия и порядок переключения

- Firestore export: `gs://avo-deal-sniper-firestore-exports/r6-production-20260727-193058`.
- Экспорт завершён успешно, сохранено 69 251 документ.
- Во время переключения `DELIVERY_ENABLED=false`, schedulers и queues были остановлены.
- Возобновление выполнено только после staging и production smoke: collectors → processing → Telegram delivery → content.
- Legacy aggregate collector оставлен PAUSED, поскольку четыре источника имеют отдельные scheduler jobs.

## Проверки

- Локальный gate: Ruff, strict mypy, 81 pytest (2 optional skipped), coverage 55,65%, pip-audit без известных уязвимостей, Terraform fmt/validate.
- Staging Firestore integration на `deal-sniper-stage-rc2`: успешно.
- Authenticated headless Chrome: пять Admin endpoints вернули 200 на staging и production.
- `/health` и `/ready` production: успешно; schema version 2.
- Telegram webhook: URL корректен, `pending_update_count=0`, последней ошибки нет.

## Production pilot

- Четыре marketplace collectors завершили ручные контрольные executions успешно.
- Очередь processing приняла 563 задания и сведена к нулю.
- Временные ошибки detail-page verification являются fail-closed: они не создают рыночную evidence или публикацию.
- 30 новых Free vehicle cards доставлены в пилоте.
- Для последних 30 карточек: 30 уникальных CTA fingerprints, 0 соседних повторов, 0 отсутствующих CTA/кнопок.
- Финальная delivery queue: 0.
- Outbox: 94 всего; `sent=92`, `pending=0`, `sending=0`, `unknown=0`, `failed=2`. Две failed-записи — исторические superseded records периода delivery-disabled cutover, а не ошибки текущего пилота.
- Данные после пилота: 6 819 snapshots, 1 489 current decisions; DubiCars, CarSwitch, Cars24 UAE и OpenSooq UAE имеют статус healthy.

## Рабочие адреса

- Admin: `https://avo-deal-sniper.web.app/admin.html`.
- User Mini App: `https://avo-deal-sniper.web.app/app.html`.
- Production Gateway: `https://deal-sniper-gateway-dglai0gq.ew.gateway.dev`.

