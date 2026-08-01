# План R8.1.2.1 — атомарная парная доставка новостей Free/Pro

Статус: **утверждён владельцем 30 июля 2026 года; реализован локально, production остаётся на R8.1.1**.

## 1. Подтверждённый диагноз

30 июля 2026 года разрешённый bounded production cutover R8.1.2 был остановлен до
Telegram-доставки. Delivery-off запуск создал правильную пару:

- `free-news/v1` — delivery `6d7a8475…636369`;
- `pro-news/v2` — delivery `fd8ea4cd…4db6b`;
- общий evidence `de880e49…09742`;
- общий image SHA-256 `07344abd…4859d`.

После временного включения постановки задач `reconcile_pro_news_publication()` увидел две
pending news-записи, но ветка `pending_records` поставила в Cloud Tasks только первый
элемент и немедленно завершилась. В очередь попали:

1. Free news `6d7a8475…636369`;
2. независимый legacy Market Pulse `content/v1`.

Парная Pro news `fd8ea4cd…4db6b` осталась `pending`. Продолжение привело бы к публикации
новости в Free без обещанной полной карточки в Pro. Обе задачи были удалены до dispatch,
Telegram сообщений не возникло, после чего API, publisher, Gateway, queue и scheduler
возвращены на R8.1.1.

## 2. Границы исправления

Изменение касается только оркестрации news outbox и bounded release-команды. Модели
evidence, изображения, фактические поля, объявления автомобилей, расчёт рынка, подписки и
исторические Telegram-сообщения не изменяются.

## 3. Обязательное поведение

1. Pending news обрабатываются группой одного `news_evidence_id`.
2. Группа допустима к постановке задач только при наличии ровно одной `free-news/v1` и
   одной `pro-news/v2` с одинаковыми publisher, URL, fingerprint и image SHA-256.
3. Обе задачи ставятся в одну paused очередь до её проверки. Частичная постановка считается
   ошибкой cutover и не разрешает resume.
4. Повтор publisher переиспользует стабильные delivery/task IDs и не создаёт дублей.
5. Bounded news cycle не создаёт и не переочередяет `content/v1`, сделки или Free object
   reconciliation. Для него вводится отдельный режим/команда `news-only`.
6. При terminal failure одной стороны вторая не отправляется автоматически; группа видна в
   Admin Web как `blocked_pair` и требует reconciliation.

## 4. Реализация

- заменить ранний возврат после `pending_records[0]` на pair-aware reconciliation;
- добавить валидатор общей evidence revision и изображения до постановки задач;
- добавить отдельную news-only точку запуска для bounded smoke и планового news publisher;
- разделить Market Pulse и news scheduling, сохранив текущий общий content job только для
  обратной совместимости до отдельного выпуска;
- добавить Admin-счётчики `paired_pending`, `paired_enqueued`, `blocked_pair` и причины;
- не изменять уже созданные pending delivery ID и evidence: исправленный runtime должен
  безопасно подобрать существующую пару.

## 5. Обязательные тесты

- две pending стороны одной evidence ставятся обе, а не только первая;
- отсутствие Free или Pro блокирует всю группу;
- несовпадающие evidence ID, publisher, URL или image SHA блокируют группу;
- повторный запуск не создаёт вторую задачу;
- news-only run не создаёт `content/v1` и deal tasks;
- ошибка постановки второй задачи оставляет наблюдаемое состояние и не разрешает resume;
- delivery-off staging содержит ровно две задачи в PAUSED-очереди и одинаковый evidence;
- bounded production smoke подтверждает два `sendPhoto`, два Telegram message ID и одну
  factual revision в существующих Free/Pro-каналах.

## 6. Порядок выпуска

1. После утверждения реализовать R8.1.2.1 и пройти полный Python 3.11/security/IaC gate.
2. Собрать новый immutable digest; digest R8.1.2 `sha256:6d6d44e2…45aa` аннулировать как
   production-кандидат.
3. Повторить delivery-off staging с уже существующей pending парой и новым материалом.
4. Зафиксировать точные task payload, evidence/image SHA и отсутствие `content/v1`.
5. Получить отдельное разрешение владельца на production deploy R8.1.2.1.
6. Использовать backup `gs://avo-deal-sniper-firestore-exports/r812-production-20260730-100157`.
7. Выполнить delivery-off exact-digest deploy и paused-queue bounded news-only run.
8. Возобновить очередь только при наличии точной пары, проверить оба Telegram message ID,
   publisher `DubiCars`, URL, изображение и ответ чата.
9. Восстановить штатное расписание либо немедленно вернуть R8.1.1.

## 7. Критерий готовности

Релиз считается завершённым только когда одна и та же реальная статья с source-backed
изображением присутствует и в существующем Free, и в существующем Pro-канале, обе записи
содержат одинаковый evidence ID/image SHA, чат отвечает из этого evidence, а повторный
запуск не создаёт дубль.

## 8. Результат реализации

Реализованы pair-aware reconciliation, стабильный `news_pair_ready` gate, блокировка
неполной/несовпадающей пары, обязательная последовательность Pro → Free, отдельная команда
`python main.py news`, отдельные Cloud Run Job/Scheduler и Admin-счётчики
`paired_pending`, `paired_enqueued`, `blocked_pair`.

Локальный gate: Ruff, strict mypy, 136 passed / 2 skipped, покрытие 61,5%, dependency audit
без известных уязвимостей и Terraform validate. Контейнер закреплён на официальном
`python:3.11.15-slim-bookworm`; окончательная Python 3.11/Trivy проверка выполняется GitHub
Actions после публикации коммита. Staging и production в рамках этого шага не изменялись.
