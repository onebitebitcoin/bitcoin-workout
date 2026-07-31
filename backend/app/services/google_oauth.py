from __future__ import annotations

import logging
import secrets
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

OAUTH_STATE_TTL = 300  # 5분


def generate_oauth_state() -> str:
    """CSRF 방어용 state 토큰 생성 후 Redis에 저장."""
    state = secrets.token_urlsafe(32)
    try:
        from app.services.job_queue import get_redis_client
        r = get_redis_client()
        r.setex(f"oauth_state:{state}", OAUTH_STATE_TTL, "1")
    except Exception:
        logger.debug("OAuth state Redis 저장 실패 — Redis 미사용 환경")
    return state


def verify_oauth_state(state: str | None) -> bool:
    """state 토큰 검증 후 Redis에서 삭제 (단회 사용)."""
    if not state:
        return False
    try:
        from app.services.job_queue import get_redis_client
        r = get_redis_client()
        valid = r.getdel(f"oauth_state:{state}")
        return valid is not None
    except Exception:
        logger.warning("OAuth state Redis 검증 실패 — Google OAuth state 검증 실패 처리")
        return False

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _google_redirect_uri() -> str:
    # The redirect URI must exactly match one of the URIs registered in Google Cloud Console.
    # To configure: APIs & Services → Credentials → OAuth 2.0 Client → Authorized redirect URIs
    # Add: {APP_URL}/api/v1/auth/google/callback
    return f"{settings.app_url}/api/v1/auth/google/callback"


def get_google_auth_url(state: str = "") -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code(code: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": _google_redirect_uri(),
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return resp.json()


async def get_google_user_info(access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()
