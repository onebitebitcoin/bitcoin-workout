"""운동 종목 분류(`app.services.exercise_classify`) 테스트.

네트워크·비용을 피하려고 Gemini HTTP 호출과 ffmpeg 프레임 추출을 모킹한다.
핵심 검증: 키 없음/추출 실패/HTTP 실패/unknown 응답이 모두 None으로 안전 폴백.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx

from app.services import exercise_classify as ec


def _gemini_response(exercise: str) -> object:
    """Gemini generateContent 응답 형태의 httpx.Response 스텁 (raise_for_status용 request 포함)."""
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": json.dumps({"exercise": exercise})}]}}
        ]
    }
    return httpx.Response(200, json=payload, request=httpx.Request("POST", "https://x"))


class TestClassifyExercise:
    def test_no_api_key_returns_none(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert ec.classify_exercise("/tmp/whatever.mp4") is None

    def test_bad_duration_returns_none(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        with patch.object(ec, "_probe_duration", return_value=None):
            assert ec.classify_exercise("/tmp/x.mp4") is None

    def test_no_frames_extracted_returns_none(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        with patch.object(ec, "_probe_duration", return_value=10.0), \
             patch.object(ec, "_extract_frame_jpeg", return_value=None):
            assert ec.classify_exercise("/tmp/x.mp4") is None

    def test_happy_path_returns_exercise(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        with patch.object(ec, "_probe_duration", return_value=10.0), \
             patch.object(ec, "_extract_frame_jpeg", return_value=b"\xff\xd8jpeg"), \
             patch.object(ec.httpx, "post", return_value=_gemini_response("bicep curl")):
            assert ec.classify_exercise("/tmp/x.mp4") == "bicep curl"

    def test_unknown_response_returns_none(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        with patch.object(ec, "_probe_duration", return_value=10.0), \
             patch.object(ec, "_extract_frame_jpeg", return_value=b"\xff\xd8jpeg"), \
             patch.object(ec.httpx, "post", return_value=_gemini_response("unknown")):
            assert ec.classify_exercise("/tmp/x.mp4") is None

    def test_http_error_returns_none(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "x")
        with patch.object(ec, "_probe_duration", return_value=10.0), \
             patch.object(ec, "_extract_frame_jpeg", return_value=b"\xff\xd8jpeg"), \
             patch.object(ec.httpx, "post", side_effect=httpx.ConnectError("boom")):
            assert ec.classify_exercise("/tmp/x.mp4") is None

    def test_explicit_api_key_overrides_env(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with patch.object(ec, "_probe_duration", return_value=10.0), \
             patch.object(ec, "_extract_frame_jpeg", return_value=b"\xff\xd8jpeg"), \
             patch.object(ec.httpx, "post", return_value=_gemini_response("squat")) as mock_post:
            assert ec.classify_exercise("/tmp/x.mp4", api_key="explicit") == "squat"
            assert mock_post.call_args.kwargs["params"]["key"] == "explicit"
