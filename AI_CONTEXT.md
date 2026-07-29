# AI Context: Dubai Deal Sniper

29 июля 2026 владелец явно утвердил R8. Реализован локальный R8.1-CODE без изменения
production: Admin Web снова сохраняет проверенный email/password-вход, а Google UI
выключен runtime-флагом до R8.2; `DELIVERY_ENABLED=false` теперь запрещает создание
Telegram/WhatsApp Cloud Tasks; staging delivery требует отдельные database, queue,
publisher Job и список production recipients для проверки коллизий. Terraform описывает
`telegram-delivery-staging`. Pro-кандидат без фотографии не публикуется, verification
требует make/model/year, а новостные ссылки известных агрегаторов отклоняются; пустая
прямая RSS-лента безопасно отключает новости. Gate: Ruff, strict mypy, 114 pytest
(112 passed, 2 skipped), coverage 59%, pip-audit без известных уязвимостей, JavaScript
module syntax и Terraform validate успешны. Production/Firebase не изменялись; следующий
этап — commit, immutable build и настоящий Telegram staging smoke.

29 июля 2026 после сквозного аудита документов, кода и release evidence подготовлен
корректирующий `docs/PLAN_R8_RECOVERY.md`. Обнаружено, что production остаётся на R6,
тогда как Pro reconciliation/news находятся только в R7.3 staging; их выпуск ошибочно
заблокирован незавершённым Google Sign-In. SPEC одновременно требовал password-вход, а
README и Admin Web — Google-only. Дополнительно staging проверял фиктивный recipient при
delivery off, а `DELIVERY_ENABLED=false` не предотвращал создание Cloud Task. R8 разделяет
R8.1 Pro Recovery и R8.2 Admin Google Auth, требует отдельных очередей окружений и
настоящего Telegram staging smoke. Этот абзац фиксирует состояние до последующего
утверждения и локальной реализации R8.1.

28 июля 2026 финальный staging RC R7 — `80872e0e70f292189864e829824f07dcf3e6591f`, GitHub Actions `30342104177`, Cloud Build `6d7de8fd-8088-4b87-a74e-26afe9a1e7fd`, immutable digest `sha256:c45e544ce9cc128353a9c8f1f96443809aded61f31c06ebde42d0b77ca2f6e2a`, Cloud Run staging revision `deal-sniper-api-staging-00033-v7k`, Gateway config `r7-02fcb6f`. Firestore integration, authenticated API/Chrome и настоящий Hosting Preview UI прошли при `DELIVERY_ENABLED=false`; все десять Admin-разделов загрузились, preview CORS возвращает 200, временные Firebase users удалены и allowlist восстановлен. Остались мутационный Stars/rollback smoke, подтверждение единой active revision в bot/TMA/Admin/CTA и устранение найденного пробела Pro reconciliation. Production не менялся и остаётся на R6 `851ddaf` / `sha256:c2e55a…a9112`; отдельного разрешения на production deploy R7 нет.

28 июля 2026 владелец отменил требование отдельного тестового Pro-канала: платных пользователей пока нет, цена должна управляться в Admin, а Telegram Stars link автоматически перевыпускается backend. Read-only аудит production подтвердил критический пробел: 3 current `INSPECT`, только 5 исторических `pro/v1`, а периодический content publisher не выполняет reconciliation Pro — публикация создаётся лишь при первичной обработке новой версии. Подготовлен неутверждённый `docs/PLAN_R7_1_PRO_PUBLICATION.md`: идемпотентный Pro reconciler, Admin preview/Publish now и controlled smoke текущего Pro-канала. До утверждения R7.1 код и production не менять.

28 июля 2026 владелец явно утвердил `docs/PLAN_R7_1_PRO_PUBLICATION.md`. Разрешены реализация и staging: общий идемпотентный Pro reconciler, Admin preview/Publish now и автоматическая ротация Stars link из Admin. Production остаётся на R6 до нового immutable build, staging evidence и отдельного разрешения владельца.

27 июля 2026 владелец явно утвердил `docs/PLAN_REVIEW_2026-07-27-R6.md`. После утверждения подготовлен кандидат R6.1–R6.4: recipient/template-scoped immutable publication revision с parent event, атомарный PublicationEvent+outbox для SQLite/Firestore, стабильный CTA при retry, единый Free teaser/leakage validator, безопасный Market Watch, запрет fallback полной Pro-карточки в Free, Gateway-only Firebase Hosting и диагностируемая Firebase-сессия Admin. Локальный gate: Ruff, mypy, 80 pytest, coverage 56%, pip-audit без известных уязвимостей и Terraform validate. GitHub Actions кандидата `f1bd8fd` дополнительно подтвердил Python 3.11, Docker build и Trivy. Реальный integration-тест в `deal-sniper-stage-rc2` обнаружил contention CTA allocator при стандартных пяти Firestore attempts; адресный budget 20 attempts прошёл 12 конкурентных reservations, атомарный event+outbox, immutable retry и cleanup. R6.5 завершён authenticated headless Chrome smoke через отдельный staging Gateway: все пять Admin read paths дали 200 и browser-enforced CORS. Промежуточный staging digest `sha256:16ab3816…74301` подтверждает код `409aa18`, schema 2 и delivery=false, но после фиксации browser test/evidence требуется новая commit-labelled сборка и полный R6.6. Production остаётся на commit `12bdee56c6b299132f55d1afedc0d25e4918ac82`, digest `sha256:561814a852339e454dca7a362d41bc68e27ffe3359fc02e5eedbe6a31597aa3e`.

