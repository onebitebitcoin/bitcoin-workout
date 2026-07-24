"""발자국 렌더러(`app.services.motion_fx`) 단위 + 영상 E2E 테스트."""

from __future__ import annotations

import shutil
import subprocess

import cv2
import numpy as np
import pytest

from app.services.motion_fx import (
    _adaptive_color,
    _COLOR_INK,
    _COLOR_NEON,
    _make_foot_mask,
    footsteps_preview_frame,
    render_footsteps_video,
)

_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _textured_frame(seed: int = 5, size: tuple[int, int] = (240, 320)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.integers(40, 220, (*size, 3), dtype=np.uint8)
    return cv2.GaussianBlur(base, (5, 5), 0)


class TestFootMask:
    def test_shape_and_range(self):
        m = _make_foot_mask(80, left=False, angle_deg=0)
        assert m.shape == (80, int(80 * 0.62))
        assert 0.0 <= m.min() and m.max() <= 1.0
        assert m.max() > 0.5  # 실제로 뭔가 그려짐

    def test_left_is_mirror_of_right(self):
        r = _make_foot_mask(80, left=False, angle_deg=0)
        left = _make_foot_mask(80, left=True, angle_deg=0)
        assert np.allclose(left, cv2.flip(r, 1), atol=1e-6)

    def test_cache_returns_same_object(self):
        a = _make_foot_mask(60, left=False, angle_deg=9)
        b = _make_foot_mask(60, left=False, angle_deg=9)
        assert a is b


class TestAdaptiveColor:
    def test_dark_background_neon(self):
        dark = np.full((100, 100, 3), 30, np.uint8)
        assert _adaptive_color(dark, 50, 50, 40) == _COLOR_NEON

    def test_bright_background_ink(self):
        bright = np.full((100, 100, 3), 220, np.uint8)
        assert _adaptive_color(bright, 50, 50, 40) == _COLOR_INK


class TestFootstepsPreviewFrame:
    def test_shape_and_no_mutation(self):
        frame = _textured_frame()
        original = frame.copy()
        out = footsteps_preview_frame(frame)
        assert out.shape == frame.shape
        assert out.dtype == np.uint8
        assert np.array_equal(frame, original)  # 입력 불변

    def test_preview_actually_draws(self):
        frame = _textured_frame()
        out = footsteps_preview_frame(frame)
        assert not np.array_equal(out, frame)  # 발자국+HUD가 그려짐


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not installed")
class TestRenderFootstepsVideo:
    @pytest.fixture()
    def sample_with_audio(self, tmp_path):
        """1초 테스트 영상(합성 패턴) + 사인파 오디오."""
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

    def test_frames_and_audio_preserved(self, sample_with_audio, tmp_path):
        out = tmp_path / "out.mp4"
        render_footsteps_video(str(sample_with_audio), str(out))
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
            render_footsteps_video(str(bad), str(tmp_path / "out.mp4"))
