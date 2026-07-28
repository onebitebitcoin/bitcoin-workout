from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_module_and_worker_import() -> None:
    """worker dispatch + 멀티 파이프라인 모듈이 정상 import 되는지."""
    import worker  # noqa: F401  (import 시 dispatch 분기 포함)
    from tasks.full_pipeline_multi import run_multi_pipeline
    assert callable(run_multi_pipeline)


def test_empty_items_raises() -> None:
    from tasks.full_pipeline_multi import run_multi_pipeline
    with pytest.raises(RuntimeError):
        run_multi_pipeline({"job_id": "j1", "user_id": 1, "items": []})


def test_over_60s_cut_and_orphan_cleanup(monkeypatch) -> None:
    from tasks import full_pipeline_multi as m

    fake_r2 = MagicMock()
    monkeypatch.setattr(m, "_get_r2_client", lambda: fake_r2)
    monkeypatch.setattr(m, "compose_items", lambda r2, items, mute_video=False: ("videos/composed-x.mp4", 65.0))

    with pytest.raises(RuntimeError, match="60"):
        m.run_multi_pipeline({
            "job_id": "j2", "user_id": 1,
            "items": [{"kind": "image", "r2_key": "img/a.png"}],
        })
    # 60초 초과 시 합쳐진 영상 고아 정리
    fake_r2.delete_object.assert_called()


def test_status_callback_invoked_with_compose(monkeypatch) -> None:
    """compose 단계에서 status_callback('compose')가 먼저 불리는지."""
    from tasks import full_pipeline_multi as m

    monkeypatch.setattr(m, "_get_r2_client", lambda: MagicMock())
    monkeypatch.setattr(m, "compose_items", lambda r2, items, mute_video=False: ("videos/composed-x.mp4", 99.0))

    steps: list[str] = []
    with pytest.raises(RuntimeError):
        m.run_multi_pipeline(
            {"job_id": "j3", "user_id": 1, "items": [{"kind": "image", "r2_key": "a"}]},
            status_callback=steps.append,
        )
    assert steps and steps[0] == "compose"


def test_should_compress_skips_when_filter_completed() -> None:
    """필터가 성공(completed)하면 compress를 생략 — 필터 인코더가 이미 동일 crf로 인코딩했으므로."""
    from tasks.full_pipeline_multi import _should_compress

    assert _should_compress("completed") is False


def test_should_compress_runs_when_no_filter() -> None:
    """필터를 아예 시도하지 않았으면(skipped) 기존대로 compress를 실행한다."""
    from tasks.full_pipeline_multi import _should_compress

    assert _should_compress("skipped") is True


def test_should_compress_falls_back_when_filter_failed() -> None:
    """필터가 실패했으면(failed) 압축 없는 원본이 나가지 않도록 compress로 대체한다."""
    from tasks.full_pipeline_multi import _should_compress

    assert _should_compress("failed") is True
