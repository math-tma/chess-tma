"""
Validates Telegram WebApp `initData` so the API knows a request genuinely
came from Telegram's client for a specific user, and hasn't been tampered
with. See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from urllib.parse import parse_qsl

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MAX_AUTH_AGE_SECONDS = 24 * 60 * 60  # reject initData older than 24h


class InvalidInitData(Exception):
    pass


def validate_init_data(init_data: str) -> dict:
    """
    Returns the parsed initData fields (including 'user' as a JSON string)
    if valid. Raises InvalidInitData otherwise.
    """
    if not BOT_TOKEN:
        raise InvalidInitData("BOT_TOKEN not configured on the server")

    parsed = dict(parse_qsl(init_data, strict_parsing=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("missing hash")

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise InvalidInitData("hash mismatch — request did not come from Telegram")

    auth_date = int(parsed.get("auth_date", 0))
    if time.time() - auth_date > MAX_AUTH_AGE_SECONDS:
        raise InvalidInitData("initData expired")

    return parsed


def is_admin(user_id: int) -> bool:
    admin_ids = {
        int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
    }
    return user_id in admin_ids