27 июля 2026 в отклонённом кандидате `1ce36ff` была предпринята реализация CTA Free → Pro и защитного поведения Admin Web. Локальный gate дал Ruff, mypy и 71 pytest, однако эти проверки не покрыли сквозные архитектурные контракты. Данный абзац является историей кандидата, а не подтверждением готовности функции; актуальный статус и блокеры определены предыдущим абзацем и планом R6.

26 июля 2026 владелец добавил обязательное требование монетизации Free-канала: под каждым автомобильным teaser должны находиться уникальный англоязычный CTA и inline-кнопка подписки Pro. План: Gemini создаёт текст один раз только для нового `publication_id` из подтверждённых полей, валидатор запрещает выдуманные числа/срочность, а библиотека минимум из 30 шаблонов служит fallback. Соседние посты не повторяют CTA или label, выбранный вариант сохраняется в `PublicationEvent`/outbox и остаётся неизменным при retry. До утверждения обновлённого плана код и production не менять.

26 июля 2026 владелец уточнил следующий источник данных: массовый мониторинг чужих публичных Telegram-каналов и групп. Подготовлен, но ещё не утверждён `docs/TELEGRAM_SOURCES_PLAN.md`. Правильный контур — отдельный MTProto collector с техническим аккаунтом, а не Bot API. План включает 200+ discovery candidates, анализ 50 источников, пилот 10–20 и последующее controlled scaling до 50–200; Admin quality reports; raw revisions, media groups, edits/deletes, cursors/leases; EN/AR/RU discovery; hybrid deterministic/Gemini extraction. Telegram evidence всегда начинается как `seller_stated` и запрещено в verified market/CONTACT без независимой проверки. До явного утверждения плана нельзя писать код, создавать Telegram API credentials/session или менять production.

26 июля 2026 добавлен отсутствовавший продуктовый контур управления источниками. Отдельная Admin Web Panel умеет протестировать и зарегистрировать публичный HTTPS JSON feed, показать число валидных автомобилей и sample, сохранить источник выключенным, включить/запустить и удалить только динамическую конфигурацию. Валидация fail-closed запрещает private-network fetch, не-JSON, пустой feed, `Price on request`, цену ниже 5 000 AED и записи без минимальных автомобильных полей. Конфигурации персистентны в Firestore/SQLite; штатные DubiCars/CarSwitch/Cars24/OpenSooq остаются кодовыми адаптерами. Gateway-контур сохранён, потому что org policy запрещает `allUsers` invoker для Cloud Run и тем самым блокирует Firebase Hosting rewrite. Gate: Ruff, mypy, 66 pytest.

## Цель

Production-сервис быстрой монетизации сигналов по недооценённым автомобилям с фиксированной ценой в ОАЭ. Недвижимость и аукционы исключены. Основные каналы: персональный Telegram-бот, Free/Pro Telegram-каналы, TMA и Admin Web. WhatsApp — только официальный opt-in API.

## Обязательные правила

- Python 3.11, type hints, русская документация/коммиты/логи.
- Не коммитить `.env`, токены, credentials или PII.
- Всегда указывать `--project=avo-deal-sniper`; локальный gcloud default не доверять.
- Production delivery fail-closed и остаётся выключенной до финального cutover.
- Не использовать mock fallback в production.
- LLM не определяет финансовые значения.
- Telegram ambiguous send становится `unknown` и не повторяется автоматически.
- WhatsApp без Meta credentials остаётся выключенным и не блокирует Telegram release.

## Реализация

- источники: DubiCars, CarSwitch, Cars24 UAE, OpenSooq UAE;
- exact immutable snapshots и transactional current pointers;
- detail-page verification, immutable semantic evidence и `valid_until` freshness;
- cross-source identity, normalization, robust comparable market;
- deterministic Decimal cost/risk/decision engines;
- market fingerprint и пересчёт затронутого make/model;
- Firestore immutable decisions/current pointers;
- transactional outbox для personal/Free/Pro/WhatsApp;
- Telegram webhook/update leases, user search, saved searches, favorites/outcomes;
- Firebase Auth, Admin/TMA APIs и статические приложения в `web/`;
- repository-backed Market Pulse/engagement content;
- migration schema v2, ledger, checksums, checkpoints и isolated direct replay;
- Terraform, GitHub Actions, pip-audit, Trivy и non-root Python 3.11 Docker image.

## Текущий release state

Ветка: `production/deal-sniper-complete`, база — commit `bc5803a9c7af86bf63f3038430ea547bef83e7ee`. Production был остановлен до начала полной стабилизации: schedules/queues paused, webhook и delivery отключены, STOP export сохранён в защищённом bucket. Существующий draft PR #1 не является baseline и не должен сливаться.

