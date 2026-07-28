"""카툰 렌더러(`app.services.cartoon`) 단위 + 영상 E2E 테스트."""

from __future__ import annotations

import shutil
import subprocess

import cv2
import numpy as np
import pytest

from app.services.cartoon import (
    _worker_pool_size,
    adaptive_gamma,
    cartoon_frame,
    cartoonize_video,
)

_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _textured_frame(seed: int = 5) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.integers(40, 220, (240, 320, 3), dtype=np.uint8)
    return cv2.GaussianBlur(base, (5, 5), 0)


class TestCartoonFrame:
    def test_shape_and_no_mutation(self):
        frame = _textured_frame()
        original = frame.copy()
        out = cartoon_frame(frame)
        assert out.shape == frame.shape
        assert np.array_equal(frame, original)

    def test_color_preserved(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :, 2] = 200  # 빨강 프레임
        out = cartoon_frame(frame)
        center = out[120, 160]
        assert center[2] > center[0]  # 빨강 채널 우세 유지


class TestWorkerPoolSize:
    def test_single_active_job_uses_full_budget(self, monkeypatch):
        monkeypatch.setattr("os.cpu_count", lambda: 10)
        monkeypatch.delenv("WORKER_INSTANCES", raising=False)
        monkeypatch.setenv("FFMPEG_ACTIVE_JOBS", "1")
        assert _worker_pool_size() == 8  # (10-2)//1

    def test_multiple_active_jobs_split_budget(self, monkeypatch):
        monkeypatch.setattr("os.cpu_count", lambda: 10)
        monkeypatch.delenv("WORKER_INSTANCES", raising=False)
        monkeypatch.setenv("FFMPEG_ACTIVE_JOBS", "2")
        assert _worker_pool_size() == 4  # (10-2)//2

    def test_falls_back_to_worker_instances_when_unset(self, monkeypatch):
        monkeypatch.setattr("os.cpu_count", lambda: 10)
        monkeypatch.delenv("FFMPEG_ACTIVE_JOBS", raising=False)
        monkeypatch.setenv("WORKER_INSTANCES", "2")
        assert _worker_pool_size() == 4  # (10-2)//2


class TestAdaptiveGamma:
    def test_dark_frame_lifts(self):
        assert adaptive_gamma(np.full((120, 160, 3), 20, dtype=np.uint8)) < 0.7

    def test_bright_frame_untouched(self):
        assert adaptive_gamma(np.full((120, 160, 3), 150, dtype=np.uint8)) == 1.0

    def test_black_frame_clamped(self):
        assert adaptive_gamma(np.zeros((120, 160, 3), dtype=np.uint8)) == 0.4


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not installed")
class TestCartoonizeVideo:
    @pytest.fixture()
    def sample_with_audio(self, tmp_path):
        """1초 테스트 영상 + 사인파 오디오."""
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
        cartoonize_video(str(sample_with_audio), str(out))
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
            cartoonize_video(str(bad), str(tmp_path / "out.mp4"))
