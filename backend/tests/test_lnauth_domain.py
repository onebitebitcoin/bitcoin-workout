"""LNURL-auth 도메인 고정 회귀 테스트.

LUD-04 는 linkingKey 를 `HMAC-SHA256(hashingKey, FQDN)` 으로 파생한다. LNURL 이
담는 도메인이 바뀌면 같은 지갑이 다른 공개키를 만들어 기존 계정에 들어오지
못한다. 서비스 도메인(app_base_url)을 바꿔도 LNURL 도메인은 따라 움직이면 안
된다는 것이 여기서 지키는 불변식이다.
"""
from __future__ import annotations

from urllib.parse import urlparse

import bech32
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.services.lnauth import encode_lnurl


def decode_lnurl(lnurl: str) -> str:
    _hrp, data = bech32.bech32_decode(lnurl.lower())
    assert data is not None
    return bytes(bech32.convertbits(data, 5, 8, False)).decode()


@pytest.fixture
def pinned_lnurl_origin(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "app_base_url", "https://new.example.com")
    monkeypatch.setattr(settings, "lnurl_base_url", "https://old.example.com")
    return "old.example.com"


def test_lnurl_origin_falls_back_to_app_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """LNURL_BASE_URL 미설정 환경(로컬·신규 배포)에서는 기존 동작을 그대로 유지한다."""
    monkeypatch.setattr(settings, "app_base_url", "http://localhost:8000")
    monkeypatch.setattr(settings, "lnurl_base_url", "")
    assert settings.lnurl_origin == "http://localhost:8000"


def test_lnurl_origin_prefers_pinned_value(pinned_lnurl_origin: str) -> None:
    assert settings.lnurl_origin == "https://old.example.com"


def test_encode_lnurl_uses_pinned_domain(pinned_lnurl_origin: str) -> None:
    """서비스 도메인이 바뀌어도 QR 이 담는 도메인은 고정값이어야 한다."""
    url = decode_lnurl(encode_lnurl("ab" * 32))
    assert urlparse(url).hostname == pinned_lnurl_origin
    assert url.startswith("https://old.example.com/api/v1/auth/lnauth?tag=login&k1=")


def test_challenge_endpoint_serves_pinned_domain(
    client: TestClient, pinned_lnurl_origin: str
) -> None:
    res = client.get("/api/v1/auth/lnauth/challenge")
    assert res.status_code == 200
    url = decode_lnurl(res.json()["data"]["lnurl"])
    assert urlparse(url).hostname == pinned_lnurl_origin


def test_callback_metadata_points_at_pinned_domain(
    client: TestClient, pinned_lnurl_origin: str
) -> None:
    """먼저 탐색 요청을 보내는 지갑에게도 같은 도메인을 돌려줘야 한다."""
    k1 = client.get("/api/v1/auth/lnauth/challenge").json()["data"]["k1"]
    body = client.get(f"/api/v1/auth/lnauth?tag=login&k1={k1}").json()
    assert urlparse(body["callback"]).hostname == pinned_lnurl_origin


def test_google_redirect_is_not_pinned(pinned_lnurl_origin: str) -> None:
    """구글 OAuth 는 서비스 도메인을 계속 따라가야 한다 — 고정 대상이 아니다."""
    assert settings.app_base_url == "https://new.example.com"


# ── 로그인 화면의 도메인 선택 (신규 사용자용) ──────────────────────────────

def test_challenge_with_current_domain_uses_service_domain(
    client: TestClient, pinned_lnurl_origin: str
) -> None:
    """처음 오는 사용자는 현재 서비스 도메인으로 신원을 만든다."""
    res = client.get("/api/v1/auth/lnauth/challenge?domain=current")
    url = decode_lnurl(res.json()["data"]["lnurl"])
    assert urlparse(url).hostname == "new.example.com"


def test_challenge_with_unknown_domain_falls_back_to_pinned(
    client: TestClient, pinned_lnurl_origin: str
) -> None:
    """모르는 값이 오면 기존 사용자 쪽으로 떨어뜨린다 — 빈 계정이 생기는 쪽이 더 나쁘다."""
    res = client.get("/api/v1/auth/lnauth/challenge?domain=거짓말")
    url = decode_lnurl(res.json()["data"]["lnurl"])
    assert urlparse(url).hostname == pinned_lnurl_origin


def test_challenge_without_domain_param_is_legacy(
    client: TestClient, pinned_lnurl_origin: str
) -> None:
    """파라미터를 모르는 호출자(설치된 모바일 앱)는 기존 동작을 유지해야 한다."""
    res = client.get("/api/v1/auth/lnauth/challenge")
    url = decode_lnurl(res.json()["data"]["lnurl"])
    assert urlparse(url).hostname == pinned_lnurl_origin
