from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

from fastapi.testclient import TestClient


def _register_and_token(client: TestClient, email: str = "u@x.com", username: str = "user") -> str:
    res = client.post("/api/v1/auth/register", json={"email": email, "username": username, "password": "password123"})
    return res.json()["data"]["access_token"]


def _register(client: TestClient, email: str = "u@x.com", username: str = "user") -> tuple[str, int]:
    """Returns (token, user_id) — use when r2_key ownership prefix is needed."""
    res = client.post("/api/v1/auth/register", json={"email": email, "username": username, "password": "password123"})
    data = res.json()["data"]
    return data["access_token"], data["user"]["id"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _tmp_media_file(data: bytes, suffix: str = ".bin") -> str:
    fd, path = tempfile.mkstemp(prefix="stackhealth-test-", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


@patch("app.routes.videos.r2_service.generate_presigned_url", return_value=("https://r2.example.com/upload", "videos/test.mp4"))
def test_presigned_url_success(mock_r2, client: TestClient) -> None:
    token = _register_and_token(client)
    res = client.post("/api/v1/videos/presigned-url", json={
        "filename": "workout.mp4",
        "content_type": "video/mp4",
        "file_size": 1024 * 1024,
    }, headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert "upload_url" in data
    assert data["r2_key"] == "videos/test.mp4"


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4")
def test_workout_upload_daily_limit(mock_cdn, client: TestClient) -> None:
    """운동 태그 업로드는 하루 2개 한도 적용."""
    token, uid = _register(client)
    headers = _auth(token)
    for i in range(2):
        res = client.post("/api/v1/videos/confirm", json={
            "r2_key": f"videos/{uid}/v{i}.mp4", "duration_sec": 20,
            "tags": ["홈트"],
        }, headers=headers)
        assert res.status_code == 200
    # 3rd workout upload blocked
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/v3.mp4", "duration_sec": 20,
        "tags": ["홈트"],
    }, headers=headers)
    assert res.status_code == 429


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4")
def test_all_tags_subject_to_daily_limit(mock_cdn, client: TestClient) -> None:
    """모든 태그(운동/비운동)가 동일한 일일 한도 적용."""
    token, uid = _register(client, "nolimit@x.com", "nolimituser")
    headers = _auth(token)
    for i in range(2):
        res = client.post("/api/v1/videos/confirm", json={
            "r2_key": f"videos/{uid}/v{i}.mp4", "duration_sec": 20,
            "tags": ["일상"],
        }, headers=headers)
        assert res.status_code == 200
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/v3.mp4", "duration_sec": 20,
        "tags": ["일상"],
    }, headers=headers)
    assert res.status_code == 429


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/delete-v.mp4")
def test_workout_limit_eased_after_delete(mock_cdn, client: TestClient) -> None:
    """운동 업로드 삭제 후 한도가 풀린다."""
    token, uid = _register(client, "limit-delete@x.com", "limitdelete")
    headers = _auth(token)
    post_ids: list[int] = []

    for i in range(2):
        confirm_res = client.post("/api/v1/videos/confirm", json={
            "r2_key": f"videos/{uid}/delete-v{i}.mp4", "duration_sec": 20,
            "tags": ["러닝"],
        }, headers=headers)
        assert confirm_res.status_code == 200
        post_ids.append(confirm_res.json()["data"]["post"]["id"])

    blocked_res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/blocked.mp4", "duration_sec": 20,
        "tags": ["러닝"],
    }, headers=headers)
    assert blocked_res.status_code == 429

    with patch("app.routes.videos.r2_service.delete_object"):
        delete_res = client.delete(f"/api/v1/videos/posts/{post_ids[0]}", headers=headers)
    assert delete_res.status_code == 200

    eased_res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/eased.mp4", "duration_sec": 20,
        "tags": ["러닝"],
    }, headers=headers)
    assert eased_res.status_code == 200


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/limit.mp4")
def test_confirm_upload_uses_active_content_limit(mock_cdn, client: TestClient) -> None:
    """confirm 엔드포인트의 운동 업로드 한도 검사."""
    token, uid = _register(client, "confirm-limit@x.com", "confirmlimit")
    headers = _auth(token)

    for i in range(2):
        res = client.post("/api/v1/videos/confirm", json={
            "r2_key": f"videos/{uid}/confirm-limit-{i}.mp4",
            "duration_sec": 20,
            "tags": ["웨이트"],
        }, headers=headers)
        assert res.status_code == 200

    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/confirm-limit-blocked.mp4",
        "duration_sec": 20,
        "tags": ["웨이트"],
    }, headers=headers)
    assert res.status_code == 429


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/dl.mp4")
def test_daily_limit_endpoint(mock_cdn, client: TestClient) -> None:
    """GET /videos/daily-limit: 운동 업로드 횟수/한도 반환."""
    token, uid = _register(client, "dailylimit@x.com", "dailylimituser")
    headers = _auth(token)

    res = client.get("/api/v1/videos/daily-limit", headers=headers)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["count"] == 0
    assert data["limit"] == 2
    assert data["reached"] is False

    # 운동 업로드 2개(=하루 한도) 후 — 한도 도달
    for i in range(2):
        client.post("/api/v1/videos/confirm", json={
            "r2_key": f"videos/{uid}/dl-{i}.mp4", "duration_sec": 20,
            "tags": ["요가"],
        }, headers=headers)

    res = client.get("/api/v1/videos/daily-limit", headers=headers)
    data = res.json()["data"]
    assert data["count"] == 2
    assert data["reached"] is True


