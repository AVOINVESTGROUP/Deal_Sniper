# AI Context: Dubai Deal Sniper

R8.1.3F утверждён владельцем, реализован и прошёл immutable delivery-off staging.
CarSwitch архивирует каждый HTTP 200
до semantic validation и в едином bounded budget проверяет строгий HTML MIME, непустое
тело и `ItemList`. После трёх semantic transient записываются
`error_category=semantic_empty_response` и `attempts=3`; snapshots/decisions не создаются.
Admin показывает категорию и число попыток. Content-addressed raw payload дедуплицирует
одинаковые тела по checksum, а каждый вызов имеет отдельное append-only событие
`raw_snapshot_attempt` с номером, временем и URI. Regression-тест подтверждает один payload
и три capture-события. Полный повторный gate успешен: Ruff, strict mypy по 42 source-файлам,
`153 passed / 2 skipped`, coverage `62,44%`, audit, Terraform, JS и Docker Python 3.11.
Commit `925597043f3596c1296723a668337dc474e8495a` прошёл оба GitHub Actions запуска;
Cloud Build `44381975-eca8-4165-b692-a3452fcfab7a` создал digest
`sha256:48ddd19e…22323`. Exact digest прошёл три цикла 4/4 источников в отдельной staging
database/bucket при PAUSED пустой queue и выключенной доставке. Production не изменён;
нужно только отдельное разрешение владельца на production deploy R8.1.3. Старый digest
`sha256:4ecc211f…8d22` остаётся запрещён к продвижению.

31 июля 2026 delivery-off staging R8.1.3 использовал commit
`737cd8a14f5f498adfd6d2a2753e1edc68e92468`, Cloud Build
`5a2f43b7-47f5-4ad5-b654-8e86e08d40c0` и digest
`sha256:4ecc211ff5d5e32f3ba58610a77775249ea80200276f737ee6fd0b5ca2188d22`.
API revision `deal-sniper-api-staging-00049-8gh` вернула точные commit/digest,
`delivery=false`; отдельная очередь `telegram-delivery-staging` осталась `PAUSED`.
Первый реальный цикл 4/4 источников завершился успешно. Второй выявил CarSwitch HTTP 200
с пустым raw body (SHA-256 `e3b0c442…b855`): семантическая ошибка возникает после
существующего network/HTTP retry и не повторяется. Staging gate остановлен, production
не изменён. Точный диагноз и требуемое отдельное утверждение исправления зафиксированы
в разделе R8.1.3F плана; этот digest запрещено продвигать.

## Production R8.1.1 Free → Pro (29 июля 2026)

R8.1.1 работает в production на source commit `308545a43a3b06d32f984e5d8d5d18294750f87a`, digest `sha256:7a8ed30227434bfe6411e3d457a76b550c5ba39d9dd877560c4fed05223af897`, API revision `deal-sniper-api-00062-s79`. Независимые `free/v2` и объектный `market-watch/v2` отключены; `free/v3` создаётся и доставляется только после exact Pro `sent` той же revision. 75 недоказуемых legacy Free-постов удалены с audit trail, повторный preview показывает `unsafe=0`. Production evidence подтверждает `eligible=1`, `sent=1`, нулевые blocked/failure/legacy-счётчики и точную пару Free message `163` → Pro message `27`. Очередь RUNNING и пуста, content scheduler ENABLED. Полное доказательство: `docs/RELEASE_EVIDENCE_2026-07-29-R8_1_1.md`.

## Локальный кандидат R8.1.1 Free → Pro (29 июля 2026)

Владелец утвердил `docs/PLAN_R8_1_1_FREE_PRO_INTEGRITY.md`. Локальный кандидат удаляет независимые Free-пути: `free/v3` создаётся только после `sent` Pro outbox с теми же `decision_id + listing_id + content_hash`, сохранённым `telegram_message_id` и parent-связью. Delivery повторно проверяет эту связь; legacy `free/v2` и объектный `market-watch/v2` блокируются. Free получает отдельные кнопки подписки и точного Pro-сообщения. Добавлены Admin-метрики и reconciliation старых публикаций. Mock, synthetic и LLM-invented факты в production запрещены. Последний полный локальный gate: 126 passed, 2 skipped, coverage 60,18%; production ещё работает на R8.1 до immutable build и контролируемого cutover.

## Текущее production-состояние R8.1 (29 июля 2026)

