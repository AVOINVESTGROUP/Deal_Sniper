# Журнал реализации

## 27 июля 2026 — утверждение R6 и локальный кандидат R6.1–R6.4

- Владелец явно утвердил `docs/PLAN_REVIEW_2026-07-27-R6.md`; только после этого начаты изменения кода.
- Введена recipient/template-scoped immutable publication revision с parent-связью на прежний subject event; существующие immutable события не изменяются.
- PublicationEvent и delivery outbox сохраняются атомарно в SQLite и Firestore; retry возвращает исходный payload и CTA, orphan/changed-payload состояние блокируется.
- Free renderer и leakage validator запрещают цену, рынок, ссылку, ID, прибыль и ROI во всех автомобильных Free-публикациях.
- Market Watch Free переведён на безопасный teaser; legacy publisher теперь fail-closed без отдельного `TELEGRAM_PRO_CHANNEL_ID` и не отправляет полную карточку в Free.
- Firebase Hosting очищен от конфликтующих Cloud Run rewrites; Admin сохраняет Gateway-only transport, CSP для Firebase runtime и понятную ошибку истёкшей сессии.
- Локальный gate: Ruff — green; mypy — green; 80 pytest — green; coverage 56%; pip-audit — без известных уязвимостей; Terraform fmt/validate — green.
- GitHub Actions кандидата `f1bd8fd` подтвердил Python 3.11, quality, Docker build, Trivy и Terraform; все три jobs завершились успешно.
- Настоящий Firestore integration в `deal-sniper-stage-rc2` воспроизвёл transaction contention при 12 конкурентных CTA reservations; retry budget только publication/CTA транзакций повышен с 5 до 20.
- Повторная интеграционная проверка прошла: 12 уникальных вариантов, стабильный retry, атомарный event+outbox, отклонение изменённого immutable event и очистка всех test IDs.
- Отдельный staging API Gateway направлен только на `deal-sniper-api-staging`; production Gateway не переключался. После выдачи ему `run.invoker` `/version` подтвердил commit `409aa18`, digest `sha256:16ab3816…74301` и schema 2.
- Серверная и настоящая headless Chrome матрицы прошли пять authenticated Admin endpoints с HTTP 200 и browser-enforced CORS от `https://avo-deal-sniper.web.app`.
- Live CSP ожидаемо запрещает staging hostname; Playwright меняет `connect-src` только в перехваченном тестовом ответе. Production Hosting не изменён.
- R6.5 завершён. Первый staging digest промежуточный: после фиксации browser test/evidence требуется финальная commit-labelled сборка и полный повтор R6.6. Production не изменён.

## 27 июля 2026 — остановка кандидата и обязательный сквозной аудит

- Владелец повторно зафиксировал порядок: перед каждым исправлением требуется изучить проект; сначала документы и утверждённый план, затем код.
- Production не изменён и продолжает работать на commit `12bdee56c6b299132f55d1afedc0d25e4918ac82` и digest `sha256:561814a852339e454dca7a362d41bc68e27ffe3359fc02e5eedbe6a31597aa3e`.
- Кандидат `1ce36ff` признан непригодным к deploy: Admin retry не доказывает устранение причины Gateway/CORS, Free Market Watch раскрывает запрещённые Pro-поля, а прежние immutable `PublicationEvent` не получают CTA при неизменившемся ID.
- Зафиксирован полный review `docs/PLAN_REVIEW_2026-07-27-R6.md` и корректирующая последовательность R6. До отдельного утверждения владельцем код и production не меняются.

## 27 июля 2026 — CTA Free → Pro и устойчивость Admin Web

- После утверждения плана реализована библиотека из 30 англоязычных CTA и подписных кнопок Pro для автомобильных публикаций Free-канала.
- Вариант резервируется атомарно для `publication_id`, сохраняется в `PublicationEvent` и outbox и не меняется при повторной доставке; соседние публикации проходят полный цикл без повторения варианта.
- Публикация автомобиля в Free-канал блокируется при отсутствующей или некорректной `TELEGRAM_PRO_SUBSCRIPTION_URL`; допустима только HTTPS-ссылка Telegram.
- Admin Web теперь повторяет временно неудачные Gateway-запросы, обновляет Firebase ID token после первого `401` и показывает доступные разделы при частичном отказе API вместо пустой панели `Failed to fetch`.
- CSP Firebase Hosting дополнена разрешением для Firebase runtime-модулей с `www.gstatic.com`.
- Локальный gate был успешен: Ruff, mypy и 71 pytest, но последующий сквозной аудит выявил архитектурные блокеры. Этот результат не является разрешением на deploy.

## 26 июля 2026 — план конверсионного CTA Free → Pro

- Уточнено требование: под каждым автомобильным объявлением Free-канала обязательны англоязычный CTA и inline-кнопка действующей подписки Pro.
- CTA должен отличаться у последовательных публикаций и менять продуктовый акцент; минимум 30 fallback-шаблонов используются без повторов до исчерпания пула.
- Gemini разрешён только один раз для нового `publication_id`, получает подтверждённые поля и не создаёт цену, прибыль, ROI или срочность. Результат валидируется и сохраняется в `PublicationEvent`/outbox; retry не генерирует новый текст.
- Определены проверки 100% наличия кнопки, корректной ссылки, отсутствия утечки Pro-данных и выдуманных чисел, разнообразия и идемпотентности.
- Это документальный этап. Код и production не изменялись; реализация ожидает утверждения владельцем.

## 26 июля 2026 — план массовых Telegram Sources

