"""Проверка Firebase ID token и Telegram Mini App initData."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

from google.auth.transport.requests import Request
from google.oauth2 import id_token


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    email: str | None = None
    admin: bool = False
    telegram_user_id: int | None = None


def verify_firebase_bearer(
    authorization: str | None,
    project_id: str,
    admin_emails: frozenset[str],
) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise PermissionError("Требуется Firebase ID token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token or not project_id:
        raise PermissionError("Firebase authentication не настроена")
    claims = id_token.verify_firebase_token(  # type: ignore[no-untyped-call]
        token, Request(), audience=project_id
    )
    if not claims or not claims.get("sub"):
        raise PermissionError("Некорректный Firebase ID token")
    email = str(claims.get("email", "")).casefold() or None
    admin = bool(claims.get("admin")) or bool(email and email in admin_emails)
    telegram_value = claims.get("telegram_user_id")
    telegram_user_id = int(telegram_value) if telegram_value is not None else None
    return Principal(
        subject=str(claims["sub"]),
        email=email,
        admin=admin,
        telegram_user_id=telegram_user_id,
    )


def verify_telegram_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 3600,
) -> Principal:
    """Проверяет подпись initData по официальному алгоритму Telegram Web Apps."""
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    supplied_hash = values.pop("hash", "")
    if not supplied_hash or not bot_token:
        raise PermissionError("Telegram initData не настроена")
    check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, supplied_hash):
        raise PermissionError("Некорректная подпись Telegram initData")
    try:
        auth_date = int(values.get("auth_date", "0"))
    except ValueError as error:
        raise PermissionError("Некорректная дата Telegram initData") from error
    if auth_date <= 0 or abs(int(time.time()) - auth_date) > max_age_seconds:
        raise PermissionError("Telegram initData истекла")
    try:
        user: dict[str, Any] = json.loads(values.get("user", "{}"))
        user_id = int(user["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise PermissionError("Telegram user отсутствует в initData") from error
    return Principal(subject=f"telegram:{user_id}", telegram_user_id=user_id)