R8.1 активен в production. Канонический runtime source commit — `aa261129415065b63d4be85f098cd0e255966ab1`, immutable digest API/publisher — `sha256:0efbc0699d8a79f9c8e4802a15f274debb1b25843d5c19cdc3b47d910c73fd0b`. API работает на revision `deal-sniper-api-00061-tlq`, publisher — generation `41`.

Существующий Pro-канал `-1004319276577` получил проверенную новостную публикацию с Telegram message ID `29`; повторный запуск не создал дубль. Scheduler `deal-sniper-content-every-6h` включён. Новая Pro-сделка публикуется только при прохождении detail-page, market, profit и ROI gates; отсутствие подходящей сделки не подменяется тестовыми данными. Отдельного тестового Telegram-канала нет и создавать его не требуется.

Полное доказательство релиза и rollback находятся в `docs/RELEASE_EVIDENCE_2026-07-29-R8_1.md` и `docs/R8_1_RELEASE_MANIFEST.json`.

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

R8.1 реализован локально после явного утверждения плана R8. Первый CI gate выявил нарушение fail-closed: конструктор `CloudTaskDispatcher` запрашивал ADC при выключенной доставке. Клиент Cloud Tasks переведён на ленивую инициализацию, добавлен регрессионный тест. Полный повторный локальный gate: 113 passed, 2 skipped, coverage 59%, Ruff, strict mypy, pip-audit и Terraform validate успешны. До зелёного повторного CI, immutable staging build и реального Telegram smoke production остаётся на R6 без изменений.

Исправление R8.1 в коммите `8eeb13326233a1b3ff6006914922385ecc3b1a05` прошло GitHub Actions push `30429176591` и PR `30429177595`: Python 3.11 quality, container/Trivy и Terraform зелёные. Следующий разрешённый этап — immutable build и изолированный staging; production deploy всё ещё требует отдельной явной команды владельца.

Immutable R8.1 staging собран из финального commit `4e3f67e4d9f5b9a46ca224c045f0e596a5514201`: Cloud Build `63ce516a-2ba4-4af7-82bb-7df6b51f7a0e`, digest `sha256:928ddb983b793e9f77a5248dd5dec4cd2a542b55b08510523857b9bc62f18649`. Exact digest работает только в staging API revision `deal-sniper-api-staging-00041-vp6` и publisher generation `5`; база `deal-sniper-stage-rc2`, delivery off, очередь `telegram-delivery-staging` PAUSED и пуста. Два publisher execution успешно подтвердили requeue без дублей и отсутствие Cloud Tasks. Для закрытия R8.1-STAGE нужен отдельный настоящий Telegram test Pro channel; production R6 не изменён.

Владелец явно потребовал отказаться от отдельного тестового канала и завершить bounded cutover в существующем production Pro-канале. Production preflight обнаружил ложную news-классификацию: подстрока `car` внутри `Pogacar` проходила automotive gate. Реализована проверка целых терминов и регрессионный тест; локальный gate — 114 passed, 2 skipped и все quality/security/IaC проверки успешны. Для production выбран проверенный прямой RSS `https://www.dubicars.com/news/feed`, возвращающий актуальные UAE automotive материалы. До нового CI и immutable build production остаётся на R6.
## R8.1.2 — обнаруженное расхождение новостей 29 июля 2026

Production evidence показал противоречие: `deal-sniper-publisher` в 13:16 GST создал одну
news delivery, доставка в Pro прошла в 13:17, а следующий webhook чата вернул сообщение об
отсутствии ленты. Pro-карточка имела прямой URL DubiCars, но publisher `Google News`.

Причина подтверждена кодом и конфигурацией. `src/pro_news.py` читает Firestore registry и при
его отсутствии создаёт environment fallback с `publisher="Google News"`; `src/web.py` содержит
отдельный глобальный `DubaiAutoNewsClient`, который для каждого chat NEWS intent напрямую
читает `AUTO_NEWS_RSS_URL`. Production registry пуст, URL равен
`https://www.dubicars.com/news/feed`, а общий сохраняемый news evidence отсутствует.

Создан план `docs/PLAN_R8_1_2_NEWS_CONSISTENCY.md`. До его утверждения нельзя менять код,
Firestore, Telegram-публикации или production. Целевое исправление — единый registry-backed
ingestion, immutable `news_evidence`, publisher/domain validation и чтение одного evidence
Pro-каналом, личным ботом и связанным чатом. LLM не имеет права создавать или изменять факты.

## R8.1.3 — отсутствие новых автомобильных публикаций 29 июля 2026