- Уточнено требование: нужны чужие публичные Telegram-каналы и группы, а не чаты, в которые добавлен продуктовый бот.
- Подготовлен `docs/TELEGRAM_SOURCES_PLAN.md`: отдельный MTProto technical account, source registry, ограниченный history backfill, quality analyzer, incremental cursors, edits/deletes/media albums и multilingual Discovery.
- Цель пилота: 200+ candidates, 50 analyzed, 10–20 enabled на 7 дней; масштабирование до 50–200 только после quality report.
- Telegram-only цена получает tier `seller_stated`, исключается из verified comparable market и не может самостоятельно сформировать `CONTACT`.
- Определены этапы TG0–TG6, quality thresholds и новые Google Cloud компоненты.
- Это документальный этап. Код, credentials, session, Cloud Jobs и production не изменялись; реализация запрещена до утверждения плана владельцем.

## 26 июля 2026 — добавление источников из Admin Web

- В Sources добавлен мастер `Test connection` → `Add source` для публичных HTTPS JSON feeds.
- Backend не сохраняет источник до реальной загрузки и распознавания автомобиля со стабильным ID, URL, названием и фиксированной ценой не ниже 5 000 AED; `Price on request`, 99/999 AED, пустой JSON и private-network URL отклоняются.
- Новый feed создаётся выключенным, затем отдельно включается администратором. Динамический feed можно удалить без удаления накопленной истории; предустановленные адаптеры удалить нельзя.
- Конфигурация хранится в Firestore/SQLite и загружается каждым новым API/collector instance. Ручной запуск использует общий Cloud Run collector с source override.
- Браузерный Admin API оставлен за API Gateway: попытка same-origin Hosting rewrite несовместима с организационным запретом публичного Cloud Run invoker.
- Локальный gate успешен: Ruff, mypy и 66 pytest.

## 25 июля 2026 — полный production candidate

- Production остановлен: schedules и Cloud Tasks paused, delivery/webhook выключены.
- Создан защищённый STOP Firestore export и зафиксирован watermark.
- Реализованы canonical IDs, immutable snapshots/evidence/decisions и current pointers.
- Исправлена обработка out-of-order версий и блокировка доставки старого snapshot.
- Реализована source-bound detail verification; `Price on request` и неподтверждённая цена не допускаются.
- Freshness отделена от immutable evidence: `last_checked_at`, `valid_until`, `freshness_status`.
- Реализованы deterministic Comparable, Cost, Risk и Decision Engines с Decimal.
- Добавлены cross-source identity/dedup, market fingerprint и controlled recalculation.
- Реализован transactional outbox personal/Free/Pro/WhatsApp и ручной reconcile `unknown`.
- Реализованы Telegram update leases, RU/EN поиск, saved searches, favorites и outcomes.
- Добавлены Free teaser без финансовых утечек и полная Pro-карточка.
- Добавлены Firebase Auth, Admin Web, TMA и content pipeline.
- Добавлен официальный WhatsApp opt-in adapter, fail-closed без credentials.
- Реализованы migration tool v1.0/schema v2, ledger, checksums, checkpoints и replay requests.
- Добавлен direct migration replay с `DELIVERY_ENABLED=false` без включения очередей.
- Terraform расширен Cloud Run Jobs/Tasks/Scheduler, Firebase, IAM, secrets, monitoring и budget.
- CI использует Python 3.11, Ruff, mypy, pytest coverage, pip-audit, Terraform, Docker и Trivy.
- Локальный gate: Ruff — green; mypy — green; 42 теста — green; coverage 46,81%; Terraform validate — green.
- Документация приведена к фактической реализации; добавлен release/cutover/rollback runbook.
- Исправлен CI pin Trivy Action на существующий официальный release `v0.36.0`.
- Runtime image очищен от ненужных build-пакетов `setuptools` и `wheel`, найденных Trivy; прежний RC digest аннулирован.
- Trivy подтверждает отсутствие исправимых HIGH/CRITICAL; 23 findings Debian 13 без `FixedVersion` сохраняются в отчёте и не блокируют gate через `ignore-unfixed`.
- Staging replay обнаружил несовместимость legacy content hash; migration tool 1.1 rekey создаёт canonical v2 snapshots, переводит current pointer и отклоняет missing/non-current replay вместо ложного `completed`.
- Direct replay получил ограниченный `--retry-failed --max-attempts 3` для временных source/network ошибок без бесконечного повтора.
- Добавлен обязательный второй catch-up pass `--recalculate-all`, чтобы ранние решения пересчитывались уже на полном verified market.
- Полный staging catch-up завершён на 2 784 объявлениях: 2 783 успешно, одно объявление изолировано после трёх временных ошибок проверки; `delivery_outbox` остался пустым.
- Повторный migration dry-run после catch-up выявил и закрыл дефект идемпотентности: migration tool 1.1.1 явно принимает собственные актуальные immutable v1-контракты и по-прежнему блокирует неизвестные схемы.
- Firebase подключён к `avo-deal-sniper`, статические TMA/Admin assets опубликованы с выключенной production delivery.
- Production reconciliation до включения delivery выявил и устранил неверный owner текущего решения: `decision_subject_id` и Firestore `current_decisions` теперь строго listing-specific; `vehicle_id` используется только для cross-source связи/дедупликации.
- Identity v3 автоматически объединяет только одинаковый валидный VIN; заглушки VIN и неоднозначные fuzzy-совпадения не создают транзитивный auto-merge.
- Engine 3.1.0 и migration tool 1.2.0 инвалидируют прежний RC; production остаётся остановленным до нового exact-digest rehearsal и повторного catch-up.
- RC 3.1.0 прошёл повторный staging rehearsal и production migration/catch-up: 1 106 detail pages подтверждены, 1 672 отклонены как permanent invalid, 6 сохранили temporary error; 1 052 listing-specific current decisions, `delivery_outbox=0`.
- PR #2 fast-forward слит в `main`; production API развёрнут на exact digest с delivery=false и подтвердил engine 3.1.0/schema 2 через `/version`.
- Из-за запрета `allUsers` в организации Admin/TMA направлены через API Gateway с backend OIDC, ограниченным Firebase CORS и сохранением исходного Firebase bearer в `X-Forwarded-Authorization`.

