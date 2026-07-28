"""FFMPEG_ACTIVE_JOBS는 worker.py(writer)와 backend/app/services/{cartoon,muscle_heat}.py
(reader)에 각각 문자열 리터럴로 하드코딩돼 있다 — 한쪽만 오타/개명하면 reader가 조용히
WORKER_INSTANCES 폴백으로 흡수해 에러 없이 성능만 저하된다(review 리포트, CLAUDE.md 참고).
무거운 의존성(mediapipe/redis) import 없이 소스 텍스트만 비교해 이 드리프트를 잡는다."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

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


def test_refresh_active_jobs_reads_current_slot_count(monkeypatch) -> None:
    """스냅샷이 슬롯 획득 시점에 고정되면 compose·R2 다운로드(수십 초~수 분) 동안의
    동시성 변화가 렌더 시점에 반영되지 않는다 — 호출할 때마다 zcard를 다시 읽어야 한다."""
    import worker

    monkeypatch.delenv(KEY, raising=False)
    r = MagicMock()
    r.zcard.return_value = 1
    worker._refresh_active_jobs(r)
    assert os.environ[KEY] == "1"

    r.zcard.return_value = 3  # 렌더 진입 시점에 잡이 늘어난 상황
    worker._refresh_active_jobs(r)
    assert os.environ[KEY] == "3"
    monkeypatch.delenv(KEY, raising=False)


def test_render_steps_cover_heavy_filter_and_compress() -> None:
    """_RENDER_STEPS가 실제 파이프라인의 무거운 렌더 단계 이름과 일치해야 재갱신이 걸린다.
    단계 이름은 full_pipeline_multi.py의 status_callback 문자열과 같은 계약."""
    import worker

    assert {"filter", "compress"} <= worker._RENDER_STEPS

    multi_src = _read(os.path.join(_WORKER_DIR, "tasks", "full_pipeline_multi.py"))
    for step in worker._RENDER_STEPS:
        assert f'status_callback("{step}")' in multi_src, f"파이프라인이 '{step}' 단계를 더 이상 알리지 않는다"