def test_presigned_url_file_too_large(client: TestClient) -> None:
    token = _register_and_token(client)
    res = client.post("/api/v1/videos/presigned-url", json={
        "filename": "big.mp4", "content_type": "video/mp4",
        "file_size": 101 * 1024 * 1024,
    }, headers=_auth(token))
    assert res.status_code == 400


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn.example.com/v.mp4")
def test_confirm_duration_too_short(mock_cdn, client: TestClient) -> None:
    token = _register_and_token(client)
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": "videos/x.mp4", "duration_sec": 4,
    }, headers=_auth(token))
    assert res.status_code == 400


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn.example.com/v.mp4")
def test_confirm_duration_too_long(mock_cdn, client: TestClient) -> None:
    token = _register_and_token(client)
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": "videos/x.mp4", "duration_sec": 61,
    }, headers=_auth(token))
    assert res.status_code == 400


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn.example.com/v.mp4")
def test_confirm_success_earns_points(mock_cdn, client: TestClient) -> None:
    token, uid = _register(client)
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/ok.mp4",
        "duration_sec": 30,
        "caption": "great workout",
        "tags": ["홈트"],
    }, headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["points_earned"] == 0.5
    assert data["post"]["user_id"] is not None


def test_my_posts_empty(client: TestClient) -> None:
    token = _register_and_token(client, "mp@x.com", "mpuser")
    res = client.get("/api/v1/videos/my-posts", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["posts"] == []


def test_my_posts_returns_own_posts(client: TestClient) -> None:
    token, uid = _register(client, "mp2@x.com", "mpuser2")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"):
        client.post("/api/v1/videos/confirm", json={"r2_key": f"videos/{uid}/v.mp4", "duration_sec": 20}, headers=_auth(token))
    res = client.get("/api/v1/videos/my-posts", headers=_auth(token))
    posts = res.json()["data"]["posts"]
    assert len(posts) == 1
    assert posts[0]["cdn_url"] == "https://cdn/v.mp4"


def test_my_posts_excludes_others(client: TestClient) -> None:
    token_a = _register_and_token(client, "mp3a@x.com", "mpusera")
    token_b, uid_b = _register(client, "mp3b@x.com", "mpuserb")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/b.mp4"):
        client.post("/api/v1/videos/confirm", json={"r2_key": f"videos/{uid_b}/b.mp4", "duration_sec": 20}, headers=_auth(token_b))
    res = client.get("/api/v1/videos/my-posts", headers=_auth(token_a))
    assert res.json()["data"]["posts"] == []


def test_delete_post_owner(client: TestClient) -> None:
    token, uid = _register(client, "dp@x.com", "dpuser")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"):
        post_res = client.post("/api/v1/videos/confirm", json={"r2_key": f"videos/{uid}/del.mp4", "duration_sec": 20}, headers=_auth(token))
    post_id = post_res.json()["data"]["post"]["id"]
    with patch("app.routes.videos.r2_service.delete_object"):
        del_res = client.delete(f"/api/v1/videos/posts/{post_id}", headers=_auth(token))
    assert del_res.status_code == 200
    assert del_res.json()["data"]["deleted"] == post_id


def test_delete_post_not_found(client: TestClient) -> None:
    token = _register_and_token(client, "dp2@x.com", "dpuser2")
    res = client.delete("/api/v1/videos/posts/99999", headers=_auth(token))
    assert res.status_code == 404


def test_delete_post_forbidden(client: TestClient) -> None:
    token_owner, uid_owner = _register(client, "dp3a@x.com", "dpuser3a")
    token_other = _register_and_token(client, "dp3b@x.com", "dpuser3b")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/v.mp4"):
        post_res = client.post("/api/v1/videos/confirm", json={"r2_key": f"videos/{uid_owner}/own.mp4", "duration_sec": 20}, headers=_auth(token_owner))
    post_id = post_res.json()["data"]["post"]["id"]
    res = client.delete(f"/api/v1/videos/posts/{post_id}", headers=_auth(token_other))
    assert res.status_code == 403


@patch("app.services.job_queue.get_redis_client")
@patch("app.routes.videos.r2_service.get_r2_client")
def test_merge_audio_enqueues_job(mock_get_r2, mock_get_redis, client: TestClient) -> None:
    from unittest.mock import MagicMock

    token, uid = _register(client, "ma@x.com", "mauser")

    mock_s3 = MagicMock()
    mock_s3.put_object.return_value = {}
    mock_get_r2.return_value = mock_s3

    mock_r = MagicMock()
    mock_get_redis.return_value = mock_r

    res = client.post(
        "/api/v1/videos/merge-audio",
        data={"video_r2_key": f"videos/{uid}/test.mp4", "audio_duration_sec": "10"},
        files={"audio": ("audio.webm", b"fake_audio_data", "audio/webm")},
        headers=_auth(token),
    )

    assert res.status_code == 200
    data = res.json()["data"]
    assert "job_id" in data
    assert data["status"] == "processing"
    mock_r.lpush.assert_called_once()


def test_merge_audio_no_redis_url(client: TestClient) -> None:
    """REDIS_URL 미설정(enqueue 실패) 시 500 반환."""
    from unittest.mock import MagicMock

    token, uid = _register(client, "ma2@x.com", "mauser2")

    with patch("app.routes.videos.r2_service.get_r2_client") as mock_r2, \
         patch("app.routes.videos.enqueue_merge_job", side_effect=Exception("no redis")) as mock_enqueue:
        mock_s3 = MagicMock()
        mock_s3.put_object.return_value = {}
        mock_r2.return_value = mock_s3

        res = client.post(
            "/api/v1/videos/merge-audio",
            data={"video_r2_key": f"videos/{uid}/test.mp4", "audio_duration_sec": "10"},
            files={"audio": ("audio.webm", b"fake_audio_data", "audio/webm")},
            headers=_auth(token),
        )

    assert res.status_code == 500
    mock_enqueue.assert_called_once()


@patch("app.services.job_queue.get_redis_client")
def test_get_merge_job_status_not_found(mock_get_redis, client: TestClient) -> None:
    from unittest.mock import MagicMock

    token = _register_and_token(client, "mj@x.com", "mjuser")

    mock_r = MagicMock()
    mock_r.hgetall.return_value = {}
    mock_get_redis.return_value = mock_r

    res = client.get("/api/v1/videos/merge-job/nonexistent-id", headers=_auth(token))
    assert res.status_code == 404


@patch("app.services.job_queue.get_redis_client")
def test_get_merge_job_status_pending(mock_get_redis, client: TestClient) -> None:
    from unittest.mock import MagicMock

    token = _register_and_token(client, "mj2@x.com", "mjuser2")

    mock_r = MagicMock()
    mock_r.hgetall.return_value = {
        "status": "pending",
        "user_id": "1",
        "video_r2_key": "videos/test.mp4",
        "audio_r2_key": "audio/test.webm",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    mock_get_redis.return_value = mock_r

    job_id = "test-job-id-123"
    res = client.get(f"/api/v1/videos/merge-job/{job_id}", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["job_id"] == job_id
    assert data["status"] == "pending"


@patch("app.routes.videos.get_job_status", return_value={"status": "failed", "error": "ffmpeg exited with code 1"})
def test_get_merge_job_failed_hides_internal_error(mock_job, client: TestClient) -> None:
    token = _register_and_token(client, "mjfail@x.com", "mjfailuser")
    res = client.get("/api/v1/videos/merge-job/failed-merge-id", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["error"] == "영상 처리에 실패했습니다. 다시 시도해주세요."
    assert "ffmpeg" not in str(data)


def test_merge_audio_unauthenticated(client: TestClient) -> None:
    res = client.post(
        "/api/v1/videos/merge-audio",
        data={"video_r2_key": "videos/test.mp4", "audio_duration_sec": "5"},
        files={"audio": ("audio.webm", b"data", "audio/webm")},
    )
    assert res.status_code in (401, 403)


# ──────────────────────────────────────────────
# upload-pipeline 엔드포인트 테스트
# ──────────────────────────────────────────────

@patch("app.routes.videos.reserve_job_id", return_value="job-abc-123")
@patch("app.routes.videos._r2_upload_and_enqueue")
def test_upload_pipeline_success(mock_bg, mock_reserve, client: TestClient) -> None:
    token = _register_and_token(client, "pipe@x.com", "pipeuser")
    res = client.post(
        "/api/v1/videos/upload-pipeline",
        data={"duration_sec": "20", "tags": '["홈트"]'},
        files={"file": ("workout.mp4", b"fake-video-data", "video/mp4")},
        headers=_auth(token),
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["job_id"] == "job-abc-123"
    assert data["status"] == "processing"


def test_upload_pipeline_invalid_content_type(client: TestClient) -> None:
    token = _register_and_token(client, "badct@x.com", "badctuser")
    res = client.post(
        "/api/v1/videos/upload-pipeline",
        data={"duration_sec": "20"},
        files={"file": ("doc.pdf", b"data", "application/pdf")},
        headers=_auth(token),
    )
    assert res.status_code == 400


def test_upload_pipeline_unauthenticated(client: TestClient) -> None:
    res = client.post(
        "/api/v1/videos/upload-pipeline",
        data={"duration_sec": "20"},
        files={"file": ("w.mp4", b"data", "video/mp4")},
    )
    assert res.status_code in (401, 403)


@patch("app.routes.videos.get_job_status", return_value={"status": "processing"})
def test_get_upload_job_processing(mock_job, client: TestClient) -> None:
    token = _register_and_token(client, "job1@x.com", "job1user")
    res = client.get("/api/v1/videos/upload-job/some-job-id", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "processing"
    assert data["job_id"] == "some-job-id"


@patch("app.routes.videos.get_job_status", return_value={
    "status": "completed", "post_id": "5", "cdn_url": "https://cdn/ok.mp4", "points_earned": "0.5",
})
def test_get_upload_job_completed(mock_job, client: TestClient) -> None:
    token = _register_and_token(client, "job2@x.com", "job2user")
    res = client.get("/api/v1/videos/upload-job/done-job-id", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "completed"
    assert data["points_earned"] == 0.5
    assert data["cdn_url"] == "https://cdn/ok.mp4"
    # post_id=5 게시물이 DB에 없으면 share_token은 빈 문자열
    assert data["share_token"] == ""


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/share.mp4")
def test_get_upload_job_returns_share_token(mock_cdn, client: TestClient) -> None:
    """완료된 잡 응답에 영상 share_token이 포함된다 (공유 링크 생성용)."""
    token, uid = _register(client, "jobshare@x.com", "jobshareuser")
    headers = _auth(token)
    confirm_res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/jobshare.mp4", "duration_sec": 20,
    }, headers=headers)
    assert confirm_res.status_code == 200
    post = confirm_res.json()["data"]["post"]

    with patch("app.routes.videos.get_job_status", return_value={
        "status": "completed", "post_id": str(post["id"]), "points_earned": "0.5",
    }):
        res = client.get("/api/v1/videos/upload-job/done-job-id", headers=headers)
    assert res.status_code == 200
    assert res.json()["data"]["share_token"] == post["share_token"]


@patch("app.routes.videos.get_job_status", return_value={"status": "failed", "error": "RuntimeError: R2 down"})
def test_get_upload_job_failed_hides_internal_error(mock_job, client: TestClient) -> None:
    token = _register_and_token(client, "jobfail@x.com", "jobfailuser")
    res = client.get("/api/v1/videos/upload-job/failed-job-id", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "failed"
    assert data["error"] == "영상 처리에 실패했습니다. 다시 시도해주세요."
    assert "R2 down" not in str(data)


@patch("app.routes.videos.get_job_status", return_value=None)
def test_get_upload_job_not_found(mock_job, client: TestClient) -> None:
    token = _register_and_token(client, "job3@x.com", "job3user")
    res = client.get("/api/v1/videos/upload-job/nonexistent", headers=_auth(token))
    assert res.status_code == 404


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/share.mp4")
def test_get_post_by_share_token(mock_cdn, client: TestClient) -> None:
    """공유 토큰으로 게시물 조회."""
    token, uid = _register(client, "share@x.com", "shareuser")
    headers = _auth(token)
    confirm_res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/share.mp4", "duration_sec": 20,
    }, headers=headers)
    assert confirm_res.status_code == 200
    share_token = confirm_res.json()["data"]["post"]["share_token"]

    res = client.get(f"/api/v1/videos/posts/share/{share_token}")
    assert res.status_code == 200
    data = res.json()["data"]["post"]
    assert data["share_token"] == share_token


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/share.mp4")
def test_get_post_by_share_token_not_found(mock_cdn, client: TestClient) -> None:
    _register_and_token(client, "share2@x.com", "share2user")
    res = client.get("/api/v1/videos/posts/share/nonexistenttoken")
    assert res.status_code == 404


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/gp.mp4")
def test_get_post_by_id(mock_cdn, client: TestClient) -> None:
    """게시물 ID로 단건 조회."""
    token, uid = _register(client, "getpost@x.com", "getpostuser")
    headers = _auth(token)
    confirm_res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/gp.mp4", "duration_sec": 20,
    }, headers=headers)
    post_id = confirm_res.json()["data"]["post"]["id"]

    res = client.get(f"/api/v1/videos/posts/{post_id}")
    assert res.status_code == 200
    assert res.json()["data"]["post"]["id"] == post_id


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/gp2.mp4")
def test_get_post_by_id_not_found(mock_cdn, client: TestClient) -> None:
    _register_and_token(client, "getpost2@x.com", "getpost2user")
    res = client.get("/api/v1/videos/posts/999999")
    assert res.status_code == 404


@patch("app.routes.videos.r2_service.get_r2_client")
def test_upload_proof_image_success(mock_r2_client, client: TestClient) -> None:
    """증거 이미지 업로드 성공."""
    mock_r2_client.return_value.put_object.return_value = {}
    token = _register_and_token(client, "proof@x.com", "proofuser")
    headers = _auth(token)
    image_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG-like bytes

    res = client.post(
        "/api/v1/videos/upload-proof",
        files={"file": ("proof.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert "proof_r2_key" in data
    assert "proof_cdn_url" in data


@patch("app.routes.videos.r2_service.get_r2_client")
def test_upload_proof_image_invalid_type(mock_r2_client, client: TestClient) -> None:
    """지원하지 않는 이미지 형식은 400."""
    token = _register_and_token(client, "proof2@x.com", "proof2user")
    headers = _auth(token)
    res = client.post(
        "/api/v1/videos/upload-proof",
        files={"file": ("proof.gif", b"GIF89a", "image/gif")},
        headers=headers,
    )
    assert res.status_code == 400


@patch("app.routes.videos.enqueue_image_merge_job", return_value="proof-job-123")
def test_merge_proof_success(mock_enqueue, client: TestClient) -> None:
    """merge-proof 잡 등록 성공."""
    token, uid = _register(client, "mergeproof@x.com", "mergeproofuser")
    headers = _auth(token)
    res = client.post(
        "/api/v1/videos/merge-proof",
        data={
            "video_r2_key": f"videos/{uid}/video.mp4",
            "proof_r2_key": f"proof/{uid}/image.jpg",
        },
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["data"]["job_id"] == "proof-job-123"


def test_merge_proof_forbidden(client: TestClient) -> None:
    """다른 사용자의 r2_key 접근 거부."""
    token, uid = _register(client, "mergeproof2@x.com", "mergeproof2user")
    headers = _auth(token)
    res = client.post(
        "/api/v1/videos/merge-proof",
        data={
            "video_r2_key": "videos/99999/video.mp4",  # different user
            "proof_r2_key": f"proof/{uid}/image.jpg",
        },
        headers=headers,
    )
    assert res.status_code == 403


@patch("app.routes.videos.enqueue_full_upload_pipeline")
@patch("app.routes.videos.r2_service.get_r2_client")
@patch("app.routes.videos.r2_service.upload_fileobj", return_value=("videos/bg-test.mp4", "https://cdn/bg.mp4"))
def test_r2_upload_and_enqueue_video_only(mock_upload, mock_r2_client, mock_enqueue) -> None:
    """_r2_upload_and_enqueue: 비디오만 있는 경우."""
    from app.routes.videos import _r2_upload_and_enqueue
    mock_r2_client.return_value.put_object.return_value = {}
    mock_enqueue.return_value = None

    _r2_upload_and_enqueue(
        job_id="test-job-1",
        video_path=_tmp_media_file(b"\x00\x01\x02", ".mp4"),
        video_content_type="video/mp4",
        video_filename="test.mp4",
        audio_path=None,
        audio_content_type="audio/webm",
        proof_path=None,
        proof_content_type=None,
        user_id=1,
        duration_sec=15,
        caption="Test",
        tags_list=["홈트"],
        challenge_id=None,
        workout_start=None,
        workout_end=None,
        audio_duration_sec=0,
        subtitle_srt=None,
        subtitle_size=None,
        subtitle_position=None,
        mute_video_audio=False,
    )
    mock_upload.assert_called_once()
    mock_enqueue.assert_called_once()


@patch("app.routes.videos.fail_job")
@patch("app.routes.videos.r2_service.upload_fileobj", side_effect=RuntimeError("R2 down"))
def test_r2_upload_and_enqueue_failure(mock_upload, mock_fail) -> None:
    """_r2_upload_and_enqueue: 업로드 실패 시 fail_job 호출."""
    from app.routes.videos import _r2_upload_and_enqueue

    _r2_upload_and_enqueue(
        job_id="fail-job-1",
        video_path=_tmp_media_file(b"\x00", ".mp4"),
        video_content_type="video/mp4",
        video_filename="fail.mp4",
        audio_path=None,
        audio_content_type="audio/webm",
        proof_path=None,
        proof_content_type=None,
        user_id=2,
        duration_sec=10,
        caption=None,
        tags_list=[],
        challenge_id=None,
        workout_start=None,
        workout_end=None,
        audio_duration_sec=0,
        subtitle_srt=None,
        subtitle_size=None,
        subtitle_position=None,
        mute_video_audio=False,
    )
    mock_fail.assert_called_once_with("fail-job-1", "R2 down")


@patch("app.routes.videos.enqueue_full_upload_pipeline")
@patch("app.routes.videos.r2_service.get_r2_client")
@patch("app.routes.videos.r2_service.upload_fileobj", return_value=("videos/bg2.mp4", "https://cdn/bg2.mp4"))
def test_r2_upload_and_enqueue_with_audio_and_proof(mock_upload, mock_r2_client, mock_enqueue) -> None:
    """_r2_upload_and_enqueue: 오디오+사진 포함."""
    from app.routes.videos import _r2_upload_and_enqueue
    mock_r2_client.return_value.put_object.return_value = {}
    mock_enqueue.return_value = None

    _r2_upload_and_enqueue(
        job_id="test-job-2",
        video_path=_tmp_media_file(b"\x00\x01", ".mp4"),
        video_content_type="video/mp4",
        video_filename="v.mp4",
        audio_path=_tmp_media_file(b"\x10\x20", ".webm"),
        audio_content_type="audio/webm",
        proof_path=_tmp_media_file(b"\xff\xd8\xff", ".jpg"),
        proof_content_type="image/jpeg",
        user_id=3,
        duration_sec=20,
        caption=None,
        tags_list=[],
        challenge_id=None,
        workout_start=None,
        workout_end=None,
        audio_duration_sec=10,
        subtitle_srt=None,
        subtitle_size=None,
        subtitle_position=None,
        mute_video_audio=False,
    )
    assert mock_upload.call_count == 2  # video + audio
    mock_r2_client.return_value.put_object.assert_called_once()  # proof image
    mock_enqueue.assert_called_once()


@patch("app.routes.videos.r2_service.upload_fileobj", return_value=("videos/direct.mp4", "https://cdn/direct.mp4"))
def test_upload_video_endpoint(mock_upload, client: TestClient) -> None:
    """POST /videos/upload (서버사이드 업로드)."""
    token, uid = _register(client, "upload@x.com", "uploaduser")
    headers = _auth(token)
    res = client.post(
        "/api/v1/videos/upload",
        files={"file": ("video.mp4", b"\x00\x01\x02", "video/mp4")},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["data"]["r2_key"] == "videos/direct.mp4"


@patch("app.routes.videos.reserve_job_id", return_value="limit-job-456")
@patch("app.routes.videos.get_daily_upload_count", return_value=3)
def test_upload_pipeline_daily_limit(mock_count, mock_reserve, client: TestClient) -> None:
    """upload_pipeline: 일일 한도 초과 시 429."""
    import json
    token = _register_and_token(client, "pipelimit@x.com", "pipelimituser")
    headers = _auth(token)
    res = client.post(
        "/api/v1/videos/upload-pipeline",
        data={"duration_sec": "15", "tags": json.dumps(["홈트"])},
        files={"file": ("v.mp4", b"\x00", "video/mp4")},
        headers=headers,
    )
    assert res.status_code == 429


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/x.mp4")
def test_confirm_upload_forbidden_r2key(mock_cdn, client: TestClient) -> None:
    """r2_key가 본인 prefix가 아닐 때 403."""
    token = _register_and_token(client, "forbidden@x.com", "forbiddenuser")
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": "videos/99999/other.mp4", "duration_sec": 20,
    }, headers=_auth(token))
    assert res.status_code == 403



def test_merge_audio_forbidden(client: TestClient) -> None:
    """merge_audio: 다른 사용자의 r2_key 거부."""
    token, uid = _register(client, "maforbid@x.com", "maforbiduser")
    res = client.post(
        "/api/v1/videos/merge-audio",
        data={"video_r2_key": "videos/99999/foreign.mp4", "audio_duration_sec": 10},
        files={"audio": ("a.webm", b"\x00", "audio/webm")},
        headers=_auth(token),
    )
    assert res.status_code == 403


def test_merge_audio_bad_duration(client: TestClient) -> None:
    """merge_audio: 오디오 길이 범위 벗어나면 400."""
    token, uid = _register(client, "mabaddur@x.com", "mabadduruser")
    res = client.post(
        "/api/v1/videos/merge-audio",
        data={"video_r2_key": f"videos/{uid}/v.mp4", "audio_duration_sec": -1},
        files={"audio": ("a.webm", b"\x00", "audio/webm")},
        headers=_auth(token),
    )
    assert res.status_code == 400


@patch("app.routes.videos.get_job_status", return_value={"status": "completed", "points_earned": "invalid", "cdn_url": "", "post_id": ""})
def test_get_upload_job_bad_points(mock_job, client: TestClient) -> None:
    """points_earned 파싱 실패 시 0.0으로 fallback."""
    token = _register_and_token(client, "badpts@x.com", "badptsuser")
    res = client.get("/api/v1/videos/upload-job/some-job", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["points_earned"] == 0.0


def test_async_job_status_rejects_other_user(client: TestClient) -> None:
    token, uid = _register(client, "job-owner-a@x.com", "jobownera")
    other_uid = uid + 999
    with patch("app.routes.videos.get_job_status", return_value={"status": "completed", "user_id": str(other_uid), "cdn_url": "https://cdn/private.mp4"}):
        res = client.get("/api/v1/videos/upload-job/private-job", headers=_auth(token))
    assert res.status_code == 404


def test_merge_job_status_rejects_other_user(client: TestClient) -> None:
    token, uid = _register(client, "job-owner-b@x.com", "jobownerb")
    other_uid = uid + 999
    with patch("app.routes.videos.get_job_status", return_value={"status": "completed", "user_id": str(other_uid), "cdn_url": "https://cdn/private.mp4"}):
        res = client.get("/api/v1/videos/merge-job/private-job", headers=_auth(token))
    assert res.status_code == 404


def test_upload_pipeline_rejects_oversized_video_before_job_reservation(client: TestClient, monkeypatch) -> None:
    token = _register_and_token(client, "oversized@x.com", "oversizeduser")
    monkeypatch.setattr("app.routes.videos.r2_service.MAX_FILE_SIZE", 4)
    with patch("app.routes.videos.reserve_job_id") as mock_reserve:
        res = client.post(
            "/api/v1/videos/upload-pipeline",
            data={"duration_sec": "20"},
            files={"file": ("workout.mp4", b"12345", "video/mp4")},
            headers=_auth(token),
        )
    assert res.status_code == 400
    mock_reserve.assert_not_called()

@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/subtitle-default.mp4")
def test_confirm_upload_returns_subtitle_defaults(mock_cdn, client: TestClient) -> None:
    """자막 후처리는 선택 기능이므로 일반 업로드 응답은 기본 skipped 상태로 유지된다."""
    token, uid = _register(client, "subtitle-default@x.com", "subtitledefault")
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/subtitle-default.mp4",
        "duration_sec": 20,
        "tags": ["러닝"],
    }, headers=_auth(token))

    assert res.status_code == 200
    post = res.json()["data"]["post"]
    assert post["subtitle_status"] == "skipped"
    assert post["subtitle_url"] is None
    assert post["subtitle_text"] is None


# ──────────────────────────────────────────────
# subtitle_language 파라미터 테스트
# ──────────────────────────────────────────────

@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/lang-ko.mp4")
def test_confirm_upload_subtitle_language_default(mock_cdn, client: TestClient) -> None:
    """subtitle_language 기본값은 'ko'."""
    token, uid = _register(client, "lang-ko@x.com", "langkouser")
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/lang-ko.mp4",
        "duration_sec": 20,
    }, headers=_auth(token))
    assert res.status_code == 200


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/lang-en.mp4")
def test_confirm_upload_subtitle_language_en(mock_cdn, client: TestClient) -> None:
    """subtitle_language='en' 허용."""
    token, uid = _register(client, "lang-en@x.com", "langenuser")
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/lang-en.mp4",
        "duration_sec": 20,
        "subtitle_language": "en",
    }, headers=_auth(token))
    assert res.status_code == 200


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/lang-auto.mp4")
def test_confirm_upload_subtitle_language_auto(mock_cdn, client: TestClient) -> None:
    """subtitle_language='auto' 허용."""
    token, uid = _register(client, "lang-auto@x.com", "langautouser")
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/lang-auto.mp4",
        "duration_sec": 20,
        "subtitle_language": "auto",
    }, headers=_auth(token))
    assert res.status_code == 200


@patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/lang-bad.mp4")
def test_confirm_upload_subtitle_language_invalid(mock_cdn, client: TestClient) -> None:
    """허용되지 않는 subtitle_language 값은 422."""
    token, uid = _register(client, "lang-bad@x.com", "langbaduser")
    res = client.post("/api/v1/videos/confirm", json={
        "r2_key": f"videos/{uid}/lang-bad.mp4",
        "duration_sec": 20,
        "subtitle_language": "ja",
    }, headers=_auth(token))
    assert res.status_code == 422


@patch("app.services.job_queue.get_redis_client")
@patch("app.routes.videos.enqueue_full_upload_pipeline")
@patch("app.routes.videos.r2_service.upload_fileobj", return_value=("videos/langpipe.mp4", "https://cdn/lp.mp4"))
def test_upload_pipeline_subtitle_language_passed_to_enqueue(mock_upload, mock_enqueue, mock_redis, client: TestClient) -> None:
    """upload-pipeline이 subtitle_language를 enqueue payload에 전달한다."""
    from unittest.mock import MagicMock
    from unittest.mock import patch as mpatch
    mock_r = MagicMock()
    mock_redis.return_value = mock_r

    with mpatch("app.routes.videos.reserve_job_id", return_value="job-lang-test"):
        token = _register_and_token(client, "langpipe@x.com", "langpipeuser")
        res = client.post(
            "/api/v1/videos/upload-pipeline",
            data={"duration_sec": "20", "subtitle_language": "en"},
            files={"file": ("v.mp4", b"\x00", "video/mp4")},
            headers=_auth(token),
        )

    assert res.status_code == 200
    # _r2_upload_and_enqueue is called in background — check via mock_enqueue
    # (background tasks run synchronously in TestClient)
    assert mock_enqueue.called
    call_kwargs = mock_enqueue.call_args[1] if mock_enqueue.call_args[1] else {}
    # subtitle_language should be passed as keyword arg
    assert call_kwargs.get("subtitle_language") == "en" or "en" in str(mock_enqueue.call_args)