Кодовая часть нового RC проходит Ruff, mypy и 42 теста. До статуса complete остаются immutable build, staging restore/rehearsal, production migration, финальный PR/merge, exact-digest deploy, staged resume и pilot. Источник истины по порядку — `docs/IMPLEMENTATION_PLAN.md`; операции — `docs/OPERATIONS.md`; контракт — `SPEC.md`.

Первый запуск CI выявил только неверный несуществующий pin Trivy Action `0.33.1`; он заменён на официальный release `v0.36.0`. Любой новый commit после этой правки требует новых immutable image digests.

Следующий container scan выявил две HIGH CVE в runtime build-tools `setuptools`/vendored `wheel`; Dockerfile удаляет эти ненужные пакеты после установки runtime dependencies. Digest, собранный до этой правки, недействителен.

После удаления build-tools Trivy не находит исправимых HIGH/CRITICAL. В Debian 13 остаются 23 OS findings без доступного `FixedVersion`; CI использует `ignore-unfixed=true`, но продолжает блокировать любую исправимую HIGH/CRITICAL.

Первый staging replay выявил несовместимость legacy hash с canonical `listing-content/v2`: 100 requests были помечены completed без evidence. Production не затронут. Migration tool повышен до 1.1.0, создаёт canonical snapshot documents и current hashes; direct replay предварительно отклоняет missing/non-current snapshot. Требуется новый RC и полный повтор staging rehearsal.

Полный staging catch-up показал временные verification/network failures. Direct replay поддерживает явный `--retry-failed` с `--max-attempts` (по умолчанию 3); бесконечного автоматического повтора нет.

Migration catch-up выполняется в два прохода: первый создаёт evidence/normalized market, второй `--recalculate-all --retry-failed` пересчитывает все current decisions на полном verified market. Оба прохода требуют delivery=false.

Staging rehearsal на `deal-sniper-stage-rc2` завершил 2 783 из 2 784 replay requests; один источник остался в fail-closed карантине после трёх `TemporaryVerificationError`, доставка не создавалась. Повторный dry-run после пересчёта обнаружил, что migration 1.1.0 не признавал собственный `verification-evidence/v1`. В 1.1.1 проверка схем явно разрешает актуальные immutable v1-контракты и продолжает отклонять неизвестные v1. После этой правки требуется новый exact digest и финальный dry-run перед production.

Firebase-проект `avo-deal-sniper` активирован, Hosting URL — `https://avo-deal-sniper.web.app`; production API rewrite остаётся fail-closed до cutover.

Production reconciliation до resume обнаружил критическое расхождение с контрактом: engine 3.0 записывал current pointer по cross-source vehicle cluster, из-за чего часть listing-specific решений схлопывалась. Engine 3.1.0 всегда использует `decision_subject_id = listing_id` и Firestore `current_decisions`; отдельный `vehicle_id` остаётся только связью и ключом дедупликации публикации. Identity v3 принимает для автоматического merge лишь совпадающий валидный VIN, а VIN-заглушки не нормализуются. Migration tool 1.2.0 инвалидирует как legacy `decision_current`, так и новый `current_decisions`. Любой предыдущий RC digest аннулирован; production delivery всё ещё выключена.

RC commit `082db10e288e` и digest `sha256:ff609767c3a20cf3f6af1043178e3a013779cee22c7aa1915f3855bc8f8ee51f` прошли staging и production migration/replay. Production verified evidence: 1 106 active verified, 1 672 permanent invalid, 6 temporary error; `current_decisions=1052`, `delivery_outbox=0`, публикуемых CONTACT/INSPECT на текущем срезе нет. PR #2 fast-forward включён в `main`; revision `deal-sniper-api-00026-6q5` возвращает engine 3.1.0/schema 2.

Организационная policy запрещает `allUsers` на Cloud Run. Telegram webhook и Web-клиенты используют существующий публичный API Gateway, который вызывает приватный Cloud Run с OIDC. Gateway v2 добавляет Admin/TMA/content endpoints и CORS только для Firebase Hosting; backend восстанавливает пользовательский Firebase bearer из стандартного `X-Forwarded-Authorization`.

## Важные команды

```powershell
python main.py collect --source dubicars
python main.py replay --direct --concurrency 10
python -m ruff check src tests main.py
python -m mypy src main.py
python -m pytest --cov=src --cov-fail-under=45
terraform -chdir=infra/terraform validate
```

`replay --direct` разрешён только при `DELIVERY_ENABLED=false` и нужен для migration catch-up без включения production Cloud Tasks.

## Production cutover 25 июля 2026

Production запущен: четыре source schedules, processing queue и Telegram delivery queue работают; legacy общий schedule оставлен paused, чтобы не дублировать per-source сбор. Telegram webhook направлен через API Gateway и не имеет pending/error. Бот является администратором Free и Pro каналов, команды и TMA menu button настроены.

Firebase Authentication инициализирован. TMA проверяет Telegram `initData`, использует отдельный Firebase signer service account, получает Firebase ID token и owner-scoped данные. Для Telegram owner в custom claims устанавливается `admin=true`; Admin в TMA управляет source switches и показывает состояние проекта. Отказ read-only Cloud Status не ломает управление источниками и возвращается как `UNAVAILABLE` для отдельного компонента.

