"""발자국 리듬 효과 렌더러 — 업로드 영상 필터 ("발자국").

걷기·계단 영상용: 걸을 때 카메라가 위아래로 흔들리는 주기적 진동이 곧 걸음 리듬이다
(실사용 계단 영상 실측: FFT 지배 주파수 77~95 steps/min — 사람 케이던스 범위와 일치).
그 박자마다 단순화된 신발 발자국을 화면 상단에 좌/우 교대로 찍고 걸음 번호를 새기며,
걸음 수·케이던스·층수는 하단 HUD로 표시한다. 사람/포즈 검출을 쓰지 않아 발이 안 보이거나
풍경만 찍혀도 동작한다.

`cartoon.py`/`muscle_heat.py`와 같은 제약: cv2/numpy 외 앱 의존성을 두지 않는다 —
worker가 `../backend`를 sys.path에 얹어 이 모듈을 단독 import한다(`worker/config.py`).
"""

from __future__ import annotations

import logging
import subprocess

import cv2
import numpy as np

logger = logging.getLogger(__name__)

W_PROC = 320        # 옵티컬 플로우 계산용 다운스케일 폭

# 걸음 검출 (실사용 계단 영상 4개로 튜닝 — FFT 케이던스와 일치 검증)
DETREND_SEC = 0.8   # 이 길이 이동평균을 빼서 저주파(전체 상승) 제거 → 걸음 진동만
STEP_MIN_AMP = 1.2  # 직전 반주기 피크가 이 이상이라야 걸음으로 인정 (px)
STEP_MIN_GAP = 0.28  # 최소 걸음 간격(초) — 4Hz 상한(240spm)으로 과검출 억제

# 층수 (세로 누적 기반 추정 — 기압계 아님)
ALT_GATE = 0.8      # 세로 성분이 이 이상이라야 상승 픽셀로 카운트
PX_PER_FLOOR = 260.0  # 세로 누적 이 만큼마다 1층 (계단 영상 기준 캘리브레이션)

# 발자국 비주얼
FOOT_LIFE = 1.6     # 발자국이 사라지기까지(초)
FOOT_MAX = 10       # 화면에 동시에 남는 최대 개수
FOOT_HEIGHT_FRAC = 0.085  # 발자국 세로 높이 / 화면 높이
FOOT_Y_FRAC = 0.20        # 발자국 세로 위치 / 화면 높이 (화면 상단)
_FOOT_WIDTH_RATIO = 0.5   # 발자국 마스크 가로/세로 비율
_COLOR_NEON = (60, 255, 57)   # 어두운 배경용 형광 그린 (BGR)
_COLOR_INK = (30, 26, 24)     # 밝은 배경용 잉크 블랙
_LUM_THRESHOLD = 115          # 이 미만이면 어두운 배경으로 판정


def _global_translation(prev_gray: np.ndarray, gray: np.ndarray) -> tuple[float, float] | None:
    """prev→cur 전역 이동 벡터 (dx, dy) 픽셀. 실패 시 None.

    LK 스파스 + RANSAC affine의 평행이동 성분 — 카메라(=촬영자)가 움직인 양.
    """
    p0 = cv2.goodFeaturesToTrack(prev_gray, 200, 0.01, 8)
    if p0 is None or len(p0) < 12:
        return None
    p1, status, _ = cv2.calcOpticalFlowPyrLK(
        prev_gray, gray, p0, None, winSize=(21, 21), maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    status = status.reshape(-1).astype(bool)
    src, dst = p0.reshape(-1, 2)[status], p1.reshape(-1, 2)[status]
    if len(src) < 12:
        return None
    affine, _ = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3)
    if affine is None:
        return None
    return float(affine[0, 2]), float(affine[1, 2])


_FOOT_CACHE: dict[tuple[int, bool, int], np.ndarray] = {}


