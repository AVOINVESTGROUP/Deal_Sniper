# Журнал реализации

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
- Следующий шаг: immutable build, exact-digest deploy и Telegram production smoke.

## Ограничения

- Существующий draft PR #1 не сливать и не использовать как production baseline.
- Terraform apply до import существующих ресурсов запрещён.
- WhatsApp включать только после внешних Meta credentials/template approval/opt-in.
- Любое изменение build context после staging rehearsal требует нового RC и повторного rehearsal.
