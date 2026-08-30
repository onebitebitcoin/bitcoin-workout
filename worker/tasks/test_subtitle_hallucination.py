"""사용자 직접입력(user_srt) 경로의 유튜브 상용구 필터 회귀 테스트.

배경: 환각 필터가 Whisper 경로에만 있어서, 사용자가 넣은 SRT 의 같은 문구가
그대로 영상에 태워졌다 (video 149·702 — "이 영상은 유료광고를 포함하고 있습니다").
"""

from __future__ import annotations

from tasks.subtitle import _contains_hallucination_phrase, strip_hallucination_cues

REAL_CASE = """1
00:00:01.000 --> 00:00:04.000
outdoor running 4km

2
00:00:04.000 --> 00:00:07.000
이 영상은 유료광고를 포함하고 있습니다.
"""


def test_drops_paid_ad_cue_keeps_real_subtitle() -> None:
    out, dropped = strip_hallucination_cues(REAL_CASE)
    assert dropped == 1
    assert "유료광고" not in out
    assert "outdoor running 4km" in out


def test_all_boilerplate_yields_empty() -> None:
    srt = """1
00:00:00.000 --> 00:00:03.000
이 동영상은 유료광고를 포함하고 있습니다.
"""
    out, dropped = strip_hallucination_cues(srt)
    assert dropped == 1
    assert out == ""


def test_renumbers_remaining_cues() -> None:
    srt = """1
00:00:00.000 --> 00:00:02.000
구독과 좋아요 부탁드립니다

2
00:00:02.000 --> 00:00:04.000
스쿼트 30개
"""
    out, dropped = strip_hallucination_cues(srt)
    assert dropped == 1
    assert out.startswith("1\n00:00:02.000")


def test_keeps_ordinary_subtitles() -> None:
    """운동 기록 자막이 오탐으로 지워지면 안 된다."""
    srt = """1
00:00:00.000 --> 00:00:03.000
오늘 5km 달렸습니다

2
00:00:03.000 --> 00:00:06.000
어싱 30분 추가
"""
    out, dropped = strip_hallucination_cues(srt)
    assert dropped == 0
    assert "5km" in out and "어싱" in out


def test_whisper_path_also_catches_paid_ad() -> None:
    """Whisper 경로 블랙리스트에도 유료광고 문구가 들어가야 한다."""
    assert _contains_hallucination_phrase("이 영상은 유료광고를 포함하고 있습니다.", "ko")
    assert _contains_hallucination_phrase("This video includes paid promotion.", "en")