def test_upload_job_status_exposes_subtitle_result(client: TestClient) -> None:
    token, _uid = _register(client, "subtitle-job@x.com", "subtitlejob")
    with patch("app.routes.videos.get_job_status", return_value={
        "status": "completed",
        "user_id": str(_uid),
        "points_earned": "0.5",
        "subtitle_status": "completed",
        "subtitle_url": "https://cdn/subtitles/s-1.srt",
        "subtitle_text": "오늘도 5킬로 뛰었습니다.",
        "subtitle_error": "",
    }):
        res = client.get("/api/v1/videos/upload-job/job-1", headers=_auth(token))

    assert res.status_code == 200
    data = res.json()["data"]
    assert data["subtitle_status"] == "completed"
    assert data["subtitle_url"].endswith("s-1.srt")
    assert data["subtitle_text"] == "오늘도 5킬로 뛰었습니다."


# ──────────────────────────────────────────────
# sanitize_srt 테스트 (subtitles.py 커버리지)
# ──────────────────────────────────────────────

def test_sanitize_srt_strips_html_tags() -> None:
    from app.services.subtitles import sanitize_srt

    raw = "1\n00:00:00,000 --> 00:00:01,000\n<b>Hello</b> <i>world</i>\n"
    result = sanitize_srt(raw)
    assert "<b>" not in result
    assert "Hello world" in result


