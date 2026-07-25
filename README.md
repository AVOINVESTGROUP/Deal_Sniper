# Dubai Deal Sniper

Production-сервис поиска недооценённых автомобилей с фиксированной ценой в ОАЭ. Система собирает объявления, подтверждает цену на detail page, объединяет дубли, строит рынок по актуальным аналогам, рассчитывает расходы и публикует только экономически подходящие сигналы.

Недвижимость, аукционы и автоматическая покупка исключены.

## Пользовательские интерфейсы

- Telegram-бот: персональный поиск, сохранённые запросы, избранное и статусы.
- Free Telegram-канал: сокращённые teaser-сигналы без цены, ссылки и финансовых показателей.
- Pro Telegram-канал: полная проверяемая карточка сделки.
- Telegram Mini App: лента, фильтры, избранное и действия.
- Admin Web: источники, состояние pipeline, delivery outbox и контент.
- WhatsApp Business Cloud API: только индивидуальная opt-in доставка; без credentials отключён.

## Источники

Активные адаптеры: DubiCars, CarSwitch, Cars24 UAE и OpenSooq UAE. Источник можно включить или выключить без удаления истории. Ошибка источника не заменяется mock-данными.

## Как принимается решение

1. Коллектор сохраняет raw snapshot до разбора.
2. Новая версия получает стабильный `listing_id + content_hash`.
3. Цена обязательно повторно подтверждается на странице объявления.
4. Аналоги дедуплицируются и проверяются на свежесть.
5. Детерминированные движки рассчитывают рынок, расходы, прибыль, ROI и риск.
6. В Pro попадают только актуальные `CONTACT`/`INSPECT`, прошедшие пользовательские и финансовые фильтры.

LLM не задаёт цену, расходы, прибыль, ROI или итоговое действие.

## Локальная проверка

Требования: Windows 11, PowerShell, Python 3.11.

```powershell
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
Copy-Item -LiteralPath .env.example -Destination .env
python main.py scan --source dubicars
```

Для long polling задайте локально `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USER_IDS` и `DELIVERY_ENABLED=true`, затем:

```powershell
python main.py bot
```

Production использует webhook, Cloud Run и Secret Manager; локальный компьютер для работы сервиса не нужен.

## Команды бота

- `/start`, `/help`, `/status`, `/sources`;
- `/find Toyota Land Cruiser 2020-2024 under 180000 AED`;
- `/my_searches`, `/stop_search`, `/deals`, `/watchlist`;
- административные `/source_on`, `/source_off`, `/source_scan`.

Язык личного бота выбирается по языку Telegram с fallback на английский. Каналы публикуются на английском.

## Проверка кода

```powershell
python -m ruff check src tests main.py
python -m mypy src main.py
python -m pytest --cov=src --cov-fail-under=45
python -m pip_audit -r requirements.txt
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
docker build -t deal-sniper:local .
```

CI дополнительно сканирует образ Trivy. Runtime-контейнер работает непривилегированным пользователем на Python 3.11.

## Google Cloud

Целевой проект: `avo-deal-sniper`. Все команды должны явно содержать `--project=avo-deal-sniper`, чтобы исключить развёртывание в другой активный gcloud project.

Инфраструктура описана в `infra/terraform`. Перед первым `terraform apply` существующие ресурсы необходимо импортировать в state; слепой apply поверх вручную созданного production запрещён.

Порядок immutable release, staging rehearsal, migration, cutover и rollback приведён в [операционном регламенте](docs/OPERATIONS.md). Архитектура — в [CLOUD_ARCHITECTURE.md](docs/CLOUD_ARCHITECTURE.md), контракт продукта — в [SPEC.md](SPEC.md).

## Конфигурация и секреты

Несекретные параметры перечислены в `.env.example`. Telegram/Meta credentials хранятся в Secret Manager. `.env`, токены и персональные данные не коммитятся. `DELIVERY_ENABLED=false` является обязательным fail-closed режимом для сборки, rehearsal и миграции.
