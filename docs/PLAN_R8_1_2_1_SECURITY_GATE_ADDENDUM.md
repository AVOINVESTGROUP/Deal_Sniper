# Дополнение к плану R8.1.2.1 — закрытие контейнерного security gate

Статус: **утверждён владельцем 30 июля 2026 года; реализован локально, production не изменён**.

## Диагноз

Коммит `6596ae85730ee948b1036799ee8e91378201e43a` прошёл Python 3.11 quality и Terraform gate,
но оба container job завершились ошибкой Trivy. 30 июля 2026 года повторная независимая проверка
официального образа `python:3.11.15-slim-bookworm` выявила два исправляемых HIGH CVE во встроенных
сборочных пакетах `setuptools`:

- `CVE-2026-23949`: `jaraco.context 5.3.0`, исправлено в `6.1.0`;
- `CVE-2026-24049`: `wheel 0.45.1`, исправлено в `0.46.2`.

Системных HIGH/CRITICAL уязвимостей Debian 12.15 не обнаружено. Текущий CI сохраняет результат только
в локальный SARIF-файл job и не публикует его, поэтому журнал GitHub Actions показывает лишь exit code 1,
но не конкретный пакет итогового application image.

## Границы изменения

1. Перевести Dockerfile на двухэтапную сборку: зависимости устанавливаются в builder, runtime получает
   только необходимые Python-пакеты и код приложения без `pip`, `setuptools`, `wheel` и их vendored metadata.
2. Сохранить блокирующий Trivy gate с прежними условиями: `HIGH,CRITICAL`, `ignore-unfixed=true`, exit code 1.
3. Добавить читаемый table/JSON-вывод при отказе и отдельную публикацию SARIF как CI artifact. Скрывать,
   игнорировать или понижать найденные CVE запрещено.
4. Не менять бизнес-логику, данные, Telegram, Firestore, Cloud Run или production.

## Проверки

- повторный полный local gate R8.1.2.1;
- GitHub Actions: quality, Terraform и container/Trivy должны быть зелёными на одном commit;
- в итоговом образе отсутствуют пути `site-packages/setuptools`, `site-packages/wheel` и их vendored metadata;
- Trivy подтверждает ноль исправляемых HIGH/CRITICAL;
- smoke импорта `src.web:app` выполняется из итогового runtime image.

## Релизный порядок

1. После утверждения дополнения изменить только Dockerfile и CI-наблюдаемость.
2. Пройти локальные проверки, обновить evidence и отправить отдельный commit в текущий Draft PR.
3. Получить зелёные GitHub Actions.
4. Только затем вернуться к immutable build и staging rehearsal исходного плана R8.1.2.1.
5. Production deploy по-прежнему требует отдельного разрешения владельца после staging evidence.

## Критерий готовности

Дополнение завершено только при зелёном блокирующем container/Trivy gate без исключений и без сборочных
инструментов в runtime image. До этого immutable release candidate не существует.

## Результат локальной реализации

- Dockerfile переведён на отдельные `builder` и `runtime` stages;
- runtime запускает Uvicorn через `python -m uvicorn` и не содержит импортируемых `pip`, `setuptools` или `wheel`;
- импорт `src.web:app` из собранного контейнера успешен;
- локальный Trivy 0.70.0 подтвердил ноль исправляемых HIGH/CRITICAL для Debian 12.15 и Python-пакетов;
- CI сохраняет блокирующий table scan, а отдельный SARIF создаётся даже при отказе и хранится как artifact 14 дней;
- полный локальный gate: Ruff, strict mypy, 136 passed / 2 skipped, покрытие 61,5%, dependency audit без известных уязвимостей, Terraform fmt/init/validate и JavaScript syntax успешны.

## Итог CI, immutable build и staging

- implementation commit: `6dd9af358772f9c37ed006632c0202b19d91fd5a`;
- GitHub Actions push `30542429343` и PR `30542431711`: quality, container/Trivy и Terraform успешны;
- оба CI-запуска сохранили отдельный `trivy-results` SARIF artifact;
- Cloud Build `623817ea-787f-45ec-af4d-9765ed44dbcd` собрал точный digest
  `sha256:b6a2e5cb9ae7de2c14e2e26bc141c077292d78e16c1e23ffee1f1f6573de75f4` из `git archive`
  указанного commit;
- импорт `src.web:app`, отсутствие импортируемых build tools и удалённый registry scan этого digest успешны;
- staging API revision `deal-sniper-api-staging-00048-bxv` вернула `/health=ok`, а `/version` — точные
  commit, digest и schema 2;
- staging publisher execution `deal-sniper-publisher-staging-qx9nb` поставил ровно две задачи:
  сначала `pro-news/v2`, затем `free-news/v1`; у них совпали evidence ID, URL, fingerprint и image SHA;
- очередь `telegram-delivery-staging` всё время оставалась `PAUSED`, обе задачи имели `dispatchCount=0`,
  после проверки они удалены;
- delivery-off повтор `deal-sniper-publisher-staging-kf8lh` не создал повторов, очередь пуста;
- fail-closed preflight отдельно отклонил запуск без явных `PUBLISHER_JOB_NAME=...-staging` и allowlist
  production recipients; защита не ослаблялась.

Security Gate и staging rehearsal завершены. Production остаётся на R8.1.1 и требует отдельного
разрешения владельца для deploy R8.1.2.1.
