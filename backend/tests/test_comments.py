from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient


def _reg(client: TestClient, email: str = "c@x.com", username: str = "cuser") -> tuple[str, dict]:
    res = client.post("/api/v1/auth/register", json={"email": email, "username": username, "password": "password123"})
    data = res.json()["data"]
    return data["access_token"], data["user"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_post(client: TestClient, token: str, user_id: int) -> int:
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"):
        res = client.post("/api/v1/videos/confirm", json={"r2_key": f"videos/{user_id}/v.mp4", "duration_sec": 20}, headers=_auth(token))
    return res.json()["data"]["post"]["id"]


def test_list_comments_empty(client: TestClient) -> None:
    token, user = _reg(client)
    post_id = _make_post(client, token, user["id"])
    res = client.get(f"/api/v1/feed/{post_id}/comments")
    assert res.status_code == 200
    assert res.json()["data"]["comments"] == []


def test_list_comments_nonexistent_post(client: TestClient) -> None:
    res = client.get("/api/v1/feed/99999/comments")
    assert res.status_code == 404


def test_create_comment_requires_auth(client: TestClient) -> None:
    token, user = _reg(client, "ca@x.com", "cusera")
    post_id = _make_post(client, token, user["id"])
    res = client.post(f"/api/v1/feed/{post_id}/comments", json={"content": "hi"})
    assert res.status_code in (401, 403)


def test_create_comment_success(client: TestClient) -> None:
    token, user = _reg(client, "cb@x.com", "cuserb")
    post_id = _make_post(client, token, user["id"])
    res = client.post(f"/api/v1/feed/{post_id}/comments", json={"content": "좋은 운동이네요"}, headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]["comment"]
    assert data["content"] == "좋은 운동이네요"
    assert data["username"] == "cuserb"


def test_create_comment_appears_in_list(client: TestClient) -> None:
    token, user = _reg(client, "cc@x.com", "cuserc")
    post_id = _make_post(client, token, user["id"])
    client.post(f"/api/v1/feed/{post_id}/comments", json={"content": "첫 번째 댓글입니다"}, headers=_auth(token))
    res = client.get(f"/api/v1/feed/{post_id}/comments")
    comments = res.json()["data"]["comments"]
    assert len(comments) == 1
    assert comments[0]["content"] == "첫 번째 댓글입니다"


def test_create_comment_too_long(client: TestClient) -> None:
    token, user = _reg(client, "cd@x.com", "cuserd")
    post_id = _make_post(client, token, user["id"])
    res = client.post(
        f"/api/v1/feed/{post_id}/comments",
        json={"content": "a" * 501},
        headers=_auth(token),
    )
    assert res.status_code == 422


def test_create_comment_empty_content(client: TestClient) -> None:
    token, user = _reg(client, "ce@x.com", "cusere")
    post_id = _make_post(client, token, user["id"])
    res = client.post(f"/api/v1/feed/{post_id}/comments", json={"content": "   "}, headers=_auth(token))
    assert res.status_code == 422


def test_create_comment_too_short(client: TestClient) -> None:
    token, user = _reg(client, "cshort@x.com", "cushort")
    post_id = _make_post(client, token, user["id"])
    res = client.post(f"/api/v1/feed/{post_id}/comments", json={"content": "짧"}, headers=_auth(token))
    assert res.status_code == 422


def test_create_comment_minimum_length_passes(client: TestClient) -> None:
    token, user = _reg(client, "cmin@x.com", "cumin")
    post_id = _make_post(client, token, user["id"])
    res = client.post(f"/api/v1/feed/{post_id}/comments", json={"content": "다섯글자댓글"}, headers=_auth(token))
    assert res.status_code == 200


def test_daily_comment_limit(client: TestClient) -> None:
    from unittest.mock import patch as _patch

    token, user = _reg(client, "climit@x.com", "culimit")
    post_id = _make_post(client, token, user["id"])

    with _patch("app.routes.comments._get_daily_comment_count", return_value=10):
        res = client.post(
            f"/api/v1/feed/{post_id}/comments",
            json={"content": "한도 초과 댓글입니다"},
            headers=_auth(token),
        )
    assert res.status_code == 429


def test_delete_comment_by_owner(client: TestClient) -> None:
    token, user = _reg(client, "cf@x.com", "caserf")
    post_id = _make_post(client, token, user["id"])
    create_res = client.post(f"/api/v1/feed/{post_id}/comments", json={"content": "삭제될 댓글입니다"}, headers=_auth(token))
    comment_id = create_res.json()["data"]["comment"]["id"]
    del_res = client.delete(f"/api/v1/feed/{post_id}/comments/{comment_id}", headers=_auth(token))
    assert del_res.status_code == 200
    comments = client.get(f"/api/v1/feed/{post_id}/comments").json()["data"]["comments"]
    assert len(comments) == 0


def test_delete_comment_by_other_user_forbidden(client: TestClient) -> None:
    token_owner, user_owner = _reg(client, "cg@x.com", "cuserg")
    token_other, _ = _reg(client, "ch@x.com", "cuserh")
    post_id = _make_post(client, token_owner, user_owner["id"])
    create_res = client.post(f"/api/v1/feed/{post_id}/comments", json={"content": "내 댓글입니다"}, headers=_auth(token_owner))
    comment_id = create_res.json()["data"]["comment"]["id"]
    del_res = client.delete(f"/api/v1/feed/{post_id}/comments/{comment_id}", headers=_auth(token_other))
    assert del_res.status_code == 403


# ---------- 대댓글 (replies) ----------


def _make_comment(client: TestClient, token: str, post_id: int, content: str, parent_id: int | None = None) -> int:
    payload: dict = {"content": content}
    if parent_id is not None:
        payload["parent_id"] = parent_id
    res = client.post(f"/api/v1/feed/{post_id}/comments", json=payload, headers=_auth(token))
    assert res.status_code == 200, res.text
    return res.json()["data"]["comment"]["id"]


def test_create_reply_success(client: TestClient) -> None:
    token, user = _reg(client, "rp1@x.com", "ruser1")
    post_id = _make_post(client, token, user["id"])
    parent_id = _make_comment(client, token, post_id, "부모 댓글입니다")
    res = client.post(
        f"/api/v1/feed/{post_id}/comments",
        json={"content": "답글입니다", "parent_id": parent_id},
        headers=_auth(token),
    )
    assert res.status_code == 200
    data = res.json()["data"]["comment"]
    assert data["parent_id"] == parent_id
    assert data["content"] == "답글입니다"


def test_reply_nested_under_parent_in_list(client: TestClient) -> None:
    token, user = _reg(client, "rp2@x.com", "ruser2")
    post_id = _make_post(client, token, user["id"])
    parent_id = _make_comment(client, token, post_id, "최상위 댓글입니다")
    _make_comment(client, token, post_id, "첫 번째 답글입니다", parent_id=parent_id)
    _make_comment(client, token, post_id, "두 번째 답글입니다", parent_id=parent_id)

    comments = client.get(f"/api/v1/feed/{post_id}/comments").json()["data"]["comments"]
    # 최상위 댓글만 top-level
    assert len(comments) == 1
    assert comments[0]["id"] == parent_id
    assert comments[0]["parent_id"] is None
    # 답글은 부모의 replies 안에 평면적으로
    assert len(comments[0]["replies"]) == 2
    assert {r["content"] for r in comments[0]["replies"]} == {"첫 번째 답글입니다", "두 번째 답글입니다"}
    assert all(r["parent_id"] == parent_id for r in comments[0]["replies"])


def test_reply_to_reply_is_flattened(client: TestClient) -> None:
    """답글의 답글은 거부하지 않고 최상위 부모로 평면화된다 (1-depth 유지)."""
    token, user = _reg(client, "rp3@x.com", "ruser3")
    post_id = _make_post(client, token, user["id"])
    parent_id = _make_comment(client, token, post_id, "최상위 댓글입니다")
    reply_id = _make_comment(client, token, post_id, "첫 답글입니다", parent_id=parent_id)
    # 답글(reply_id)에 다시 답글을 달아도 parent_id는 최상위(parent_id)로 평면화
    grandchild_id = _make_comment(client, token, post_id, "답글의 답글입니다", parent_id=reply_id)

    comments = client.get(f"/api/v1/feed/{post_id}/comments").json()["data"]["comments"]
    assert len(comments) == 1
    replies = comments[0]["replies"]
    assert len(replies) == 2
    grandchild = next(r for r in replies if r["id"] == grandchild_id)
    assert grandchild["parent_id"] == parent_id  # reply_id가 아니라 최상위로 평면화


def test_reply_to_nonexistent_parent_404(client: TestClient) -> None:
    token, user = _reg(client, "rp4@x.com", "ruser4")
    post_id = _make_post(client, token, user["id"])
    res = client.post(
        f"/api/v1/feed/{post_id}/comments",
        json={"content": "없는 부모 답글", "parent_id": 99999},
        headers=_auth(token),
    )
    assert res.status_code == 404


def test_delete_parent_cascades_replies(client: TestClient) -> None:
    """최상위 댓글을 삭제하면 딸린 답글도 함께 삭제된다."""
    token, user = _reg(client, "rp5@x.com", "ruser5")
    post_id = _make_post(client, token, user["id"])
    parent_id = _make_comment(client, token, post_id, "삭제될 부모 댓글")
    _make_comment(client, token, post_id, "딸린 답글입니다", parent_id=parent_id)

    del_res = client.delete(f"/api/v1/feed/{post_id}/comments/{parent_id}", headers=_auth(token))
    assert del_res.status_code == 200
    comments = client.get(f"/api/v1/feed/{post_id}/comments").json()["data"]["comments"]
    assert len(comments) == 0


def test_delete_reply_keeps_parent(client: TestClient) -> None:
    """답글만 삭제하면 부모 댓글은 유지된다."""
    token, user = _reg(client, "rp6@x.com", "ruser6")
    post_id = _make_post(client, token, user["id"])
    parent_id = _make_comment(client, token, post_id, "유지될 부모 댓글")
    reply_id = _make_comment(client, token, post_id, "삭제될 답글입니다", parent_id=parent_id)

    del_res = client.delete(f"/api/v1/feed/{post_id}/comments/{reply_id}", headers=_auth(token))
    assert del_res.status_code == 200
    comments = client.get(f"/api/v1/feed/{post_id}/comments").json()["data"]["comments"]
    assert len(comments) == 1
    assert comments[0]["id"] == parent_id
    assert comments[0]["replies"] == []
