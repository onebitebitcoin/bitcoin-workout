from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

TZ = "Asia/Seoul"


def _reg(client: TestClient, email: str = "h@x.com", username: str = "huser") -> tuple[str, dict]:
    res = client.post("/api/v1/auth/register", json={"email": email, "username": username, "password": "password123"})
    data = res.json()["data"]
    return data["access_token"], data["user"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload(client: TestClient, token: str, user_id: int, filename: str = "v.mp4") -> None:
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"):
        client.post("/api/v1/videos/confirm", json={"r2_key": f"videos/{user_id}/{filename}", "duration_sec": 20}, headers=_auth(token))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def test_history_requires_auth(client: TestClient) -> None:
    res = client.get("/api/v1/history")
    assert res.status_code in (401, 403)


def test_history_empty_month(client: TestClient) -> None:
    token, _ = _reg(client)
    now = _now_utc()
    res = client.get(f"/api/v1/history?year={now.year}&month={now.month}", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["streak"] == 0
    assert data["total_days"] == 0
    assert data["workout_days"] == {}


def test_history_after_upload(client: TestClient) -> None:
    from zoneinfo import ZoneInfo
    token, user = _reg(client, "hu2@x.com", "huser2")
    _upload(client, token, user["id"])
    now_kst = _now_utc().astimezone(ZoneInfo(TZ))
    res = client.get(f"/api/v1/history?year={now_kst.year}&month={now_kst.month}", headers=_auth(token))
    data = res.json()["data"]
    assert data["total_days"] == 1
    assert data["streak"] == 1
    today_str = now_kst.strftime("%Y-%m-%d")
    assert today_str in data["workout_days"]
    day_posts = data["workout_days"][today_str]
    assert len(day_posts) == 1
    assert "cdn_url" in day_posts[0]
    assert "like_count" in day_posts[0]


def test_history_multiple_uploads_same_day(client: TestClient) -> None:
    from zoneinfo import ZoneInfo
    token, user = _reg(client, "hu3@x.com", "huser3")
    _upload(client, token, user["id"], "v1.mp4")
    _upload(client, token, user["id"], "v2.mp4")
    now_kst = _now_utc().astimezone(ZoneInfo(TZ))
    res = client.get(f"/api/v1/history?year={now_kst.year}&month={now_kst.month}", headers=_auth(token))
    data = res.json()["data"]
    assert data["total_days"] == 1
    today_str = now_kst.strftime("%Y-%m-%d")
    assert len(data["workout_days"][today_str]) == 2


def test_history_default_current_month(client: TestClient) -> None:
    token, _ = _reg(client, "hu4@x.com", "huser4")
    res = client.get("/api/v1/history", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    from zoneinfo import ZoneInfo
    now_kst = _now_utc().astimezone(ZoneInfo(TZ))
    assert data["year"] == now_kst.year
    assert data["month"] == now_kst.month


def test_history_only_shows_own_posts(client: TestClient) -> None:
    token_a, _ = _reg(client, "ha@x.com", "husera")
    token_b, user_b = _reg(client, "hb@x.com", "huserb")
    _upload(client, token_b, user_b["id"], "other.mp4")
    now = _now_utc()
    res = client.get(f"/api/v1/history?year={now.year}&month={now.month}", headers=_auth(token_a))
    data = res.json()["data"]
    assert data["total_days"] == 0
