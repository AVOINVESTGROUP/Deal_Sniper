"""Проверки подписи Telegram Mini App и owner identity."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from google.auth import exceptions

from src.auth import verify_firebase_bearer, verify_telegram_init_data


def signed_init_data(bot_token: str, user_id: int) -> str:
    values = {
        "auth_date": str(int(time.time())),
        "query_id": "query-1",
        "user": json.dumps({"id": user_id}, separators=(",", ":")),
    }
    check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_valid_telegram_init_data_returns_owner() -> None:
    principal = verify_telegram_init_data(signed_init_data("test-token", 42), "test-token")
    assert principal.telegram_user_id == 42
    assert principal.subject == "telegram:42"


def test_tampered_telegram_init_data_is_rejected() -> None:
    with pytest.raises(PermissionError):
        verify_telegram_init_data(
            signed_init_data("test-token", 42).replace("query-1", "query-2"),
            "test-token",
        )


def test_malformed_firebase_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def reject_token(*args: object, **kwargs: object) -> None:
        raise exceptions.MalformedError("invalid token")

    monkeypatch.setattr("src.auth.id_token.verify_firebase_token", reject_token)
    with pytest.raises(PermissionError, match="Некорректный Firebase ID token"):
        verify_firebase_bearer("Bearer invalid", "project", frozenset())


def test_verified_allowlisted_firebase_email_is_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.auth.id_token.verify_firebase_token",
        lambda *args, **kwargs: {
            "sub": "google-user",
            "email": "OWNER@EXAMPLE.COM",
            "email_verified": True,
        },
    )
    principal = verify_firebase_bearer(
        "Bearer valid",
        "project",
        frozenset({"owner@example.com"}),
    )
    assert principal.email == "owner@example.com"
    assert principal.email_verified is True
    assert principal.admin is True


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "unverified", "email": "owner@example.com", "email_verified": False},
        {"sub": "outsider", "email": "other@example.com", "email_verified": True},
        {"sub": "legacy-claim", "admin": True},
    ],
)
def test_unverified_or_non_allowlisted_firebase_identity_is_not_admin(
    monkeypatch: pytest.MonkeyPatch,
    claims: dict[str, object],
) -> None:
    monkeypatch.setattr(
        "src.auth.id_token.verify_firebase_token",
        lambda *args, **kwargs: claims,
    )
    principal = verify_firebase_bearer(
        "Bearer valid",
        "project",
        frozenset({"owner@example.com"}),
    )
    assert principal.admin is False