Production-проход всех четырёх collectors успешен. После обработки актуальный market содержит 1 177 verified evidence, 1 671 permanent invalid и 4 temporary error; current decisions не содержат CONTACT/INSPECT, поэтому система корректно не публикует недостоверные автомобили. Информационный Market Pulse и production status доставлены, старые pending outbox записи периода delivery-disabled помечены superseded.

WhatsApp реализация присутствует и остаётся `WHATSAPP_ENABLED=false`: это единственный внешний credential blocker, требующий Meta access token, phone number ID, утверждённый template и user opt-in.

После production-проверки TMA устранён браузерный `Failed to fetch`: точный API Gateway добавлен в `connect-src` Firebase Hosting. Пользовательский путь больше не строится вокруг slash-команд. Основной интерфейс — Telegram menu button и Mini App с вкладками Deals/Search/Saved/Settings; владелец дополнительно видит Admin и управляет source switches кнопками. Backend содержит owner-scoped `/tma/settings` и `/tma/searches`, поэтому пользователь не может читать или менять чужие настройки и подборы.

Документ TMA, runtime-config, JavaScript и CSS отдаются с `Cache-Control: no-store`; ссылки на assets версионированы. Это исключает повтор старого интерфейса из кэша Telegram WebView после развёртывания.

После пользовательской проверки обнаружено, что технически корректный fail-closed feed создавал пустой продукт: из 1 179 current decisions не было ни одного CONTACT/INSPECT/WATCH, а обычный текст webhook отправлял пользователя к командам. TMA теперь разделяет `Investment deals` и `Verified market`: второе показывает только объекты с market estimate и предупреждает, что это не инвестиционная рекомендация. `/tma/summary` объясняет состояние данных числами, `/tma/market-watch` даёт рыночные карточки, а обычный текст Telegram детерминированно создаёт активный saved search. Контентный publisher использует обработанные current decisions вместо непроверенных raw listings.

TMA не блокирует первый экран ожиданием Market Watch: feed и summary используют общий 30-секундный market snapshot cache, а рыночные карточки загружаются при открытии вкладки. Это важно для холодного Cloud Run/Firestore пути внутри Telegram WebView.

Язык production-продукта — английский. Mini App, личный Telegram-бот и канальные публикации используют английский независимо от `language_code` пользователя или языка устройства; русским остаётся только внутренняя документация проекта.

Реализованное разделение интерфейсов: `/app.html` является только пользовательским кабинетом и не показывает административную вкладку даже владельцу; `/admin.html` является отдельным кабинетом оператора с административной аутентификацией. Пользовательские и канальные карточки используют `ListingSnapshot.image_urls[0]`, когда фотография доступна. Контентный publisher идемпотентно выпускает до пяти ещё не опубликованных англоязычных `MARKET WATCH` карточек за запуск с проверяемыми фактами и не смешивает их с `DEAL`.

Утверждён контракт следующего шага: Telegram webhook должен поддерживать естественный англоязычный диалог и постоянные кнопки без требования знать slash-команды. Новости авторынка Дубая загружаются read-only клиентом, фильтруются по свежести и релевантности и показываются только с издателем, датой и HTTPS-ссылкой. Ошибка ленты не подменяется выдуманным материалом; новости не влияют на финансовый движок.

Контракт реализован: публичный личный бот больше не ограничен пользовательским allowlist, но admin-команды остаются закрыты. Кнопки запускают подбор, Market Overview, Dubai auto news и справку. Pro delivery использует первую фотографию объявления; англоязычная карточка переводит известные risk/reason сообщения и скрывает fingerprint/build-поля и slash CTA. Локальный gate: Ruff, mypy, 56 тестов, coverage 52,6%. До завершения релиза остаются immutable build/deploy и живой Telegram smoke.

Production smoke дополнительно выявил, что Telegram преобразовал группу `Avto_invest` в supergroup. В update присутствует `migrate_to_chat_id`; webhook обязан использовать новый ID для ответа, иначе Telegram возвращает `ChatMigrated` и группа выглядит неработающей. Обработка добавлена до маршрутизации сообщения.

Релиз диалога прошёл production smoke: личный бот ответил на приветствие и запрос живых новостей, migrated supergroup использовала новый ID `-1004451580668`, Pro-канал `-1004319276577` подтвердил права администратора/публикации и принял контрольное сообщение 22. Pending updates равны нулю, у проверенной финальной ревизии после cutover нет новых ERROR. Для получения всех обычных сообщений внутри supergroup владелец Telegram должен отдельно сделать бота администратором либо отключить Privacy Mode; через Bot API бот не может повысить собственные права.

Утверждён контракт монетизации: единственный тариф Pro стоит 100 AED за 30 дней. Поскольку продаётся цифровой доступ внутри Telegram, платёж и recurring membership реализуются нативной Telegram Stars subscription link приватного Pro-канала. `PRO_PRICE_STARS` отделён от коммерческой цены AED; Telegram автоматически управляет вступлением/продлением/окончанием. Бот и TMA показывают Upgrade CTA и проверенный membership status; Free не получает полный Pro audit trail.

