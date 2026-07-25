"""운동 종목 분류 — 업로드 영상에서 프레임 몇 장을 뽑아 Gemini로 종목을 판별한다.

`muscle_heat.py`의 근육군 프리셋(`preset_for_exercise`)에 넘길 종목 문자열을 만든다.
영상당 1회 호출(프레임 3장, gemini-3.5-flash-lite) — 실측 ~1.6원/영상.

`muscle_heat.py`와 같은 제약: cv2/httpx 외 앱 의존성을 두지 않는다 — worker가
`../backend`를 sys.path에 얹어 이 모듈을 단독 import한다(`worker/config.py`).
API 키(GEMINI_API_KEY)는 os.environ에서 직접 읽는다. 키가 없거나 호출이 실패하면
None을 반환해, 호출측이 프리셋 없이(exercise=None) 그대로 진행하게 한다 — 절대 크래시하지 않는다.
"""

from __future__ import annotations

import base64
import json
import logging
import os

import cv2
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


def _sample_frames_jpeg(path: str) -> list[bytes]:
    """영상 길이의 _SAMPLE_FRACTIONS 지점에서 프레임을 뽑아 JPEG 바이트로 반환한다.

    cv2는 이미 이 서비스 레이어의 의존성이라 ffprobe/ffmpeg 프로세스를 띄우지 않는다
    (파일 핸들 1개로 duration·프레임·인코딩까지 처리).
    """
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return []
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            return []
        out: list[bytes] = []
        for frac in _SAMPLE_FRACTIONS:
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(total - 1, int(total * frac)))
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            if w > _FRAME_WIDTH:
                frame = cv2.resize(
                    frame, (_FRAME_WIDTH, max(1, round(h * _FRAME_WIDTH / w))),
                    interpolation=cv2.INTER_AREA,
                )
            enc, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if enc:
                out.append(buf.tobytes())
        return out
    finally:
        cap.release()


def classify_exercise(video_path: str, api_key: str | None = None) -> str | None:
    """로컬 영상에서 운동 종목명을 판별한다. 실패/키없음/미검출이면 None.

    반환값은 그대로 `muscle_heat.render_heat_video(exercise=...)`에 넘길 수 있다
    (`preset_for_exercise`가 부분 일치로 프리셋을 고른다).
    """
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        logger.info("classify_exercise: GEMINI_API_KEY not set — skipping (exercise=None)")
        return None

    frames = _sample_frames_jpeg(video_path)
    if not frames:  # 열기 실패 / 프레임을 하나도 못 뽑음
        return None

    parts: list[dict] = [{"text": _PROMPT}]
    parts += [
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(j).decode()}}
        for j in frames
    ]

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
