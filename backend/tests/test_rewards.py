from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.reward import RewardPoint


def _reg(client: TestClient, email: str = "r@x.com", username: str = "ruser") -> tuple[str, dict]:
    res = client.post("/api/v1/auth/register", json={"email": email, "username": username, "password": "password123"})
    data = res.json()["data"]
    return data["access_token"], data["user"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _upload(client: TestClient, token: str, user_id: int, filename: str = "v.mp4") -> None:
    key = f"videos/{user_id}/{filename}"
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"):
        client.post("/api/v1/videos/confirm", json={"r2_key": key, "duration_sec": 20}, headers=_auth(token))


def _age_queued_rewards(db: Session) -> None:
    """Backdate queued rewards past the 24h cutoff so settle_queued_rewards fixes them.

    On Mondays (week < 25h old) we cannot backdate into this week AND past the 24h
    settle cutoff simultaneously, so we settle directly to keep created_at this week.
    """
    from datetime import datetime, timedelta, timezone
    from app.services.reward import get_week_range, UTC, REWARD_STATUS_FIXED

    now = datetime.now(timezone.utc)
    week_start, _ = get_week_range(UTC)
    cutoff_24h = now - timedelta(hours=24)
    backdate_to = max(now - timedelta(hours=25), week_start + timedelta(seconds=1))

    for reward in db.query(RewardPoint).filter(RewardPoint.status == "queued").all():
        if backdate_to <= cutoff_24h:
            reward.created_at = backdate_to
        else:
            # Week started < 25h ago (e.g., early Monday); settle directly
            reward.created_at = week_start + timedelta(seconds=1)
            reward.status = REWARD_STATUS_FIXED
    db.commit()


def test_summary_returns_points(client: TestClient) -> None:
    token, _ = _reg(client)
    res = client.get("/api/v1/rewards/summary", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "current_week_points" in data
    assert "fixed_week_points" in data
    assert "queued_week_points" in data


def test_summary_no_sats_field(client: TestClient) -> None:
    token, _ = _reg(client)
    res = client.get("/api/v1/rewards/summary", headers=_auth(token))
    data = res.json()["data"]
    assert "satoshi_amount" not in data
    assert "claimable" not in data


def test_summary_points_after_upload(client: TestClient) -> None:
    token, user = _reg(client, "pts@x.com", "ptsuser")
    _upload(client, token, user["id"])
    res = client.get("/api/v1/rewards/summary", headers=_auth(token))
    data = res.json()["data"]
    assert data["current_week_points"] == 0
    assert data["fixed_week_points"] == 0
    assert data["queued_week_points"] == 0.5


def test_summary_moves_queued_upload_reward_to_fixed_after_24h(client: TestClient, db: Session) -> None:
    token, user = _reg(client, "settle@x.com", "settleuser")
    _upload(client, token, user["id"], "settle.mp4")
    _age_queued_rewards(db)

    res = client.get("/api/v1/rewards/summary", headers=_auth(token))
    data = res.json()["data"]
    assert data["current_week_points"] == 0.5
    assert data["fixed_week_points"] == 0.5
    assert data["queued_week_points"] == 0


def test_delete_retrieves_queued_upload_reward(client: TestClient) -> None:
    token, user = _reg(client, "revoke@x.com", "revokeuser")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/revoke.mp4"):
        upload_res = client.post(
            "/api/v1/videos/confirm",
            json={"r2_key": f"videos/{user['id']}/revoke.mp4", "duration_sec": 20},
            headers=_auth(token),
        )
    post_id = upload_res.json()["data"]["post"]["id"]

    with patch("app.routes.videos.r2_service.delete_object"):
        delete_res = client.delete(f"/api/v1/videos/posts/{post_id}", headers=_auth(token))
    assert delete_res.status_code == 200

    summary_res = client.get("/api/v1/rewards/summary", headers=_auth(token))
    data = summary_res.json()["data"]
    assert data["current_week_points"] == 0
    assert data["queued_week_points"] == 0



def test_weekly_claim_endpoint_removed(client: TestClient) -> None:
    token, _ = _reg(client, "nc@x.com", "ncuser")
    res = client.post("/api/v1/rewards/claim", json={}, headers=_auth(token))
    assert res.status_code in (404, 405)


def test_daily_upload_count_uses_utc_window(client: TestClient, db: Session) -> None:
    from datetime import datetime, timedelta, timezone

    from app.models.video import Video
    from app.services.reward import get_daily_upload_count

    token, user = _reg(client, "utc-window@x.com", "utcwindow")
    assert token
    start_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    db.add(Video(
        user_id=user["id"],
        r2_key="videos/utc-window/old.mp4",
        cdn_url="https://cdn/old.mp4",
        file_hash="old",
        duration_sec=20,
        created_at=start_utc - timedelta(seconds=1),
    ))
    db.add(Video(
        user_id=user["id"],
        r2_key="videos/utc-window/current.mp4",
        cdn_url="https://cdn/current.mp4",
        file_hash="current",
        duration_sec=20,
        created_at=start_utc + timedelta(seconds=1),
    ))
    db.commit()

    assert get_daily_upload_count(db, user["id"]) == 1


def test_points_for_tags_light_activity() -> None:
    from app.services.reward import POINTS_LIGHT_ACTIVITY, points_for_tags

    assert points_for_tags(["가벼운 활동"]) == POINTS_LIGHT_ACTIVITY
    assert points_for_tags(["가벼운 활동", "산책"]) == POINTS_LIGHT_ACTIVITY


def test_points_for_tags_sweaty_exercise() -> None:
    from app.services.reward import POINTS_SWEATY_EXERCISE, points_for_tags

    assert points_for_tags(["땀 흘리는 운동"]) == POINTS_SWEATY_EXERCISE
    assert points_for_tags(["땀 흘리는 운동", "런닝"]) == POINTS_SWEATY_EXERCISE


def test_points_for_tags_empty_defaults_to_sweaty() -> None:
    from app.services.reward import POINTS_SWEATY_EXERCISE, points_for_tags

    assert points_for_tags([]) == POINTS_SWEATY_EXERCISE


def test_upload_light_activity_earns_025(client: TestClient) -> None:
    token, user = _reg(client, "light@x.com", "lightuser")
    key = f"videos/{user['id']}/light.mp4"
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/light.mp4"):
        client.post(
            "/api/v1/videos/confirm",
            json={"r2_key": key, "duration_sec": 20, "tags": ["가벼운 활동", "산책"]},
            headers=_auth(token),
        )
    res = client.get("/api/v1/rewards/summary", headers=_auth(token))
    assert res.json()["data"]["queued_week_points"] == 0.25


def test_upload_sweaty_exercise_earns_05(client: TestClient) -> None:
    token, user = _reg(client, "sweaty@x.com", "sweatyuser")
    key = f"videos/{user['id']}/sweaty.mp4"
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/sweaty.mp4"):
        client.post(
            "/api/v1/videos/confirm",
            json={"r2_key": key, "duration_sec": 20, "tags": ["땀 흘리는 운동", "런닝"]},
            headers=_auth(token),
        )
    res = client.get("/api/v1/rewards/summary", headers=_auth(token))
    assert res.json()["data"]["queued_week_points"] == 0.5


def test_comment_earns_001_points(client: TestClient) -> None:

    token, user = _reg(client, "commenter@x.com", "commenter")
    key = f"videos/{user['id']}/c.mp4"
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/c.mp4"):
        post_res = client.post(
            "/api/v1/videos/confirm",
            json={"r2_key": key, "duration_sec": 20},
            headers=_auth(token),
        )
    post_id = post_res.json()["data"]["post"]["id"]

    client.post(f"/api/v1/feed/{post_id}/comments", json={"content": "좋은 운동이에요"}, headers=_auth(token))

    res = client.get("/api/v1/rewards/summary", headers=_auth(token))
    # upload (queued 0.5) + comment (fixed 0.01) = 0.01 fixed
    data = res.json()["data"]
    assert data["fixed_week_points"] == 0.01


def test_daily_limit_uses_client_timezone(client: TestClient, db: Session) -> None:
    """클라이언트 타임존 기준 자정에 카운트가 리셋된다."""
    from datetime import timedelta

    from app.models.video import Video
    from app.services.reward import _parse_tz, get_daily_upload_window

    token, user = _reg(client, "tz-limit@x.com", "tzlimit")

    adak_tz = _parse_tz("America/Adak")
    today_start_utc, _ = get_daily_upload_window(adak_tz)

    db.add_all([
        Video(
            user_id=user["id"],
            r2_key=f"videos/tz-limit/{idx}.mp4",
            cdn_url=f"https://cdn/{idx}.mp4",
            file_hash=f"tz-limit-{idx}",
            duration_sec=20,
            created_at=today_start_utc + timedelta(seconds=idx + 1),
        )
        for idx in range(3)
    ])
    db.commit()

    res = client.get(
        "/api/v1/videos/daily-limit",
        headers={**_auth(token), "X-Client-Timezone": "America/Adak"},
    )

    assert res.status_code == 200
    assert res.json()["data"]["count"] == 3


def test_reward_summary_ignores_client_timezone_header(client: TestClient, db: Session) -> None:
    from datetime import timedelta

    from app.services.reward import UTC, get_week_range

    token, user = _reg(client, "tz-reward@x.com", "tzreward")
    week_start_utc, _week_end_utc = get_week_range(UTC)
    db.add(RewardPoint(
        user_id=user["id"],
        points=0.5,
        reason="upload",
        status="fixed",
        created_at=week_start_utc + timedelta(seconds=1),
    ))
    db.commit()

    res = client.get(
        "/api/v1/rewards/summary",
        headers={**_auth(token), "X-Client-Timezone": "America/Adak"},
    )

    assert res.status_code == 200
    assert res.json()["data"]["current_week_points"] == 0.5


def test_hashrate_empty_week(client: TestClient) -> None:
    token, _ = _reg(client, "hash0@x.com", "hashzero")
    res = client.get("/api/v1/users/me/hashrate", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data == {"my_points": 0.0, "total_points": 0.0, "percent": 0.0}


def test_hashrate_share_of_total(client: TestClient) -> None:
    token_a, user_a = _reg(client, "hasha@x.com", "hashusera")
    token_b, user_b = _reg(client, "hashb@x.com", "hashuserb")
    _upload(client, token_a, user_a["id"], "a.mp4")   # 0.5 (queued 포함)
    _upload(client, token_b, user_b["id"], "b.mp4")   # 0.5

    res = client.get("/api/v1/users/me/hashrate", headers=_auth(token_a))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["my_points"] == 0.5
    assert data["total_points"] == 1.0
    assert data["percent"] == 50.0


def test_hashrate_requires_auth(client: TestClient) -> None:
    res = client.get("/api/v1/users/me/hashrate")
    assert res.status_code in (401, 403)


def test_hashrate_week_range_clipped_by_month() -> None:
    from datetime import datetime, timezone as _tz
    from unittest.mock import patch as _patch
    from app.services.reward import get_hashrate_week_range

    # 2026-07-02(목) UTC: ISO 주 시작은 6/29(월)이지만 월 시작 7/1로 잘려야 한다
    fake_now = datetime(2026, 7, 2, 12, 0, tzinfo=_tz.utc)

    class _FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now.astimezone(tz) if tz else fake_now

    with _patch("app.services.reward.datetime", _FakeDatetime):
        start, end = get_hashrate_week_range()
    assert start == datetime(2026, 7, 1, tzinfo=_tz.utc)
    assert end == datetime(2026, 7, 6, tzinfo=_tz.utc)  # 다음 월요일 (7월 내)


def test_hashrate_user_and_admin_views_agree(client: TestClient, db: Session) -> None:
    """돈 정산 무결성: 사용자 프로필 %와 관리자 순위 %는 항상 같아야 한다.

    queued(미확정)·fixed(확정)·revoked(회수) 상태를 섞어 시드하고,
    두 엔드포인트의 분자·분모·percent가 일치하는지 검증한다.
    """
    from app.services.reward import REWARD_STATUS_FIXED, REWARD_STATUS_REVOKED

    token_a, user_a = _reg(client, "agree_a@x.com", "agreea")
    token_b, user_b = _reg(client, "agree_b@x.com", "agreeb")
    _upload(client, token_a, user_a["id"], "a.mp4")  # A: 0.5 queued
    _upload(client, token_b, user_b["id"], "b.mp4")  # B: 0.5 queued

    # B에 fixed 0.5 추가, A에 revoked 9.9 추가(양쪽 다 제외되어야 함)
    db.add(RewardPoint(user_id=user_b["id"], points=0.5, reason="upload", status=REWARD_STATUS_FIXED))
    db.add(RewardPoint(user_id=user_a["id"], points=9.9, reason="upload", status=REWARD_STATUS_REVOKED))
    db.commit()

    admin_res = client.get("/api/v1/admin/hashrate", headers={"X-Admin-Key": "test-admin-key"})
    assert admin_res.status_code == 200
    admin = admin_res.json()["data"]
    admin_by_user = {row["user_id"]: row for row in admin["items"]}

    for token, user in ((token_a, user_a), (token_b, user_b)):
        me = client.get("/api/v1/users/me/hashrate", headers=_auth(token)).json()["data"]
        row = admin_by_user[user["id"]]
        assert row["points"] == me["my_points"], f"user {user['id']}: 분자 불일치"
        assert row["percent"] == me["percent"], f"user {user['id']}: percent 불일치"
        assert admin["total_points"] == me["total_points"], f"user {user['id']}: 분모 불일치"

    # 기대값 자체도 고정: A=0.5(25%), B=1.0(50%+25%), 전체 1.5 — revoked 9.9는 미포함
    assert admin["total_points"] == 1.5
    assert admin_by_user[user_a["id"]]["percent"] == 33.3
    assert admin_by_user[user_b["id"]]["percent"] == 66.7