Read-only production-аудит подтвердил, что Telegram delivery и exact Pro→Free linkage работоспособны, но конвейер почти не формирует новых кандидатов. Из 1 643 current decisions: `INSUFFICIENT_DATA=1578`, `REJECT=64`, `INSPECT=1`, `CONTACT=0`; market estimate существует у 65. Единственный допустимый candidate уже имеет terminal `sent`, поэтому повторная публикация корректно подавляется.

Также обнаружены неправильная фактическая частота source schedulers (`0/10`, `2/10`, `4/10`, `6/10` дают часовой интервал), schema drift DubiCars по отсутствующему `offers`, detail verification `ReadTimeout` и шестичасовая задержка планового publisher. Создан черновик `docs/PLAN_R8_1_3_LISTING_PUBLICATION_RECOVERY.md`. Он сохраняет fail-closed и запрет вымышленных данных, исправляет сбор/verification, вводит версионируемые уровни доказуемых аналогов, event-driven exact Pro→Free delivery, bounded replay и Admin funnel. Код и production до утверждения плана не изменяются.

Дополнительный read-only аудит новостных иллюстраций подтвердил отсутствующую функцию, а не Telegram-сбой. Новости направляются только в Pro как `pro-news/v1`; Free получает отдельный текстовый Market Pulse `content/v1`. Все 31 production `content/v1` и три `pro-news/v1` payload не имеют `image_url`; `NewsItem` также не хранит изображение. План R8.1.2 дополнен source-backed image evidence, проверкой publisher/CDN-домена и MIME, immutable asset в Cloud Storage, отдельными `free-news/v1`/`pro-news/v2`, запретом text fallback при ошибке изображения и Admin preview. Код и production не изменены.

R8.1.2 явно утверждён владельцем и реализован локально. `NewsIngestionService` является единственным live-fetch путём и сохраняет проверенный `news_evidence` вместе с immutable Cloud Storage asset; Pro, Free, личный бот и чат читают это evidence. Publisher создаёт парные `pro-news/v2`/`free-news/v1` photo outbox с одинаковыми factual fields и image SHA-256. Реальный DubiCars smoke принял 5 из 5 материалов; парный delivery-off smoke создал четыре карточки для двух статей. Ruff, strict mypy, 130 passed/2 skipped и Terraform validate успешны. Production остаётся без изменений до CI, immutable staging и отдельного разрешения deploy.

Cloud preflight R8.1.2 обнаружил IAM-разрыв до staging: фактический publisher Job работает под `deal-sniper-publisher`, но Storage binding был только у runtime SA. Terraform и архитектурная документация исправлены; ранний build `sha256:0e27a52fdbc36d4a7e1e728dc914806f1ac805a7bf5137a12b3dd85ff1a6f977` не является кандидатом и не развёртывался. Требуются новый commit, CI и immutable build.

Первый delivery-off staging digest `sha256:f51b0a167abbf8528c84b5ca37a2209c01ee5638d9cdcf1b4cbc3beb57804435` корректно сохранил 5 DubiCars evidence/assets и создал точные Free/Pro preview-пары без Cloud Tasks. Проверка двухлентового health выявила накопительный `accepted` между feeds; публикации и evidence не искажались, но Admin-метрика могла быть завышена. Исправление добавляет per-feed counter и regression test, поэтому этот digest также аннулирован и требуется новый CI/build/staging.

Следующий staging digest `sha256:6a0f6e41fbb2d178f3312fda79b6d821581cf5382d08a7fdb44da2f008201c19` подтвердил exact Free/Pro evidence/image пары, идемпотентный повтор и ноль Cloud Tasks. Перед финализацией к обязательной матрице добавлен отдельный transient-feed regression: сохранённая свежая evidence переживает временную сетевую ошибку, а source health фиксирует её тип. Runtime не менялся, но build context изменён, поэтому требуется последний exact commit/build/staging.

Immutable staging R8.1.2 завершён. Финальный source commit `946db4e175fbe3c46f4ce155660bafb2656b9f7f`, Cloud Build `91fa7335-18b4-4bf9-a0fe-bfa7154521c3`, digest `sha256:6d6d44e29a9512819460c46b648bc037716614d78af9148a76fbcde07e7745aa`, API revision `deal-sniper-api-staging-00047-k42`. Live ingestion сохранил пять DubiCars evidence/assets; две статьи имеют четыре точные Free/Pro preview-записи с одинаковыми evidence/image SHA. Повтор не создал дублей, staging queue PAUSED и пуста. Production не изменён; следующий шаг — только отдельное разрешение владельца на bounded production cutover. Evidence: `docs/RELEASE_EVIDENCE_2026-07-29-R8_1_2.md`.

