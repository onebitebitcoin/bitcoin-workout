"""운동열 렌더러(`app.services.muscle_heat`) 단위 + 영상 E2E 테스트."""

from __future__ import annotations

import shutil
import subprocess

import cv2
import numpy as np
import pytest

from app.services.muscle_heat import (
    PW,
    _RenderState,
    heat_preview_frame,
    light_cartoonize,
    render_heat_video,
)

_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _textured_frame(seed: int = 5, size: tuple[int, int] = (240, 320)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.integers(40, 220, (*size, 3), dtype=np.uint8)
    return cv2.GaussianBlur(base, (5, 5), 0)


class TestLightCartoonize:
    def test_shape_and_no_mutation(self):
        frame = _textured_frame()
        original = frame.copy()
        out = light_cartoonize(frame)
        assert out.shape == frame.shape
        assert np.array_equal(frame, original)

    def test_color_preserved(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :, 2] = 200  # 빨강 프레임
        out = light_cartoonize(frame)
        center = out[120, 160]
        assert center[2] > center[0]  # 빨강 채널 우세 유지


class _FakeLandmark:
    def __init__(self, x: float, y: float, visibility: float = 0.9):
        self.x = x
        self.y = y
        self.visibility = visibility


class _FakePoseResult:
    """`_RenderState.step`이 읽는 속성만 흉내낸 mediapipe 결과 스텁 — 실제 사진 없이
    포즈 좌표를 직접 지정해 정적 부하(오버헤드 지지) 로직을 단위 테스트한다."""

    def __init__(self, landmarks: dict[int, _FakeLandmark]):
        self.pose_landmarks = [landmarks]
        self.segmentation_masks = None


def _overhead_pose() -> _FakePoseResult:
    """팔꿈치가 어깨보다 위 = 오버헤드 지지 자세. 무릎은 편 상태(하체 정적부하 미발동).

    `_RenderState.step`은 랜드마크 0..32 전체를 딕셔너리에서 조회하므로, 사용하지
    않는 나머지 관절도 화면 중앙 낮은 신뢰도 좌표로 채워 KeyError를 막는다.
    """
    coords = {
        0: (0.50, 0.15), 7: (0.47, 0.14), 8: (0.53, 0.14),
        11: (0.40, 0.35), 12: (0.60, 0.35),
        13: (0.35, 0.15), 14: (0.65, 0.15),
        15: (0.45, 0.05), 16: (0.55, 0.05),
        23: (0.42, 0.65), 24: (0.58, 0.65),
        25: (0.42, 0.85), 26: (0.58, 0.85),
        27: (0.42, 0.98), 28: (0.58, 0.98),
    }
    landmarks = {i: _FakeLandmark(0.5, 0.5, visibility=0.0) for i in range(33)}
    landmarks.update({i: _FakeLandmark(x, y) for i, (x, y) in coords.items()})
    return _FakePoseResult(landmarks)


class TestRenderStateConvergence:
    """단일 프레임 프리뷰(`heat_preview_frame`)가 오버레이 하한(lo=0.12)을 못 넘어
    열이 아예 안 보이던 버그의 회귀 테스트. 같은 정적 자세를 유지하면 EMA가
    수렴해 열이 보여야 한다."""

    def test_single_step_stays_below_overlay_threshold(self):
        state = _RenderState(ph=200)
        dummy = np.zeros((200, PW, 3), np.uint8)
        heat = state.step(dummy, _overhead_pose())
        assert heat.max() < 0.12  # 수렴 전: 오버레이에서 안 보임 (수정 전 버그 상태)

    def test_repeated_steps_converge_above_overlay_threshold(self):
        state = _RenderState(ph=200)
        dummy = np.zeros((200, PW, 3), np.uint8)
        heat = None
        for _ in range(12):
            heat = state.step(dummy, _overhead_pose())
        assert heat.max() > 0.12  # 수렴 후: 오버레이에서 보임


class TestHeatPreviewFrame:
    """사람이 없는 합성 프레임 — 포즈 미검출 그레이스풀 폴백 검증."""

    def test_no_pose_returns_unchanged_shape(self):
        frame = _textured_frame()
        out = heat_preview_frame(frame, weak_cartoon=False)
        assert out.shape == frame.shape
        assert out.dtype == np.uint8

    def test_no_pose_with_cartoon_base(self):
        frame = _textured_frame()
        out = heat_preview_frame(frame, weak_cartoon=True)
        assert out.shape == frame.shape

    def test_does_not_mutate_input(self):
        frame = _textured_frame()
        original = frame.copy()
        heat_preview_frame(frame, weak_cartoon=False)
        assert np.array_equal(frame, original)


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not installed")
class TestRenderHeatVideo:
    @pytest.fixture()
    def sample_with_audio(self, tmp_path):
        """1초 테스트 영상(합성 패턴, 사람 없음) + 사인파 오디오."""
        path = tmp_path / "in.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                str(path),
            ],
            check=True, timeout=60,
        )
        return path

    @pytest.mark.parametrize("weak_cartoon", [False, True])
    def test_frames_and_audio_preserved(self, sample_with_audio, tmp_path, weak_cartoon):
        out = tmp_path / f"out_{weak_cartoon}.mp4"
        render_heat_video(str(sample_with_audio), str(out), weak_cartoon=weak_cartoon)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,nb_frames",
             "-of", "json", str(out)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        import json

        streams = json.loads(probe.stdout)["streams"]
        types = {s["codec_type"] for s in streams}
        assert types == {"video", "audio"}, f"streams: {streams}"
        video_stream = next(s for s in streams if s["codec_type"] == "video")
        assert int(video_stream["nb_frames"]) == 10  # 1초 x 10fps

    def test_invalid_input_raises(self, tmp_path):
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(b"not a video")
        with pytest.raises((ValueError, RuntimeError)):
            render_heat_video(str(bad), str(tmp_path / "out.mp4"), weak_cartoon=False)