Монетизация реализована локально. Создана нативная recurring-ссылка Pro-канала на 1500 Stars / 30 дней; ссылка не коммитится и передаётся production через `TELEGRAM_PRO_SUBSCRIPTION_URL`. Endpoint `/tma/subscription` проверяет реальное членство, отдаёт цену и персональный referral URL. `/tma/feed` fail-closed для Free. Бот и TMA содержат Upgrade CTA, Admin показывает channel members, Stars balance и referral summary. Gate: Ruff, mypy, 58 тестов, coverage 52,1%.

Production-монетизация развёрнута: коммерческая цена интерфейса 100 AED / 30 дней, нативная recurring-оплата Telegram настроена на 1500 Stars / 30 дней. API Gateway использует `deal-sniper-config-pro-c2b38b7`; Firebase Hosting опубликован с Pro-карточкой, проверкой membership и referral CTA. Telegram direct messages канала требуют `direct_messages_topic_id`; webhook передаёт его из `direct_messages_topic.topic_id` или резервного `message_thread_id`. Служебные updates без текста, включая `supergroup_chat_created`, подтверждаются без ответа. Финальный локальный gate: Ruff, mypy и 61 тест.

Пользователь отклонил Admin Web внутри Telegram как постоянный рабочий интерфейс. Утверждён новый контракт: `/admin.html` — самостоятельная desktop-first панель в обычном браузере, Google Sign-In включён, административная роль определяется `ADMIN_EMAILS`. Telegram остаётся клиентским каналом и каналом owner alerts, но не является обязательной оболочкой управления.

Production smoke административного пути завершён: владельцу отправлена рабочая Web App кнопка сообщением 91; синтетический подписанный Telegram `initData` владельца успешно прошёл `/tma/auth` (200), Firebase custom-token sign-in (200) и `/admin/overview` (200). Overview вернул 6 337 snapshots, включённую delivery и источники cars24/carswitch/dubicars/opensooq. Webhook queue — 0, новых ошибок production-ревизии нет.

Административный путь заменён на самостоятельный браузерный кабинет `/admin.html`. После выявленного `redirect_uri_mismatch` у ошибочно выбранного IAP OAuth-клиента контракт входа уточнён: панель использует одноразовую Firebase email-ссылку без пароля и серверный allowlist `ADMIN_EMAILS`, не зависит от Telegram Web App и не показывается пользователям бота. Интерфейс содержит Dashboard, Sources, Cloud runtime, Publications и Subscriptions; внутренние JSON/provenance скрыты, ошибки источников не могут отображаться как успешный запуск. Установленный source adapter можно включить, приостановить и вручную запустить с аудитом.

Production-релиз passwordless Admin Authentication завершён: Firebase Email provider включён, `avo-deal-sniper.firebaseapp.com` и `avo-deal-sniper.web.app` находятся в authorized domains, Hosting version `d025401af3558362` опубликована. Live smoke подтвердил HTTP 200, отсутствие Google popup-кода, наличие email-link flow и успешную отправку одноразовой ссылки на разрешённый административный адрес.

Пользовательский screenshot выявил только визуальный stale error: CSS-класс `.notice` перекрывал стандартное поведение атрибута `hidden`. Исправление — глобальное `[hidden]{display:none!important}`; состояние отправки email было успешным и backend/auth flow ошибки не возвращали. Hosting version `1e168b3b11990c1a` опубликована, live CSS вернул HTTP 200, нужное правило и `Cache-Control: no-store`.

Письмо email-link фактически не пришло владельцу, несмотря на успешный ответ Identity Toolkit; последующая точная проверка показала, что account record при этом не была создана. Для устранения зависимости от внешней почтовой доставки контракт заменён на Firebase email/password. Случайный пароль устанавливается административно в Firebase, не хранится в репозитории или Cloud Run env и однократно передаётся владельцу в личный Telegram-чат; доступ backend всё равно ограничен `ADMIN_EMAILS`.

Production smoke email/password завершён: Hosting version `5abe3c43043b3e9c` содержит password field и `signInWithEmailAndPassword`, email-link код удалён. Подтверждённая Firebase account создана для административного email; реальный password sign-in, Firebase ID token и `/admin/overview` прошли успешно. Первоначальный случайный пароль передан владельцу Telegram-сообщением `93` и не записан в код, Git, `.env`, Secret Manager или документацию.

После входа Chrome владельца показал `Failed to fetch`. Полная серверная браузерная матрица с `Origin=https://avo-deal-sniper.web.app` подтвердила HTTP 200 и CORS для overview, market pulse, preview и обоих outbox запросов. Вариант с same-origin Firebase Hosting rewrite был рассмотрен, но отклонён: организационная policy запрещает публичный Cloud Run ingress. Действующий путь остаётся Firebase Hosting -> защищённый API Gateway -> приватный Cloud Run; middleware восстанавливает пользовательский Firebase bearer из `X-Forwarded-Authorization`.

Read-only REST-запросы Admin Web к Scheduler, Tasks и Cloud Run передают явный quota project `avo-deal-sniper`; это отделяет фактический IAM-статус от ошибок отсутствующего billing/quota consumer в Application Default Credentials.

API Gateway содержит отдельный защищённый маршрут `POST /admin/sources/{source_name}/run`; браузерная кнопка ручного запуска не обращается к Cloud Run напрямую.