## 25 июля 2026 — production запущен

- API Gateway v2, private Cloud Run API и Firebase Hosting развернуты и прошли smoke-проверку.
- Firebase Authentication инициализирован; TMA обменивает подписанный Telegram `initData` на Firebase custom token.
- Владелец получает admin claim и управляет четырьмя источниками прямо в TMA.
- Коллекторы DubiCars, CarSwitch, Cars24 UAE и OpenSooq UAE успешно выполнены под отдельным service account.
- Очереди processing и Telegram delivery работают; delivery включена только после полного reconciliation.
- Telegram webhook, команды, menu button и права бота в Free/Pro каналах проверены.
- Текущий production market содержит только `INSUFFICIENT_DATA` и `REJECT`; неподтверждённые или ложные сделки не публикуются.
- WhatsApp adapter остаётся fail-closed до предоставления внешних Meta credentials, template approval и opt-in.
- Локальный gate: Ruff, mypy и 47 тестов — green.
- Исправлена CSP Firebase Hosting: Mini App разрешены запросы к точному production API Gateway; ошибка `Failed to fetch` устранена.
- Техническое управление slash-командами заменено основным кнопочным интерфейсом: постоянная кнопка открытия Mini App, разделы «Сделки», «Подбор», «Избранное», «Настройки» и закрытый раздел владельца «Управление».
- Пользовательский интерфейс зафиксирован на английском языке для рынка ОАЭ: Mini App и ответы личного бота не зависят от языка устройства; контент каналов также публикуется на английском.
- Утверждён следующий продуктовый релиз: удалить Admin из пользовательской Mini App, оставить отдельный `/admin.html`, показывать фотографии в карточках и публиковать в канал 3–5 отдельных `MARKET WATCH` объектов с фото, ценой, рыночным диапазоном, источником и ссылкой. `MARKET WATCH` не является инвестиционным сигналом.
- Релиз реализован и покрыт автоматическими проверками: пользовательская Mini App больше не содержит Admin, карточки выводят первую фотографию объявления с безопасным fallback, отдельная панель оператора показывает failed/unknown delivery, а publisher идемпотентно выбирает до пяти ещё не опубликованных рыночных объектов на запуск.
- Добавлены owner-scoped TMA API для чтения/сохранения фильтров и создания, включения и остановки персональных подборов.
- Для TMA assets установлен `Cache-Control: no-store` и versioned URL, чтобы Telegram WebView не удерживал старый экран после production-релиза.
- Production-аудит пустого интерфейса выявил 2 912 текущих объявлений, 1 196 подтверждённых цен и 1 179 решений: 1 127 `INSUFFICIENT_DATA`, 52 `REJECT`, прибыльных сигналов нет. Пустой канал был следствием данных и отсутствующего расписания publisher, а не отсутствия сбора.
- Добавлены TMA Summary и Market Watch: пользователь видит объём рынка, покрытие аналогами, состояние источников и подтверждённые рыночные объекты, которые явно не выдаются за инвестиционные сделки.
- Обычный текст в личном чате теперь создаёт активный owner-scoped подбор; неизвестный текст возвращает понятный пример и кнопку приложения вместо требования вводить slash-команду.
- Market Pulse строится только по объявлениям, прошедшим обработку и verification; в публикацию добавляются до трёх честно обозначенных Market Watch объектов.
- Параллельные TMA-запросы объединены 30-секундным server-side snapshot cache; Market Watch загружается лениво после показа главного экрана.

## Следующая эксплуатационная операция

Наблюдать первый недельный pilot, проверять source health и temporary verification errors в Admin/TMA. WhatsApp включать отдельно только после появления внешних Meta credentials.

## Диалог и новости авторынка

- Зафиксирован контракт естественного англоязычного общения без обязательных slash-команд.
- Основные пользовательские намерения: подбор автомобиля, обзор рынка, новости, справка и открытие приложения.
- Новость считается допустимой только при наличии заголовка, издателя, даты и HTTPS-ссылки; при ошибке ленты действует fail-closed.
- Новостной текст не участвует в Comparable, Cost, Risk или Decision Engine.
- Реализованы news client, кнопочный chat router и публичный личный бот без пользовательского allowlist; административные операции по-прежнему защищены отдельным admin allowlist.
- Pro-карточка полностью англоязычна, получила фотографию объявления и больше не показывает fingerprint, внутреннюю конфигурацию и slash-команду.
- Живая RSS-проверка вернула релевантные материалы с издателем, датой и ссылкой; нерелевантные, старые, неполные и HTTP-записи отбрасываются.
- Ruff, mypy и 56 тестов прошли; покрытие 52,6%.
- Production smoke выявил Telegram `ChatMigrated`: группа `Avto_invest` стала supergroup с новым ID. Webhook теперь отвечает в `migrate_to_chat_id`, не возвращает 500 и не создаёт цикл повторов старого update.
- Production smoke успешен: личный webhook ответил на приветствие и запрос новостей, migrated supergroup получила ответ по новому ID, Pro-канал принял контрольную публикацию с message ID 22.
- Telegram webhook queue равна нулю; после исправления `ChatMigrated` у финальной ревизии новых ERROR нет.
- Production API и десять Cloud Run Jobs выровнены по одному immutable digest; `/version` подтверждает commit, digest, schema и engine.
- Для чтения произвольных сообщений в группе `Avto_invest` бот всё ещё должен быть назначен администратором группы либо Privacy Mode должен быть отключён владельцем через BotFather. Личный чат работает без этого действия.
- Следующий шаг: наблюдать pilot и качество внешней новостной ленты; новые источники новостей подключать только с обязательными publisher/date/HTTPS provenance.

## Монетизация Pro 100 AED

