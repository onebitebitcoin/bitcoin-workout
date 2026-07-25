"""운동 종목 분류(`app.services.exercise_classify`) 테스트.

네트워크·비용을 피하려고 Gemini HTTP 호출과 프레임 샘플링을 모킹한다.
핵심 검증: 키 없음/추출 실패/HTTP 실패/unknown 응답이 모두 None으로 안전 폴백.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from unittest.mock import patch

import cv2
import httpx
import numpy as np
import pytest

from app.services import exercise_classify as ec

_FRAMES = [b"\xff\xd8jpeg1", b"\xff\xd8jpeg2", b"\xff\xd8jpeg3"]
_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _gemini_response(exercise: str) -> object:
    """Gemini generateContent 응답 형태의 httpx.Response 스텁 (raise_for_status용 request 포함)."""
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps({"exercise": exercise})}]}}
        ]
    }
    return httpx.Response(200, json=payload, request=httpx.Request("POST", "https://x"))


class TestSampleFramesJpeg:
    def test_unopenable_path_returns_empty(self):
        assert ec._sample_frames_jpeg("/tmp/does-not-exist-xyz.mp4") == []

    @pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg 필요 (테스트 영상 생성)")
    def test_real_video_yields_decodable_downscaled_frames(self, tmp_path):
        path = str(tmp_path / "clip.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", "testsrc=size=640x360:rate=30:duration=4",
             "-pix_fmt", "yuv420p", path],
            check=True, timeout=60,
        )
        frames = ec._sample_frames_jpeg(path)
        assert len(frames) == len(ec._SAMPLE_FRACTIONS)
        for jpeg in frames:
            img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            assert img is not None
            assert img.shape[1] == ec._FRAME_WIDTH  # 토큰 절약용 다운스케일이 실제로 적용됨


class TestClassifyExercise:
    def test_no_api_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert ec.classify_exercise("/tmp/whatever.mp4") is None

    def test_no_frames_extracted_returns_none(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        with patch.object(ec, "_sample_frames_jpeg", return_value=[]):
            assert ec.classify_exercise("/tmp/x.mp4") is None

    def test_happy_path_returns_exercise(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        with patch.object(ec, "_sample_frames_jpeg", return_value=_FRAMES), \
             patch.object(ec.httpx, "post", return_value=_gemini_response("bicep curl")) as mock_post:
            assert ec.classify_exercise("/tmp/x.mp4") == "bicep curl"
            # 프롬프트 1 + 프레임 3 파트가 그대로 실려야 한다
            parts = mock_post.call_args.kwargs["json"]["contents"][0]["parts"]
            assert len(parts) == 1 + len(_FRAMES)
            assert parts[0]["text"]
            assert all("inline_data" in p for p in parts[1:])

    def test_unknown_response_returns_none(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        with patch.object(ec, "_sample_frames_jpeg", return_value=_FRAMES), \
             patch.object(ec.httpx, "post", return_value=_gemini_response("unknown")):
            assert ec.classify_exercise("/tmp/x.mp4") is None

    def test_http_error_returns_none(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        with patch.object(ec, "_sample_frames_jpeg", return_value=_FRAMES), \
             patch.object(ec.httpx, "post", side_effect=httpx.ConnectError("boom")):
            assert ec.classify_exercise("/tmp/x.mp4") is None

    def test_explicit_api_key_overrides_env(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with patch.object(ec, "_sample_frames_jpeg", return_value=_FRAMES), \
             patch.object(ec.httpx, "post", return_value=_gemini_response("squat")) as mock_post:
            assert ec.classify_exercise("/tmp/x.mp4", api_key="explicit") == "squat"
            assert mock_post.call_args.kwargs["params"]["key"] == "explicit"