Production-диагностика service account показала `ACCESS_TOKEN_SCOPE_INSUFFICIENT` для Scheduler/Tasks/Run: Admin REST-клиент должен получать token с OAuth scope `cloud-platform`, тогда как полномочия остаются ограничены viewer IAM. Raw GCS archive создаёт объекты атомарным `if_generation_match=0` без предварительного `blob.exists()`; это соответствует роли Object Creator и устраняет ложный 403 на ещё не существующем checksum-объекте.

Firestore `source_registry.last_run` должен заменяться целиком через явный merge field path. Рекурсивный `merge=True` запрещён для health-записи, потому что он сохраняет устаревшее поле `error` после успешного запуска и создаёт ложный красный статус.

27 июля 2026 владелец явно утвердил R6. R6.1–R6.6 завершены без изменения production. RC commit `2a42735d57af6e3549af1d5fa0a975cee120a76f` прошёл GitHub Actions и собран как commit-labelled image digest `sha256:abd5cf8b368e2fffa5cc9fc70023ac68baf4572202942634092dc61bef145d8a`. Exact digest работает только в staging revision `deal-sniper-api-staging-00020-mgd` с отдельной Firestore database `deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false` и `WHATSAPP_ENABLED=false`. `/version` совпал с RC/digest/schema 2. Реальный Firestore concurrency/atomicity test и настоящий authenticated Chrome smoke пяти Admin endpoints через отдельный staging Gateway прошли. Telegram payload проверен как preview без доставки. R6.7 и любое production-развёртывание требуют нового отдельного разрешения владельца; production пока остаётся на `12bdee56` / `sha256:561814a8…aa3e`.

После отдельного разрешения на R6.7 production STOP и export выполнены корректно. Exact RC `2a42735` был развёрнут с delivery off, Hosting version `c110b289b2855e7f` опубликована, четыре collector smoke получили 502 объявления и processing queue полностью обработана. Production Chrome smoke обнаружил Gateway 504 только для `/admin/overview`; остальные четыре Admin endpoint дали 200. Cutover остановлен до Telegram delivery. Причина — последовательные Cloud API timeouts и потоковые Firestore dashboard counts на production объёме. Исправление переводит Cloud status и независимые агрегаты overview на параллельное выполнение, а Firestore counts — на aggregation queries. Новый локальный gate: Ruff, strict mypy, 81 тест, coverage 55,65%, audit и Terraform успешны. Требуется новый commit/digest и полный staging rehearsal; production пока находится в maintenance-состоянии: delivery off, Scheduler и обе queue paused.
## Production baseline R6 — 27 июля 2026

R6 утверждён владельцем и отдельно разрешён к production deploy. Рабочий baseline кода — commit `851ddaf26852aaaa0547df1b60e222d7f74b5d9a`, image digest `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`. Production API revision после включения доставки — `deal-sniper-api-00060-kkc`; тот же digest установлен во всех 10 Cloud Run Jobs. Hosting version — `c110b289b2855e7f`.

Перед cutover выполнен Firestore export `r6-production-20260727-193058` (69 251 документ). Staging и production authenticated Chrome smoke проходят для `/admin/overview`, `/content/market-pulse`, `/admin/preview`, failed и unknown outbox. Admin timeout устранён параллельным чтением Cloud API и Firestore aggregation counts.

Активны четыре отдельных collector scheduler, content scheduler и обе очереди. Aggregate collector scheduler остаётся PAUSED как защита от двойного сбора. Telegram delivery включён; webhook pending=0 и без последней ошибки. Финальный pilot: 30/30 Free-карточек доставлены с валидной Pro-кнопкой, 30 уникальных CTA fingerprints, без соседних повторов; delivery queue равна нулю. Текущее наблюдаемое состояние: 6 819 snapshots, 1 489 решений, четыре marketplace sources healthy, outbox `sent=92`, `unknown=0`.

## 28 июля 2026 — утверждён план R7

- Production baseline R6 не меняется до отдельного разрешения на deploy.
- Владелец утвердил R7: полноценный browser Control Center, динамическая версионированная несекретная конфигурация и безопасная смена цены Pro.
- Коммерческая сумма AED и фактическая цена Telegram Stars являются разными полями. Смена Stars создаёт новую 30-дневную subscription invite link; затем immutable revision и active pointer переключаются транзакционно.
- Старая платная ссылка не отзывается автоматически. Retry существующего outbox продолжает использовать исходный сохранённый payload.
- Итоговый Admin Web обязан содержать Dashboard, Sources, Runs, Listings, Decisions, Publications, Users, Revenue, Errors и Settings. Reconcile разрешён только для `unknown`; исторические `failed` не получают неработающих кнопок.
- Секреты остаются в Secret Manager/environment и никогда не сохраняются в runtime configuration или Admin Web.
- Полный обязательный контракт: `docs/ADMIN_CONTROL_CENTER_PLAN_R7.md`.

