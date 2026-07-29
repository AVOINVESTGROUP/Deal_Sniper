# План R8 — восстановление Pro и разделение контуров

Статус: **утверждён владельцем 29 июля 2026 года**.

Статус исполнения: `R8.1-CODE` завершён локально; immutable build и `R8.1-STAGE`
ещё не выполнялись. Production остаётся на R6 и не изменён.

Утверждение разрешает реализацию и staging R8.1. Cloud production и Firebase
Authentication не изменяются до соответствующих отдельных разрешений.

## 1. Причина корректирующего релиза

Production работает на baseline R6. Реализация R7.1/R7.3 с периодической сверкой
Pro-сделок и новостей находится только в staging. Её production-выпуск был ошибочно
связан с незавершённой заменой входа Admin Web на Google Sign-In.

Это смешало независимые контуры:

1. сбор, проверка и расчёт автомобилей;
2. публикация Free/Pro-контента;
3. административная авторизация и Control Center.

Отказ или незавершённая настройка третьего контура не должен останавливать первые два.

## 2. Цель

Без остановки работающего R6 получить управляемый production-контур, который:

- регулярно публикует в Pro-канал только подтверждённые выгодные автомобили;
- публикует англоязычный дайджест новостей авторынка Dubai/UAE;
- доставляет реальные фотографии и прямые ссылки;
- не создаёт повторных сообщений;
- сохраняет работающий административный доступ на протяжении cutover;
- изолирует staging от production на уровне кода и Terraform.

## 3. Решение по архитектуре

```text
Data Plane
  collectors -> verification -> market/cost/risk/decision -> Firestore

Product Delivery Plane
  content publisher -> transactional outbox -> environment queue -> Telegram

Control Plane
  Admin Web -> Firebase Auth -> API Gateway -> Admin API
```

Правила зависимости:

- Data Plane не зависит от доступности Admin Web.
- Product Delivery читает последнюю активную versioned configuration, но не зависит от
  интерактивного входа администратора.
- Сбой Google/Firebase popup не останавливает Scheduler или publisher.
- Изменение способа входа выпускается отдельно от контентного runtime.

## 4. Границы R8.1 — Pro Recovery

В R8.1 входят:

- периодическая reconciliation текущих Pro-сделок;
- отдельная reconciliation Pro-новостей;
- стабильные PublicationEvent, delivery ID и transactional outbox;
- реальная Telegram-доставка текста и фотографии;
- лимиты одного запуска и интервалы публикаций;
- отдельные staging/production queues и recipients;
- контроль состояния публикаций в Admin Web;
- строгая проверка detail page до допуска объявления;
- component release manifest и rollback.

В R8.1 не входят:

- удаление существующего способа входа администратора;
- переключение Firebase Google provider;
- удаление Firebase account владельца;
- WhatsApp;
- Telegram MTProto sources;
- изменение модели Pro entitlement или цены;
- изменение финансовых формул.

## 5. Границы R8.2 — Admin Google Auth

R8.2 выполняется только после успешного production pilot R8.1.

В него входят:

- корректный Firebase Web OAuth client;
- Google popup и redirect fallback;
- `email_verified=true` и серверный `ADMIN_EMAILS`;
- проверенный резервный административный доступ до завершения production smoke;
- независимый Hosting release и rollback.

R8.2 не изменяет collectors, publisher, очереди, финансовые решения или Telegram delivery.

## 6. Этап R8.1-DOC — документация

1. Сделать этот план частью canonical implementation plan.
2. Согласовать `SPEC.md`, `README.md`, `CLOUD_ARCHITECTURE.md` и `AI_CONTEXT.md`.
3. Зафиксировать production baseline R6 и staging-кандидаты R7 как evidence, а не как
   разрешение на production.
4. Получить явное утверждение владельца до изменения кода.

## 7. Этап R8.1-CODE — минимальный контентный кандидат

1. Сохранить текущий рабочий production-способ входа Admin Web.
2. Скрыть Google-only переход за отдельным выключенным feature flag до R8.2.
3. Оставить backend-проверку Firebase ID token, `email_verified` и `ADMIN_EMAILS`.
4. Вынести Pro publisher в независимую release boundary внутри репозитория.
5. Добавить компонентный manifest: commit, API digest, publisher digest, schema,
   template versions и compatibility contract.
6. Проверить обратную совместимость `/tasks/deliver-content` с `pro/v1` и
   `pro-news/v1`.
7. При `DELIVERY_ENABLED=false` разрешить запись outbox, но запретить создание Cloud
   Task. Повторный разрешённый запуск должен поставить сохранённый `pending` в очередь.

## 8. Этап R8.1-ISO — изоляция окружений

Terraform создаёт и связывает разные ресурсы:

| Назначение | Staging | Production |
|---|---|---|
| Firestore | отдельная named database | production database |
| Delivery queue | `telegram-delivery-staging` | `telegram-delivery` |
| Publisher Job | `deal-sniper-publisher-staging` | `deal-sniper-publisher` |
| Telegram recipient | test Pro channel | production Pro channel |
| Delivery | включается только на controlled smoke | включается после cutover gate |

