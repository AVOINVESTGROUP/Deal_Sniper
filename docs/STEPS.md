# Журнал реализации

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
