# Операционный регламент

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
4. Выполнить `python main.py replay --direct --concurrency 10` в maintenance Job.
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