- Зафиксирован один тариф: Pro — 100 AED за 30 дней; Free остаётся бесплатным.
- Для цифрового доступа внутри Telegram выбран нативный recurring-механизм Telegram Stars и приватная платная ссылка Pro-канала.
- Telegram является источником истины по членству, продлению и окончанию доступа; backend не имитирует успешную оплату.
- Требуется реализовать: конфигурацию цены/ссылки, Upgrade CTA в боте и TMA, endpoint статуса членства, ограничение полного feed для Free, реферальную атрибуцию и production smoke.
- Создана нативная Telegram Stars recurring-ссылка Pro-канала: 1500 Stars каждые 30 дней; коммерческая цена интерфейса — 100 AED.
- Реализованы `/tma/subscription`, membership entitlement, закрытие полного deal feed для Free, Upgrade CTA, referral link/атрибуция и агрегаты subscription/referrals в Admin.
- Бот показывает постоянную кнопку `Upgrade to Pro`; успешным entitlement считается только фактический статус member/administrator/owner/restricted в Pro-канале.
- Ruff, mypy и 58 тестов прошли; покрытие 52,1%.
- Следующий шаг: immutable build, API Gateway config, Firebase Hosting и production payment-link smoke.
- Production-монетизация опубликована: API и 10 Jobs используют один immutable digest, API Gateway активен на конфигурации `deal-sniper-config-pro-c2b38b7`, а Firebase Hosting содержит Pro-карточку и endpoint `/tma/subscription`.
- Проверка Telegram подтвердила entitlement владельца Pro-канала; неизвестный участник обрабатывается fail-closed. Ответ через direct messages канала передаёт обязательный `direct_messages_topic_id` из `direct_messages_topic.topic_id` или резервного `message_thread_id`.
- Диагностика живого webhook показала служебный `supergroup_chat_created` без текста и topic ID; такие события теперь подтверждаются без попытки отправить ответ.
- Финальный локальный gate после исправления: Ruff, mypy и 61 тест прошли.

## Исправление административного входа

- Удалён нерабочий Google Sign-In: Google IdP не был включён, а административная роль проекта привязана к Telegram ID владельца.
- Бот показывает владельцу отдельную кнопку **Open admin panel**; она открывает `/admin.html` как Telegram Web App с подписанным `initData`.
- Admin Web автоматически обменивает `initData` через `/tma/auth` на Firebase custom token с `admin=true` и только затем загружает данные.
- Прямое открытие страницы в браузере больше не показывает пустую псевдопанель: оно объясняет требование Telegram и ведёт в бот.
- Ruff, mypy и 62 теста прошли.
- Production smoke успешен: Telegram-кнопка панели отправлена владельцу сообщением `91`; `/tma/auth` вернул 200, Firebase custom-token sign-in вернул 200, `/admin/overview` вернул 200 и загрузил 6 337 snapshots и четыре источника. Webhook queue равна нулю, новых ошибок ревизии нет.

## Ограничения

- Существующий draft PR #1 не сливать и не использовать как production baseline.
- Terraform apply до import существующих ресурсов запрещён.
- WhatsApp включать только после внешних Meta credentials/template approval/opt-in.
- Любое изменение build context после staging rehearsal требует нового RC и повторного rehearsal.

## 27 июля 2026 — завершение R6.6 в staging

- Владелец явно утвердил план R6; production-развёртывание этим сообщением не разрешалось.
- Чистый RC commit `2a42735d57af6e3549af1d5fa0a975cee120a76f` прошёл GitHub Actions `30278152829`.
- Из RC собран commit-labelled образ `r6-2a42735` с неизменяемым digest `sha256:abd5cf8b368e2fffa5cc9fc70023ac68baf4572202942634092dc61bef145d8a`.
- Exact digest развёрнут только в `deal-sniper-api-staging`, revision `deal-sniper-api-staging-00020-mgd`, с `FIRESTORE_DATABASE=deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false` и `WHATSAPP_ENABLED=false`.
- `/health` вернул `ok`; `/version` подтвердил RC commit, runtime digest и schema `2`.
- Реальный Firestore integration прошёл: 12 конкурентных CTA reservations, атомарный PublicationEvent + outbox, стабильный retry, блокировка изменённого retry и очистка тестовых документов.
- Настоящий headless Chrome прошёл защищённый путь Hosting origin → отдельный staging API Gateway → приватный Cloud Run. `/admin/overview`, `/content/market-pulse`, `/admin/preview` и оба состояния `/admin/outbox` вернули HTTP 200 с browser-enforced CORS.
- Telegram payload проверялся только как preview; фактическая доставка в Telegram и WhatsApp не выполнялась.
- Production остаётся на commit `12bdee56c6b299132f55d1afedc0d25e4918ac82` и digest `sha256:561814a852339e454dca7a362d41bc68e27ffe3359fc02e5eedbe6a31597aa3e` до отдельного разрешения владельца на R6.7.

## 27 июля 2026 — R6.7 production smoke и новый RC

- После отдельного разрешения владельца выполнен STOP: delivery выключена, Scheduler и обе Cloud Tasks queue приостановлены; защищённый export `r6-production-20260727-193058` успешно сохранил 69 251 документ.
- RC `2a42735` и Hosting version `c110b289b2855e7f` были развёрнуты с delivery off. Четыре collector smoke получили 502 объявления, все источники вернули `success=true`; processing queue из 57 уникальных задач полностью обработана без ERROR.
- Настоящий production Chrome smoke остановил cutover: четыре Admin endpoint вернули 200, а `/admin/overview` получил Gateway 504 без CORS и проявился как `Failed to fetch`. Telegram delivery и content scheduler не включались.
- Подтверждённая причина: overview последовательно ждал три Cloud API запроса до 20 секунд и потоково считывал десятки тысяч Firestore документов для счётчиков.
- Исправление не меняет продуктовый контракт: Cloud API запрашиваются параллельно отдельными сессиями с ограниченным timeout; независимые части overview выполняются через `asyncio.gather`; Firestore dashboard counts используют aggregation queries вместо полного stream.
- Gate нового кандидата: Ruff, strict mypy, 81 pytest, coverage 55,65%, dependency audit и Terraform успешно. До повторного staging rehearsal production остаётся в maintenance-состоянии с delivery off, всеми расписаниями и очередями paused.
## 26 июля 2026 — отдельная браузерная админ-панель

