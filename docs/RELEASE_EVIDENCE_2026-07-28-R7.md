# Release evidence R7 — staging-кандидат

Статус: **immutable build, staging runtime, Gateway, Firestore integration и authenticated browser smoke пройдены; выпуск ещё не готов**.

## Зафиксированные версии

- ветка: `production/deal-sniper-complete`;
- план R7: `4f4e3b2`;
- реализация R7: `2cb2bd20310743bc5d88706ea25c21d98f16c24e`;
- evidence head: `02fcb6f919c22d5f6504dd46667d2439ca8e9d55`;
- GitHub Actions: `30336329612` — success;
- финальный GitHub Actions: `30336520291` — success;
- Cloud Build: `1a47a7e3-cf4c-4613-ac3f-543a3ee3c0b6`;
- staging digest: `sha256:ab0b8880041985c47bf2a7eb69b638ed6d2370a21e3e5044b42ebfe4e2ffe94a`;
- staging Cloud Run revision: `deal-sniper-api-staging-00026-cfj`;
- staging Gateway config: `r7-02fcb6f`;
- production baseline остаётся `851ddaf26852aaaa0547df1b60e222d7f74b5d9a` / `sha256:c2e55afdf949b348ef9307246511edbdfec6f73864ff636a13a76f6846da9112`.

## Пройденные проверки

- Ruff — success;
- strict mypy — success;
- pytest — 89 passed, 2 skipped;
- coverage — 56,15% при пороге 45%;
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

## Невыполненные проверки

- Firebase Hosting preview;
- тестовая смена Stars и rollback в отдельном тестовом Pro-канале;
- подтверждение единой active revision в bot, TMA, Admin и новом CTA.

## Текущие блокеры

1. Firebase CLI использует отдельную истёкшую сессию и требует `firebase login --reauth`; попытка preview завершилась `invalid_rapt`, Hosting не изменён.
2. До мутационного smoke нужен отдельный тестовый Pro-канал с тестовым ботом или изолированными staging credentials. Production Pro-канал использовать для staging запрещено.

Production deploy R7 не разрешён и не выполнялся.
