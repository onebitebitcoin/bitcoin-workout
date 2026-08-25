"""다중 미디어 업로드(/upload-multi) 엔드포인트 테스트."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.test_videos import _auth, _register_and_token


def _img(name: str = "a.png") -> tuple[str, bytes, str]:
    return (name, b"fake-image-bytes", "image/png")


def _vid(name: str = "v.mp4") -> tuple[str, bytes, str]:
    return (name, b"fake-video-bytes", "video/mp4")


@patch("app.routes.videos.reserve_job_id", return_value="multi-img-1")
@patch("app.routes.videos._r2_upload_and_enqueue_multi")
def test_upload_multi_images_only_success(mock_bg, mock_reserve, client: TestClient) -> None:
    token = _register_and_token(client, "m1@x.com", "muser1")
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps([{"kind": "image"}, {"kind": "image"}]), "tags": '["가벼운 활동"]'},
        files=[("files", _img("a.png")), ("files", _img("b.png"))],
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["job_id"] == "multi-img-1"
    assert res.json()["data"]["status"] == "processing"


@patch("app.routes.videos.reserve_job_id", return_value="multi-mix-1")
@patch("app.routes.videos._r2_upload_and_enqueue_multi")
def test_upload_multi_image_then_video_preserves_order(mock_bg, mock_reserve, client: TestClient) -> None:
    token = _register_and_token(client, "m2@x.com", "muser2")
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps([{"kind": "image"}, {"kind": "video"}])},
        files=[("files", _img("first.png")), ("files", _vid("second.mp4"))],
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    # 백그라운드로 넘어간 spooled 의 kind 순서가 전송 순서와 일치
    spooled = mock_bg.call_args.kwargs["spooled"]
    assert [item[0] for item in spooled] == ["image", "video"]


def test_upload_multi_two_videos_rejected(client: TestClient) -> None:
    token = _register_and_token(client, "m3@x.com", "muser3")
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps([{"kind": "video"}, {"kind": "video"}])},
        files=[("files", _vid("a.mp4")), ("files", _vid("b.mp4"))],
        headers=_auth(token),
    )
    assert res.status_code == 400


def test_upload_multi_six_images_rejected(client: TestClient) -> None:
    token = _register_and_token(client, "m4@x.com", "muser4")
    meta = [{"kind": "image"}] * 6
    files = [("files", _img(f"{i}.png")) for i in range(6)]
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps(meta)},
        files=files,
        headers=_auth(token),
    )
    assert res.status_code == 400


def test_upload_multi_meta_count_mismatch_rejected(client: TestClient) -> None:
    token = _register_and_token(client, "m5@x.com", "muser5")
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps([{"kind": "image"}])},
        files=[("files", _img("a.png")), ("files", _img("b.png"))],
        headers=_auth(token),
    )
    assert res.status_code == 400


def test_upload_multi_invalid_image_type_rejected(client: TestClient) -> None:
    token = _register_and_token(client, "m6@x.com", "muser6")
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps([{"kind": "image"}])},
        files=[("files", ("doc.pdf", b"data", "application/pdf"))],
        headers=_auth(token),
    )
    assert res.status_code == 400


def test_upload_multi_unauthenticated(client: TestClient) -> None:
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps([{"kind": "image"}])},
        files=[("files", _img("a.png"))],
    )
    assert res.status_code in (401, 403)


@patch("app.routes.videos.reserve_job_id", return_value="multi-filter-1")
@patch("app.routes.videos._r2_upload_and_enqueue_multi")
def test_upload_multi_cartoon_filter_accepted(mock_bg, mock_reserve, client: TestClient) -> None:
    token = _register_and_token(client, "mf1@x.com", "mfuser1")
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps([{"kind": "video"}]), "video_filter": "cartoon"},
        files=[("files", _vid("a.mp4"))],
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    assert mock_bg.call_args.kwargs["video_filter"] == "cartoon"


def test_upload_multi_unknown_filter_rejected(client: TestClient) -> None:
    token = _register_and_token(client, "mf2@x.com", "mfuser2")
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps([{"kind": "video"}]), "video_filter": "sepia"},
        files=[("files", _vid("a.mp4"))],
        headers=_auth(token),
    )
    assert res.status_code == 400


@pytest.mark.parametrize("video_filter", ["heat", "cartoon_heat", "footsteps"])
@patch("app.routes.videos.reserve_job_id", return_value="multi-heat-1")
@patch("app.routes.videos._r2_upload_and_enqueue_multi")
def test_upload_multi_heat_filter_accepted(mock_bg, mock_reserve, client: TestClient, video_filter: str) -> None:
    token = _register_and_token(client, f"mf3-{video_filter}@x.com", f"mfuser3{video_filter}")
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={"items_meta": json.dumps([{"kind": "video"}]), "video_filter": video_filter},
        files=[("files", _vid("a.mp4"))],
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    assert mock_bg.call_args.kwargs["video_filter"] == video_filter


class TestFilterPreview:
    def test_unauthenticated(self, client: TestClient) -> None:
        res = client.post(
            "/api/v1/videos/filter-preview",
            files={"frame": ("f.jpg", b"data", "image/jpeg")},
        )
        assert res.status_code in (401, 403)

    def test_returns_cartoonized_jpeg(self, client: TestClient) -> None:
        import cv2
        import numpy as np

        token = _register_and_token(client, "fp1@x.com", "fpuser1")
        rng = np.random.default_rng(3)
        img = rng.integers(40, 220, (120, 160, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", img)
        assert ok
        res = client.post(
            "/api/v1/videos/filter-preview",
            files={"frame": ("f.jpg", buf.tobytes(), "image/jpeg")},
            headers=_auth(token),
        )
        assert res.status_code == 200, res.text
        assert res.headers["content-type"] == "image/jpeg"
        out = cv2.imdecode(np.frombuffer(res.content, np.uint8), cv2.IMREAD_COLOR)
        assert out is not None
        assert out.shape == img.shape  # 1280px 이하는 해상도 유지

    @pytest.mark.parametrize("video_filter", ["heat", "cartoon_heat", "footsteps"])
    def test_returns_heat_jpeg(self, client: TestClient, video_filter: str) -> None:
        import cv2
        import numpy as np

        token = _register_and_token(client, f"fp4-{video_filter}@x.com", f"fpuser4{video_filter}")
        rng = np.random.default_rng(3)
        img = rng.integers(40, 220, (120, 160, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", img)
        assert ok
        res = client.post(
            "/api/v1/videos/filter-preview",
            data={"video_filter": video_filter},
            files={"frame": ("f.jpg", buf.tobytes(), "image/jpeg")},
            headers=_auth(token),
        )
        assert res.status_code == 200, res.text
        assert res.headers["content-type"] == "image/jpeg"
        out = cv2.imdecode(np.frombuffer(res.content, np.uint8), cv2.IMREAD_COLOR)
        assert out is not None
        assert out.shape == img.shape

    def test_unknown_filter_rejected(self, client: TestClient) -> None:
        token = _register_and_token(client, "fp5@x.com", "fpuser5")
        res = client.post(
            "/api/v1/videos/filter-preview",
            data={"video_filter": "sepia"},
            files={"frame": ("f.jpg", b"data", "image/jpeg")},
            headers=_auth(token),
        )
        assert res.status_code == 400

    def test_invalid_file_rejected(self, client: TestClient) -> None:
        token = _register_and_token(client, "fp2@x.com", "fpuser2")
        res = client.post(
            "/api/v1/videos/filter-preview",
            files={"frame": ("f.jpg", b"not-an-image", "image/jpeg")},
            headers=_auth(token),
        )
        assert res.status_code == 400

    def test_empty_file_rejected(self, client: TestClient) -> None:
        token = _register_and_token(client, "fp3@x.com", "fpuser3")
        res = client.post(
            "/api/v1/videos/filter-preview",
            files={"frame": ("f.jpg", b"", "image/jpeg")},
            headers=_auth(token),
        )
        assert res.status_code == 400


@patch("app.routes.videos.reserve_job_id", return_value="multi-text-1")
@patch("app.routes.videos._r2_upload_and_enqueue_multi")
def test_upload_multi_with_text_subtitle(mock_bg, mock_reserve, client: TestClient) -> None:
    token = _register_and_token(client, "m8@x.com", "muser8")
    res = client.post(
        "/api/v1/videos/upload-multi",
        data={
            "items_meta": json.dumps([{"kind": "image"}]),
            "subtitle_text": "오늘 운동 완료했다",
            "tags": '["땀 흘리는 운동"]',
        },
        files=[("files", _img("a.png"))],
        headers=_auth(token),
    )
    assert res.status_code == 200, res.text
    assert mock_bg.call_args.kwargs["subtitle_text"] == "오늘 운동 완료했다"
