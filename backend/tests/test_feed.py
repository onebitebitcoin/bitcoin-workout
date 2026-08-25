from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _make_user(client: TestClient, email: str, username: str) -> tuple[str, dict]:
    res = client.post("/api/v1/auth/register", json={"email": email, "username": username, "password": "password123"})
    data = res.json()["data"]
    return data["access_token"], data["user"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_post(client: TestClient, token: str, user_id: int, tag: str = "홈트") -> dict:
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"):
        res = client.post("/api/v1/videos/confirm", json={
            "r2_key": f"videos/{user_id}/{tag}.mp4",
            "duration_sec": 20,
            "tags": [tag],
        }, headers=_auth(token))
    return res.json()["data"]["post"]


def test_feed_unauthenticated(client: TestClient) -> None:
    token, user = _make_user(client, "a@x.com", "usera")
    _create_post(client, token, user["id"])
    res = client.get("/api/v1/feed")
    assert res.status_code == 200
    assert len(res.json()["data"]["posts"]) == 1


def test_feed_pagination_cursor(client: TestClient) -> None:
    token, user = _make_user(client, "b@x.com", "userb")
    posts = []
    for i in range(3):
        with patch("app.routes.videos.r2_service.get_cdn_url", return_value=f"https://cdn/v{i}.mp4"):
            res = client.post("/api/v1/videos/confirm", json={
                "r2_key": f"videos/{user['id']}/v{i}.mp4", "duration_sec": 15,
            }, headers=_auth(token))
        posts.append(res.json()["data"]["post"])

    # Get first 2
    res = client.get("/api/v1/feed?limit=2")
    data = res.json()["data"]
    assert len(data["posts"]) == 2
    assert data["next_cursor"] is not None

    # Get rest using cursor
    res2 = client.get(f"/api/v1/feed?cursor={data['next_cursor']}&limit=2")
    data2 = res2.json()["data"]
    assert len(data2["posts"]) >= 1


def test_like_toggle(client: TestClient) -> None:
    token1, _ = _make_user(client, "liker@x.com", "liker")
    token2, user2 = _make_user(client, "poster@x.com", "poster")
    post = _create_post(client, token2, user2["id"])
    post_id = post["id"]

    # First like
    res = client.post(f"/api/v1/feed/{post_id}/like", headers=_auth(token1))
    assert res.status_code == 200
    assert res.json()["data"]["liked"] is True
    assert res.json()["data"]["like_count"] == 1

    # Second like = unlike
    res2 = client.post(f"/api/v1/feed/{post_id}/like", headers=_auth(token1))
    assert res2.json()["data"]["liked"] is False
    assert res2.json()["data"]["like_count"] == 0


def test_view_dedup_same_user_same_day(client: TestClient) -> None:
    token_viewer, _ = _make_user(client, "vw@x.com", "vw")
    token_poster, user_poster = _make_user(client, "vp@x.com", "vp")
    post = _create_post(client, token_poster, user_poster["id"])

    # 같은 날 같은 유저가 2번 조회 — dedup으로 view_count는 1만 증가
    client.post(f"/api/v1/feed/{post['id']}/view", headers=_auth(token_viewer))
    res = client.post(f"/api/v1/feed/{post['id']}/view", headers=_auth(token_viewer))
    assert res.status_code == 200

    feed_res = client.get("/api/v1/feed?limit=10")
    posts = feed_res.json()["data"]["posts"]
    found = next((p for p in posts if p["id"] == post["id"]), None)
    assert found is not None
    assert found["view_count"] == 1