30 июля владелец разрешил production deploy R8.1.2. Backup `r812-production-20260730-100157`, delivery-off exact-digest deploy и production ingestion прошли, но paused-queue gate остановил отправку: publisher поставил Free news и legacy `content/v1`, оставив парную Pro news pending. Обе задачи удалены при dispatch=0; Telegram не затронут. Выполнен полный rollback на R8.1.1 (`deal-sniper-api-00064-9sk`, digest `sha256:7a8ed302…af897`, publisher generation 55, прежний Gateway, queue RUNNING/пуста, scheduler ENABLED). Immutable evidence, registry entry и pending Free/Pro пара сохранены без Cloud Tasks для следующего идемпотентного rehearsal. Digest R8.1.2 аннулирован как production candidate.

План R8.1.2.1 утверждён и реализован в ветке `production/deal-sniper-complete`, но ещё не
развёрнут. Новый контракт: ровно одна `free-news/v1` + одна `pro-news/v2` на evidence;
одинаковые factual fields/image SHA; Pro-задача ставится первой; общий `news_pair_ready`
создаётся только после обеих постановок; delivery endpoint fail-closed без ready-маркера;
Free отправляется только после `sent` соответствующей Pro-карточки. `python main.py news`
не запускает сделки, Free object reconciliation или `content/v1`; Terraform добавляет
`deal-sniper-news-publisher` и `deal-sniper-news-every-6h`. Admin показывает
`paired_pending`, `paired_enqueued`, `blocked_pair`. Локальный gate: 136 passed / 2 skipped,
61,5% coverage, Ruff, strict mypy, dependency audit и Terraform validate. Production
по-прежнему R8.1.1; старые pending evidence/outbox и backup сохранены.

## R8.1.2.1 — блокирующий container gate 30 июля 2026

Commit `6596ae85730ee948b1036799ee8e91378201e43a` имеет зелёные Python 3.11 quality и Terraform jobs, но красный container/Trivy. Read-only диагностика официального `python:3.11.15-slim-bookworm` нашла `CVE-2026-23949` в vendored `setuptools/_vendor/jaraco.context 5.3.0` и `CVE-2026-24049` в vendored `setuptools/_vendor/wheel 0.45.1`; исправленные версии — `6.1.0` и `0.46.2`. Debian HIGH/CRITICAL отсутствуют. Текущий workflow скрывает детали в неэкспортируемом SARIF. Создан черновик `docs/PLAN_R8_1_2_1_SECURITY_GATE_ADDENDUM.md`: двухэтапный runtime без build tooling и наблюдаемый, но неизменно блокирующий Trivy. Код и облако не изменены; требуется явное утверждение владельца.

Дополнение утверждено и реализовано локально. Dockerfile использует отдельные builder/runtime stages; итоговый runtime не содержит импортируемых `pip`, `setuptools` и `wheel`, но успешно импортирует `src.web:app`. Локальный Trivy 0.70.0 подтверждает ноль исправляемых HIGH/CRITICAL для Debian 12.15 и Python-зависимостей. CI сохраняет прежний блокирующий порог и добавляет читаемый table output плюс всегда сохраняемый SARIF artifact. Полный локальный gate: 136 passed / 2 skipped, 61,5% coverage, Ruff, strict mypy, pip-audit, Terraform и JavaScript syntax. Production и staging не изменены; требуется зелёный GitHub Actions commit до immutable build.

Security Gate R8.1.2.1 закрыт на implementation commit `6dd9af358772f9c37ed006632c0202b19d91fd5a`: GitHub Actions `30542429343` и `30542431711` зелёные и сохраняют Trivy SARIF. Cloud Build `623817ea-787f-45ec-af4d-9765ed44dbcd` собрал exact digest `sha256:b6a2e5cb9ae7de2c14e2e26bc141c077292d78e16c1e23ffee1f1f6573de75f4`; exact runtime/registry smoke успешны. Staging API revision `deal-sniper-api-staging-00048-bxv` подтвердила commit/digest/schema 2. В PAUSED staging queue execution `deal-sniper-publisher-staging-qx9nb` поставил ровно `pro-news/v2` → `free-news/v1` для одной evidence revision и одного image SHA, без `content/v1`, dispatch=0; обе задачи после проверки удалены. Delivery-off повтор `deal-sniper-publisher-staging-kf8lh` не создал дублей, очередь пуста. Fail-closed guard отдельно отклонил staging delivery до явной конфигурации staging publisher и production-recipient allowlist. Production остался на R8.1.1 (`deal-sniper-api-00064-9sk`, publisher generation 55, digest `sha256:7a8ed302…af897`); новый production deploy R8.1.2.1 требует отдельного разрешения владельца.

