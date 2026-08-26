from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


def _reg(client: TestClient, email: str = "a@x.com", username: str = "au") -> tuple[str, dict]:
    res = client.post("/api/v1/auth/register", json={"email": email, "username": username, "password": "password123"})
    data = res.json()["data"]
    return data["access_token"], data["user"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_admin_by_email(db: Session, email: str) -> None:
    from app.models.user import User
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.is_admin = True
        db.commit()


def _reg_admin(client: TestClient, db: Session, email: str = "admin@x.com", username: str = "admin") -> str:
    token, _ = _reg(client, email=email, username=username)
    _make_admin_by_email(db, email)
    return token


def _get_user_id(client: TestClient, token: str) -> int:
    res = client.get("/api/v1/auth/me", headers=_auth(token))
    return res.json()["data"]["id"]


def test_admin_videos_list(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    user_token, user = _reg(client, email="user@x.com", username="user1")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"):
        client.post("/api/v1/videos/confirm", json={"r2_key": f"videos/{user['id']}/v.mp4", "duration_sec": 20}, headers=_auth(user_token))
    res = client.get("/api/v1/admin/videos", headers=_auth(admin_token))
    assert res.status_code == 200
    assert len(res.json()["data"]["videos"]) == 1


def test_admin_reject_video(client: TestClient, db: Session) -> None:
    admin_token = _reg_admin(client, db)
    user_token, user = _reg(client, email="user@x.com", username="user1")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"):
        client.post("/api/v1/videos/confirm", json={"r2_key": f"videos/{user['id']}/v.mp4", "duration_sec": 20}, headers=_auth(user_token))
    videos = client.get("/api/v1/admin/videos", headers=_auth(admin_token)).json()["data"]["videos"]
    vid_id = videos[0]["id"]

    res = client.patch(f"/api/v1/admin/videos/{vid_id}/reject", headers=_auth(admin_token))
    assert res.status_code == 200
    assert res.json()["data"]["video"]["status"] == "rejected"


def test_admin_app_links_public_empty_then_update(client: TestClient) -> None:
    public_res = client.get("/api/v1/admin/app-links")
    assert public_res.status_code == 200
    assert public_res.json()["data"]["android_url"] is None

    update_res = client.put(
        "/api/v1/admin/app-links",
        json={"android_url": "https://example.com/app.apk", "ios_url": None},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["data"]["android_url"] == "https://example.com/app.apk"

    public_res = client.get("/api/v1/admin/app-links")
    assert public_res.json()["data"]["android_url"] == "https://example.com/app.apk"


@patch("app.routes.admin.r2_service.get_cdn_url", return_value="https://cdn/apps/android/app.apk")
@patch("app.routes.admin.r2_service.generate_apk_presigned_url", return_value=("https://r2/upload", "apps/android/app.apk"))
def test_admin_app_upload_url_and_confirm(mock_upload_url, mock_cdn, client: TestClient) -> None:
    upload_res = client.post(
        "/api/v1/admin/app-links/upload-url",
        json={"platform": "android", "filename": "app.apk", "content_type": "application/vnd.android.package-archive"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert upload_res.status_code == 200
    assert upload_res.json()["data"]["cdn_url"] == "https://cdn/apps/android/app.apk"

    confirm_res = client.post(
        "/api/v1/admin/app-links/confirm-upload",
        json={"platform": "android", "cdn_url": "https://cdn/apps/android/app.apk", "filename": "app.apk"},
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["data"]["android_filename"] == "app.apk"


def test_admin_users_shows_referral_tracking(client: TestClient, db: Session) -> None:
    """admin 유저 목록에서 누가 누구를 초대했는지(referred_by_username)와
    각 유저가 데려온 가입자 수(referred_count)를 확인할 수 있다."""
    admin_token = _reg_admin(client, db)

    # 초대자 가입 → referral_code 확보
    inviter_token, inviter = _reg(client, email="inv@x.com", username="inviter")
    code = client.get("/api/v1/users/me/referral", headers=_auth(inviter_token)).json()["data"]["referral_code"]

    # 피초대자 2명이 초대 코드로 가입
    client.post("/api/v1/auth/register", json={"email": "in1@x.com", "username": "invitee1", "password": "password123", "referral_code": code})
    client.post("/api/v1/auth/register", json={"email": "in2@x.com", "username": "invitee2", "password": "password123", "referral_code": code})

    res = client.get("/api/v1/admin/users", headers=_auth(admin_token), params={"limit": 100})
    assert res.status_code == 200
    users = {u["username"]: u for u in res.json()["data"]["users"]}

    # 초대자: 2명 데려옴
    assert users["inviter"]["referred_count"] == 2
    # 피초대자: inviter가 초대자로 표시됨
    assert users["invitee1"]["referred_by_username"] == "inviter"
    assert users["invitee2"]["referred_by_username"] == "inviter"
    # 일반 가입자: 초대자 없음
    assert users["invitee1"]["referred_count"] == 0


def test_admin_delete_user_success(client: TestClient, db: Session) -> None:
    """reward_points 테이블이 없는 현재 스키마에서 유저 삭제가 정상 동작해야 한다."""
    admin_token = _reg_admin(client, db)
    _, user = _reg(client, email="deleteme@x.com", username="deleteme")

    res = client.delete(f"/api/v1/admin/users/{user['id']}", headers=_auth(admin_token))
    assert res.status_code == 200, res.text
    assert res.json()["data"]["user_id"] == user["id"]

    detail_res = client.get(f"/api/v1/admin/users/{user['id']}", headers=_auth(admin_token))
    assert detail_res.status_code == 404


def test_admin_delete_user_with_legacy_reward_points_table(client: TestClient, db: Session) -> None:
    """포인트(땀방울) 체계 제거로 RewardPoint 모델은 삭제됐지만, DROP 마이그레이션이
    배포 창 문제로 지연되는 동안에는 운영 DB에 reward_points 테이블이 그대로 남아 있을 수
    있다. 그 테이블의 FK(reward_points_user_id_fkey)에는 ondelete가 없어, 참조하는 행이
    남아 있으면 유저 삭제가 FK 위반으로 500과 함께 전체 롤백된다 — 이 테스트는 그 상태를
    수동으로 재현해 삭제가 성공하고 orphan 행까지 정리되는지 확인한다."""
    admin_token = _reg_admin(client, db)
    _, user = _reg(client, email="legacy@x.com", username="legacyuser")
    user_id = user["id"]

    # 운영에 남아있을 수 있는 legacy reward_points 테이블 재현 (모델은 이미 삭제됨 → raw SQL).
    # Base.metadata에 없는 테이블이라 setup_db 픽스처의 drop_all/create_all이 건드리지 못하고,
    # 이 테스트가 켜는 PRAGMA foreign_keys도 같은 커넥션(StaticPool)을 쓰는 이후 테스트에
    # 그대로 새어나간다 — 둘 다 finally에서 명시적으로 되돌려 다른 테스트를 오염시키지 않는다.
    db.execute(
        text(
            "CREATE TABLE reward_points ("
            "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, points INTEGER NOT NULL, "
            "reason VARCHAR NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "FOREIGN KEY(user_id) REFERENCES users(id))"
        )
    )
    db.commit()
    try:
        # SQLite는 기본적으로 FK를 강제하지 않는다 — 실제 프로덕션(PostgreSQL)의
        # ForeignKeyViolation을 재현하려면 이 커넥션에서 명시적으로 켜야 한다.
        db.execute(text("PRAGMA foreign_keys=ON"))
        db.execute(
            text("INSERT INTO reward_points (user_id, points, reason) VALUES (:uid, 10, 'legacy')"),
            {"uid": user_id},
        )
        db.commit()

        res = client.delete(f"/api/v1/admin/users/{user_id}", headers=_auth(admin_token))
        assert res.status_code == 200, res.text

        remaining = db.execute(
            text("SELECT COUNT(*) FROM reward_points WHERE user_id = :uid"), {"uid": user_id}
        ).scalar()
        assert remaining == 0
    finally:
        db.rollback()
        db.execute(text("PRAGMA foreign_keys=OFF"))
        db.execute(text("DROP TABLE IF EXISTS reward_points"))
        db.commit()


