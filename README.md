# Dubai Deal Sniper

Сервис подбора автомобилей с фиксированной ценой на рынке ОАЭ. Первый интерфейс —
Telegram-бот; TMA будет добавлена после нового официального пилота.

> **Статус репозитория на 24.07.2026:** default-ветка `main` пока содержит legacy-прототип
> с mock/SQLite/Gemini и не воспроизводит развёрнутый Google Cloud контур. Новая реализация
> находится в draft PR #1 и требует отдельно разрешённого `0.11-STOP`, repository gate
> `0.11R`, стабилизационных релизов `0.11A–0.11C`, immutable candidate `0.11RC`,
> миграции `0.11M`, baseline-релиза `0.11D` и официального пилота `0.11P` из
> `docs/IMPLEMENTATION_PLAN.md` до слияния. Production временно развёрнут из этой неслитой
> рабочей ветки и содержит известные блокирующие дефекты; считать `main`, draft PR или
> развёрнутый образ утверждённым production-baseline нельзя.

## Что реализовано в draft-ветке, но не принято

- реальный сбор объявлений DubiCars, CarSwitch, Cars24 UAE и OpenSooq UAE;
- несколько страниц источника за один запуск;
- SQLite-хранилище для локального запуска с `listing_id` и `content_hash`;
- сохранение новых версий и обнаружение изменения цены;
- raw HTML/JSON в Cloud Storage до parsing;
- первая версия cross-source identity resolution и исключения дублей, требующая `0.11B`;
- первая версия Comparable, Cost, Risk и Decision Engines, не принятая как экономически надёжная;
- команды Telegram `/start`, `/status`, `/scan`, `/deals`, `/settings` и `/watchlist`;
- английские карточки в Telegram-канале и автоматический русский/английский язык личного бота по языку устройства;
- Telegram delivery с известным failure window между отправкой и записью результата;
- тесты, Ruff, mypy, GitHub Actions и Dockerfile.

SQLite используется только локально. Production-контур хранит объявления, версии цен,
решения и отметки доставки в Firestore.

## Временно развёрнутый кандидат production-контур — использование ограничено

- Cloud Run API принимает Telegram webhook через API Gateway;
- отдельные Cloud Run Jobs собирают DubiCars, CarSwitch, Cars24 и OpenSooq;
- Cloud Scheduler запускает каждый источник каждые 10 минут по времени Дубая;
- `listing-processing` выполняет расчёты, `telegram-delivery` доставляет карточки;
- токены хранятся в Secret Manager, данные — в Firestore, raw — в Cloud Storage;
- delivery использует отметку отправки, но не гарантирует отсутствие дубля при сбое после Telegram API;
- snapshot provenance, owner scope, роли и актуальность решений требуют исправления до пользовательской эксплуатации.

До выполнения `0.11-STOP`, `0.11R` и `0.11A` не следует использовать `/scan`, `/deals`, `/watchlist`
и команды управления источниками для обычных пользователей. Автоматические финансовые
публикации должны быть остановлены отдельным подтверждённым эксплуатационным действием.

## Локальная подготовка

Требования: Windows 11, PowerShell и Python 3.11.

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

## Первый запуск без Telegram

```powershell
python main.py scan
```

Команда получает реальные объявления, сохраняет их в `data/deal_sniper.db` и выводит
сводку. Повторный запуск не создаёт новые версии неизменившихся объявлений.

## Запуск Telegram-бота

1. Создайте бота через `@BotFather` и получите токен.
2. Скопируйте `.env.example` в `.env`.
3. Запишите токен в `TELEGRAM_BOT_TOKEN`.
4. Временно запустите бота и отправьте ему `/id`:

```powershell
python main.py bot
```

5. Запишите показанный ID в `TELEGRAM_ALLOWED_USER_IDS`. Несколько ID разделяются
   запятыми.
