"""게시물 글(캡션·태그·운동시간) 수정 — PATCH /videos/posts/{id} 테스트."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.post import Post
from app.models.video import Video
from tests.test_videos import _auth, _register


def _seed_post(db: Session, user_id: int, *, tags: list[str]) -> int:
    video = Video(
        user_id=user_id, r2_key=f"videos/{user_id}/v.mp4", cdn_url="https://cdn/v.mp4",
        file_hash="h", duration_sec=15, subtitle_status="skipped",
    )
    db.add(video)
    db.flush()
    post = Post(
        video_id=video.id, user_id=user_id, caption="원본 설명",
        tags=json.dumps(tags, ensure_ascii=False), share_token=f"tok{user_id}{video.id}",
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post.id


def test_update_caption_success(client: TestClient, db: Session) -> None:
    token, uid = _register(client, "edit1@x.com", "edit1")
    post_id = _seed_post(db, uid, tags=["가벼운 활동"])
    res = client.patch(f"/api/v1/videos/posts/{post_id}", json={"caption": "수정된 설명"}, headers=_auth(token))
    assert res.status_code == 200, res.text
    assert res.json()["data"]["post"]["caption"] == "수정된 설명"


def test_update_caption_too_long(client: TestClient, db: Session) -> None:
    token, uid = _register(client, "edit2@x.com", "edit2")
    post_id = _seed_post(db, uid, tags=["가벼운 활동"])
    res = client.patch(f"/api/v1/videos/posts/{post_id}", json={"caption": "x" * 141}, headers=_auth(token))
    assert res.status_code == 400


def test_update_workout_time(client: TestClient, db: Session) -> None:
    token, uid = _register(client, "edit3@x.com", "edit3")
    post_id = _seed_post(db, uid, tags=["가벼운 활동"])
    res = client.patch(f"/api/v1/videos/posts/{post_id}", json={"workout_start": "08:30", "workout_end": "09:00"}, headers=_auth(token))
    assert res.status_code == 200, res.text
    assert res.json()["data"]["post"]["workout_start"] == "08:30"


def test_update_invalid_time_format(client: TestClient, db: Session) -> None:
    token, uid = _register(client, "edit4@x.com", "edit4")
    post_id = _seed_post(db, uid, tags=["가벼운 활동"])
    res = client.patch(f"/api/v1/videos/posts/{post_id}", json={"workout_start": "25:99"}, headers=_auth(token))
    assert res.status_code == 400


def test_update_other_user_forbidden(client: TestClient, db: Session) -> None:
    _, owner_id = _register(client, "owner@x.com", "owner")
    post_id = _seed_post(db, owner_id, tags=["가벼운 활동"])
    other_token, _ = _register(client, "other@x.com", "other")
    res = client.patch(f"/api/v1/videos/posts/{post_id}", json={"caption": "해킹"}, headers=_auth(other_token))
    assert res.status_code == 403


def test_update_not_found(client: TestClient) -> None:
    token, _ = _register(client, "edit5@x.com", "edit5")
    res = client.patch("/api/v1/videos/posts/999999", json={"caption": "x"}, headers=_auth(token))
    assert res.status_code == 404


def test_unauthenticated(client: TestClient, db: Session) -> None:
    _, uid = _register(client, "edit9@x.com", "edit9")
    post_id = _seed_post(db, uid, tags=["가벼운 활동"])
    res = client.patch(f"/api/v1/videos/posts/{post_id}", json={"caption": "x"})
    assert res.status_code in (401, 403)