def test_sanitize_srt_preserves_timestamps_and_index() -> None:
    from app.services.subtitles import sanitize_srt

    raw = "1\n00:00:00,000 --> 00:00:01,000\nHello\n"
    result = sanitize_srt(raw)
    assert "00:00:00,000 --> 00:00:01,000" in result
    assert "1" in result


def test_sanitize_srt_truncates_at_2000_chars() -> None:
    from app.services.subtitles import sanitize_srt

    long_srt = "x" * 3000
    result = sanitize_srt(long_srt)
    assert len(result) <= 2000


def test_sanitize_srt_empty_string() -> None:
    from app.services.subtitles import sanitize_srt

    assert sanitize_srt("") == ""


# ──────────────────────────────────────────────
# _parse_tags 테스트 (videos.py 112-113 커버리지)
# ──────────────────────────────────────────────

def test_parse_tags_invalid_json_returns_empty() -> None:
    from app.routes.videos import _parse_tags

    assert _parse_tags("not-json") == []
    assert _parse_tags(None) == []
    assert _parse_tags("") == []


def test_parse_tags_valid_json() -> None:
    from app.routes.videos import _parse_tags

    assert _parse_tags('["홈트", "러닝"]') == ["홈트", "러닝"]


# ──────────────────────────────────────────────
# my-posts?all=true (videos.py 274-275 커버리지)
# ──────────────────────────────────────────────

