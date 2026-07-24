# Dubai Deal Sniper

Сервис подбора автомобилей с фиксированной ценой на рынке ОАЭ. Первый интерфейс —
Telegram-бот; TMA будет добавлена после пилота. Production-версия работает в Google Cloud,
а новые кандидаты публикуются в канале `@Dubai_Auto_Invest`.

## Что уже работает

- реальный сбор объявлений DubiCars, CarSwitch и Cars24 UAE;
- несколько страниц источника за один запуск;
- SQLite-хранилище для локального запуска с `listing_id` и `content_hash`;
- сохранение новых версий и обнаружение изменения цены;
- детерминированные Comparable Price и Decision Engines без LLM;
- команды Telegram `/start`, `/id`, `/status`, `/scan` и `/deals`;
- публикация новых кандидатов в Telegram-канал без повторной отправки;
- тесты, Ruff, mypy, GitHub Actions и Dockerfile.

SQLite используется только локально. Production-контур хранит объявления, версии цен,
решения и отметки доставки в Firestore.

## Рабочий production-контур

- Cloud Run API принимает Telegram webhook через API Gateway;
- Cloud Run Job `deal-sniper-publisher` выполняет сбор, расчёт и публикацию;
- Cloud Scheduler запускает задачу каждые 10 минут по времени Дубая;
- токен Telegram хранится в Secret Manager, а данные — в Firestore;
- повторная публикация одной версии объявления блокируется отметкой доставки.

Проверка для владельца: откройте `@DubaiDealSniper111_bot` и выполните `/status`, `/scan`
или `/deals`. Для работы по расписанию компьютер пользователя включать не требуется.

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
6. Перезапустите бота и выполните `/scan`, затем `/deals`.

Команды:

- `/id` — показать Telegram user ID;
- `/start` и `/help` — справка;
- `/status` — число сохранённых версий;
- `/scan` — получить свежие объявления и рассчитать кандидатов;
- `/deals` — показать последние `CONTACT` и `INSPECT` решения.
- `/sources` — показать все зарегистрированные источники и их состояние;
- `/source_on cars24` или `/source_add cars24` — включить источник;
- `/source_off cars24` или `/source_remove cars24` — отключить без удаления истории;
- `/source_scan cars24` — проверить только выбранный источник.

## Публикация в Telegram-канал

1. Добавьте бота администратором канала с правом публикации сообщений.
2. Укажите в `.env` `TELEGRAM_CHANNEL_ID=@channel_username`. Для приватного канала
   используется числовой ID вида `-100...`.
3. Выполните:

```powershell
python main.py publish
```

Команда сканирует источник и отправляет в канал только новые версии решений
`CONTACT` и `INSPECT`. Успешная отправка записывается в локальную базу, поэтому
повторный запуск не дублирует публикацию.

Для автоматического запуска команду `python main.py publish` можно добавить в
Планировщик заданий Windows. Целевой production-вариант — Cloud Run Job и Cloud
Scheduler после перехода хранилища на Firestore.

## Настройка подбора

Основные параметры `.env`:

- `DUBICARS_MAX_PAGES` — сколько страниц проверять;
- `MIN_COMPARABLES_COUNT` — минимум аналогов для расчёта;
- `TARGET_PROFIT_AED` — целевая прибыль;
- `MIN_ROI_PERCENT` — минимальный ROI;
- `DEFAULT_NON_PURCHASE_COST_AED` — базовые расходы помимо покупки;
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

## Docker

```powershell
docker build -t deal-sniper .
docker run --rm --env-file .env -v "${PWD}/data:/app/data" deal-sniper python main.py scan
docker run --rm --env-file .env -v "${PWD}/data:/app/data" deal-sniper python main.py bot
```

Для публикации в канал замените последнюю команду контейнера на `publish`.