Кандидат R7 реализован локально. Добавлены `runtime_configuration/active`, immutable revisions, idempotent administrative operations, Preview/Apply/Rollback цены и операционных параметров, новая Telegram subscription link при смене Stars, динамическое чтение конфигурации bot/TMA/content и десять разделов browser Control Center. Scheduler mutations ограничены префиксом проекта и действиями run/pause/resume; повторный запрос не запускает вторую мутацию, исторический `failed` больше не получает ложных reconcile-кнопок. Локальный gate: Ruff, strict mypy, 89 тестов, coverage 56,15%, audit, JavaScript и Terraform успешны. Docker Desktop выключен, поэтому container build/Trivy, immutable digest, staging evidence и production deploy не выполнялись. Production остаётся на R6 commit `851ddaf26852aaaa0547df1b60e222d7f74b5d9a` и digest `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`.

Кандидат R7 опубликован в GitHub: plan commit `4f4e3b2`, implementation commit `2cb2bd2`, branch `production/deal-sniper-complete`. GitHub Actions run `30336329612` завершён успешно: quality на Python 3.11, container build, Trivy и Terraform зелёные. Это устраняет локальный пробел выключенного Docker Desktop, но не заменяет immutable Artifact Registry build и staging rehearsal. Production R6 не изменялся.

Предварительный release evidence R7 создан в `docs/RELEASE_EVIDENCE_2026-07-28-R7.md`. Попытка read-only проверки Google Cloud остановилась на истёкшей локальной `gcloud`-сессии: требуется интерактивный `gcloud auth login`. До staging мутации также требуется отдельный тестовый Pro-канал; production Pro-канал запрещено использовать для смены тестовой цены. Production deploy R7 не выполнялся.
## R7.1 — локальная реализация 28 июля 2026

Владелец утвердил `docs/PLAN_R7_1_PRO_PUBLICATION.md`. Реализован единый идемпотентный Pro reconciliation в `src/pro_publication.py`; его вызывает плановый `content` job. Он рассматривает только текущий engine, актуальную финансовую policy version, наличие semantic verification и market fingerprint, повторно применяет `is_publishable`, сортирует кандидатов и использует стабильную пару publication/delivery ID для Pro recipient и `pro/v1`. Существующие `sent`, `sending`, `unknown`, `failed` не отправляются повторно; `pending` переочередяется; отсутствующая пара event/outbox создаётся атомарно.

Admin API содержит `GET /admin/pro-publications` и `POST /admin/pro-publications/run`. Ручное действие не принимает recipient или текст, требует точного подтверждения и запускает только `deal-sniper-publisher` через Cloud Run API. Admin Web показывает покрытие и результат запуска. Price-only runtime revision сохраняет прежнюю financial config version; при изменении финансовых порогов используется детерминированный policy fingerprint.

Локальный gate успешен: 94 passed, 2 skipped, Ruff, strict mypy, ES-module syntax и diff check. Production остаётся на R6 (`851ddaf26852aaaa0547df1b60e222d7f74b5d9a`, digest `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`) до нового immutable build, staging evidence и отдельного разрешения владельца.

## R7.1 — staging 28 июля 2026

Реализация `07e89b79e3a46deade619a87b115157d3df4209a` прошла два GitHub Actions запуска. Cloud Build `18c2f73a-d5e5-4ec4-84dc-e948c7f9b706` собрал immutable digest `sha256:d1fa347b8b4a528b89ba93ad6ab0a3ca11c86813ad514c44097cf8300d92998c` из точного git archive. Digest работает только в staging revision `deal-sniper-api-staging-00035-gst` с базой `deal-sniper-stage-rc2` и delivery/WhatsApp off. Staging Gateway `r71-07e89b7`, системные endpoints и CORS успешны. Hosting Preview version `06e7b909a8895569` направлен только на staging. Автоматический authenticated smoke Pro coverage требует повторной ADC-авторизации либо `iam.serviceAccounts.signBlob`; временный Firebase user не создавался. Production полностью остаётся на R6.

Перед ручным smoke обнаружено, что Admin API использовал жёсткое production-имя publisher Job. R7.1 дополнен обязательным разделением: `PUBLISHER_JOB_NAME=deal-sniper-publisher-staging` в staging и `deal-sniper-publisher` в production, оба значения входят в точный allowlist, остальные отклоняются. Исправленный local gate: 95 passed, 2 skipped, Ruff, strict mypy, JavaScript и diff check. Digest `sha256:d1fa347b…2998c` больше не является финальным кандидатом; требуется новый commit/build/staging. Production не изменён.

Финальный R7.1 commit `4aaf252c47e1c7d1f60e839fcf7cac6c019fd07c` прошёл оба GitHub Actions запуска. Cloud Build `977cb039-a9b4-4234-9803-cd09a1037e77` собрал immutable digest `sha256:41b04c0ed5f1e7fd5a3e738f34dbb7121d60e4c3c02cc28300d2002ab11caa99`; он развёрнут только в staging API revision `deal-sniper-api-staging-00036-87b` и отдельном `deal-sniper-publisher-staging`. Изолированный fixture подтвердил один выбранный и один атомарно созданный Pro outbox без ошибок и без внешней доставки, затем все тестовые данные удалены. Production остаётся на R6 commit `851ddaf26852aaaa0547df1b60e222d7f74b5d9a`, digest `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`, Gateway `deal-sniper-config-source-12bdee5` и Hosting `c110b289b2855e7f`. Для закрытия staging остаётся ручная authenticated проверка Publications в Preview; production deploy требует отдельного разрешения.

