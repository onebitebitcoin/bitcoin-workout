"""FFMPEG_ACTIVE_JOBS는 worker.py(writer)와 backend/app/services/{cartoon,muscle_heat}.py
(reader)에 각각 문자열 리터럴로 하드코딩돼 있다 — 한쪽만 오타/개명하면 reader가 조용히
WORKER_INSTANCES 폴백으로 흡수해 에러 없이 성능만 저하된다(review 리포트, CLAUDE.md 참고).
무거운 의존성(mediapipe/redis) import 없이 소스 텍스트만 비교해 이 드리프트를 잡는다."""

from __future__ import annotations

import os

_WORKER_DIR = os.path.dirname(__file__)
_BACKEND_SERVICES_DIR = os.path.abspath(os.path.join(_WORKER_DIR, "../backend/app/services"))

KEY = "FFMPEG_ACTIVE_JOBS"


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_ffmpeg_active_jobs_key_matches_writer_and_readers() -> None:
    writer_src = _read(os.path.join(_WORKER_DIR, "worker.py"))
    assert f'os.environ["{KEY}"]' in writer_src, "worker.py가 더 이상 이 키로 env를 설정하지 않는다"

    for reader in ("cartoon.py", "muscle_heat.py"):
        reader_src = _read(os.path.join(_BACKEND_SERVICES_DIR, reader))
        assert f'os.environ.get("{KEY}")' in reader_src, f"{reader}가 더 이상 이 키를 읽지 않는다"
