# Release evidence R7 — staging-кандидат

Статус: **immutable build, staging runtime, Gateway, Firestore integration и authenticated browser smoke пройдены; выпуск ещё не готов**.

## Зафиксированные версии

- ветка: `production/deal-sniper-complete`;
- план R7: `4f4e3b2`;
- реализация R7: `2cb2bd20310743bc5d88706ea25c21d98f16c24e`;
- CORS RC: `80872e0e70f292189864e829824f07dcf3e6591f`;
- GitHub Actions: `30336329612` — success;
- финальный GitHub Actions: `30342104177` — success;
- Cloud Build: `6d7de8fd-8088-4b87-a74e-26afe9a1e7fd`;
- staging digest: `sha256:c45e544ce9cc128353a9c8f1f96443809aded61f31c06ebde42d0b77ca2f6e2a`;
- staging Cloud Run revision: `deal-sniper-api-staging-00033-v7k`;
- staging Gateway config: `r7-02fcb6f`;
- production baseline остаётся `851ddaf26852aaaa0547df1b60e222d7f74b5d9a` / `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`.

## Пройденные проверки

- Ruff — success;
- strict mypy — success;
- pytest — 90 passed, 2 skipped;
- coverage — 64% при пороге 45%;
- dependency audit — уязвимости не обнаружены;
- JavaScript module syntax — success;
- Terraform format/validate — success;
- GitHub container build — success;
- Trivy — success;
- проверка diff на секреты — совпадения не обнаружены;
- exact digest развёрнут в `deal-sniper-api-staging`; `/version` подтвердил commit, digest и schema `2`;
- staging сохраняет `FIRESTORE_DATABASE=deal-sniper-stage-rc2`, `DELIVERY_ENABLED=false` и `WHATSAPP_ENABLED=false`;
- API Gateway operation `operation-1785224470598-657a6f66a1249-64f99469-32663c27` завершена, Gateway активен на `r7-02fcb6f`;
- Firestore integration подтвердил идемпотентность, архивирование прежней revision и единственный active pointer;
- настоящий headless Chrome прошёл Firebase Auth и browser-enforced CORS для `/admin/overview`, Market Pulse, preview и двух outbox states;
- дополнительные защищённые endpoints Runs, Listings, Decisions, Users, Errors и Settings вернули HTTP 200;
- краткоживущий Firebase test user удалён, staging `ADMIN_EMAILS` восстановлен, временный доступ отсутствует.
- Hosting Preview `https://avo-deal-sniper--r7-02fcb6f-gswik35m.web.app` направлен только на staging Gateway и автоматически истекает 29 июля 2026;
- реальный Preview UI вошёл через Firebase Auth, загрузил Dashboard без ошибок и открыл Dashboard, Sources, Runs, Listings, Decisions, Publications, Users, Revenue, Errors и Settings;
- preview-origin получил CORS preflight HTTP 200; wildcard origins отсутствуют.

## Невыполненные проверки

- тестовая смена Stars и rollback в отдельном тестовом Pro-канале;
- подтверждение единой active revision в bot, TMA, Admin и новом CTA.

## Текущие блокеры

До мутационного smoke нужен отдельный тестовый Pro-канал с тестовым ботом или изолированными staging credentials. Production Pro-канал использовать для staging запрещено.

Production deploy R7 не разрешён и не выполнялся.