- Документация утверждает отдельный desktop-first Admin Web; Telegram больше не является оболочкой административного интерфейса.
- В Firebase Authentication включён Google provider, доступ backend ограничивается серверным `ADMIN_EMAILS`.
- Реализованы разделы Dashboard, Sources, Cloud runtime, Publications и Subscriptions без вывода внутренних JSON-дампов и секретов.
- Для установленных источников доступны понятные состояния, включение/пауза и аудитируемый ручной запуск Cloud Run Job.
- Ошибка источника имеет приоритет над историческим `success=true`: в панели такой запуск всегда обозначается как требующий внимания.
- Локальный gate: Ruff и 62 теста прошли; JavaScript-модуль прошёл синтаксическую проверку Node.js.
- Для read-only REST-запросов панели явно передаётся Google Cloud quota project, чтобы service-account credentials не возвращали ложный `403` при наличии viewer IAM.
- Маршрут ручного запуска `/admin/sources/{source_name}/run` добавлен в API Gateway, поэтому кнопка `Run now` работает через тот же защищённый production endpoint, что и остальная панель.
- При браузерном smoke выявлен `redirect_uri_mismatch`: Google provider был связан с IAP OAuth-клиентом, который нельзя использовать как Firebase Web client. Утверждена замена входа на одноразовую Firebase email-ссылку без пароля; запрос разрешён только для `ADMIN_EMAILS`, backend сохраняет обязательную проверку Firebase ID token и email allowlist.
- Passwordless-вход развёрнут в production: Email provider включён, оба Hosting-домена авторизованы, релиз `d025401af3558362` опубликован. Live-проверка подтвердила новый интерфейс и успешную отправку одноразовой ссылки на разрешённый адрес администратора; Google OAuth popup полностью удалён.
- По пользовательскому smoke обнаружено, что `.notice { display:flex }` визуально перекрывает HTML-атрибут `hidden`: успешная отправка ссылки отображалась одновременно со старой ошибкой. Контракт интерфейса дополнен обязательным глобальным правилом `[hidden]{display:none!important}`; исправление опубликовано в Hosting version `1e168b3b11990c1a` и подтверждено live-проверкой.
- Фактическое письмо с email-link не доставляется почтовым доменом, хотя Identity Toolkit принимает запрос без ошибки. Утверждён независимый от почтовой доставки вход Firebase email/password: пароль не хранится в коде, первоначальное случайное значение однократно доставляется владельцу через личный Telegram-бот, backend продолжает проверять `ADMIN_EMAILS`.
- Email/password-вход развёрнут в Hosting version `5abe3c43043b3e9c`. Создана подтверждённая Firebase account владельца, реальный `signInWithPassword` получил ID token, защищённый `/admin/overview` успешно загрузил production-данные. Случайный пароль однократно доставлен владельцу личным сообщением бота `93`; само значение нигде в проекте не сохранено.
- После успешного входа пользовательский браузер показал `Failed to fetch`, хотя все пять production endpoints с `Origin` и Firebase token вернули HTTP 200 и CORS-заголовки. Для устранения зависимости от конкретного браузера утверждён same-origin путь через Firebase Hosting rewrites; middleware обязан сохранять обычный `Authorization` и заменять его только при наличии gateway-заголовка `X-Forwarded-Authorization`.
- Диагностика service-account runtime установила точную причину read-only `403`: access token запрашивался с недостаточным OAuth scope. Клиент использует полный `cloud-platform`, а фактический доступ по-прежнему ограничен viewer IAM.
- GCS raw archive больше не делает предварительный `GET`: immutable-объект создаётся атомарно с `if_generation_match=0`, а существующий объект определяется по precondition. Collector сохраняет write-once модель и не требует чтения отсутствующего объекта.
- Firestore source health заменяет карту `last_run` целиком. Поле `error` предыдущего запуска не сохраняется после следующего успешного запуска из-за рекурсивного `merge=True`.
## 27 июля 2026 — R6 полностью развёрнут в production

- Владелец явно разрешил production deploy после утверждения плана R6.
- Перед переключением создан защищённый Firestore export: `gs://avo-deal-sniper-firestore-exports/r6-production-20260727-193058`, 69 251 документ, операция завершена успешно.
- Первый production smoke обнаружил тайм-аут только у `/admin/overview`; доставка оставалась выключенной. Причина устранена без расширения объёма R6: Cloud API читаются параллельно, счётчики Firestore используют aggregation queries.
- Финальный RC commit: `851ddaf26852aaaa0547df1b60e222d7f74b5d9a`; immutable digest: `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`.
- GitHub Actions run `30282317974` успешен: quality, container/Trivy и Terraform прошли.
- Тот же digest прошёл повторный staging Firestore integration и authenticated Chrome smoke для пяти Admin endpoints, затем развёрнут в production API revision `deal-sniper-api-00060-kkc` и во все 10 Cloud Run Jobs.
- Firebase Hosting version `c110b289b2855e7f` остаётся активной; Admin доступен по `https://avo-deal-sniper.web.app/admin.html`.
- Поэтапно возобновлены четыре collector scheduler, `listing-processing`, delivery и content scheduler. Legacy aggregate scheduler `deal-sniper-collector-every-10m` намеренно оставлен остановленным, чтобы не создавать двойной сбор.
- Контрольный сбор четырёх источников завершился успешно. Очередь обработки приняла 563 задания и была сведена к нулю; временные `ReadTimeout` detail pages обрабатывались retry/fail-closed и не создавали ложные решения.
- Telegram webhook подтверждён: pending updates 0, последняя ошибка отсутствует. Обе Cloud Tasks queues работают.
- Production pilot отправил ровно 30 новых Free-карточек с CTA: 30 уникальных fingerprints, 0 соседних повторов, 0 карточек без CTA или кнопки, очередь доставки 0.
- После пилота: 6 819 snapshots, 1 489 current decisions, outbox 94 (`sent=92`, `pending=0`, `sending=0`, `unknown=0`, две исторические `failed` относятся к delivery-disabled cutover). Все четыре marketplace sources имеют статус `healthy`.

