# План R7.2 — вход администратора через Google

Статус: **утверждён владельцем 28 июля 2026 года**.

## 1. Цель

Убрать зависимость Admin Web от отдельного Firebase-пароля. Администратор входит обычной кнопкой **Continue with Google**, выбирает разрешённый Google-аккаунт и получает доступ к Control Center.

## 2. Подтверждённая причина текущей проблемы

- Admin Web сейчас использует `signInWithEmailAndPassword` и требует отдельный пароль Firebase.
- Google provider в Firebase включён.
- К provider ошибочно привязан OAuth client типа **Identity-Aware Proxy**, а не **Web application**.
- Поэтому прежняя попытка Google Sign-In завершалась `redirect_uri_mismatch`.
- Firebase authorized domains уже содержат production Hosting и текущий staging Preview.
- Backend независимо от способа входа проверяет Firebase ID token и серверный allowlist `ADMIN_EMAILS`.

## 3. Целевой поток

```text
Admin Web
  -> Continue with Google
  -> Firebase GoogleAuthProvider
  -> Web OAuth client
  -> Firebase ID token
  -> API Gateway
  -> Cloud Run API
  -> проверка email_verified + ADMIN_EMAILS
```

Пароль, Google access token и OAuth client secret не сохраняются в браузерном коде, Firestore, Git или runtime configuration.

## 4. Изменения конфигурации

1. В Google Auth Platform создаётся отдельный OAuth client типа **Web application** для Admin Web.
2. Разрешённые JavaScript origins:
   - `https://avo-deal-sniper.web.app`;
   - `https://avo-deal-sniper.firebaseapp.com`;
   - краткоживущий Hosting Preview добавляется только для staging-проверки.
3. Разрешённый redirect URI:
   - `https://avo-deal-sniper.firebaseapp.com/__/auth/handler`.
4. Firebase Google provider переключается с IAP client на новый Web client.
5. OAuth client secret вводится только в защищённом интерфейсе Firebase/Google Cloud и не передаётся в чат или репозиторий.
6. Старый IAP client не удаляется в R7.2: он перестаёт использоваться Firebase и сохраняется до успешного production smoke.

## 5. Изменения Admin Web

- удалить поля email/password и `signInWithEmailAndPassword`;
- добавить одну понятную кнопку **Continue with Google**;
- использовать `GoogleAuthProvider` и `signInWithPopup` для desktop-браузера;
- при блокировке popup показывать явное действие повторного входа через redirect, а не выполнять скрытый redirect;
- показывать выбранный email и кнопку **Sign out** после входа;
- для `auth/account-exists-with-different-credential` показывать контролируемое сообщение о необходимости миграции существующей password-account;
- не загружать административные данные до получения и проверки Firebase ID token.

## 6. Усиление backend-проверки

Административный доступ разрешён только когда одновременно выполняются условия:

- Firebase token валиден для проекта `avo-deal-sniper`;
- token содержит email;
- `email_verified=true`;
- нормализованный email присутствует в `ADMIN_EMAILS`.

Наличие Google-аккаунта само по себе не даёт административной роли. Любой другой Google-аккаунт получает HTTP 403.

## 7. Миграция существующей password-account

До cutover проверяется, что Firebase UID текущего администратора не используется как бизнес-идентификатор. Если Google успешно связывается с существующей записью, UID сохраняется.

Если Firebase возвращает `auth/account-exists-with-different-credential`, выполняется контролируемая миграция:

1. зафиксировать UID, email, дату создания и состояние account без password hash;
2. подтвердить отсутствие ссылок на UID в Firestore;
3. удалить только существующую Firebase password-account администратора непосредственно перед Google smoke;
4. сразу войти тем же разрешённым Google-аккаунтом, чтобы Firebase создал новую account;
5. проверить `/admin/overview` и все десять разделов;
6. при неуспехе остановить выпуск и временно восстановить password-account административной командой, не публикуя пароль.

Удаление существующей account и production cutover выполняются только после отдельного явного разрешения владельца.

## 8. Тесты и выпуск

Локально:

- проверка отсутствия password-полей и `signInWithEmailAndPassword`;
- тест Google-кнопки, logout и состояний popup/error;
- backend-тесты для verified allowlisted email, неверифицированного email и постороннего email;
- Ruff, strict mypy, pytest, JavaScript syntax, dependency audit, Terraform validate и secret scan.

Staging:

- immutable build из точного commit;
- Hosting Preview и staging API с delivery off;
- настоящий Google popup;
- Firebase ID token;
- HTTP 200 для разрешённого администратора и HTTP 403 для неразрешённого аккаунта;
- загрузка всех десяти разделов Admin Web;
- production API, jobs, Gateway и live Hosting остаются неизменными.

Production deploy выполняется только после release evidence, ручного подтверждения staging владельцем и отдельной команды **«Разрешаю production deploy R7.2»**.

## 9. Критерий готовности

Владелец открывает `/admin.html`, нажимает **Continue with Google**, выбирает свой Google-аккаунт и сразу видит рабочий Control Center. Отдельный пароль Firebase больше не нужен и не показывается интерфейсом.