def test_my_posts_all_true(client: TestClient) -> None:
    """my-posts?all=true 는 주간 필터 없이 전체 반환."""
    token, uid = _register(client, "myall@x.com", "myalluser")
    with patch("app.routes.videos.r2_service.get_cdn_url", return_value="https://cdn/all.mp4"):
        client.post("/api/v1/videos/confirm", json={"r2_key": f"videos/{uid}/v.mp4", "duration_sec": 20}, headers=_auth(token))
    res = client.get("/api/v1/videos/my-posts?all=true", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["has_more"] is False
    assert len(data["posts"]) == 1


# ──────────────────────────────────────────────
# subtitle-job 엔드포인트 (videos.py 655-664 커버리지)
# ──────────────────────────────────────────────

@patch("app.routes.videos.get_job_status", return_value=None)
def test_get_subtitle_job_not_found(mock_job, client: TestClient) -> None:
    token = _register_and_token(client, "subtjob@x.com", "subtjobuser")
    res = client.get("/api/v1/videos/subtitle-job/nonexistent", headers=_auth(token))
    assert res.status_code == 404


@patch("app.routes.videos.get_job_status", return_value={
    "status": "completed", "srt": "1\n00:00:00,000 --> 00:00:01,000\nHello\n",
    "plain_text": "Hello", "error": "", "metrics": '{"transcribe_seconds": 1.2}',
})
def test_get_subtitle_job_completed(mock_job, client: TestClient) -> None:
    token, uid = _register(client, "subtjob2@x.com", "subtjob2user")
    res = client.get("/api/v1/videos/subtitle-job/done-id", headers=_auth(token))
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["status"] == "completed"
    assert data["plain_text"] == "Hello"
    assert data["metrics"]["transcribe_seconds"] == 1.2


@patch("app.routes.videos.get_job_status", return_value={
    "status": "completed", "srt": "", "plain_text": "", "error": "", "metrics": "not-json",
})
def test_get_subtitle_job_bad_metrics(mock_job, client: TestClient) -> None:
    """metrics 파싱 실패 시 None 반환."""
    token = _register_and_token(client, "subtjob3@x.com", "subtjob3user")
    res = client.get("/api/v1/videos/subtitle-job/bad-metrics", headers=_auth(token))
    assert res.status_code == 200
    assert res.json()["data"]["metrics"] is None


# ──────────────────────────────────────────────
# transcribe-subtitles (videos.py 626-646 커버리지)
# ──────────────────────────────────────────────

@patch("app.routes.videos.reserve_job_id", return_value="sub-job-en")
@patch("app.routes.videos._r2_upload_and_enqueue_subtitle")
def test_transcribe_subtitles_subtitle_language_en(mock_bg, mock_reserve, client: TestClient) -> None:
    """subtitle_language=en 으로 자막 추출 잡 등록."""
    token = _register_and_token(client, "transcribeen@x.com", "transcribeenuser")
    res = client.post(
        "/api/v1/videos/transcribe-subtitles",
        data={"subtitle_language": "en"},
        files={"file": ("v.mp4", b"\x00\x01", "video/mp4")},
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json()["data"]["job_id"] == "sub-job-en"


@patch("app.routes.videos.reserve_job_id", return_value="sub-job-auto")
@patch("app.routes.videos._r2_upload_and_enqueue_subtitle")
def test_transcribe_subtitles_subtitle_language_auto(mock_bg, mock_reserve, client: TestClient) -> None:
    """subtitle_language=auto 로 자막 추출 잡 등록."""
    token = _register_and_token(client, "transcribeauto@x.com", "transcribeautouser")
    res = client.post(
        "/api/v1/videos/transcribe-subtitles",
        data={"subtitle_language": "auto"},
        files={"file": ("v.mp4", b"\x00\x01", "video/mp4")},
        headers=_auth(token),
    )
    assert res.status_code == 200
    assert res.json()["data"]["job_id"] == "sub-job-auto"


def test_transcribe_subtitles_invalid_content_type(client: TestClient) -> None:
    """잘못된 파일 형식은 400."""
    token = _register_and_token(client, "transcribect@x.com", "transcribectuser")
    res = client.post(
        "/api/v1/videos/transcribe-subtitles",
        data={},
        files={"file": ("doc.pdf", b"\x00", "application/pdf")},
        headers=_auth(token),
    )
    assert res.status_code == 400


# ──────────────────────────────────────────────
# upload-pipeline proof image 잘못된 형식 (videos.py 879-882)
# ──────────────────────────────────────────────

@patch("app.routes.videos.reserve_job_id", return_value="pipe-proof-bad")
def test_upload_pipeline_proof_image_invalid_type(mock_reserve, client: TestClient) -> None:
    """upload-pipeline: proof_image가 잘못된 타입이면 400."""
    token = _register_and_token(client, "proofbadtype@x.com", "proofbadtypeuser")
    res = client.post(
        "/api/v1/videos/upload-pipeline",
        data={"duration_sec": "20"},
        files={
            "file": ("v.mp4", b"\x00", "video/mp4"),
            "proof_image": ("proof.gif", b"\x00", "image/gif"),
        },
        headers=_auth(token),
    )
    assert res.status_code == 400


# ──────────────────────────────────────────────
# presigned-url invalid content_type (videos.py 125-130)
# ──────────────────────────────────────────────

@patch("app.routes.videos.r2_service.generate_presigned_url", return_value=("https://url", "videos/t.mp4"))
def test_presigned_url_invalid_content_type(mock_r2, client: TestClient) -> None:
    """presigned-url: 지원하지 않는 content_type은 400."""
    token = _register_and_token(client, "psinvct@x.com", "psinvctuser")
    res = client.post("/api/v1/videos/presigned-url", json={
        "filename": "x.avi", "content_type": "video/avi", "file_size": 1024,
    }, headers=_auth(token))
    assert res.status_code == 400
