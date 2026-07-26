# AI Context: Dubai Deal Sniper

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