Владелец потребовал заменить забытый Firebase-пароль на Google Sign-In. Read-only аудит подтвердил, что Firebase Google provider включён, authorized domains настроены, но provider связан с IAP OAuth client, который ранее вызвал `redirect_uri_mismatch`. Создан план `docs/PLAN_R7_2_GOOGLE_ADMIN_AUTH.md`: отдельный Web OAuth client, popup-вход, сохранение `ADMIN_EMAILS`, обязательный `email_verified`, контролируемая миграция существующей password-account и staging без изменения production. Код и облачная конфигурация не меняются до утверждения R7.2.

R7.2 утверждён и реализован локально: Admin Web использует Google popup с явным redirect fallback, password UI удалён, backend требует `email_verified=true` и allowlisted email. Полный локальный gate успешен: 99 passed, 2 skipped, coverage 57,55%, Ruff, strict mypy, JavaScript syntax, dependency audit, Terraform validate и diff check. OAuth provider и production ещё не менялись. Одновременно подтверждено, что production R6 не имеет R7.1 Pro reconciliation, а новости существуют только как on-demand ответ бота. Для регулярных проверяемых Pro deals/news и управляемого Vertex AI summary создан отдельный черновик `docs/PLAN_R7_3_PRO_CHANNEL_CONTENT.md`; требуется утверждение до кода.

R7.2 commit `fe13453392f2b9007e97b84d3695f9dd9fe749c4` прошёл GitHub Actions `30382432905` и `30382437156`: Python 3.11 quality, container build, Trivy и Terraform успешны. До staging Google smoke требуется отдельный Web OAuth client и переключение Firebase provider; production R6 не изменён.

R7.3 утверждён и реализован локально. `run_content_publication` сначала сверяет полные Pro deal cards через R7.1, затем независимо формирует Pro news digest и после этого публикует Free Market Pulse. Новостной контур читает только настроенные HTTPS RSS/Atom, фильтрует свежесть, Dubai/UAE и automotive relevance, сохраняет URL/publisher/date, дедуплицирует semantic fingerprint и использует стабильные PublicationEvent/outbox IDs. Pending digest можно безопасно переочередить; sent/sending/unknown/failed автоматически не дублируются.

News feed registry реализован в SQLite и Firestore (`news_feed_registry`). Admin Web и API управляют registry, Pro deals/news switches, 1–3 items, interval и Vertex intro. Vertex AI получает только данные отобранных материалов и является необязательным: при ошибке публикуется детерминированный английский digest. Полный локальный gate: 105 passed, 2 skipped, coverage 58,82%, Ruff, strict mypy, ES-module syntax, dependency audit, Terraform validate и diff check. Docker Desktop Linux engine выключен, поэтому локальный container build не выполнен и должен быть закрыт CI container/Trivy. Production остаётся на R6; до выпуска нужны commit/CI, immutable image, delivery-off staging evidence и отдельная команда production deploy.

Implementation commit `48e3132f12fa2b4fa7f7ad8fdb6cf747543d3cbb` отправлен в Draft PR #3. GitHub Actions `30387369703` и `30387367900` прошли quality, container build, Trivy и Terraform. Предварительный R7.3 evidence создан; production не изменён. Следующий шаг — новый evidence commit, immutable Cloud Build из его точного git archive и delivery-off staging.

R7.3 immutable staging почти завершён. Evidence commit `c6c283667a889f030581fe3adcc6814d52d8f9cd` прошёл CI; Cloud Build `46d3f002-8073-4ebb-8cf7-3faefa507831` создал digest `sha256:d52c10aae8b19afad46ef380d47887e5ecdcf8d30136a245fdbf05b16cda50f5`. Он развёрнут только в `deal-sniper-api-staging-00038-f2j` и publisher staging generation 4. Активна runtime revision `r73-stage-c6c2836` с Pro deals/news; staging Gateway использует config `r73-c6c2836`, системные endpoints и CORS успешны. Два последовательных publisher execution создали ровно один pending `pro-news/v1` outbox и один стабильный task ID, подтвердив отсутствие дублей. Проверка выполнялась через отдельную PAUSED-очередь `telegram-delivery-staging`; тестовая задача удалена, очередь пуста. Delivery/WhatsApp выключены. Остались Firebase re-auth, Hosting Preview и authenticated UI smoke. Production остаётся на R6 и не изменялся.

Firebase re-auth выполнен; R7.3 Hosting Preview version `ec7232df3745213e` опубликована по `https://avo-deal-sniper--r73-c6c2836-j51jtx2p.web.app` и направлена только на staging. Static assets, CSP, runtime config и CORS успешны; staging API revision `deal-sniper-api-staging-00040-xf9` использует тот же immutable digest. Authenticated smoke выявил незакрытый R7.2 cloud prerequisite: Google provider связан с IAP-only OAuth client и возвращает `INVALID_IDP_RESPONSE` по audience. До создания отдельного Web OAuth client и переключения provider R7.3 staging не закрыт, production R6 не изменяется.