Fail-fast правила:

- staging recipient не равен production recipient;
- staging job не может ссылаться на production queue;
- production job не принимает staging database;
- отсутствующий environment marker запрещает delivery;
- тесты проверяют Terraform wiring и runtime validation.

## 9. Этап R8.1-DQ — шлюз качества объявления

До финансового решения и публикации detail page подтверждает:

- объявление доступно и относится к автомобилю;
- цена является полной фиксированной ценой в AED;
- цена на detail page совпадает с нормализованной ценой;
- отсутствуют `Price on request`, deposit, downpayment и monthly payment;
- цена не равна placeholder или аномально низкому техническому значению;
- известны make, model и year;
- evidence имеет `valid_until > now`;
- ссылка и хотя бы одна фотография доступны;
- рынок содержит требуемое число свежих verified comparables;
- decision создан действующей financial configuration.

Непрошедшее объявление сохраняется с причиной quarantine, но не попадает в Free, Pro,
персональные рекомендации или verified market.

## 10. Этап R8.1-TEST — автоматические проверки

Обязательны:

- unit tests финансовых и quality gates;
- contract tests `pro/v1` и `pro-news/v1`;
- два запуска publisher без дублей;
- `DELIVERY_ENABLED=false` создаёт ноль Cloud Tasks;
- проверка несовпадающих staging/production ресурсов;
- проверка фотографии, ссылки и Telegram HTML limits;
- проверка outbox `pending -> sending -> sent` и provider message ID;
- Ruff, strict mypy, pytest, coverage, dependency audit, Terraform validate и container scan.

## 11. Этап R8.1-STAGE — настоящий staging smoke

Используется отдельный тестовый Telegram Pro-канал. Фиктивный recipient и paused queue
не являются достаточным доказательством доставки.

Порядок:

1. Развернуть immutable API/publisher artifacts только в staging.
2. Включить staging delivery с лимитом `1 deal + 1 digest`.
3. Опубликовать одну реальную Pro-карточку с фотографией и прямой ссылкой.
4. Опубликовать один англоязычный news digest с прямыми ссылками на издателей.
5. Повторить publisher и доказать отсутствие дублей.
6. Проверить outbox, task name, Telegram chat ID и message ID.
7. Остановить staging delivery и приложить скриншоты/ID без секретов к release evidence.

## 12. Этап R8.1-PROD — ограниченный cutover

Требует отдельной команды владельца **«Разрешаю production deploy R8.1»**.

1. Сохранить active configuration и состояние outbox.
2. Остановить только content publisher schedule.
3. Развернуть проверенные immutable artifacts и подтвердить component manifest.
4. Не менять Admin Auth, collectors, processing и Free delivery.
5. Выполнить один bounded run: максимум одна Pro-сделка и один digest.
6. Владелец проверяет сообщение непосредственно в production Pro-канале.
7. При успехе возобновить publisher schedule.
8. При ошибке вернуть прежние artifacts/configuration; новые ambiguous delivery не
   повторять автоматически.

## 13. Критерии приёмки R8.1

R8.1 завершён только если:

- Pro-канал получил настоящее англоязычное объявление с фотографией;
- цена совпадает с актуальной detail page;
- карточка содержит verified market, max purchase, costs, profit, ROI, confidence,
  risks и прямую ссылку;
- опубликован свежий англоязычный news digest;
- ссылки новостей ведут к исходным издателям, а не только к агрегатору;
- повторный запуск не создал дублей;
- outbox имеет `sent` и Telegram message ID;
- Admin Web оставался доступен на всём протяжении cutover;
- Free-канал, личный бот, collectors и processing не деградировали;
- rollback проверен и не требует миграции данных.

## 14. Наблюдаемость

Control Center отдельно показывает:

- active version каждого компонента;
- время последнего успешного Pro deal и news digest;
- publishable/missing/pending/sending/sent/failed/unknown;
- причину quarantine объявления;
- активные recipient, queue и environment без показа секретов;
- кнопку bounded publish с явным подтверждением;
- preview/apply/rollback versioned configuration.

Надпись `implemented` не означает `active in production`. Для каждой функции показываются
отдельные состояния: `documented`, `implemented`, `staging verified`, `production active`.

## 15. Rollback

- Publisher и API откатываются по immutable digest из component manifest.
- Runtime configuration переключается на предыдущую immutable revision.
- Publisher schedule остаётся остановленным до сверки outbox.
- `unknown` не переотправляется автоматически.
- Откат R8.1 не меняет Firebase Auth и не требует восстановления административного
  пользователя.

## 16. Порядок утверждений

```text
R8.1-DOC   утверждение этого плана
R8.1-CODE  реализация и локальные проверки
R8.1-STAGE immutable build и настоящий Telegram staging smoke
R8.1-PROD  отдельное разрешение production deploy
R8.1-PILOT отчёт и утверждение результата
R8.2-DOC   отдельное утверждение Google Auth
```

Утверждение R8 не является разрешением на production deploy.
