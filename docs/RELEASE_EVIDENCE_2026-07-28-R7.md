# Release evidence R7 — кандидат до staging

Статус: **локальный и GitHub CI gate пройдены; staging не начат**.

## Зафиксированные версии

- ветка: `production/deal-sniper-complete`;
- план R7: `4f4e3b2`;
- реализация R7: `2cb2bd20310743bc5d88706ea25c21d98f16c24e`;
- GitHub Actions: `30336329612` — success;
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
- проверка diff на секреты — совпадения не обнаружены.

## Невыполненные проверки

- Artifact Registry immutable build и digest;
- отдельная staging runtime revision и Hosting preview;
- Firestore staging integration;
- browser/auth/CORS smoke всех десяти разделов;
- тестовая смена Stars и rollback в отдельном тестовом Pro-канале;
- подтверждение единой active revision в bot, TMA, Admin и новом CTA.

## Текущие блокеры

1. Локальная `gcloud`-сессия истекла и требует интерактивного `gcloud auth login`.
2. До мутационного smoke необходимо подтвердить отдельный тестовый Pro-канал. Production Pro-канал использовать для staging запрещено.

Production deploy R7 не разрешён и не выполнялся.
