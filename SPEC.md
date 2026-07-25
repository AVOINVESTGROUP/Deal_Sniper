# Спецификация Dubai Deal Sniper

## 1. Назначение

Сервис находит автомобили с фиксированной ценой в ОАЭ, которые потенциально можно купить ниже подтверждённого рынка с заданной прибылью и ROI. Пользователь получает объяснимое решение `CONTACT`, `INSPECT`, `WATCH`, `REJECT` либо `INSUFFICIENT_DATA`.

В продукт не входят недвижимость, аукционы, ставки, автоматическая покупка и автоматическое общение с продавцом.

## 2. Результат расчёта

Полное решение содержит:

- точную версию объявления и подтверждённую цену;
- нижнюю, медианную и верхнюю границы рынка;
- максимальную цену покупки;
- inspection, registration, preparation, repair, holding, capital, selling и risk costs;
- ожидаемую прибыль и ROI;
- риски, причины решения, уверенность и использованные аналоги;
- версии движка/конфигурации и semantic market fingerprint.

Финансовая арифметика выполняется `Decimal`-алгоритмами. Одинаковые канонические входы дают одинаковый decision ID. LLM может только обогащать текст и не участвует в финансовом решении.

## 3. Источники и достоверность

Production-адаптеры: DubiCars, CarSwitch, Cars24 UAE, OpenSooq UAE. Каждый источник имеет независимые настройки, health и переключатель. Коллектор обязан сохранить raw HTML/JSON в Cloud Storage до parsing.

Объявление допускается к расчёту только если:

1. имеет фиксированную цену в AED;
2. detail page принадлежит заявленному источнику и listing;
3. подтверждённая цена отличается от snapshot не более чем на 3%;
4. `freshness_status=active` и `valid_until > now`;
5. версия остаётся current.

`Price on request`, неверная валюта, несовпадающая страница, подозрительно низкая цена и постоянная ошибка переводят запись в quarantine/reject. Временная ошибка повторяется по retry policy, но не создаёт сигнал.

Semantic evidence revision неизменяема. Повторная успешная проверка той же цены обновляет только `last_checked_at` и `valid_until`, не меняя evidence, decision и delivery IDs.

## 4. Версионирование и идентичность

- raw snapshot и исторические версии неизменяемы;
- current pointer меняется транзакционно по серверной последовательности и tie-breaker;
- запоздавшая версия сохраняется, но не становится current;
- task всегда адресует `listing_id + content_hash`;
- старый snapshot не рассчитывается и не доставляется;
- cross-source дубли объединяются до построения рынка;
- отсутствие объявления на первой странице не равно удалению.

Канонические ID используют UTF-8/NFC, отсортированные ключи JSON, точное представление Decimal/UTC и SHA-256 lowercase. `null` и отсутствующее поле различаются.

## 5. Рынок и решение

Comparable Engine использует только verified/current/fresh аналоги того же нормализованного make/model, затем применяет ограничения year, mileage, trim/specification и robust-очистку MAD. Один физический автомобиль учитывается один раз.

Решение не публикуется, если аналогов меньше настроенного минимума, данные просрочены, прибыль/ROI ниже порога, цена выше максимальной покупки либо сработал hard-stop риска. `INSPECT` означает финансово подходящий автомобиль, которому нужна проверка, а не отрицательную сделку.

При изменении объявления пересчитываются current-решения затронутого make/model, потому что market fingerprint изменился.

## 6. Доставка

Delivery строится через transactional outbox. Идентичность subject/recipient разделена: одно решение независимо доставляется пользователю, Free и Pro каналам. Состояния: `pending`, `sending`, `sent`, `failed`, `unknown`.

После неоднозначного timeout запись становится `unknown` и автоматически не повторяется. Администратор выполняет reconcile: `mark_sent`, `mark_failed` или единственный `retry_once`. Перед отправкой повторно проверяется current snapshot.

Free teaser не раскрывает цену, ссылку, ID, рынок, прибыль или ROI. Pro-карточка содержит полный audit trail. WhatsApp разрешён только для opt-in получателей через официальный Cloud API; без Meta credentials fail-closed.

## 7. Пользовательские функции

Telegram-бот и TMA используют один Application API. Поддерживаются RU/EN запросы по make/model, бюджету, году, mileage, specification, body type, profit и ROI. Неизвестные параметры не выдумываются: бот показывает распознанные фильтры для подтверждения. Saved searches, settings, favorites и outcomes изолированы по owner ID.

Admin Web использует Firebase Authentication и admin claim/allowlist. Панель показывает состояние источников/pipeline, previews, контент и outbox reconciliation, но никогда не показывает секреты.

## 8. Контент

Плановые форматы: Market Pulse, price drop, weekly review, deal analysis и audience poll. Каждый материал имеет период, выборку, provenance, template version и PublicationEvent. Финансовые утверждения строятся только из verified данных.

## 9. Нефункциональные требования

- Python 3.11 и type hints;
- Firebase/Google Cloud без обязательного VPS;
- Firestore и Cloud Storage вместо локального production-файла;
- идемпотентные Jobs/Tasks, retry/backoff/rate limits;
- Secret Manager и минимальные service-account permissions;
- structured logs, metrics, alerts и budget alerts;
- immutable image digest от staging до production;
- migration ledger, checkpoints, checksums, rehearsal и rollback export;
- CI: Ruff, mypy, pytest, coverage, pip-audit, Terraform validate и Trivy.

## 10. Критерий production-ready

Production разрешено возобновить только когда один RC commit собран в immutable runtime/migration digests, тот же migration digest прошёл staging restore/rehearsal, production migration завершена с delivery disabled, `main` указывает на RC, runtime digest развёрнут и `/version` подтверждает commit/digest/schema. Resume выполняется collectors → processing → delivery; затем проходит пилот 100–300 объявлений без ложных цен, утечек Free и неконтролируемых дублей.