## 28 июля 2026 — утверждение R7

- Владелец утвердил план R7: полноценный браузерный Control Center и управляемая монетизация.
- До изменения кода повторно проверены SPEC, план реализации, облачная архитектура, production evidence R6, API, repository contract, Admin Web и тесты.
- Подтверждены блокеры baseline: статичная цена из окружения, отсутствие безопасной ротации Stars subscription link, неполный набор административных разделов и ложные reconcile-действия для исторических `failed`.
- Полный контракт данных, API, интерфейса, тестов и выпуска зафиксирован в `docs/ADMIN_CONTROL_CENTER_PLAN_R7.md`.
- Production R6 остаётся без изменений. R7 допускается к реализации и staging, но production deploy требует отдельного разрешения владельца после release evidence.

## 28 июля 2026 — кандидат реализации R7

- Реализована единая версионированная runtime-конфигурация с active pointer, immutable revisions, audit trail и SQLite-эквивалентом для локальных тестов. При недоступности или невалидности active revision runtime использует значения окружения как fail-safe fallback.
- Добавлены Preview, Apply и Rollback для цены AED/Stars, финансовых порогов и лимита публикаций. Смена Stars создаёт новую 30-дневную Telegram subscription link; повтор операции с тем же operation ID не создаёт вторую активную версию.
- Bot, TMA, content publisher и новые Free CTA читают одну активную конфигурацию. Старый outbox payload при retry не переписывается.
- Admin Web содержит Dashboard, Sources, Runs, Listings, Decisions, Publications, Users, Revenue, Errors и Settings. Для исторического `failed` доступны только диагностические данные; reconcile-действия показываются исключительно для `unknown`.
- Добавлено allowlisted управление Scheduler: run, pause и resume. Произвольные имена Cloud-ресурсов и произвольные действия запрещены.
- API Gateway и Terraform дополнены маршрутами R7 и минимальной ролью Scheduler operator.
- Локальный gate успешен: Ruff, strict mypy, 89 тестов, coverage 56,15%, dependency audit, JavaScript syntax, Terraform format/validate и `git diff --check` прошли. Секреты в изменённых и новых файлах не обнаружены.
- Локальная container build не выполнена: Docker Desktop Linux engine выключен. Immutable image, Trivy, staging и release evidence ещё не созданы; production R6 не изменялся.
- Коммиты плана `4f4e3b2` и реализации `2cb2bd2` отправлены в ветку `production/deal-sniper-complete`. GitHub Actions run `30336329612` успешно выполнил Python 3.11 quality, container build, Trivy и Terraform. Artifact Registry digest, staging rehearsal и production deploy ещё не выполнялись.
- Создан предварительный `docs/RELEASE_EVIDENCE_2026-07-28-R7.md`. Staging остановлен до повторной интерактивной авторизации `gcloud` и подтверждения отдельного тестового Pro-канала; production Pro-канал для этих проверок не используется.

## 28 июля 2026 — staging R7

- Из evidence head `02fcb6f919c22d5f6504dd46667d2439ca8e9d55` Cloud Build `1a47a7e3-cf4c-4613-ac3f-543a3ee3c0b6` собрал immutable digest `sha256:ab0b8880041985c47bf2a7eb69b638ed6d2370a21e3e5044b42ebfe4e2ffe94a`.
- Exact digest развёрнут только в staging; актуальная revision `deal-sniper-api-staging-00026-cfj` сохраняет schema `2`, отдельную базу `deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false` и `WHATSAPP_ENABLED=false`.
- Staging API Gateway активен на config `r7-02fcb6f`; `/health`, `/ready` и `/version` успешны и подтверждают точный commit/digest.
- Firestore staging integration подтвердил идемпотентную активацию immutable runtime revision и корректное архивирование предыдущей версии без Telegram delivery.
- Краткоживущий Firebase user, разрешённый только в staging, прошёл настоящий Chrome/CORS smoke. Пять основных Admin read paths и шесть дополнительных R7 endpoints вернули HTTP 200; затем test user удалён, а allowlist восстановлен.
- Hosting preview пока не создан: отдельная Firebase CLI-сессия завершилась `invalid_rapt`; production Hosting не менялся, временные локальные адреса staging полностью восстановлены.
- Мутационная смена Stars, rollback и единая revision в bot/TMA/Admin/CTA ожидают отдельный тестовый Pro-канал. Production Pro-канал для staging не используется.
- Production остаётся на R6 commit `851ddaf26852aaaa0547df1b60e222d7f74b5d9a`, digest `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`, revision `deal-sniper-api-00060-kkc`.
- После Firebase re-auth создан краткоживущий Hosting Preview. Firebase Auth в нём успешен, но настоящий UI-smoke выявил HTTP 400 на CORS preflight preview-origin: backend разрешал только два production Hosting origin. По утверждённому R7 контракт уточнён: credentialed CORS использует явный env allowlist без wildcard; preview origin добавляется только в staging. Требуется новый immutable RC и повтор staging.
- Реализован точный `CORS_ALLOWED_ORIGINS` с безопасным production fallback и fail-fast проверкой HTTPS/wildcard. Новый локальный gate успешен: Ruff, strict mypy, 90 passed / 2 skipped, coverage 64%, dependency audit и Terraform validate. Предыдущий staging digest аннулирован до новой immutable сборки.
- GitHub Actions `30342104177` прошёл quality, container/Trivy и Terraform. Cloud Build `6d7de8fd-8088-4b87-a74e-26afe9a1e7fd` собрал новый immutable digest `sha256:c45e544ce9cc128353a9c8f1f96443809aded61f31c06ebde42d0b77ca2f6e2a` из RC `80872e0`.
- Exact digest развёрнут только в staging revision `deal-sniper-api-staging-00033-v7k`; `/version` совпадает с RC/digest, delivery выключена, временные Firebase users отсутствуют.
- Настоящий Hosting Preview UI успешно вошёл через Firebase Auth, загрузил Dashboard без ошибок и открыл все десять разделов. Preview CORS preflight возвращает HTTP 200; staging allowlist восстановлен после smoke.
- Владелец уточнил, что отдельный тестовый Pro-канал не нужен: платных пользователей пока нет, цена должна меняться только в Admin, а новая Telegram Stars link должна создаваться backend автоматически.
- Read-only аудит production обнаружил 3 текущих `INSPECT`, 5 исторических `pro/v1` outbox и отсутствие Pro reconciliation в периодическом publisher. Подготовлен `docs/PLAN_R7_1_PRO_PUBLICATION.md`; до его утверждения код и production не менять.
- Владелец явно утвердил `docs/PLAN_R7_1_PRO_PUBLICATION.md`. Разрешены реализация и staging R7.1; production deploy по-прежнему требует отдельной команды после нового release evidence.
## 28 июля 2026 — R7.1 реализован локально

