"""운동 종목 분류 — 업로드 영상에서 프레임 몇 장을 뽑아 Gemini로 종목을 판별한다.

`muscle_heat.py`의 근육군 프리셋(`preset_for_exercise`)에 넘길 종목 문자열을 만든다.
영상당 1회 호출(프레임 3장, gemini-3.5-flash-lite) — 실측 ~1.6원/영상.

`muscle_heat.py`와 같은 제약: cv2/httpx 외 앱 의존성을 두지 않는다 — worker가
`../backend`를 sys.path에 얹어 이 모듈을 단독 import한다(`worker/config.py`).
API 키(GEMINI_API_KEY)는 os.environ에서 직접 읽는다. 키가 없거나 호출이 실패하면
None을 반환해, 호출측이 프리셋 없이(exercise=None) 그대로 진행하게 한다 — 절대 크래시하지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess

import httpx

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.5-flash-lite"  # 이미지 입력 최저가권 (docs 확인: $0.30/M in, $2.50/M out)
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_TIMEOUT = 30.0
_SAMPLE_FRACTIONS = (0.3, 0.5, 0.7)  # 영상 길이 대비 프레임 추출 지점
_FRAME_WIDTH = 320  # 분류엔 이 해상도로 충분 (토큰 절약)

_PROMPT = (
    "These are frames sampled from one workout video. Identify the exercise being "
    "performed. Reply ONLY with JSON: {\"exercise\": \"<short english exercise name, "
    "e.g. squat, push-up, pull-up, bicep curl, jump rope>\"}. If no clear exercise or "
    "no person is visible, use \"exercise\": \"unknown\"."
)


def _probe_duration(path: str) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return float(out.stdout.strip())
    except (subprocess.SubprocessError, ValueError):
        return None


def _extract_frame_jpeg(path: str, ts: float) -> bytes | None:
    try:
        out = subprocess.run(
            ["ffmpeg", "-v", "error", "-ss", f"{ts:.3f}", "-i", path,
             "-vf", f"scale={_FRAME_WIDTH}:-2", "-frames:v", "1",
             "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
            capture_output=True, timeout=20, check=True,
        )
        return out.stdout or None
    except subprocess.SubprocessError:
        return None


def classify_exercise(video_path: str, api_key: str | None = None) -> str | None:
    """로컬 영상에서 운동 종목명을 판별한다. 실패/키없음/미검출이면 None.

    반환값은 그대로 `muscle_heat.render_heat_video(exercise=...)`에 넘길 수 있다
    (`preset_for_exercise`가 부분 일치로 프리셋을 고른다).
    """
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        logger.info("classify_exercise: GEMINI_API_KEY not set — skipping (exercise=None)")
        return None

    dur = _probe_duration(video_path)
    if dur is None or dur <= 0:
        return None

    import base64

    parts: list[dict] = [{"text": _PROMPT}]
    for frac in _SAMPLE_FRACTIONS:
        jpeg = _extract_frame_jpeg(video_path, dur * frac)
        if jpeg:
            parts.append({"inline_data": {"mime_type": "image/jpeg",
                                          "data": base64.b64encode(jpeg).decode()}})
    if len(parts) == 1:  # 프레임을 하나도 못 뽑음
        return None

    body = {"contents": [{"parts": parts}],
            "generationConfig": {"response_mime_type": "application/json"}}
    url = _ENDPOINT.format(model=_MODEL)
    try:
        resp = httpx.post(url, params={"key": key}, json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        exercise = json.loads(text).get("exercise", "").strip()
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
        logger.warning("classify_exercise failed (exercise=None): %s", e)
        return None

    if not exercise or exercise.lower() == "unknown":
        return None
    logger.info("classify_exercise: %s → '%s'", os.path.basename(video_path), exercise)
    return exercise
