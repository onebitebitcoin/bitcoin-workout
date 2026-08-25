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


def test_generated_srt_upload_failure_does_not_abort_pipeline(monkeypatch) -> None:
    """생성 SRT의 put_object 실패는 고아 정리 블록 밖에서 일어나므로, 예외를 그대로 올리면
    이미 렌더된 필터/압축 결과물이 영구 고아가 된다 — 자막만 건너뛰고 업로드는 계속해야 한다."""
    from tasks import full_pipeline_multi as m

    fake_r2 = MagicMock()
    fake_r2.put_object.side_effect = RuntimeError("R2 down")
    monkeypatch.setattr(m, "_get_r2_client", lambda: fake_r2)
    monkeypatch.setattr(m, "compose_items", lambda r2, items, mute_video=False: ("videos/composed-x.mp4", 10.0))
    monkeypatch.setattr(m, "_compress_video", lambda r2, key, mute_video=False: None)
    monkeypatch.setattr(m, "_extract_thumbnail", lambda r2, key: None)
    monkeypatch.setattr(m, "_probe_duration_safe", lambda r2, key: 10.0)
    monkeypatch.setattr(m, "build_srt_from_text", lambda *a, **kw: "1\n00:00:00,000 --> 00:00:05,000\n텍스트\n")

    # db_save까지 가면 DB가 필요하므로, 그 직전에 멈추도록 SessionLocal 첫 호출에서 끊는다.
    # (업로드 한도 검사가 사라져 파이프라인 중 SessionLocal 호출은 db_save 한 번뿐이다.)
    def flaky_session():
        raise RuntimeError("STOP_AT_DB_SAVE")

    monkeypatch.setattr(m, "SessionLocal", flaky_session)

    with pytest.raises(RuntimeError, match="STOP_AT_DB_SAVE"):
        m.run_multi_pipeline({
            "job_id": "j6", "user_id": 1,
            "items": [{"kind": "image", "r2_key": "img/a.png"}],
            "subtitle_text": "테스트 후기",
        })

    # put_object가 실제로 시도되고 실패했는데도 SRT 단계에서 파이프라인이 죽지 않고
    # db_save까지 진행했다(= STOP_AT_DB_SAVE 도달)는 것이 검증 포인트.
    assert fake_r2.put_object.called
