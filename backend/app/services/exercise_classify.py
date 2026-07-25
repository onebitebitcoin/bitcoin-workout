"""운동 종목 분류 — 업로드 영상에서 프레임 몇 장을 뽑아 Gemini에게 근육군을 직접 고르게 한다.

Gemini에게 자유 텍스트 운동명이 아니라 `muscle_heat.PRESETS`의 키 중 하나를 그대로
고르게 한다(구조화 선택지) — "bench press"를 "press" 키워드로 오분류하는 식의 부분일치
버그를 프롬프트 계약으로 원천 차단한다. 응답도 PRESETS 키에 없으면 무조건 None.
영상당 1회 호출(프레임 3장, gemini-3.5-flash-lite) — 실측 ~1.6원/영상.

`muscle_heat.py`와 같은 제약: cv2/httpx 외 앱 의존성을 두지 않는다 — worker가
`../backend`를 sys.path에 얹어 이 모듈을 단독 import한다(`worker/config.py`).
PRESETS 키 목록만 `muscle_heat`에서 지연 임포트한다(무거운 mediapipe를 모듈 로드 시점에
물지 않기 위해 함수 안에서 임포트).
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

_PROMPT_TEMPLATE = (
    "These are frames sampled from one workout video. Identify which muscle group this "
    "exercise primarily targets. Reply ONLY with JSON: "
    '{{"muscle_group": "<one of: {groups}>"}}. If no clear exercise, no person is visible, '
    'or it does not clearly fit one of those groups, use "muscle_group": "unknown".'
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
    """로컬 영상에서 근육군을 판별한다. 실패/키없음/미검출/모르는 그룹이면 None.

    반환값은 `muscle_heat.PRESETS`의 키(arms/legs/back/chest/core/fullbody) 중 하나이거나
    None이며, 그대로 `muscle_heat.render_heat_video(exercise=...)`에 넘길 수 있다.
    """
    from app.services.muscle_heat import PRESETS

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        logger.info("classify_exercise: GEMINI_API_KEY not set — skipping (muscle_group=None)")
        return None

    frames = _sample_frames_jpeg(video_path)
    if not frames:  # 열기 실패 / 프레임을 하나도 못 뽑음
        return None

    prompt = _PROMPT_TEMPLATE.format(groups=", ".join(sorted(PRESETS)))
    parts: list[dict] = [{"text": prompt}]
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
        group = json.loads(text).get("muscle_group", "").strip().lower()
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError) as e:
        logger.warning("classify_exercise failed (muscle_group=None): %s", e)
        return None

    if group not in PRESETS:  # "unknown"이나 환각 응답도 여기서 걸러짐
        return None
    logger.info("classify_exercise: %s → '%s'", os.path.basename(video_path), group)
    return group
