from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi import HTTPException, Request, Response

from app.config import Settings


ADMIN_SESSION_COOKIE = "songshanhu_admin_session"


def admin_login_enabled(settings: Settings) -> bool:
    return bool(settings.admin_password and settings.admin_session_secret)


def create_admin_token(
    settings: Settings,
    username: str,
    *,
    expires_at: int | None = None,
    last_seen_at: int | None = None,
) -> str:
    now = int(time.time())
    resolved_expires_at = expires_at or (now + settings.admin_session_ttl_hours * 3600)
    resolved_last_seen = last_seen_at or now
    payload = f"{username}:{resolved_expires_at}:{resolved_last_seen}"
    signature = hmac.new(
        settings.admin_session_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    token = f"{payload}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(token).decode("ascii")


def set_admin_cookie(
    response: Response,
    settings: Settings,
    username: str,
    *,
    expires_at: int | None = None,
) -> None:
    now = int(time.time())
    resolved_expires_at = expires_at or (now + settings.admin_session_ttl_hours * 3600)
    max_age = max(resolved_expires_at - now, 0)
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        create_admin_token(
            settings,
            username,
            expires_at=resolved_expires_at,
            last_seen_at=now,
        ),
        httponly=True,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


def clear_admin_cookie(response: Response) -> None:
    response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")


def read_admin_token(settings: Settings, token: str | None) -> dict[str, int | str] | None:
    if not token or not admin_login_enabled(settings):
        return None
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        parts = decoded.split(":")
    except (ValueError, UnicodeDecodeError):
        return None

    now = int(time.time())
    if len(parts) == 3:
        username, expires_at, signature = parts
        payload = f"{username}:{expires_at}"
        expected = hmac.new(
            settings.admin_session_secret.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            expires_at_value = int(expires_at)
        except ValueError:
            return None
        if expires_at_value < now:
            return None
        return {
            "username": username,
            "expires_at": expires_at_value,
            "last_seen_at": now,
        }

    if len(parts) != 4:
        return None

    username, expires_at, last_seen_at, signature = parts
    payload = f"{username}:{expires_at}:{last_seen_at}"
    expected = hmac.new(
        settings.admin_session_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        expires_at_value = int(expires_at)
        last_seen_at_value = int(last_seen_at)
    except ValueError:
        return None
    if expires_at_value < now:
        return None

    idle_limit_seconds = settings.admin_session_idle_minutes * 60
    if idle_limit_seconds > 0 and now - last_seen_at_value > idle_limit_seconds:
        return None

    return {
        "username": username,
        "expires_at": expires_at_value,
        "last_seen_at": last_seen_at_value,
    }


def require_admin_session(settings: Settings, request: Request, response: Response) -> str:
    session = read_admin_token(settings, request.cookies.get(ADMIN_SESSION_COOKIE))
    if not session:
        clear_admin_cookie(response)
        raise HTTPException(status_code=401, detail="admin authentication required")
    set_admin_cookie(response, settings, str(session["username"]), expires_at=int(session["expires_at"]))
    return str(session["username"])