- Утверждённый план R7.1 реализован без изменения production R6.
- Добавлен периодический Pro reconciliation текущих подтверждённых `CONTACT`/`INSPECT`: стабильные ID, атомарный PublicationEvent/outbox, повторная постановка только `pending`, fail-closed для `sent`/`sending`/`unknown`/`failed` и ограничение batch.
- Publisher выполняет Pro reconciliation до Free/Market Pulse, поэтому ошибка Free-контента не лишает Pro-контур очередной сверки.
- В Admin Web раздел Publications показывает publishable/sent/pending/sending/unknown/failed/missing, последний запуск и кнопку `Publish Pro now` с точным подтверждением; браузер запускает только Cloud Run Job `deal-sniper-publisher`.
- Цена AED и Stars остаётся управляемой в Settings. Price-only revision не меняет версию финансовой политики и не инвалидирует действующие расчёты автомобилей.
- Добавлены защищённые Gateway routes `/admin/pro-publications` и `/admin/pro-publications/run`.
- Локальный gate: 94 теста прошли, 2 условно пропущены; Ruff, strict mypy, JavaScript ES-module syntax и `git diff --check` успешны.
- Следующий разрешённый этап: commit/push, immutable build и staging rehearsal. Production deploy по-прежнему требует отдельного явного разрешения владельца.

## 28 июля 2026 — staging R7.1

- Commit `07e89b79e3a46deade619a87b115157d3df4209a` отправлен в Draft PR #3; оба GitHub Actions запуска завершились успешно.
- Cloud Build `18c2f73a-d5e5-4ec4-84dc-e948c7f9b706` собрал из точного `git archive` immutable digest `sha256:d1fa347b8b4a528b89ba93ad6ab0a3ca11c86813ad514c44097cf8300d92998c`.
- Exact digest развёрнут только в staging revision `deal-sniper-api-staging-00035-gst`; отдельная база `deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false` и `WHATSAPP_ENABLED=false` сохранены.
- Staging Gateway активен на config `r71-07e89b7`; `/version`, `/health`, `/ready` и CORS preflight успешны, новый защищённый Pro endpoint без Firebase-сессии возвращает 401.
- Hosting Preview version `06e7b909a8895569` содержит UI R7.1 и направлен только на staging Gateway. Production API/Gateway/publisher/live Hosting остаются на R6.
- Для завершения staging evidence владелец должен открыть Publications в Preview своей существующей Firebase-сессией. Автоматический временный Firebase login не создавался из-за отсутствия у оператора `iam.serviceAccounts.signBlob` и истёкших локальных ADC.
- Финальная проверка выявила, что staging Admin мог запускать production Job по жёстко заданному имени. Контракт исправлен до точного allowlist из `deal-sniper-publisher` и `deal-sniper-publisher-staging`; имя выбирается через `PUBLISHER_JOB_NAME`. Новый local gate: 95 passed, 2 skipped, Ruff, strict mypy, JavaScript и diff check успешны. Предыдущий staging digest аннулирован как release candidate; production не менялся.
- Финальный safety-fix commit `4aaf252c47e1c7d1f60e839fcf7cac6c019fd07c` прошёл GitHub Actions `30347621234` и `30347621827`. Cloud Build `977cb039-a9b4-4234-9803-cd09a1037e77` собрал immutable digest `sha256:41b04c0ed5f1e7fd5a3e738f34dbb7121d60e4c3c02cc28300d2002ab11caa99`.
- Exact digest развёрнут в staging API revision `deal-sniper-api-staging-00036-87b` и в отдельном Job `deal-sniper-publisher-staging`. Staging сохраняет базу `deal-sniper-stage-rc2`, отключённую delivery/WhatsApp и фиктивный Pro recipient.
- Два staging execution успешны. Изолированный fixture подтвердил `selected=1, created=1, failed=0`, атомарный PublicationEvent/outbox и правильный staging recipient; все тестовые документы удалены по точным ID, тестовая Cloud Task отсутствует.
- Production повторно проверен и не изменён: API `deal-sniper-api-00060-kkc`, R6 digest `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`, Gateway `deal-sniper-config-source-12bdee5`, Hosting `c110b289b2855e7f`.
- Осталась только ручная authenticated проверка раздела Publications в Hosting Preview. Production deploy по-прежнему требует отдельного явного разрешения владельца.

