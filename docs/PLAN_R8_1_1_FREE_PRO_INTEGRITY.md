# План R8.1.1 — целостность Free → Pro и запрет вымышленных данных

Статус: **ожидает утверждения владельца**.

## 1. Критический дефект

Текущая реализация ставит Free- и Pro-публикации одного решения в независимые задачи.
Cloud Tasks не гарантирует порядок их доставки. Плановый Market Watch дополнительно выбирает
объекты шире, чем строгий список публикуемых Pro-кандидатов. Поэтому объект может появиться
в Free раньше Pro либо вообще не получить полную Pro-карточку.

Такое поведение запрещено: Free-публикация обещает доступ к конкретному объекту и обязана
вести к уже существующей полной карточке именно этого объекта в Pro.

## 2. Непереговорные инварианты

1. Объект разрешён в Free только после подтверждённой доставки его полной карточки в Pro.
2. Связь определяется не названием автомобиля, а точным набором:
   `decision_id + listing_id + content_hash + recipient + template_version`.
3. Pro outbox обязан иметь состояние `sent` и непустой `telegram_message_id`.
4. Free payload обязан содержать `parent_pro_delivery_id`, `pro_message_id` и точную ссылку
   на соответствующее сообщение Pro.
5. `pending`, `sending`, `failed`, `unknown`, устаревшая или отсутствующая Pro-доставка
   блокирует Free fail-closed.
6. Изменение цены или объявления создаёт новую immutable revision. Старая Pro-карточка
   не разрешает Free-публикацию новой версии.
7. Ни объект, цена, фотография, ссылка, характеристики, рыночный диапазон, прибыль, ROI,
   риск, новость, дата или источник не могут быть придуманы, дополнены догадкой либо
   восстановлены моделью.
8. LLM не создаёт факты. Для новостей разрешены только source-backed заголовок, дата,
   издатель и прямая ссылка. Рекламный CTA отделён от фактического блока и не содержит
   утверждений об объекте или рынке.
9. Mock-данные запрещены в production и не могут попадать в outbox.

## 3. Немедленная защита

До production-выпуска R8.1.1 новые объектные Free-публикации должны быть выключены.
Pro, collectors, processing, личный бот и нефактический агрегированный контент продолжают
работать. Включение Free выполняется только после reconciliation уже опубликованных объектов.

## 4. Новый порядок публикации

```text
verified listing revision
    → deterministic decision
    → immutable Pro outbox
    → Telegram Pro delivery
    → state=sent + telegram_message_id
    → Free eligibility gate для той же revision
    → immutable Free outbox с parent_pro_delivery_id
    → Telegram Free delivery с точной ссылкой на Pro message
```

`process-listing` больше не ставит объектную Free-доставку напрямую. Он создаёт только
решение и Pro-кандидата. Free reconciler выбирает исключительно уже доставленные Pro-карточки.

## 5. Market Watch

- Объектные строки Market Watch формируются только из точных Pro deliveries со статусом `sent`.
- Для каждой строки сохраняются `decision_id`, `content_hash`, `pro_delivery_id` и
  `pro_message_id`.
- Если ни одного подтверждённого Pro-объекта нет, публикуется только агрегированная статистика
  с явным размером выборки либо публикация пропускается.
- Объекты `REJECT`, устаревшие решения и неподтверждённые detail pages исключаются.

## 6. Исправление уже опубликованных несоответствий

1. Построить reconciliation-отчёт по всем `sent` Free `free/v2` и `market-watch/v2`.
2. Для каждого Free объекта найти точную Pro revision, а не похожее название.
3. Если актуальный объект подтверждён и проходит все gates — сначала доставить Pro и получить
   message ID, затем обновить Free-пост точной ссылкой, если Telegram допускает редактирование.
4. Если объект устарел, не подтверждён либо не проходит gates — не создавать замену и не
   придумывать данные; Free-пост пометить как withdrawn либо удалить только после отдельной
   фиксации списка message ID.
5. Сохранить машинно-читаемый отчёт: `matched`, `repaired`, `withdrawn`, `manual_review`.

## 7. Изменения кода и данных

- Добавить `FreePublicationEligibility` с явными причинами блокировки.
- Добавить parent-поля в Free publication payload и immutable event.
- Добавить repository-запрос точной `sent` Pro revision.
- Удалить прямое создание Free target из `process_listing_task`.
- Перевести объектный Market Watch на Free reconciler.
- Добавить аудит `free_pro_integrity_gate` и счётчики в Admin Web:
  `eligible`, `blocked_no_pro`, `blocked_not_sent`, `blocked_revision_mismatch`, `repaired`.
- Кнопка Free ведёт к точной Pro-карточке; отдельная кнопка подписки остаётся только для
  пользователя, который ещё не состоит в Pro.

## 8. Проверки

Обязательные автоматические сценарии:

- Free не создаётся без Pro outbox;
- Free не создаётся при Pro `pending/sending/failed/unknown`;
- Free создаётся после Pro `sent` и содержит тот же `decision_id/content_hash`;
- изменение цены блокирует старую связь;
- конкурентные задачи не нарушают порядок;
- повторный запуск не создаёт дубль;
- REJECT и объект без detail-page evidence не попадают в Free;
- ни один production renderer не создаёт отсутствующие факты;
- новость без прямого источника, даты или automotive relevance блокируется;
- полный Python 3.11 quality/security/IaC gate проходит.

## 9. Выпуск

1. После утверждения плана реализовать код и миграцию payload без изменения production.
2. Выполнить delivery-off staging и сформировать reconciliation preview.
3. Зафиксировать immutable digest и rollback.
4. В production сначала выключить объектный Free output.
5. Развернуть API/publisher, выполнить reconciliation существующих сообщений.
6. Выполнить один bounded Pro → Free цикл в существующих каналах; отдельный тестовый канал
   не создаётся.
7. Подтвердить точное совпадение object revision и Telegram message IDs.
8. Только после этого включить регулярный Free output.

## 10. Критерии приёмки

- количество `sent Free object without sent exact Pro object` равно нулю;
- каждый новый Free-объект открывает существующую полную Pro-карточку той же revision;
- расхождение цены, ссылки, фото, характеристик и content hash равно нулю;
- никаких mock, synthetic или LLM-invented facts в production нет;
- повторный запуск не создаёт дублей;
- reconciliation старых публикаций завершён и приложен к release evidence;
- collectors, processing, бот, Pro и Free работают по расписанию после cutover.

До выполнения этих критериев R8.1.1 не считается завершённым.
