# Операционный регламент

> **Исполнение этого исторического регламента остановлено.** До утверждения и
> реализации R9 нельзя запускать migration, replay, resume или production cutover по
> старой последовательности. Актуальные gates и запрет partial rollback определены в
> `PLAN_R9_FULL_PROJECT_RECOVERY.md`.

Все команды выполняются с явным `--project=avo-deal-sniper`. Production delivery запрещена до финального cutover.

## 1. Локальный gate

```powershell
.\venv\Scripts\python.exe -m ruff check src tests main.py
.\venv\Scripts\python.exe -m mypy src main.py
.\venv\Scripts\python.exe -m pytest --cov=src --cov-fail-under=45
.\venv\Scripts\python.exe -m pip_audit -r requirements.txt
terraform -chdir=infra/terraform fmt -check
terraform -chdir=infra/terraform validate
docker build -t deal-sniper:rc .
```

## 2. Immutable RC

1. Зафиксировать clean commit и push release branch.
2. Собрать runtime и migration images из одного commit в Artifact Registry.
3. Получить SHA-256 digests и записать commit/digests в release evidence.
4. Не изменять код, зависимости или Docker context после фиксации.

## 3. Staging rehearsal

1. Создать/проверить отдельную named Firestore database.
2. Восстановить STOP export.
3. Развернуть exact runtime digest с `DELIVERY_ENABLED=false` и без Telegram/Meta secret access.
4. Запустить exact migration digest: dry-run, затем apply.
5. Выполнить direct replay 100–300, затем полный catch-up.
6. Сверить counts/checksums, schema ledger, current pointers, verification provenance и отсутствие outbox send.
7. Провести source, search, TMA/Admin, Free/Pro preview и unknown-reconcile smoke tests.

Любая ошибка исправляется новым commit/digest и полным повтором rehearsal.

## 4. Production migration

1. Подтвердить paused schedulers/queues и `DELIVERY_ENABLED=false`.
2. Создать новый защищённый Firestore export.
3. Запустить тот же migration digest: dry-run и apply.
4. Выполнить `python main.py replay --direct --concurrency 10` в maintenance Job; временные ошибки повторить `--retry-failed --max-attempts 3`; после наполнения verified market выполнить второй проход `--recalculate-all --retry-failed`.
5. Сверить migration report, failed/rejected replay и derived-state counts. Delivery остаётся выключенной.

## 5. Cutover

1. Слить RC без изменения содержимого; `main` должен указывать на проверенный commit.
2. Развернуть тот же runtime digest.
3. Проверить `/version`: commit, runtime digest, schema и `delivery_enabled=false`.
4. Возобновить collectors.
5. После health/catch-up возобновить processing.
6. Выдать API доступ к Telegram secret, настроить webhook, включить delivery и delivery queue.
7. Запустить пилот 100–300: ручная проверка detail page, точности цены/рынка, Free/Pro и дублей.
8. Включить расписание content только после успешного пилота.

WhatsApp включается отдельно только после наличия Meta credentials, template approval и opt-in recipients.

## 6. Rollback

- немедленно pause schedulers/queues и установить `DELIVERY_ENABLED=false`;
- убрать webhook/secret access при delivery-инциденте;
- вернуть предыдущий runtime digest;
- данные не удалять: использовать export, migration ledger и rollback reader;
- ambiguous sends оставить `unknown`, не повторять автоматически;
- задокументировать watermark, affected IDs и reconciliation.

## 7. Дополнительный rehearsal R7

Перед выпуском Control Center обязательны отдельные проверки поверх общего staging rehearsal:

1. Развернуть immutable runtime digest и Hosting preview без production delivery.
2. Создать активную runtime-конфигурацию из fallback baseline и проверить одинаковую версию в Admin, bot/TMA preview и content preview.
3. Выполнить Preview без мутации, затем Apply с тестовой ценой Stars в отдельном тестовом Pro-канале. Production Pro-канал для staging не использовать.
4. Подтвердить создание ровно одной subscription link при повторе того же operation ID, корректное маскирование URL и отсутствие токена в API/audit/logs.
5. Проверить rollback как создание новой active revision и убедиться, что старые outbox payload не изменились.
6. Проверить все десять разделов Control Center, CORS/OPTIONS и Firebase allowlist настоящим браузером.
7. Проверить run/pause/resume только для разрешённых scheduler jobs; произвольное имя и произвольное действие должны завершаться отказом.
8. Записать commit, image digest, Hosting preview, тестовую active version и результаты smoke в `docs/RELEASE_EVIDENCE_2026-07-28-R7.md`.

Production deploy R7 запрещён до отдельного явного разрешения владельца после изучения release evidence.