## 28 июля 2026 — план R7.2 для Google Admin Sign-In

- Владелец сообщил, что пароль Firebase утрачен, и потребовал вход через Google-аккаунт.
- Read-only аудит подтвердил: Google provider включён, но связан с IAP OAuth client `Dubai Deal Sniper Admin Web`; именно это вызвало прежний `redirect_uri_mismatch`.
- Backend уже использует Firebase ID token и `ADMIN_EMAILS`, поэтому модель административной авторизации сохраняется; меняется только способ входа.
- Создан `docs/PLAN_R7_2_GOOGLE_ADMIN_AUTH.md`: отдельный Web OAuth client, Google popup, обязательный `email_verified`, миграция существующей password-account, staging и rollback.
- До утверждения R7.2 код, Firebase provider и production не изменяются.

## 28 июля 2026 — локальная реализация R7.2

- Владелец утвердил R7.2.
- Admin Web больше не содержит email/password fields и `signInWithEmailAndPassword`; добавлены **Continue with Google**, desktop popup и явный redirect fallback при блокировке popup.
- Backend выдаёт административную роль только при `email_verified=true` и совпадении нормализованного email с `ADMIN_EMAILS`; legacy custom claim `admin=true` без подтверждённого allowlisted email больше не открывает Admin API.
- Полный локальный gate успешен: 99 тестов прошли, 2 условно пропущены, coverage 57,55%; Ruff, strict mypy, JavaScript ES-module syntax, dependency audit, Terraform validate и `git diff --check` прошли без ошибок.
- Облачный Google provider пока не переключался с IAP client, Hosting и production не изменялись.
- Дополнительный аудит подтвердил отсутствие периодических Pro-новостей и отсутствие R7.1 reconciliation в production R6. Создан черновик `docs/PLAN_R7_3_PRO_CHANNEL_CONTENT.md`; его код не реализуется до отдельного утверждения.
- Commit `fe13453392f2b9007e97b84d3695f9dd9fe749c4` отправлен в Draft PR #3. GitHub Actions `30382432905` и `30382437156` завершились успешно: quality на Python 3.11, container build, Trivy и Terraform прошли.
- Следующий разрешённый этап R7.2: создать отдельный Web OAuth client, переключить Firebase Google provider и выполнить настоящий Google Sign-In smoke только в Hosting Preview/staging. Production остаётся на R6 до отдельной команды владельца.

## 28 июля 2026 — локальная реализация R7.3

- Владелец утвердил `docs/PLAN_R7_3_PRO_CHANNEL_CONTENT.md`; перед кодом повторно проверены content job, R7.1 Pro reconciliation, outbox, runtime revisions, Admin API/Web, RSS-клиент и API Gateway.
- Плановый publisher теперь независимо выполняет сверку полных Pro-карточек и нового англоязычного Dubai/UAE automotive digest. Новости принимаются только из HTTPS RSS/Atom, проходят freshness/relevance/provenance-фильтры и дедупликацию по semantic fingerprint.
- Создан управляемый реестр новостных лент для SQLite и Firestore. Admin Web позволяет проверить и добавить ленту, включить, приостановить или удалить её без удаления истории публикаций.
- В versioned Settings добавлены отдельные переключатели Pro deals и Pro news, размер дайджеста 1–3, интервал публикации и опциональное вступление Vertex AI. При недоступности модели используется детерминированный текст; модель не определяет цены и инвестиционные решения.
- Раздел Publications раздельно показывает состояния сделок и новостей; ручной запуск остаётся идемпотентным и использует allowlisted publisher job. `pending` переочередяется, а финальные состояния не публикуются повторно.
- Локальный gate успешен: 105 тестов прошли, 2 условно пропущены, coverage 58,82%; Ruff, strict mypy, JavaScript ES-module syntax, dependency audit, Terraform validate и `git diff --check` прошли. Локальный container build недоступен, потому что Docker Desktop Linux engine выключен; его обязан заменить CI container/Trivy и последующая immutable Cloud Build. Production R6 не изменялся; immutable build и staging ещё не выполнялись.
- Реализация R7.3 зафиксирована commit `48e3132f12fa2b4fa7f7ad8fdb6cf747543d3cbb` и отправлена в Draft PR #3. GitHub Actions `30387369703` и `30387367900` успешно выполнили quality, container build, Trivy и Terraform. Создан предварительный `docs/RELEASE_EVIDENCE_2026-07-28-R7_3.md`; production остаётся без изменений.

## 28 июля 2026 — immutable staging R7.3

- Evidence commit `c6c283667a889f030581fe3adcc6814d52d8f9cd` прошёл GitHub Actions `30387653569` и `30387651492`.
- Cloud Build `46d3f002-8073-4ebb-8cf7-3faefa507831` собрал exact digest `sha256:d52c10aae8b19afad46ef380d47887e5ecdcf8d30136a245fdbf05b16cda50f5` из точного git archive.
- Digest развёрнут только в staging API revision `deal-sniper-api-staging-00038-f2j` и publisher staging generation `3`; delivery и WhatsApp выключены, база `deal-sniper-stage-rc2` сохранена.
- Активна runtime revision `r73-stage-c6c2836`: Pro deals и Pro news включены, прежние цены/финансовые пороги сохранены.
- Staging Gateway переключён на config `r73-c6c2836`; health/version и CORS нового news-feed route успешны.
- Полный publisher/UI smoke остановлен после истечения интерактивных сессий `gcloud` и Firebase CLI. Требуется повторный вход; production R6 не изменён.