30 июля владелец отдельно разрешил и завершён production deploy R8.1.2.1. Перед cutover создан успешный export `gs://avo-deal-sniper-firestore-exports/r8121-production-20260730-144413`. Exact digest `sha256:b6a2e5cb9ae7de2c14e2e26bc141c077292d78e16c1e23ffee1f1f6573de75f4` работает в API revision `deal-sniper-api-00066-lcf`, основном content job и отдельном news-only job; `/version` возвращает implementation commit `6dd9af358772f9c37ed006632c0202b19d91fd5a`, тот же digest и schema 2. Первая production-пара одной DubiCars evidence доставлена Pro message `37` → Free message `171`; вторая bounded-проверка выбрала другую, ещё не публиковавшуюся evidence и доставила Pro `38` → Free `172`, поэтому дубля первой статьи не возникло. В каждой паре совпадают publisher, URL, semantic fingerprint и image SHA, legacy `content/v1` в news-only run отсутствует. Публичные Free URL `https://t.me/Dubai_Auto_Invest/171` и `/172` возвращают HTTP 200 и содержат изображения. `deal-sniper-news-every-6h` и `deal-sniper-weekly-market-pulse` включены; прежний совмещённый `deal-sniper-content-every-6h` остановлен во избежание конкуренции. Очередь `telegram-delivery` RUNNING, лимиты 5 concurrent/10 per second, хвост пуст.

Повторный read-only аудит автомобильного pipeline 30 июля подтвердил, что R8.1.2.1 решил
парную доставку новостей, но не восстановил автомобильные предложения. В production 1 690
current decisions: 1 608 `INSUFFICIENT_DATA`, 81 `REJECT`, один `INSPECT`, ноль `CONTACT`; market
есть только у 82. Единственный publishable `opensooq:284587230` уже отправлен в Pro message `35`,
поэтому нового объекта для доставки нет. Источники не пусты: последние циклы получили
DubiCars/CarSwitch/Cars24/OpenSooq 143/120/125/141 записей, однако ошибочные cron `0/10`, `2/10`,
`4/10`, `6/10` запускают их раз в час. DubiCars продолжает фиксировать `KeyError: offers`, а API
за два часа получил 136 HTTP 429 при detail verification. Дополнительно collectors остались на
старом digest `sha256:c2e55afd…da9112`, тогда как API/publishers используют
`sha256:b6a2e5cb…de75f4`. План R8.1.3 обновлён: единый immutable runtime, правильные интервалы,
schema-compatible adapters, source-aware rate limiting, tiered deterministic comparables,
event-driven Pro→Free и Admin funnel. Код и production до явного утверждения R8.1.3 не меняются.
## R8.1.3 — текущий контекст (30 июля 2026)

План R8.1.3 утверждён. Локально реализовано восстановление контура автомобильных
объявлений без ослабления доказательности: правильные десятиминутные cron, устойчивый
DubiCars parser, source-aware verification retry/rate limit, tiered comparable selector,
двухволновая обработка для перерасчёта рынка, event-driven Pro→Free и отдельный
15-минутный reconciliation publisher. Free по-прежнему создаётся только после точной
Pro revision со статусом `sent`; выдуманные объекты, цены и аналоги запрещены.

Admin Web получил воронку `fetched → verified → normalized → market → decision → Pro
sent → Free sent`, ограниченную параллельность запросов и прямой Cloud Run admin API с
Firebase ID token. Локальный gate успешен: Ruff, strict mypy, 143 passed / 2 skipped,
Terraform fmt/validate и Docker build. Production остаётся на прежнем релизе: deploy,
replay и Telegram-доставка допускаются только после immutable commit/build,
delivery-off staging evidence и отдельного разрешения владельца.

## R8.1.3F — immutable delivery-off staging (31 июля 2026)

