"""Проверки подписи Telegram Mini App и owner identity."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from src.auth import verify_telegram_init_data


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
