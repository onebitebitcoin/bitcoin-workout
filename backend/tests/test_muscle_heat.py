"""운동열 렌더러(`app.services.muscle_heat`) 단위 + 영상 E2E 테스트."""

from __future__ import annotations

import shutil
import subprocess

import cv2
import numpy as np
import pytest

from app.services.muscle_heat import (
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