6. До завершения стабилизации не используйте `/scan` и `/deals` с production-данными;
   локальные команды допустимы только в изолированной fixture/dev-среде.

Команды:

- `/id` — показать Telegram user ID;
- `/start` и `/help` — справка;
- `/status` — число сохранённых версий;
- `/scan` — получить свежие объявления и рассчитать кандидатов;
- `/deals` — показать последние `CONTACT` и `INSPECT` решения.
- `/sources` — показать источники, состояние и объём последнего сбора;
- `/source_on cars24` или `/source_add cars24` — включить источник;
- `/source_off cars24` или `/source_remove cars24` — отключить без удаления истории;
- `/source_scan cars24` — проверить только выбранный источник.
- `/settings` — показать персональные фильтры;
- `/set_budget 150000`, `/set_profit 7000`, `/set_roi 12` — изменить пороги;
- `/set_makes Toyota,Lexus` — ограничить марки;
- `/watch <listing_id>` и `/watchlist` — вести список наблюдения;
- `/contacted`, `/inspect`, `/reject` с ID — вести сделку по воронке.

## Публикация в Telegram-канал

1. Добавьте бота администратором канала с правом публикации сообщений.
2. Укажите в `.env` `TELEGRAM_CHANNEL_ID=@channel_username`, а для платного закрытого канала — `TELEGRAM_PRO_CHANNEL_ID=-100...`. Для приватного канала
   используется числовой ID вида `-100...`.
3. Выполните:

```powershell
python main.py publish
```

Команда сканирует источник и отправляет в канал решения `CONTACT` и `INSPECT`.
Текущая реализация не гарантирует отсутствие дубля во всех failure windows и не должна
использоваться для production-публикации до `0.11-STOP`, repository gate `0.11R`,
`0.11A–0.11C`, immutable candidate `0.11RC`, миграции `0.11M`, baseline `0.11D` и пилота `0.11P`.

В production публикацию выполняют Cloud Tasks; локальная команда `publish` оставлена
для smoke test. Компьютер владельца для расписания не требуется.

## Настройка подбора

Основные параметры `.env`:

- `DUBICARS_MAX_PAGES` — сколько страниц проверять;
- `CARSWITCH_MAX_PAGES`, `CARS24_MAX_PAGES`, `OPENSOOQ_MAX_PAGES` — глубина каждого коллектора;
- `MIN_COMPARABLES_COUNT` — минимум аналогов для расчёта;
- `TARGET_PROFIT_AED` — целевая прибыль;
- `MIN_ROI_PERCENT` — минимальный ROI;
- `DEFAULT_NON_PURCHASE_COST_AED` — базовые расходы помимо покупки;
- `INSPECTION_COST_AED`, `PREPARATION_COST_AED`, `BASE_REPAIR_RESERVE_AED` — расходы;
- `HOLDING_COST_PER_DAY_AED`, `ANNUAL_CAPITAL_PERCENT`, `SELLING_COST_PERCENT` — экономика;
- `CHANNEL_MAX_POSTS_PER_RUN` — максимальное количество лучших новых карточек за один проход;
- `DUBICARS_URL_TEMPLATE` — страница поиска; можно использовать уже отфильтрованный
  URL, сохранив `{page}` для номера страницы.

Секреты нельзя добавлять в Git. Файл `.env` уже исключён через `.gitignore`.

## Проверки

```powershell
python -m pytest
python -m ruff check .
python -m mypy src
```

Terraform production-контура находится в `infra/terraform`; конфигурация проходит
`terraform validate` в CI. Для существующего проекта перед `apply` требуется import,
описанный в `infra/terraform/README.md`.

## Docker

```powershell
docker build -t deal-sniper .
docker run --rm --env-file .env -v "${PWD}/data:/app/data" deal-sniper python main.py scan
docker run --rm --env-file .env -v "${PWD}/data:/app/data" deal-sniper python main.py bot
```

Для публикации в канал замените последнюю команду контейнера на `publish`.
