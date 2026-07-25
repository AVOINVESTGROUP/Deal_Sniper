# Контекст проекта: Dubai Deal Sniper

Этот файл содержит описание структуры папок, архитектуры проекта и статус разработки.

GitHub: `https://github.com/AVOINVESTGROUP/Deal_Sniper` (public).

## Current verified state

- Default-ветка `main` содержит legacy mock/SQLite/Gemini pipeline и не воспроизводит Google Cloud deployment.
- Draft PR #1 является крупным монолитным изменением кода, Terraform и документации; он не утверждён и не должен сливаться.
- Google Cloud временно использует образ из неслитой ветки с известными дефектами snapshot provenance, owner scope, ролей, verified market и delivery.
- Зелёный CI подтверждает текущие Ruff/mypy/pytest/Terraform checks, но не подтверждает экономическую корректность, конкурентность Firestore, изоляцию пользователей и документацию.
- Канонический следующий порядок: после утверждения плана отдельно разрешить `0.11-STOP`, затем выполнить `0.11R`, `0.11A`, `0.11B`, `0.11C`, immutable candidate `0.11RC`, миграцию `0.11M`, baseline `0.11D` и официальный пилот `0.11P`.
- Код следующих релизов и состояние production не изменяются без утверждения плана и отдельного разрешения на `0.11-STOP`.

## Known blockers

- processing task может связать решение не с тем snapshot;
- Firestore watchlist не изолирован по владельцу, а административные команды не отделены от обычного allowlist;
- current listing допускает out-of-order overwrite;
- временная detail verification ошибка теряется как успешная task;
- неподтверждённые цены могут влиять на рынок аналогов;
- Cost/Risk/Comparable и entity resolution не приняты как надёжные;
- delivery не имеет строгой exactly-once гарантии и reconciliation состояния `unknown`;
- существующие данные требуют schema migration и полного пересчёта verified market;
- прежние pilot/backfill результаты являются диагностическими и не доказывают precision.
- текущий код не имеет application-level delivery kill switch; до `0.11A/0.11C` STOP возможен только инфраструктурными controls;
- immutable release candidate и RC manifest ещё не реализованы, поэтому production migration запрещена;
- текущие decision/delivery модели ещё не прошли разделение `decision_subject_id` и `delivery_recipient_id`;
- operational verification refresh ещё требует исправления, чтобы не менять semantic fingerprint и не создавать повторную публикацию.
- протокол второй проверки и открытые решения владельца сохранены в `docs/PLAN_REVIEW_2026-07-24.md`.
- третья проверка не утвердила план; исправления approval gates, repository gate, STOP watermark, migration replay, canonical ID и pilot order сохранены в `docs/PLAN_REVIEW_2026-07-24-R3.md`.
- четвёртая проверка также не утвердила план; инфраструктурный STOP, immutable `0.11RC`, разделение decision subject/recipient и semantic fingerprint описаны в `docs/PLAN_REVIEW_2026-07-25-R4.md`.

## Historical implementation log — SUPERSEDED как описание текущего состояния

Следующие разделы сохраняются как история действий. Отметка `[SUPERSEDED]` означает, что утверждение не является действующей гарантией и требует повторной приёмки после `0.11D`.

## Историческая структура default-ветки `main`

```
C:\Dev\Deal_Sniper
├── docs/
│   ├── STEPS.md            # Журнал выполненных шагов и прогресса
│   ├── IMPLEMENTATION_PLAN.md # Поэтапный план: Telegram-бот, затем TMA
│   ├── CLOUD_ARCHITECTURE.md # Целевая Firebase/Google Cloud архитектура
│   └── legacy/             # Неисполняемый архив исключённых прототипов
├── src/
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base_scraper.py  # Базовый абстрактный класс для парсеров
│   │   └── dubizzle_mock.py # Мок-парсер для Dubizzle
│   ├── __init__.py
│   ├── models.py           # Pydantic-модели данных
│   ├── evaluator.py        # Оценщик сделок с помощью Gemini API
│   ├── db.py               # Legacy SQLite-прототип; целевая БД — Cloud Firestore
│   └── notifier.py         # Telegram-оповещатель
├── .env.example            # Пример файла настроек окружения
├── .gitignore              # Исключения Git
├── requirements.txt        # Список зависимостей Python
├── SPEC.md                 # Техническая спецификация проекта
├── AI_CONTEXT.md           # Этот файл (описание проекта)
├── GEMINI.md               # Документация по Vertex AI Gemini
├── AGENTS.md               # Документация/правила для агентов
└── main.py                 # Главный оркестратор сервиса
```

