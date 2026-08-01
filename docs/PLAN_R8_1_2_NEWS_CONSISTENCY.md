# План R8.1.2 — единый проверяемый контур новостей

Статус: **утверждён владельцем; локальная реализация и проверка завершены, production не изменён**.

## 1. Подтверждённый дефект

29 июля 2026 года Pro-канал успешно опубликовал материал DubiCars, а через несколько секунд
бот в связанном чате ответил, что новостная лента недоступна. В той же Pro-публикации ссылка
и Telegram preview вели на DubiCars, но издателем был указан `Google News`.

Read-only проверка подтвердила:

- Pro-публикатор читает управляемый `news_feed_registry`, а при пустом реестре использует
  environment fallback;
- чат использует отдельный глобальный `DubaiAutoNewsClient` и напрямую читает только
  `AUTO_NEWS_RSS_URL` при каждом запросе пользователя;
- production `news_feed_registry` пуст;
- fallback присваивает RSS `https://www.dubicars.com/news/feed` издателя `Google News`;
- RSS DubiCars указывает собственный домен и название канала `DubiCars – New and Used Cars`;
- в 13:16 GST publisher создал одну news delivery, в 13:17 delivery прошла, после чего webhook
  чата независимо вернул пустой результат без использования уже подтверждённой новости.

Следовательно, проблема вызвана двумя источниками истины, отсутствием сохраняемого news
evidence и недостоверным fallback provenance.

## 2. Непереговорные инварианты

1. Pro-канал, личный бот и связанный чат читают один и тот же набор подтверждённых новостей.
2. Заголовок, URL, дата и издатель берутся только из полученного source evidence.
3. Издатель обязан соответствовать проверенной конфигурации ленты и домену конечного URL.
4. `Google News` нельзя указывать издателем прямой статьи DubiCars.
5. LLM не создаёт заголовки, даты, издателей, ссылки, события, числа или рыночные факты.
6. Ошибка live-fetch не отменяет уже сохранённую свежую evidence revision.
7. Если свежего evidence нет, система сообщает об отсутствии данных и ничего не придумывает.
8. Одинаковая статья имеет один semantic fingerprint во всех интерфейсах и доставках.

## 3. Целевая схема

```text
управляемый news_feed_registry
    → единый NewsIngestionService
    → HTTPS fetch + redirect resolution
    → relevance/freshness/domain/provenance validation
    → immutable news_evidence revision
    → active fresh news index
       ├─ Pro digest
       ├─ ответ личного бота
       └─ ответ бота в связанном чате
```

Ни один пользовательский путь не обращается к отдельному URL в обход реестра и evidence.

## 4. Модель `news_evidence`

Каждая подтверждённая статья сохраняет:

- `evidence_id` и `semantic_fingerprint`;
- `feed_id` и immutable revision конфигурации ленты;
- `publisher_name` и разрешённые домены издателя;
- исходный и конечный canonical URL после redirect;
- исходный заголовок, summary и `published_at`;
- `fetched_at`, `last_checked_at`, `valid_until` и `freshness_status`;
- результат automotive/UAE relevance gate;
- hash исходного RSS/Atom item.

Повторная проверка неизменившейся статьи обновляет только operational freshness. Изменение
source-backed полей создаёт новую immutable revision.

## 5. Исправление provenance

- Удалить fallback `publisher="Google News"`.
- Создать обязательную production-конфигурацию DubiCars с издателем `DubiCars` и allowlist
  доменов `dubicars.com`/`www.dubicars.com`.
- Значение `<source>` или `<author>` не может переопределить проверенного издателя ленты.
- Если final URL не принадлежит allowlist издателя, item блокируется и фиксируется как
  `publisher_domain_mismatch`.
- Заголовок RSS-канала используется только как проверочный сигнал, а не как свободная замена
  издателя.

## 6. Поведение чата и Pro

- Publisher сначала выполняет ingestion, затем строит digest только из активного evidence.
- Бот отвечает из того же активного evidence, а не выполняет отдельный одиночный fetch.
- При временной ошибке источника разрешён последний evidence с `valid_until > now`; в ответе
  показываются фактический издатель и дата публикации.
- При отсутствии свежего evidence возвращается честное сообщение без вымышленной новости.
- Уже опубликованная свежая Pro-новость должна быть доступна в чате в тот же момент.

## 7. Исправление существующих данных

1. Найти `pro-news/v1`, где publisher не соответствует домену URL.
2. Не переписывать историю как будто ошибка не происходила: сохранить audit event.
3. Для текущей ошибочной публикации выполнить Telegram edit только из повторно проверенного
   source evidence; при невозможности редактирования опубликовать короткое исправление.
4. Пересчитать fingerprint только для новой template version `pro-news/v2`, не создавая
   повторной публикации одной и той же статьи.

## 8. Изменения кода и интерфейса

- Ввести единый `NewsIngestionService` и repository-контракт для `news_evidence`.
- Удалить глобальный независимый `news_client` из webhook-пути.
- Перевести `pro_news` и chat intent `NEWS` на единый query service.
- Добавить в Admin Web состояние каждой ленты: publisher, домены, last success/error,
  количество принятых/отклонённых items и причины отклонения.
- Запретить включение ленты до live validation publisher/domain/relevance.
- Добавить admin preview точного текста и provenance до публикации.

## 9. Обязательные тесты

- DubiCars URL всегда отображается с publisher `DubiCars`;
- конфликт `<source>Google News</source>` и домена DubiCars не подменяет издателя;
- несовпадающий домен блокируется;
- Pro и чат получают один evidence ID и одинаковые фактические поля;
- transient live-fetch failure использует только ещё свежий сохранённый evidence;
- истёкший evidence не выдаётся;
- пустой evidence не приводит к генерации заголовка;
- повторный ingestion и publisher run не создают дублей;
- Vertex AI не может изменить фактические поля;
- миграция ошибочного outbox сохраняет аудит и идемпотентна.