def _make_foot_mask(height_px: int, left: bool, angle_deg: float) -> np.ndarray:
    """단순화된 신발 밑창 모양 알파 마스크(0..1).

    토박스(앞)·허리(중족)·힐(뒤) 타원 3개를 겹쳐 만든 매끈한 신발 밑창 실루엣 —
    맨발 발가락 디테일은 뺐다(작은 화면에서 더 잘 알아보는 단순한 형태). 좌우가 거의
    대칭인 모양이라 left는 육안상 차이가 거의 없고, 실제 좌/우 구분은 호출부가 넘기는
    회전각(angle_deg)이 만든다.
    """
    key = (height_px, left, round(angle_deg))
    if key in _FOOT_CACHE:
        return _FOOT_CACHE[key]
    h = height_px
    w = int(h * _FOOT_WIDTH_RATIO)
    mask = np.zeros((h, w), np.uint8)
    sx, sy = w / 100.0, h / 160.0

    def ell(cx: float, cy: float, ax: float, ay: float) -> None:
        cv2.ellipse(mask, (int(cx * sx), int(cy * sy)),
                    (max(1, int(ax * sx)), max(1, int(ay * sy))), 0, 0, 360, 255, -1)

    ell(50, 32, 30, 30)   # 토박스 — 둥글고 넓게
    ell(50, 84, 22, 36)   # 허리(중족) — 좁게 이어줌
    ell(50, 132, 27, 28)  # 힐 — 둥글게

    if left:
        mask = cv2.flip(mask, 1)
    if angle_deg:
        rot = cv2.getRotationMatrix2D((w // 2, h // 2), -angle_deg, 1.0)
        mask = cv2.warpAffine(mask, rot, (w, h))
    mask = cv2.GaussianBlur(mask, (0, 0), max(1.0, h * 0.012))
    out = mask.astype(np.float32) / 255.0
    _FOOT_CACHE[key] = out
    return out


def _stamp_footprint(
    canvas: np.ndarray, cx: int, cy: int, size: int, angle_deg: float,
    alpha: float, color: tuple[int, int, int], left: bool,
) -> np.ndarray:
    """발자국 1개를 알파 블렌드. size는 발자국 세로 높이(px)."""
    mask = _make_foot_mask(max(12, size), left, angle_deg)
    mh, mw = mask.shape
    x0, y0 = cx - mw // 2, cy - mh // 2
    x1, y1 = x0 + mw, y0 + mh
    ch, cw = canvas.shape[:2]
    mx0, my0 = max(0, -x0), max(0, -y0)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(cw, x1), min(ch, y1)
    if x1 <= x0 or y1 <= y0:
        return canvas
    sub = mask[my0:my0 + (y1 - y0), mx0:mx0 + (x1 - x0)] * alpha
    region = canvas[y0:y1, x0:x1].astype(np.float32)
    col = np.array(color, np.float32)
    canvas[y0:y1, x0:x1] = (region * (1 - sub[..., None]) + col * sub[..., None]).astype(np.uint8)
    return canvas


def _stamp_step_number(
    canvas: np.ndarray, cx: int, cy: int, size: int, step_num: int,
    alpha: float, color: tuple[int, int, int],
) -> np.ndarray:
    """발자국 위에 걸음 번호를 새긴다(발자국과 같은 alpha로 페이드).

    ponytail: 자릿수가 늘어나면(3자리+) 발자국 폭을 넘칠 수 있음 — 실사용 걸음 수 범위(수백
    이하)에선 안 보이는 문제라 폭에 맞춘 자동 축소는 생략.
    """
    text = str(step_num)
    font_scale = max(0.35, size / 70.0)
    thickness = max(1, size // 40)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
    org = (cx - tw // 2, cy + th // 2)
    ov = canvas.copy()
    cv2.putText(ov, text, org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness, cv2.LINE_AA)
    cv2.addWeighted(ov, alpha, canvas, 1 - alpha, 0, canvas)
    return canvas


def _adaptive_color(frame: np.ndarray, cx: int, cy: int, size: int) -> tuple[int, int, int]:
    """찍는 지점 주변 밝기를 샘플해 어두우면 형광, 밝으면 잉크 블랙."""
    h, w = frame.shape[:2]
    y0, y1 = max(0, cy - size // 2), min(h, cy + size // 2)
    x0, x1 = max(0, cx - size // 2), min(w, cx + size // 2)
    patch = frame[y0:y1, x0:x1]
    lum = float(cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY).mean()) if patch.size else 128.0
    return _COLOR_NEON if lum < _LUM_THRESHOLD else _COLOR_INK


def _draw_hud(
    canvas: np.ndarray, steps: int, cadence: float, floor: int, climbing: bool,
) -> np.ndarray:
    """하단 HUD 한 줄: 층수(계단일 때) + 케이던스 + 걸음 수. 콘텐츠를 안 가리게 최소화."""
    h, w = canvas.shape[:2]
    if steps <= 0 and floor <= 1:
        return canvas
    ov = canvas.copy()
    cv2.rectangle(ov, (0, h - 48), (w, h), (12, 14, 22), -1)
    cv2.addWeighted(ov, 0.55, canvas, 0.45, 0, canvas)

    x = 16
    if floor > 1:
        cv2.putText(canvas, "FLOOR", (x, h - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 160, 185), 1, cv2.LINE_AA)
        col = (44, 232, 245) if climbing else (200, 210, 230)
        cv2.putText(canvas, f"{floor}F", (x, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2, cv2.LINE_AA)
        if climbing:
            cv2.putText(canvas, "UP", (x + 44, h - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (44, 232, 245), 1, cv2.LINE_AA)

    # 걸음 수 (우측, 크게) — 리듬 검출 이벤트당 +1 (정직한 추정치)
    txt = f"{steps:,}"
    (tw, _), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.78, 2)
    cv2.putText(canvas, "STEPS", (w - tw - 16, h - 28), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 160, 185), 1, cv2.LINE_AA)
    cv2.putText(canvas, txt, (w - tw - 16, h - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.78, (245, 176, 44), 2, cv2.LINE_AA)
    if cadence > 0:
        ctxt = f"{cadence:.0f} spm"
        (cw2, _), _ = cv2.getTextSize(ctxt, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        cv2.putText(canvas, ctxt, (w - tw - cw2 - 34, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 210, 230), 1, cv2.LINE_AA)
    return canvas


def footsteps_preview_frame(frame: np.ndarray) -> np.ndarray:
    """단일 프레임 미리보기 — 리듬 신호가 없으므로 샘플 발자국 2개(좌/우) + HUD를 정적 합성.

    발자국 색은 실제 로직대로 배경 밝기에 적응한다. 걸음 수는 화면에 보이는 2로 표시(정직).
    """
    out = frame.copy()
    h, w = out.shape[:2]
    size = max(12, int(h * FOOT_HEIGHT_FRAC))
    cy = int(h * FOOT_Y_FRAC)
    for step_num, (side, fx_frac, ang) in enumerate(((True, 0.34, -9), (False, 0.66, 9)), start=1):
        cx = int(w * fx_frac)
        color = _adaptive_color(out, cx, cy, size)
        out = _stamp_footprint(out, cx, cy, size, ang, 0.85, color, side)
        out = _stamp_step_number(out, cx, cy, size, step_num, 0.85, color)
    return _draw_hud(out, steps=2, cadence=0.0, floor=1, climbing=False)


def render_footsteps_video(input_path: str, output_path: str) -> None:
    """영상 전체에 발자국 리듬 효과를 합성한다. 원본 오디오 스트림은 그대로 보존(-c:a copy).

    걸음 검출이 프레임 순차 상태(디트렌드 히스토리·발자국 목록)에 의존하므로 순차 처리 —
    포즈 모델이 없어 muscle_heat보다 훨씬 가볍다.
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {input_path}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    out_w, out_h = w - w % 2, h - h % 2  # yuv420p는 짝수 해상도 필요
    if out_w < 2 or out_h < 2:
        cap.release()
        raise ValueError(f"video too small: {w}x{h}")
    ph = max(2, int(round(W_PROC * out_h / out_w)))

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{out_w}x{out_h}",
        "-r", f"{fps:.6f}", "-i", "-",
        "-i", input_path,
        "-map", "0:v", "-map", "1:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    proc = subprocess.Popen(
        ffmpeg_cmd, stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None

    rng = np.random.default_rng(7)  # 지터 재현성 (같은 입력 → 같은 출력)
    detrend_n = max(3, int(fps * DETREND_SEC) | 1)
    dy_hist: list[float] = []
    prev_gray: np.ndarray | None = None
    alt_px = 0.0
    prev_osc = 0.0
    half_peak = 0.0
    last_step_t = -10.0
    step_times: list[float] = []
    # (t, x, y, size, angle, is_left, color, step_num)
    feet: list[tuple[float, int, int, int, float, bool, tuple[int, int, int], int]] = []
    side = 0
    step_count = 0
    processed = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if (frame.shape[1], frame.shape[0]) != (out_w, out_h):
                frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
            t_now = processed / fps
            small = cv2.resize(frame, (W_PROC, ph), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            climbing = False
            if prev_gray is not None:
                tr = _global_translation(prev_gray, gray)
                dy = tr[1] if tr else 0.0
                dy_hist.append(dy)
                if len(dy_hist) > detrend_n:
                    dy_hist.pop(0)
                osc = dy - float(np.mean(dy_hist))  # 걸음 진동 성분

                # 걸음 = 진동의 하강 제로크로싱. 진폭은 직전 양(+) 반주기의 피크로 판정
                # (크로싱 시점엔 osc≈0이라 시점값으로 보면 놓친다 — 실측으로 확인된 버그).
                if osc > 0:
                    half_peak = max(half_peak, osc)
                if (prev_osc > 0 >= osc
                        and half_peak > STEP_MIN_AMP
                        and t_now - last_step_t > STEP_MIN_GAP):
                    half_peak = 0.0
                    last_step_t = t_now
                    step_times.append(t_now)
                    step_count += 1
                    side ^= 1
                    fx = int(out_w * (0.34 if side else 0.66) + rng.uniform(-0.03, 0.03) * out_w)
                    fy = int(out_h * (FOOT_Y_FRAC + rng.uniform(-0.04, 0.04)))
                    fsize = max(12, int(out_h * FOOT_HEIGHT_FRAC))
                    fang = -9 if side else 9
                    fcol = _adaptive_color(frame, fx, fy, fsize)
                    feet.append((t_now, fx, fy, fsize, fang, bool(side), fcol, step_count))
                    if len(feet) > FOOT_MAX:
                        feet.pop(0)
                prev_osc = osc

                rise = max(0.0, dy - ALT_GATE)
                if rise > 0:
                    alt_px += rise
                    climbing = True
            prev_gray = gray

            for (ft, fx, fy, fsz, fang, is_left, fcol, fstep) in feet:
                age = t_now - ft
                if age > FOOT_LIFE:
                    continue
                alpha = max(0.0, 1.0 - age / FOOT_LIFE) * 0.85
                pop = 1.0 + 0.30 * max(0.0, 1.0 - age / 0.18)  # 찍히는 순간 살짝 커짐
                frame = _stamp_footprint(frame, fx, fy, int(fsz * pop), fang, alpha, fcol, is_left)
                frame = _stamp_step_number(frame, fx, fy, fsz, fstep, alpha, fcol)
            feet = [f for f in feet if t_now - f[0] <= FOOT_LIFE]

            step_times = [s for s in step_times if t_now - s <= 4.0]
            cadence = len(step_times) / 4.0 * 60 if len(step_times) >= 2 else 0.0
            floor = 1 + int(alt_px / PX_PER_FLOOR)
            frame = _draw_hud(frame, step_count, cadence, floor, climbing)

            proc.stdin.write(frame.tobytes())
            processed += 1
    finally:
        cap.release()
        proc.stdin.close()
        stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        code = proc.wait()

    if code != 0:
        raise RuntimeError(f"ffmpeg encode failed (exit {code}): {stderr[-500:]}")
    if processed == 0:
        raise ValueError("no frames decoded from input video")
    logger.info(
        "render_footsteps_video: %d frames, %d steps, floor=%d → %s",
        processed, step_count, 1 + int(alt_px / PX_PER_FLOOR), output_path,
    )