## Исторический статус — SUPERSEDED

- [x] Создана техническая спецификация `SPEC.md`.
- [x] Создан файл контекста `AI_CONTEXT.md`.
- [x] Определение правил для агентов (`AGENTS.md`).
- [x] Определение инструкций по Gemini (`GEMINI.md`).
- [x] Инициализация виртуального окружения Python и установка зависимостей.
- [x] Разработка модулей сбора и обработки данных.
- [x] Полное завершение Фазы 1 и Фазы 2.

## Пересмотр концепции от 23 июля 2026 года

- Дальнейший продуктовый контур ограничен только автомобилями; недвижимость исключена.
- Текущая схема `новое объявление → Gemini → is_deal` признана недостаточной для решения о покупке автомобиля.
- Целевой результат системы: максимальная цена покупки, диапазон чистой прибыли, ROI, уровень уверенности, риски и рекомендуемое действие.
- Аукционы полностью исключены из продуктового контура: нет ставок, таймеров, live-мониторинга и аукционных комиссий. Активные источники — только объявления с фиксированной ценой.
- Первый интерфейс MVP — простой Telegram-бот. Telegram Mini App не входит в начальный MVP и разрабатывается после пилота поверх стабильного Application API.
- Backend, коллекторы, расчёты и фоновые задачи работают независимо от Telegram; бот и будущая TMA являются пользовательскими клиентами одной бизнес-логики и базы данных.
- Целевой backend полностью размещается в Firebase/Google Cloud: Cloud Run Service и Jobs, Cloud Scheduler, Cloud Tasks, Cloud Firestore, Cloud Storage, Secret Manager, Cloud Logging/Monitoring и Vertex AI.
- Отдельный VPS, PostgreSQL, Redis и Celery не входят в первый MVP. Текущая SQLite реализация считается локальным legacy-прототипом и не задаёт целевую архитектуру.
- Будущая TMA размещается на Firebase Hosting, использует Firebase Authentication после проверки Telegram `initData` и обращается к тому же Cloud Run API.
- Vertex AI Gemini через `google-genai` используется для извлечения признаков и объяснения, но не как источник рыночной цены или финансовой арифметики. Production-аутентификация выполняется service account без API-ключа.
- Концептуальный отчёт сохранён в `docs/concept-cars-report.html`; канонический исходный артефакт — `docs/concept-cars-artifact.json`.
- Целевая карта включает 15 источников и внутренних наборов: классифайды, C2B-ориентиры, certified retail, RTA/инспекции, стоимость деталей и собственный outcome loop.
- Для всех внешних источников требуется `source_registry` с ролью, типом цены, доверием, способом доступа и состоянием адаптера; одинаковые автомобили между сайтами должны объединяться до расчёта рынка.
- `SPEC.md` переписан для автомобилей с фиксированной ценой; недвижимость и аукционы явно исключены. Бизнес-пороги и целевой сегмент автомобилей остаются конфигурацией, которую нужно утвердить до пилота.
- Детальный порядок разработки и критерии готовности релизов закреплены в `docs/IMPLEMENTATION_PLAN.md`.
- План реализации пересобран: сначала безопасный baseline и детерминированное расчётное ядро на fixture-данных, затем Vertex AI, Google Cloud, Telegram-бот, пилот, дополнительные источники и TMA.
- Проверка источников в плане ограничена техническими параметрами интеграции: форматами, авторизацией, лимитами, стабильностью схемы, частотой и стоимостью обработки.
- Исходный код и документация опубликованы в публичном GitHub-репозитории `AVOINVESTGROUP/Deal_Sniper`; основная ветка — `main`.
- `docs/IMPLEMENTATION_PLAN.md` переработан в черновик для согласования из 12 вертикальных релизов: baseline, контракт данных, минимальный cloud/Telegram skeleton, реальный источник и история цены, нормализация, расчётные движки, многопользовательский бот, Vertex AI enrichment, расширение источников, пилот и TMA.
- Владелец проекта подтвердил переход от согласования документации к полной реализации рабочего бота; релизы выполняются последовательно до работающего канального режима.
- [SUPERSEDED] После команды владельца перейти к результату был реализован локальный вертикальный срез; гарантия идемпотентной публикации не принята аудитом.
- Рабочие команды: `python main.py scan`, `python main.py bot` и `python main.py publish`. Для фактической Telegram-проверки требуются локальные `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS` и, для канала, `TELEGRAM_CHANNEL_ID`.
- Production backend развёрнут в Google Cloud проекте `avo-deal-sniper`: приватный Cloud Run API, публичный API Gateway для Telegram webhook, Firestore, Secret Manager и Cloud Run Jobs.
- Telegram-бот работает из Google Cloud; канал публикации — `@Dubai_Auto_Invest`.
- [SUPERSEDED] Задача `deal-sniper-publisher` была развёрнута и прошла smoke run; экономическая корректность и доставка требуют повторной приёмки.
- Cloud Scheduler запускает `deal-sniper-publisher` каждые 10 минут по часовому поясу `Asia/Dubai`; проверен запуск именно через Scheduler.
- Реальные источники объединяются композитным адаптером; ошибка одной площадки не останавливает остальные.
- Зарегистрированные реальные источники: DubiCars, CarSwitch, Cars24 UAE и OpenSooq UAE. Включение и отключение хранится в `source_registry` Firestore и управляется командами Telegram.
- Команды администратора источников: `/sources`, `/source_on`, `/source_off`, `/source_add`, `/source_remove`, `/source_scan`.
- [SUPERSEDED] Первая реализация claim `update_id` подавляет повтор, но может потерять side effect после ошибки; исправление запланировано в `0.11A`.
- Cars24 smoke test от 24 июля 2026 года: 75 уникальных машин на трёх страницах, у всех распознаны цена и пробег.
- Production-релиз `0.2.2` развёрнут в Cloud Run; Scheduler снова включён с периодом 10 минут, Telegram command menu обновлено.
- В рабочей ветке подготовлено расчётное ядро 2.0: нормализация, строгий cross-source identity resolution, отбор аналогов по году/пробегу/trim/specification и полная структура расходов.
- Решения имеют `engine_version`; повторный запуск не пересчитывает ту же версию snapshot тем же алгоритмом, но позволяет контролируемо пересчитать данные после обновления движка.
- Raw-ответы источников архивируются до parsing; production URI имеет вид `gs://.../raw/{source}/...`.
- Production pipeline разделён на collector Jobs, очередь `listing-processing` и очередь `telegram-delivery`.
- Telegram webhook не выполняет долгий сбор: `/scan` только запускает фоновые collector Jobs.
- Пользовательские фильтры и действия хранятся в Firestore независимо для каждого Telegram user ID.
- Production image `0.4.3` добавляет OpenSooq, пакетную запись объявлений, ограниченный запрос аналогов по марке/модели, параллельную постановку backfill в Cloud Tasks, понятный статус `/sources`, полную выборку кандидатов для `/deals` и локализованную Telegram-доставку.
- Рабочие production jobs: `deal-sniper-collector-dubicars`, `deal-sniper-collector-carswitch`, `deal-sniper-collector-cars24`, `deal-sniper-collector-opensooq`.
- Raw bucket: `avo-deal-sniper-raw-snapshots`; очереди: `listing-processing`, `telegram-delivery`.
- Terraform в `infra/terraform` прошёл `terraform validate`; существующие ручные ресурсы требуют import до apply.
- Decision Engine `2.2.1`: расширенный рынок пересчитывается только после завершения общего backfill; `INSPECT` означает экономически подходящую сделку с warning, отрицательная прибыль всегда `REJECT`.
- Production backfill 24.07.2026: 2 042 объявления, 2 042 решения (`CONTACT` 1, `INSPECT` 6, `WATCH` 4, `REJECT` 427, `INSUFFICIENT_DATA` 1 604), экономических нарушений в публикуемой выборке — 0.
- Cloud Run Job `deal-sniper-publisher` описана в Terraform и получает обязательные `RAW_SNAPSHOTS_BUCKET`, Firestore и Telegram параметры; ручное исправление production не должно теряться при следующем развёртывании.
- Telegram channel locale всегда `en`. В личном чате язык берётся из Telegram `from.language_code`, сохраняется в `UserSettings.language_code`; поддерживается русский, остальные локали получают английский fallback.
- `/id` возвращает Telegram chat ID и user ID раздельно; это используется для подключения закрытого Pro-канала.
- Монетизация начинается с закрытого канала: `TELEGRAM_PRO_CHANNEL_ID` имеет приоритет над публичным `TELEGRAM_CHANNEL_ID` для полных карточек и publisher job.
- [SUPERSEDED] Publisher читает исторические решения, но правило current/superseded и delivery identity недостаточны; исправление запланировано в `0.11A/0.11B`.
- Инцидент 24.07.2026: DubiCars `Price on request` был ошибочно преобразован в 999/1 109 AED. Контур остановлен; API `0.6.0`/Engine `2.3.0` требует минимум 5 000 AED, безопасное отношение к рынку и подтверждение AED-цены detail page перед доставкой.
- После исправления выполнен полный production-пересчёт: 2 374 нормализуемых объявления из 2 381 получили решение Engine `2.3.0`; 7 недопустимых записей исключены.
- Из пересчитанной базы только 9 решений прошли финансовый фильтр публикации; все 9 независимо подтверждены по актуальной detail page, расхождений и неподтверждённых цен нет.
- Очереди обработки и доставки работают с production-лимитами. Включены отдельные расписания DubiCars, CarSwitch, Cars24 и OpenSooq; устаревшее общее расписание оставлено выключенным.
- Семь старых записей дешевле 5 000 AED находятся в карантине и удалены из `normalized_vehicles`, поэтому не участвуют в оценке рынка; исходные документы сохранены как проверяемый след инцидента.
- Контрольный production-запуск DubiCars после исправления завершён успешно и не добавил новых ложных цен.
- Следующая продуктовая программа описана в документации, но ещё не утверждена: Free/Pro split, пользовательский поиск, административная панель, информационный контент и мультиканальная доставка.
- До явного утверждения владельцем код этих функций не изменяется.
- Официальный WhatsApp Business Cloud API поддерживает индивидуальных получателей, но не публикацию в WhatsApp Channel; допустимый план — opt-in рассылка через официальный API и отдельный channel-adapter только при появлении официальной возможности Meta.
- Проверка draft PR #1 подтвердила, что `main` остаётся legacy, PR является крупным монолитным изменением, а развёрнутый production собран из неслитой рабочей ветки. Динамические количества коммитов и файлов здесь намеренно не фиксируются.
- До Free/Pro, поиска и панели обязательны отдельно разрешённый `0.11-STOP`, repository gate `0.11R`, `0.11A–0.11C`, immutable candidate `0.11RC`, миграция `0.11M`, baseline `0.11D` и официальный пилот `0.11P`.
- Строгая exactly-once Telegram-доставка не заявляется: используется outbox и состояние `unknown` для неоднозначного результата без слепого повтора.