## 10. Выпуск

1. После утверждения реализовать модель, сервис, миграцию и тесты без изменения production.
2. Прогнать полный quality/security/IaC gate.
3. Собрать immutable image и выполнить delivery-off staging с fixture двух лент и transient
   failure.
4. Проверить одинаковый evidence в Pro preview и chat response.
5. Перед production сохранить backup и зафиксировать список ошибочных публикаций.
6. Развернуть exact digest, создать проверенную DubiCars registry entry и отключить старый
   environment fallback.
7. Выполнить один bounded ingestion/publication cycle в существующих каналах.
8. Подтвердить Telegram message ID, publisher, URL, дату и ответ чата; затем вернуть расписание.

## 11. Критерии приёмки

- расхождение publisher и URL domain равно нулю;
- расхождение фактических полей Pro и чата равно нулю;
- бот не сообщает о недоступности при наличии свежей опубликованной evidence;
- у каждой новости есть сохранённая source-backed evidence revision;
- вымышленные либо восстановленные моделью факты отсутствуют;
- повторные запуски не создают дублей;
- Admin Web показывает здоровье и причины отклонения каждой ленты;
- release evidence содержит staging и production smoke с точными evidence/message IDs.

## 12. Дополнение: иллюстрированные новости в Free-канале

Read-only проверка production outbox выявила ещё один дефект исходного контракта:

- все 31 записи `content/v1` для `@Dubai_Auto_Invest` не содержат `image_url`;
- три записи `pro-news/v1` также не содержат `image_url`;
- модель `NewsItem` хранит только title, publisher, URL, date и summary;
- `run_content_publication` направляет новости только в Pro, а в Free независимо отправляет текстовый Market Pulse;
- изображение, иногда видимое в Pro, является случайным Telegram link preview и не контролируется приложением.

Следовательно, Free-новости с иллюстрациями сейчас не реализованы. Market Pulse не является новостью и не должен подменять новостную ленту.

### 12.1. Контракт изображения

Каждая канальная новость обязана иметь source-backed изображение из одного из допустимых источников:

1. RSS/Atom `media:content`, `media:thumbnail` или image enclosure;
2. `og:image` или `twitter:image` канонической страницы издателя;
3. отсутствие проверенного изображения делает материал непригодным для канальной публикации.

Запрещены сгенерированные изображения, случайные stock-фото, изображения другой статьи и восстановление URL моделью. LLM не выбирает и не создаёт иллюстрацию.

При ingestion сохраняются исходный и конечный image URL, тип источника изображения, MIME type, размер, width/height при наличии, SHA-256 файла, publisher/feed/evidence ID и результат проверки.

Разрешены только HTTPS, настоящий `image/*`, ограниченный размер и домен издателя либо явно настроенный CDN-домен этой ленты. HTML, tracking pixel, placeholder и недоступный файл блокируются.

Проверенный файл сохраняется как immutable asset в Cloud Storage. Telegram delivery загружает именно этот сохранённый asset, поэтому публикация не зависит от последующего hotlink, удаления файла издателем или поведения link preview.

### 12.2. Free и Pro используют одно evidence

Одна подтверждённая статья создаёт один immutable `news_evidence`, но отдельные версионированные представления:

- `free-news/v1` — изображение, заголовок, фактический издатель, дата, короткий source-backed анонс и кнопка чтения статьи;
- `pro-news/v2` — то же изображение/evidence плюс расширенный проверяемый контекст и допустимое Vertex AI-вступление без новых фактов;
- личный бот и связанный чат читают то же evidence.

Free и Pro payload обязаны содержать одинаковые `evidence_id`, `semantic_fingerprint`, publisher, article URL и image SHA-256. Отличаться может только объём представления и CTA.

Каждая статья публикуется отдельной карточкой с изображением. Нельзя прикреплять одно hero-изображение к дайджесту из нескольких несвязанных статей.

### 12.3. Доставка и отказоустойчивость

- для канальных новостей разрешён только `sendPhoto` с caption и inline-кнопками;
- при ошибке загрузки или отправки изображения нельзя молча переходить на `sendMessage`;
- временная ошибка получает bounded retry, terminal ошибка остаётся видна в outbox/Admin Web;
- один `evidence_id + recipient + template_version` имеет стабильный delivery ID;
- повторный ingestion, publisher или delivery не создаёт дубликаты;
- текстовый Market Pulse остаётся отдельной аналитической рубрикой и не учитывается как news-card.

### 12.4. Управление в Admin Web

Для каждой новости показывать thumbnail проверенного изображения, publisher, article/image domains, image status, MIME, размер, SHA-256, состояния Free/Pro delivery, Telegram message ID, причину блокировки и preview обеих карточек.

### 12.5. Дополнительные тесты и критерии приёмки

- RSS media image и page `og:image` корректно извлекаются и связываются с evidence;
- redirect на неподтверждённый image domain блокируется;
- HTML вместо изображения, pixel и oversized asset блокируются;
- материал без source-backed изображения не попадает в каналы;
- Free и Pro получают одну статью с одинаковым image SHA-256;
- `sendPhoto` проверяется контрактным Telegram payload test;
- ошибка `sendPhoto` не создаёт текстовую публикацию без изображения;
- production smoke подтверждает реальный image message ID в существующих Free и Pro каналах без создания тестового канала;
- после выпуска новые канальные news deliveries без изображения равны нулю.