После отдельного утверждения дополнения CarSwitch получил bounded semantic retry для пустого
HTTP 200, неверного MIME и отсутствующего ItemList. Каждый HTTP capture создаёт append-only
`raw_snapshot_attempt`; одинаковые тела сохраняют один content-addressed payload, но имеют
раздельные события с номером попытки и временем. Полный локальный gate: Ruff, strict mypy по
42 source-файлам, 153 passed / 2 skipped, coverage 62,44%, pip-audit, Terraform,
JavaScript syntax и Docker Python 3.11 runtime без build tooling.

Source commit `925597043f3596c1296723a668337dc474e8495a` прошёл GitHub Actions push
`30619171198` и Draft PR `30619176067`. Cloud Build
`44381975-eca8-4165-b692-a3452fcfab7a` создал immutable digest
`sha256:48ddd19e9f0abe8a93240045f0d51e9dbfb283a32d7265ddaf06df026be22323`.
Exact digest развёрнут только в staging API `deal-sniper-api-staging-00052-82s` и пяти
staging jobs. Используются `deal-sniper-stage-rc2`, отдельный bucket
`avo-deal-sniper-raw-snapshots-staging`, `DELIVERY_ENABLED=false` и PAUSED пустая очередь;
Telegram secrets отсутствуют.

Три последовательных live-цикла DubiCars, CarSwitch, Cars24 и OpenSooq завершились 12/12
успешно. Три CarSwitch capture имеют отдельные audit-события; live-сайт отвечал валидно с
первой попытки, а recovery/exhaustion ветки доказаны regression tests. Два publisher rehearsal
корректно дали ноль новых карточек и ноль задач, поскольку новой publishable revision не было.
Нормализованный production diff подтвердил неизменность revision/digest API, specs/generations
всех девяти jobs, Scheduler и очередей. Полное evidence находится в
`docs/RELEASE_EVIDENCE_2026-07-31-R8_1_3.md`. Production deploy, replay и Telegram-доставка
по-прежнему запрещены без отдельной команды владельца `Разрешаю production deploy R8.1.3`.

## R8.1.3G — migration allowlist blocker (31 июля 2026)

После явного разрешения production deploy preflight не допустил production-мутаций. Старый
migration replay epoch покрывает только 2 326 из 4 179 текущих revisions; 1 757 current
decisions используют engine 3.1.0, тогда как release требует 3.2.0. Дополнительный exact
staging replay завершился без application errors (`2 390 completed`, `389 skipped`), delivery
была выключена, staging queue PAUSED и пуста.

Новый migration epoch обязателен, но exact dry-run `deal-sniper-migration-staging-2wm9j`
остановился до apply: одиннадцать `publication_events` имеют фактически используемый
`publication-event/v3`, который пишет `src/firestore_storage.py`, а migration tool 1.2.0
явно знает только publication-event/v1 и общий `/v2`. План R8.1.3G ограничивает исправление
явным allowlist v3, generic upgrade только legacy `None`/`"1"`, сохранение всех уже
валидированных native contracts без write, bump tool до 1.2.1, validation/apply regression
tests, новый immutable build и полный staging migration/replay. Production не изменён. Код
и новый digest запрещены до утверждения владельцем `План R8.1.3G утверждаю`.

Read-only production schema audit подтвердил точную границу: `publication_events=177`, из
них `48` v1 и `129` v3; других unknown schema versions среди всех коллекций migrator и
вложенных snapshots нет. Migration apply текущего digest запускать нельзя.

Независимый review других code/schema blockers не нашёл и уточнил rollback: Firestore import
имеет merge-семантику. Staging apply выполняется только на disposable restored clone; при
сбое clone создаётся заново. Production при сбое остаётся STOP и delivery=false; предыдущий
digest является только maintenance rollback, а resume запрещён до компенсирующей процедуры
и сверки с export/ledger.

Владелец утвердил R8.1.3G. Локальная реализация завершена в точной границе: explicit
`publication-event/v3`, generic write только legacy `None`/`"1"`, сохранение native
v1/v2/v3 и `MIGRATION_TOOL_VERSION=1.2.1`. Усиленные regression-тесты используют реальный
validation path и commit-aware fake batch. Полный gate: Ruff, strict mypy, 156 passed / 2
skipped, coverage 63%, pip-audit, Terraform, JavaScript ES-module syntax и Docker Python
3.11 runtime; внутри образа подтверждён tool 1.2.1. Старый digest не продвигается.
Production не изменён. Следующий этап — новый immutable build и полный delivery-off
rehearsal на disposable staging clone; затем требуется новое отдельное разрешение владельца.
