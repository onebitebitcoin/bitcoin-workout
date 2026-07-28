"""포즈 기반 근육 히트맵 렌더러 — 업로드 영상 필터 ("운동열 강조").

실사 운동 영상(프레스·딥스·바이크·풀업·줄넘기) 12라운드 튜닝으로 검증된 알고리즘.
관절 "이동 속도"가 아니라 "각속도"로 부하를 판단해, 딥스처럼 몸 전체가 오르내리는
운동에서도 실려가는 몸통이 아니라 실제로 굽혀지는 관절(팔꿈치 등)만 달아오른다.
기물(원판·손잡이)·배경·얼굴은 세그멘테이션 마스크와 얼굴 제외 마스크로 차단한다.

`cartoon.py`와 같은 제약: cv2/numpy/mediapipe 외 앱 의존성을 두지 않는다 —
worker가 `../backend`를 sys.path에 얹어 이 모듈을 단독 import한다(`worker/config.py`).
"""

from __future__ import annotations

import logging
import multiprocessing
import os
import subprocess
import tempfile
import threading

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

logger = logging.getLogger(__name__)

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "pose_landmarker_full.task")

PW = 360     # 히트맵 그리드 폭 — 캡슐/블러/오버레이 연산용 (합성 시 원본 해상도로 업샘플)
DET_W = 480  # 포즈 검출 입력 폭 — 그리드와 분리 (랜드마크는 정규화 좌표라 어느 그리드로든 매핑 가능).
             # 프로덕션 영상 스윕에서 근접/누운 자세 검출률이 480에서 최대 (360: 실패, 640: 오히려 하락)
_CONF = 0.35  # 검출/존재 신뢰도 — 기본 0.5에서는 근접 크롭(상체 일부만)을 못 잡는다.
              # 사람 없는 영상의 오탐 증가는 EMA 수렴 지연 + 세그 마스크 컷이 억제 (실측 검증)

# 회전 폴백: BlazePose 1단계 검출기는 서 있는 자세 위주라 플랭크/푸쉬업(수평 자세)을 놓친다.
# 성공한 회전을 기억(sticky)하고, 실패가 이어질 때만 다른 회전을 주기적으로 프로브한다.
_ROTS: list[int | None] = [None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_180]
_PROBE_INTERVAL = 5  # 연속 실패 시 N프레임마다만 전체 회전 프로브 (사람 없는 영상 비용 억제)
_STREAK_GATE = 12    # 연속 K프레임 검출돼야 열 활성화 — conf 0.35의 산발적 오탐(기구·야경에
                     # 유령 열) 차단. 실측: 오탐 연속길이 중앙값 1~12 vs 진짜 사람 98~605.
                     # 진짜 영상은 시작 ~0.4초만 지연되는데 EMA 수렴 시간과 겹쳐 체감 없음.
_GAP_TOLERANCE = 2   # 이 이하의 짧은 검출 끊김은 streak 유지 — 트래킹 순간 놓침(1~2프레임)으로
                     # 게이트가 재대기하는 것 방지. 오탐(x281)의 끊김 간격은 3~4프레임이라 안 살아남음.

POSE_STRIDE = 2  # 비디오 렌더 루프(_render_heat_segment/_render_heat_sequential)에서 격프레임마다만
                 # mediapipe 포즈 추론을 실행 — 나머지 프레임은 마지막 근육 캔버스를 그대로 유지(freeze)
                 # 해 렌더한다(`_RenderState.step(..., hold=True)`). heat/cartoon_heat의 지배적 비용이
                 # 포즈 추론이라 실측 확인 후 도입(성능 리포트 P6).
                 #
                 # 위 _STREAK_GATE/_GAP_TOLERANCE/_PROBE_INTERVAL은 전부 "비디오 프레임" 단위 상수다.
                 # _PoseTracker는 스트릭을 시도 횟수가 아니라 `frame_gap` 누적(=비디오 프레임 수)으로
                 # 세므로 stride가 몇이든 이 상수들을 그대로 쓴다 — stride로 나눈 파생 상수를 두면
                 # ① 정수 나눗셈 손실로 게이트가 조용히 어긋나고(예: stride=5면 12//5=2 → 실제 10프레임)
                 # ② _PROBE_INTERVAL처럼 나누는 걸 잊은 상수만 wall-clock 기준 stride배 느려진다.

# 관절 각도 정의: 이름 -> (A, 꼭짓점, B). 각도 = ∠A-꼭짓점-B (MediaPipe Pose 33 랜드마크 인덱스)
ANGLES: dict[str, tuple[int, int, int]] = {
    "elbowL": (11, 13, 15), "elbowR": (12, 14, 16),
    "shoL": (13, 11, 23), "shoR": (14, 12, 24),
    "hipL": (11, 23, 25), "hipR": (12, 24, 26),
    "kneeL": (23, 25, 27), "kneeR": (24, 26, 28),
}

# 근육 캡슐: (이름, a관절, b관절, 반지름/torso, 각도 드라이버, 게인, 이동속도 보조 관절)
# 기본은 "관절이 굽혀지는 각속도" = 실제로 일하는 근육.
# 팔 계열만 이동속도 보조(에어바이크처럼 편 팔로 미는 동작). 몸통/하체는 각속도 전용(딥스 오탐 방지).
CAPS: list[tuple[str, int, int, float, list[str], float, list[int] | None]] = [
    ("uarmL", 11, 13, 0.15, ["elbowL", "shoL"], 1.0, [13, 15]),
    ("uarmR", 12, 14, 0.15, ["elbowR", "shoR"], 1.0, [14, 16]),
    ("farmL", 13, 15, 0.12, ["elbowL"], 0.9, [15]),
    ("farmR", 14, 16, 0.12, ["elbowR"], 0.9, [16]),
    ("deltL", 11, 11, 0.15, ["shoL"], 1.0, [13]),
    ("deltR", 12, 12, 0.15, ["shoR"], 1.0, [14]),
    ("thighL", 23, 25, 0.20, ["kneeL", "hipL"], 1.0, None),
    ("thighR", 24, 26, 0.20, ["kneeR", "hipR"], 1.0, None),
    ("calfL", 25, 27, 0.13, ["kneeL"], 0.6, None),
    ("calfR", 26, 28, 0.13, ["kneeR"], 0.6, None),
    ("gluteL", 23, 23, 0.12, ["hipL"], 0.9, None),
    ("gluteR", 24, 24, 0.12, ["hipR"], 0.9, None),
]
CORE_ANGLES = ["hipL", "hipR"]  # 코어 = 몸통 굽힘(힙 각도) 변화만. 단순 이동은 무시

# 근육군 프리셋 — Gemini가 영상을 보고 이 딕셔너리의 키 중 하나를 직접 골라주면(`exercise_classify.py`)
# "이 근육군만" 게인을 살리고 나머지는 강하게 감쇠(_PRESET_SUPPRESS)한다. 각속도 휴리스틱만으론
# 스미스 스쿼트에서 팔 캡슐이 1.0으로 오발화하는 등 부위 오귀속이 큰데(측정 실증), 근육군을 알면
# 이걸 원천 차단할 수 있다. 값은 캡슐 접두사(uarm/farm/delt/thigh/calf/glute/core) 집합.
# 키(arms/legs/.../fullbody) 자체가 Gemini 프롬프트에 노출되는 계약이므로 이름 변경 시 프롬프트도 같이 바꿔야 한다.
# None이면 전 캡슐 균등(기존 동작).
MUSCLE_GROUPS = ("uarm", "farm", "delt", "thigh", "calf", "glute", "core")
_PRESET_SUPPRESS = 0.12  # 프리셋에 없는 근육군의 게인 배율 (0=완전차단, 1=억제없음).
                         # off-target(엉뚱한 근육) 열을 실측 30~46% → 1~8%로 낮춤.
PRESETS: dict[str, set[str]] = {
    "arms":      {"uarm", "farm", "delt"},          # 컬·프레스류
    "legs":      {"thigh", "calf", "glute", "core"}, # 스쿼트·런지·레그
    "back":      {"uarm", "delt", "core"},           # 풀업·로우 (광배 캡슐 없어 이두·어깨로 근사)
    "chest":     {"uarm", "delt", "core"},           # 푸쉬업·벤치 (가슴 캡슐 없어 삼두·어깨로 근사)
    "core":      {"core"},                           # 플랭크·싯업·크런치 — 팔다리 오발화 억제가 핵심
    "fullbody":  set(MUSCLE_GROUPS),                 # 줄넘기·버피 등 복합
}


def preset_for_exercise(muscle_group: str | None) -> set[str] | None:
    """Gemini가 고른 근육군(PRESETS 키) → 캡슐 프리셋. 매칭 없으면 None(전 캡슐 균등).

    Gemini가 운동명이 아니라 이 PRESETS 키 중 하나를 직접 고르므로(`exercise_classify.py`
    참고) 여기선 그대로 조회만 한다 — 부분일치/키워드 순서 문제가 구조적으로 없다.
    """
    if not muscle_group:
        return None
    return PRESETS.get(muscle_group.strip().lower())


K_ANG = 0.030       # 각속도(rad/frame) -> effort=1 스케일 (~1.7도/frame)
DB_ANG = 0.006       # 각도 지터 데드밴드 (팔)
DB_ANG_LOW = 0.010   # 하체/코어 데드밴드 (지터 얼룩 방지)
K_LIN = 0.045        # 이동속도 보조 스케일 (torso 길이 단위/frame)
DB_LIN = 0.012
VIS_MIN = 0.5
DECAY, ALPHA = 0.90, 0.65  # 히트 잔열 감쇠, 순간 부하 반영률


def _make_landmarker(running_mode: vision.RunningMode) -> vision.PoseLandmarker:
    options = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=_MODEL_PATH),
        running_mode=running_mode,
        min_pose_detection_confidence=_CONF,
        min_pose_presence_confidence=_CONF,
        output_segmentation_masks=True,
    )
    return vision.PoseLandmarker.create_from_options(options)


def _unrotate_norm(u: float, v: float, rot_idx: int) -> tuple[float, float]:
    """회전된 검출 이미지의 정규화 좌표 (u,v) → 원래(비회전) 프레임 정규화 좌표."""
    if rot_idx == 1:   # 검출 입력이 90CW 회전 → 원좌표 (u, v) = (v', 1-u')
        return v, 1.0 - u
    if rot_idx == 2:   # 90CCW
        return 1.0 - v, u
    if rot_idx == 3:   # 180
        return 1.0 - u, 1.0 - v
    return u, v


class _PoseTracker:
    """회전 폴백이 있는 포즈 검출기. 성공한 회전을 기억(sticky)하고 프레임 간 재사용한다.

    반환 좌표·세그 마스크는 항상 비회전 기준으로 역매핑돼 있어, 호출측(히트 그리드)은
    회전을 몰라도 된다.

    landmarker는 회전 계열별로 분리한다 — 0°/180°(원본 치수)와 90°양방향(치수 뒤집힘).
    VIDEO 모드 landmarker 하나에 치수가 다른 프레임을 섞어 넣으면 내부 그래프 버퍼가
    오염돼 세그 마스크 numpy_view()가 C++ FATAL(ChannelSize 1 vs 4)로 죽는다(실측) —
    파이썬에서 잡을 수 없어 구조적으로 차단해야 한다. 90° 계열은 지연 생성이라
    회전이 필요 없는 일반 영상에서는 추가 비용이 없다.
    """

    def __init__(self, video_mode: bool) -> None:
        self._video_mode = video_mode
        self._lmks: dict[str, vision.PoseLandmarker] = {}
        self._ts: dict[str, int] = {"land": 0, "port": 0}
        self._rot = 0          # _ROTS 인덱스
        # 아래 세 카운터는 전부 "비디오 프레임 수" 단위다(process()의 frame_gap을 누적) —
        # POSE_STRIDE로 추론을 건너뛰어도 게이트 상수들의 wall-clock 의미가 보존된다.
        self._fail_streak = 0
        self._det_streak = 0            # 연속 검출 프레임 수 — _STREAK_GATE 도달 전에는 열 비활성
        self._frames_since_probe = 0    # 마지막 회전 프로브 이후 경과 — _PROBE_INTERVAL 주기 판정용

    @staticmethod
    def _family(rot_idx: int) -> str:
        return "port" if rot_idx in (1, 2) else "land"

    def _detect(self, det_bgr: np.ndarray, rot_idx: int, frame_gap: int = 1) -> vision.PoseLandmarkerResult:
        fam = self._family(rot_idx)
        if fam not in self._lmks:
            self._lmks[fam] = _make_landmarker(
                vision.RunningMode.VIDEO if self._video_mode else vision.RunningMode.IMAGE
            )
        code = _ROTS[rot_idx]
        img = det_bgr if code is None else cv2.rotate(det_bgr, code)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if self._video_mode:
            # frame_gap: 이번 호출이 직전 호출로부터 몇 비디오 프레임 지났는지(POSE_STRIDE로
            # 건너뛴 프레임 포함) — VIDEO 모드는 타임스탬프 단조증가만 요구하므로 실제 경과
            # 시간을 근사해 넘겨준다(정확한 모니터링용, 하류 로직은 타임스탬프를 읽지 않음).
            self._ts[fam] += 33 * frame_gap
            return self._lmks[fam].detect_for_video(mp_image, self._ts[fam])
        return self._lmks[fam].detect(mp_image)

    @staticmethod
    def _extract(
        result: vision.PoseLandmarkerResult, rot_used: int, grid_w: int, grid_h: int,
    ) -> tuple[dict[int, tuple[float, float]], dict[int, float], np.ndarray | None]:
        """검출 직후 즉시 호출 — 다음 detect가 내부 버퍼를 재사용하기 전에 복사해 둔다."""
        landmarks = result.pose_landmarks[0]
        pts: dict[int, tuple[float, float]] = {}
        vis: dict[int, float] = {}
        for i in range(33):
            u, v = _unrotate_norm(landmarks[i].x, landmarks[i].y, rot_used)
            pts[i] = (u * grid_w, v * grid_h)
            vis[i] = landmarks[i].visibility
        seg = None
        # 회전 검출(rot != 0)의 세그 마스크는 읽지 않는다 — mediapipe 0.10.35에서
        # 치수가 뒤집힌 입력의 마스크에 numpy_view()를 호출하면 C++ FATAL(ChannelSize
        # 1 vs 4)로 프로세스가 죽는다(실측: rot=0 마스크 수백 회는 안전, rot=2에서 즉사).
        # 파이썬 쪽 channels 메타데이터는 1로 거짓 보고하므로 사전 감지도 불가능 —
        # 회전 프레임은 세그 컷 없이 진행한다(캡슐+얼굴 마스크는 유지, 품질만 소폭 저하).
        if rot_used == 0 and result.segmentation_masks:
            seg = np.array(result.segmentation_masks[0].numpy_view(), copy=True)
            if seg.ndim == 3:
                seg = seg[..., 0]
            seg = cv2.resize(seg, (grid_w, grid_h))
        return pts, vis, seg

    def process(
        self, det_bgr: np.ndarray, grid_w: int, grid_h: int, frame_gap: int = 1,
    ) -> tuple[dict[int, tuple[float, float]], dict[int, float], np.ndarray | None] | None:
        """검출 입력(det_bgr, DET_W 폭)에서 포즈를 찾아 (그리드 좌표 pts, vis, 세그) 반환. 실패 시 None.

        frame_gap: 이번 호출이 직전 호출로부터 몇 비디오 프레임 지났는지(POSE_STRIDE로 건너뛴
        프레임 포함). 스트릭 카운터를 1이 아니라 이 값만큼 올려 `_STREAK_GATE`/`_GAP_TOLERANCE`/
        `_PROBE_INTERVAL`을 원래의 비디오 프레임 단위로 그대로 쓴다.

        한계: stride>1이면 건너뛴 프레임의 검출 여부를 알 수 없으므로, 실패 1회를 stride
        프레임 끊김으로 간주한다(보수적 근사). 3프레임 끊김이 샘플링 위상에 따라 2회로도
        1회로도 관측될 수 있어 _GAP_TOLERANCE 경계 부근은 여전히 위상에 따라 갈린다 —
        stride 샘플링의 구조적 한계라 관용도를 0으로 낮추지 않는 한 완전히 없앨 수 없고,
        그렇게 하면 원래 방지하려던 "순간 놓침에 게이트 재대기"가 되살아난다.
        """
        result = self._detect(det_bgr, self._rot, frame_gap)
        if not result.pose_landmarks:
            first_fail = self._fail_streak == 0
            self._fail_streak += frame_gap
            self._frames_since_probe += frame_gap
            # 프로브 스로틀: 첫 실패와 이후 _PROBE_INTERVAL 프레임마다만 나머지 회전 시도
            if first_fail or self._frames_since_probe >= _PROBE_INTERVAL:
                self._frames_since_probe = 0
                for k in range(len(_ROTS)):
                    if k == self._rot:
                        continue
                    probe = self._detect(det_bgr, k, frame_gap)
                    if probe.pose_landmarks:
                        self._rot = k
                        result = probe
                        break
        if not result.pose_landmarks:
            # 짧은 끊김(_GAP_TOLERANCE 프레임 이하)은 streak 유지 — 프로브 복구·순간 놓침으로
            # 게이트가 재대기하지 않게 한다. 최종 실패가 길어질 때만 리셋.
            if self._fail_streak > _GAP_TOLERANCE:
                self._det_streak = 0
            return None

        self._fail_streak = 0
        self._frames_since_probe = 0
        self._det_streak += frame_gap
        # 시간적 일관성 게이트 — 산발적 오탐 차단. 프리뷰(IMAGE 모드, 단일 프레임)는 예외.
        if self._video_mode and self._det_streak < _STREAK_GATE:
            return None
        return self._extract(result, self._rot, grid_w, grid_h)

    def close(self) -> None:
        for lmk in self._lmks.values():
            lmk.close()
        self._lmks.clear()


def _global_affine(prev_gray: np.ndarray | None, gray: np.ndarray) -> np.ndarray | None:
    """카메라 전역 움직임 추정(스파스 LK + RANSAC). 실패하거나 이전 프레임이 없으면 None.

    핸드헬드 촬영에서 배경이 아니라 실제 관절 이동만 남기기 위한 보정 —
    나머지 로직 대부분(각속도)은 이 보정 없이도 카메라 흔들림에 불변이지만,
    팔 캡슐의 이동속도 보조 항목(`CAPS`의 마지막 필드)에는 필요하다.
    """
    if prev_gray is None:
        return None
    p0 = cv2.goodFeaturesToTrack(prev_gray, 300, 0.01, 8)
    if p0 is None or len(p0) < 12:
        return None
    p1, status, _ = cv2.calcOpticalFlowPyrLK(
        prev_gray, gray, p0, None, winSize=(21, 21), maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    mask = status.reshape(-1).astype(bool)
    src, dst = p0.reshape(-1, 2)[mask], p1.reshape(-1, 2)[mask]
    if len(src) < 12:
        return None
    affine, _inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3)
    return affine


def _alpha_lut(gain: float, lo: float) -> np.ndarray:
    """0..255 양자화 히트값 -> 0..255 알파. lo 이하 저강도는 0(투명)."""
    v = np.arange(256, dtype=np.float32) / 255.0
    trimmed = np.clip((v - lo) / (1 - lo), 0, 1)
    return np.clip(trimmed**0.85 * gain * 255, 0, 255).astype(np.uint8)


def _overlay(base_bgr: np.ndarray, heat01: np.ndarray, gain: float = 1.4, lo: float = 0.12) -> np.ndarray:
    """base 위에 히트맵을 알파 블렌드. lo 이하 저강도는 투명(원본 노출) → 핫스팟만 선명.

    heat01은 base보다 작은 그리드 해상도로 들어온다(호출부가 업샘플하지 않는다) — 컬러맵
    (applyColorMap)과 알파 곡선(pow)을 그리드 픽셀 수에서 LUT로 계산한 뒤 base 해상도로
    업샘플한다. heat는 이미 3중 EMA로 스무딩된 값이라 그리드 해상도로 계산해도 육안 차이가
    없다(실측 ~10x, cartoon.py의 LUT+정수블렌드와 동일 논리).
    """
    h, w = base_bgr.shape[:2]
    u8 = np.clip(heat01 * 255, 0, 255).astype(np.uint8)
    thermal = cv2.applyColorMap(u8, cv2.COLORMAP_INFERNO)
    alpha = cv2.LUT(u8, _alpha_lut(gain, lo))
    if u8.shape != (h, w):
        thermal = cv2.resize(thermal, (w, h), interpolation=cv2.INTER_LINEAR)
        alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
    alpha3 = cv2.merge((alpha, alpha, alpha)).astype(np.uint16)
    out = (base_bgr.astype(np.uint16) * (255 - alpha3) + thermal.astype(np.uint16) * alpha3) // 255
    return out.astype(np.uint8)


def light_cartoonize(frame: np.ndarray) -> np.ndarray:
    """약한 카툰화: bilateral 평탄화 + 색 양자화(8단계) + 얇은 윤곽선.

    `cartoon.py`의 `cartoon_frame`(감마/CLAHE/NlMeans 포함, 카툰 필터 단독용)보다 가볍다.
    질감·음영을 지워 신원 식별성을 낮추면서 동작 윤곽은 유지 — "카툰+운동열" 조합 전용 베이스.
    """
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (max(2, w // 2), max(2, h // 2)))
    for _ in range(2):
        small = cv2.bilateralFilter(small, 9, 75, 75)
    flat = cv2.resize(small, (w, h))
    quantized = (flat // 32) * 32 + 16

    # medianBlur는 ksize<=5까지만 OpenCV SIMD 경로를 타고 7부터 일반 히스토그램 구현으로
    # 떨어진다 — 1080x1920 단일스레드 실측 k5 2.1ms vs k7 49.3ms(23배)로, k7은 이 함수
    # 전체(90ms)의 55%를 혼자 먹었다. 이 블러는 adaptiveThreshold 입력 전처리(스펙클 억제)
    # 전용이고 최종 색·질감은 아래 quantized(bilateral+양자화)에서 나오므로 익명화 강도와
    # 무관하다. 실사 프레임 A/B: 엣지 마스크 불일치 2.0%, 최종 출력 픽셀 diff 0.15% —
    # 오히려 k7에서 뭉개지던 작은 글자 윤곽이 살아난다.
    gray = cv2.medianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 5)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 11, 5)
    edges = cv2.medianBlur(edges, 3)  # 점 스펙클 제거

    out = quantized.astype(np.float32)
    out[edges == 0] *= 0.68  # 윤곽선은 은은하게
    return out.astype(np.uint8)


def _joint_angle(pts: dict[int, tuple[float, float]], vis: dict[int, float], name: str) -> float | None:
    a, b, c = ANGLES[name]
    if any(vis.get(i, 0) < VIS_MIN for i in (a, b, c)):
        return None
    v1 = np.array(pts[a]) - np.array(pts[b])
    v2 = np.array(pts[c]) - np.array(pts[b])
    cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
    return float(np.arccos(np.clip(cos, -1, 1)))


def _joint_speed(
    pts: dict[int, tuple[float, float]],
    prev_pts: dict[int, tuple[float, float]] | None,
    vis: dict[int, float],
    joint: int,
    torso: float,
    affine: np.ndarray | None,
) -> float:
    """카메라 보정 관절 이동속도 (torso 길이 단위/frame). 팔 캡슐 보조 신호용.

    # ponytail: affine은 항상 "직전 비디오 프레임 1개" 기준 카메라 이동이다. POSE_STRIDE>1로
    # prev_pts가 여러 프레임 전 값일 때도 단일 프레임 affine으로만 보정하므로 카메라가 흔들리는
    # 구간에서 보정이 근소하게 과소해질 수 있다 — 이 신호는 팔 캡슐의 0.7 가중 보조항일 뿐이고
    # 주 신호(각속도)는 애초에 카메라 흔들림에 불변이라 체감 영향은 낮다. 완전히 없애려면
    # stride개 프레임의 affine을 누적 합성해야 하는데, 그 정도까지는 필요하지 않다고 판단.
    """
    if prev_pts is None or joint not in prev_pts or vis.get(joint, 0) < VIS_MIN:
        return 0.0
    px, py = prev_pts[joint]
    if affine is not None:
        wx = affine[0, 0] * px + affine[0, 1] * py + affine[0, 2]
        wy = affine[1, 0] * px + affine[1, 1] * py + affine[1, 2]
    else:
        wx, wy = px, py
    return float(np.hypot(pts[joint][0] - wx, pts[joint][1] - wy) / torso)


def _static_load_floors(pts: dict[int, tuple[float, float]], vis: dict[int, float]) -> dict[str, float]:
    """등척성 버티기 보정: 오버헤드 지지·깊은 무릎 굽힘은 각속도가 0이어도 부하로 인식."""
    floors: dict[str, float] = {}
    for side, shoulder, elbow in (("L", 11, 13), ("R", 12, 14)):
        if vis.get(shoulder, 0) >= VIS_MIN and vis.get(elbow, 0) >= VIS_MIN and pts[elbow][1] < pts[shoulder][1]:
            floors[f"delt{side}"] = 0.45
            floors[f"uarm{side}"] = 0.40
            floors[f"farm{side}"] = 0.30
    for side, hip, knee, ankle in (("L", 23, 25, 27), ("R", 24, 26, 28)):
        if all(vis.get(i, 0) >= VIS_MIN for i in (hip, knee, ankle)):
            v1 = np.array(pts[hip]) - np.array(pts[knee])
            v2 = np.array(pts[ankle]) - np.array(pts[knee])
            cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
            if np.degrees(np.arccos(np.clip(cos, -1, 1))) < 110:
                floors[f"thigh{side}"] = 0.45
                floors[f"glute{side}"] = 0.40
    return floors


def _preset_scale(prefix: str, preset: set[str] | None) -> float:
    """프리셋에 속하지 않는 근육군은 게인을 강하게 낮춘다(0 아님 — 살짝은 남겨 자연스럽게)."""
    if preset is None or prefix in preset:
        return 1.0
    return _PRESET_SUPPRESS


_EFF_EMA_ALPHA = 0.5  # per-캡슐 EMA 반영률(프레임당 기준으로 튜닝된 값)


def _ema_alpha(stride: int) -> float:
    """stride 프레임마다 한 번만 갱신될 때 프레임당 `_EFF_EMA_ALPHA`와 같은 시정수를 내는 계수.

    per-캡슐 eff_ema는 `_muscle_layer` 안에 있어 포즈를 실제로 검출한 프레임에서만 갱신된다
    (step()의 e_ema/heat는 hold 프레임에서도 매 프레임 돌아 stride 영향이 없다). 보정하지
    않으면 갱신 빈도가 1/stride로 줄어든 만큼 wall-clock 시정수가 stride배 길어진다
    (stride=2: 48ms→96ms, stride=4: 192ms). 잔여 비율 (1-α)를 stride제곱으로 누적시키는
    등가 계수 = 1-(1-α)**stride. stride=1이면 정확히 `_EFF_EMA_ALPHA`.
    """
    return 1.0 - (1.0 - _EFF_EMA_ALPHA) ** stride


def _muscle_layer(
    pts: dict[int, tuple[float, float]],
    vis: dict[int, float],
    seg: np.ndarray | None,
    ph: int,
    pw: int,
    prev_pts: dict[int, tuple[float, float]] | None,
    prev_angs: dict[str, float],
    eff_ema: dict[str, float],
    affine: np.ndarray | None,
    preset: set[str] | None = None,
    stride: int = 1,
) -> tuple[np.ndarray, dict[str, float]]:
    """한 프레임의 근육 부하 맵(0..1)과 이번 프레임 관절 각도를 계산한다.

    preset: 운동 종목이 특정하는 근육군 집합(캡슐 접두사). 여기 없는 근육군은 게인을
    _PRESET_SUPPRESS 로 낮춰 부위 오귀속(스쿼트 팔 오발화 등)을 억제한다. None이면 균등.
    stride: prev_pts/prev_angs가 몇 비디오 프레임 전 값인지(POSE_STRIDE). K_ANG/DB_ANG/
    K_LIN/DB_LIN은 모두 "프레임당" 단위로 튜닝된 상수라, stride>1이면 원시 델타(수 프레임에
    걸쳐 누적된 이동량)를 프레임당으로 되돌린 뒤(나눗셈) 데드밴드를 적용해야 임계값 의미가
    유지된다 — 데드밴드 자체는 측정 잡음 크기라 stride와 무관하므로 나누지 않는다.
    아래 per-캡슐 EMA 계수도 같은 이유로 보정한다(`_ema_alpha`).
    """
    mid_sho = ((pts[11][0] + pts[12][0]) / 2, (pts[11][1] + pts[12][1]) / 2)
    mid_hip = ((pts[23][0] + pts[24][0]) / 2, (pts[23][1] + pts[24][1]) / 2)
    torso = max(20.0, float(np.hypot(mid_sho[0] - mid_hip[0], mid_sho[1] - mid_hip[1])))

    angs = {name: _joint_angle(pts, vis, name) for name in ANGLES}
    ema_a = _ema_alpha(stride)

    def effort(drivers: list[str], gain: float, aux: list[int] | None, db: float) -> float:
        """각속도 기반 + (팔만) 이동속도 보조. 각도는 카메라 흔들림에 불변."""
        samples = [
            abs(angs[name] - prev_angs[name])
            for name in drivers
            if angs.get(name) is not None and prev_angs.get(name) is not None
        ]
        angular = 0.0
        if samples:
            v = max(0.0, float(np.mean(samples)) / stride - db)
            angular = min(1.0, v / K_ANG) ** 1.2
        linear = 0.0
        if aux:
            speeds = [_joint_speed(pts, prev_pts, vis, j, torso, affine) for j in aux if vis.get(j, 0) >= VIS_MIN]
            if speeds:
                v = max(0.0, float(np.mean(speeds)) / stride - DB_LIN)
                linear = min(1.0, v / K_LIN) ** 1.2 * 0.7  # 보조 신호라 감쇠
        return max(angular, linear) * gain

    floors = _static_load_floors(pts, vis)
    muscle = np.zeros((ph, pw), np.float32)
    for name, a, b, radius_ratio, drivers, gain, aux in CAPS:
        lower_body = name[0] in "tcg"  # thigh/calf/glute — 다리는 프레임 밖 추정이 잦음
        vmin = 0.7 if lower_body else VIS_MIN
        if vis.get(a, 0) < vmin or vis.get(b, 0) < vmin:
            continue

        def in_bounds(p: tuple[float, float]) -> bool:
            return -10 <= p[0] <= pw + 10 and -10 <= p[1] <= ph + 10

        if not (in_bounds(pts[a]) and in_bounds(pts[b])):  # 유령 사지 방지
            continue
        scale = _preset_scale(name[:-1], preset)  # uarmL -> uarm
        e = max(effort(drivers, gain, aux, DB_ANG_LOW if lower_body else DB_ANG), floors.get(name, 0.0)) * scale
        e = eff_ema[name] = ema_a * e + (1.0 - ema_a) * eff_ema.get(name, 0.0)
        if e < 0.12:
            continue
        radius = max(3, int(radius_ratio * torso))
        layer = np.zeros((ph, pw), np.float32)
        pa = (int(pts[a][0]), int(pts[a][1]))
        pb = (int(pts[b][0]), int(pts[b][1]))
        if a == b:
            cv2.circle(layer, pa, radius, e, -1)
        else:
            cv2.line(layer, pa, pb, e, radius * 2)
        muscle = np.maximum(muscle, layer)

    if all(vis.get(i, 0) >= VIS_MIN for i in (11, 12, 23, 24)):  # 코어: 어깨-엉덩이 사각형
        e = effort(CORE_ANGLES, 0.75, None, DB_ANG_LOW) * _preset_scale("core", preset)
        e = eff_ema["core"] = ema_a * e + (1.0 - ema_a) * eff_ema.get("core", 0.0)
        if e >= 0.12:
            poly = np.array([pts[11], pts[12], pts[24], pts[23]], np.int32)
            layer = np.zeros((ph, pw), np.float32)
            cv2.fillPoly(layer, [poly], float(e))
            muscle = np.maximum(muscle, layer)

    if vis.get(0, 0) >= 0.3:  # 얼굴 제외 마스크 — 열이 얼굴을 덮지 않게
        head_x, head_y = pts[0]
        if vis.get(7, 0) >= 0.3 and vis.get(8, 0) >= 0.3:
            head_x = (pts[7][0] + pts[8][0]) / 2
            head_y = (pts[7][1] + pts[8][1]) / 2
        head_r = max(6, int(0.38 * torso))
        head_mask = np.zeros((ph, pw), np.float32)
        cv2.circle(head_mask, (int(head_x), int(head_y)), head_r, 1.0, -1)
        head_mask = cv2.GaussianBlur(head_mask, (31, 31), 0)
        muscle *= 1.0 - np.clip(head_mask, 0, 1)

    muscle = cv2.GaussianBlur(muscle, (21, 21), 0)
    if seg is not None:
        muscle *= np.clip((seg - 0.25) / 0.75, 0, 1)  # 사람 확실한 픽셀만 (기물·배경 컷)
    return muscle, angs


class _RenderState:
    """프레임 간 유지되는 트래킹 상태(관절 각도·EMA·잔열). 영상 1개당 인스턴스 1개."""

    def __init__(self, ph: int, pw: int = PW, preset: set[str] | None = None) -> None:
        self.ph = ph
        self.pw = pw
        self.preset = preset  # 운동 종목 근육군 프리셋 (None = 균등)
        self.prev_pts: dict[int, tuple[float, float]] | None = None
        self.prev_angs: dict[str, float] = {}
        self.prev_gray: np.ndarray | None = None
        self.eff_ema: dict[str, float] = {}
        self.last_muscle = np.zeros((ph, pw), np.float32)  # hold=True 프레임이 재사용할 마지막 근육 캔버스
        self.e_ema = np.zeros((ph, pw), np.float32)
        self.heat = np.zeros((ph, pw), np.float32)
        # prev_pts/prev_angs가 캡처된 이후 경과한 비디오 프레임 수(hold 프레임·검출 실패 모두 누적,
        # 성공 검출에서 1로 리셋). POSE_STRIDE 고정값 대신 이 값을 _muscle_layer(stride=...)에 넘긴다 —
        # 검출 드롭아웃이 이어지면 실제 간격이 POSE_STRIDE보다 커지는데 고정값으로 나누면 각속도/
        # 이동속도 델타가 실제 경과 프레임 수만큼 과대평가돼 복귀 프레임에 열이 폭발적으로 튄다(실측
        # 확인: 14프레임 드롭아웃 후 고정 나눗셈은 정상상태 대비 최대 ~3.7배).
        self.frames_since_pose = 1

    def step(
        self,
        small_bgr: np.ndarray,
        pose: tuple[dict[int, tuple[float, float]], dict[int, float], np.ndarray | None] | None,
        hold: bool = False,
    ) -> np.ndarray:
        """한 프레임 처리, 0..1 히트맵(내부 해상도 ph×pw)을 반환한다.

        `pose`는 `_PoseTracker.process()`의 출력(그리드 좌표 pts, vis, 세그) 또는 None.
        포즈 미검출(None, hold=False) 시 근육 맵은 0으로 유지되고 기존 잔열만 감쇠한다 —
        크래시 없이 그레이스풀 폴백(운동열 없이 베이스 화면만 출력).

        hold=True: POSE_STRIDE로 포즈 추론 자체를 건너뛴 프레임(진짜 검출 실패와 다름) —
        마지막으로 그린 근육 캔버스(`last_muscle`)를 그대로 재사용하고, gray 변환·
        `_global_affine`(goodFeaturesToTrack+LK, 프레임당 ~2~3ms) 계산도 함께 건너뛴다 —
        hold 분기는 결과를 쓰지 않으므로 계산 자체가 순수 낭비였다. `prev_gray`도 갱신하지
        않는데, 그래야 다음 검출 프레임의 `_global_affine`이 "마지막 검출 프레임 → 지금"
        구간 전체(=frames_since_pose 프레임)를 커버해 `prev_pts`가 실제로 몇 프레임 전
        값인지와 정확히 일치한다 — 매 프레임 갱신했다면 최신 1프레임 이동만 반영해 그보다
        오래된 prev_pts 기준 이동속도 보조항(_joint_speed)이 카메라 팬을 과소보정했다.

        실패(pose=None)처럼 0으로 채우면 잔열이 매 스킵 프레임마다 꺼졌다 켜지며 깜빡이고
        정상상태 히트 강도가(실측) 연속 검출 대비 최대 ~31% 낮게 수렴한다 — hold는 그 문제를
        피하려는 것으로, 진짜 미검출(사람이 실제로 사라짐)은 hold=False 경로로 여전히 즉시
        0 처리해 잔열이 정상적으로 감쇠하게 둔다.
        """
        if hold:
            muscle = self.last_muscle
            self.frames_since_pose += 1
        else:
            gray = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2GRAY)
            affine = _global_affine(self.prev_gray, gray)

            if pose is not None:
                pts, vis, seg = pose
                muscle, angs = _muscle_layer(
                    pts, vis, seg, self.ph, self.pw, self.prev_pts, self.prev_angs, self.eff_ema, affine,
                    preset=self.preset, stride=self.frames_since_pose,
                )
                self.prev_pts, self.prev_angs = pts, angs
                self.last_muscle = muscle
                self.frames_since_pose = 1
            else:
                muscle = np.zeros((self.ph, self.pw), np.float32)
                self.last_muscle = muscle
                self.frames_since_pose += 1
            self.prev_gray = gray

        self.e_ema = 0.55 * muscle + 0.45 * self.e_ema
        self.heat = np.maximum(self.heat * DECAY, ALPHA * self.e_ema)
        return self.heat


_PREVIEW_CONVERGE_STEPS = 12  # EMA가 정적 부하의 정상상태(steady state)에 도달하는 데 필요한 반복 수


def heat_preview_frame(frame: np.ndarray, weak_cartoon: bool, exercise: str | None = None) -> np.ndarray:
    """단일 프레임 미리보기.

    각속도·이동속도 신호가 없어(프레임 1장) 정적 부하 휴리스틱(오버헤드 지지·깊은 무릎
    굽힘)만 반영된다. 실제 영상에서는 움직일수록 열이 진해진다 — 프론트 힌트 텍스트로
    이 한계를 안내한다.

    exercise: 근육군 키(PRESETS 참고, 선택) — 프리셋으로 부위 오귀속을 억제한다.

    같은 포즈 결과로 `_RenderState`를 여러 스텝 돌려 EMA를 정상상태로 수렴시킨다 —
    "이 자세를 계속 유지하면"의 정확한 극한값이며, 1회 호출로는 잔열 누적(`ALPHA`,
    `DECAY`, per-캡슐 EMA)이 시작 단계라 열이 오버레이 하한(`lo=0.12`)을 못 넘어 아예
    안 보이는 문제를 해결한다.
    """
    h, w = frame.shape[:2]
    ph = max(2, int(round(PW * h / w)))
    dh = max(2, int(round(DET_W * h / w)))
    small = cv2.resize(frame, (PW, ph), interpolation=cv2.INTER_AREA)
    det = cv2.resize(frame, (DET_W, dh), interpolation=cv2.INTER_AREA)

    tracker = _PoseTracker(video_mode=False)
    try:
        pose = tracker.process(det, PW, ph)
    finally:
        tracker.close()

    state = _RenderState(ph, preset=preset_for_exercise(exercise))
    for _ in range(_PREVIEW_CONVERGE_STEPS):
        heat = state.step(small, pose)
    base = light_cartoonize(frame) if weak_cartoon else frame
    return _overlay(base, heat)


def _worker_pool_size() -> int:
    """호출 시점의 병렬 프로세스 수. FFMPEG_ACTIVE_JOBS(현재 동시 처리 중인 잡 수 —
    worker.py가 ffmpeg:slots 리스 점유 직후 설정)가 있으면 그 값으로, 없으면(단독
    실행·테스트) WORKER_INSTANCES(정적 인스턴스 수)로 코어를 나눈다.

    잡마다 값이 바뀌므로 모듈 임포트 시점이 아니라 매 호출 시점에 읽는다 — 정적
    WORKER_INSTANCES 나눗셈은 "모든 인스턴스가 항상 바쁘다"고 가정해 잡이 하나뿐일
    때도 코어를 남겨뒀다(예: 8코어·2인스턴스 → 잡 1개뿐이어도 3개만 사용).
    (cartoon.py와 동일 로직 — 두 모듈 다 cv2/numpy/mediapipe 외 앱 의존성을 두지
    않는 계약이라 공유 유틸 모듈을 만들지 않고 각자 둔다.)
    """
    active = os.environ.get("FFMPEG_ACTIVE_JOBS") or os.environ.get("WORKER_INSTANCES", "1")
    return max(1, ((os.cpu_count() or 4) - 2) // max(1, int(active)))


_MIN_SEGMENT_FRAMES = 90  # ~3초@30fps 미만은 분할 실익이 없음(프로세스 기동비용이 더 큼)
_SEG_PAD_FRAMES = 24  # 구간 경계 예열 프레임 수(_STREAK_GATE=12 + 여유) — 열 EMA/스트릭 게이트 워밍업용


def _heat_worker_init() -> None:
    cv2.setNumThreads(1)


def _plan_segments(frame_count: int, k: int) -> list[tuple[int, int, int]]:
    """frame_count를 k개 구간 (start, end, pad_start)로 분할. 나머지 프레임은 마지막 구간이 흡수.

    pad_start: 이 구간이 실제로 쓰기 시작하는 start보다 앞서 읽기 시작하는 지점(예열용).
    0번 구간은 원래도 처음부터 시작이라 예열이 필요 없다.
    """
    if k <= 1:
        return [(0, frame_count, 0)]
    base = frame_count // k
    segments: list[tuple[int, int, int]] = []
    start = 0
    for i in range(k):
        end = frame_count if i == k - 1 else start + base
        pad_start = 0 if i == 0 else max(0, start - _SEG_PAD_FRAMES)
        segments.append((start, end, pad_start))
        start = end
    return segments


def _render_heat_segment(args: tuple) -> tuple[int, str]:
    """구간 하나를 렌더링해 비디오 전용(오디오 없음) mp4로 저장. (처리된 프레임 수, seg_path) 반환.

    pad_start부터 읽어 tracker/state를 예열시키고 start 이후 프레임만 ffmpeg에 쓴다 —
    구간 경계에서 열 EMA·스트릭 게이트가 0부터 다시 쌓이며 생기는 깜빡임을 줄이기 위함.
    """
    (input_path, start, end, pad_start, out_w, out_h, ph, dh, fps, weak_cartoon, exercise, seg_path) = args

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {input_path}")
    if pad_start > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pad_start)

    # x264 -threads auto는 코어당 ~1.5개 프레임 스레드를 띄운다. 구간마다 인코더가 하나씩
    # 떠서(k개) 렌더 프로세스 수와 별개로 코어를 오버섭스크립션한다 — 2로 고정.
    # -crf 28: worker의 compress 단계와 같은 목표 화질/용량 — video_filter 지정 시 compress를
    # 건너뛰고 이 인코더가 직접 최종 결과물을 만들기 때문(이중 인코딩 제거, full_pipeline_multi.py).
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{out_w}x{out_h}",
        "-r", f"{fps:.6f}", "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "28", "-threads", "2",
        "-movflags", "+faststart",
        seg_path,
    ]
    proc = subprocess.Popen(
        ffmpeg_cmd, stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None

    stderr_chunks: list[bytes] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for chunk in iter(lambda: proc.stderr.read(4096), b""):
            stderr_chunks.append(chunk)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    tracker = _PoseTracker(video_mode=True)
    state = _RenderState(ph, preset=preset_for_exercise(exercise))
    processed = 0
    frame_idx = pad_start
    try:
        while frame_idx < end:
            ok, frame = cap.read()
            if not ok:
                break
            if (frame.shape[1], frame.shape[0]) != (out_w, out_h):
                frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
            small = cv2.resize(frame, (PW, ph), interpolation=cv2.INTER_AREA)
            # frame_idx는 원본 영상 절대 프레임 번호(구간마다 다른 pad_start에서 시작)라
            # 구간 경계에서도 스트라이드 위상이 어긋나지 않는다.
            if frame_idx % POSE_STRIDE == 0:
                det = cv2.resize(frame, (DET_W, dh), interpolation=cv2.INTER_AREA)
                heat = state.step(small, tracker.process(det, PW, ph, frame_gap=POSE_STRIDE))
            else:
                heat = state.step(small, None, hold=True)

            if frame_idx >= start:
                base = light_cartoonize(frame) if weak_cartoon else frame
                canvas = _overlay(base, heat)
                proc.stdin.write(canvas.tobytes())
                processed += 1
            frame_idx += 1
    finally:
        tracker.close()
        cap.release()
        proc.stdin.close()
        code = proc.wait()
        stderr_thread.join(timeout=5)

    if code != 0:
        stderr = b"".join(stderr_chunks).decode(errors="replace")
        raise RuntimeError(f"ffmpeg encode failed (exit {code}): {stderr[-500:]}")
    if processed != end - start:
        raise ValueError(f"segment frame mismatch: expected {end - start}, got {processed}")
    return processed, seg_path


def _concat_and_mux(seg_paths: list[str], input_path: str, output_path: str) -> None:
    """구간 mp4들을 무손실로 이어붙이고(-c:v copy) 원본 오디오를 한 번만 입힌다."""
    concat_list = output_path + ".concat.txt"
    with open(concat_list, "w") as f:
        for p in seg_paths:
            f.write(f"file '{p}'\n")
    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-i", input_path,
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "copy", "-c:a", "copy",
            "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")
            raise RuntimeError(f"concat mux failed (exit {result.returncode}): {stderr[-500:]}")
    finally:
        try:
            os.remove(concat_list)
        except OSError:
            pass


def render_heat_video(input_path: str, output_path: str, weak_cartoon: bool, exercise: str | None = None) -> None:
    """영상 전체에 근육 히트맵을 합성한다. 원본 오디오 스트림은 그대로 보존(-c:a copy).

    프레임 수가 `_MIN_SEGMENT_FRAMES` 이상이면 영상을 `_worker_pool_size()`개 구간으로 나눠
    프로세스 풀로 병렬 렌더링한다 — MediaPipe `PoseLandmarker`의 VIDEO 모드는 타임스탬프 단조증가가
    필요한 상태 기반 트래커라 `cartoonize_video()`처럼 프레임 단위 풀 병렬화는 불가능하지만,
    구간 단위로는 각 구간이 독립된 트래커·히트 상태를 가지고 각자 순차 처리할 수 있다.
    짧은 영상은 프로세스 기동 비용이 더 크므로 기존 단일 프로세스 경로(`_render_heat_sequential`)를
    그대로 쓴다.
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
    ph = max(2, int(round(PW * out_h / out_w)))
    dh = max(2, int(round(DET_W * out_h / out_w)))

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    # 컨테이너가 프레임 수를 신뢰할 수 없게 보고하면(0 이하) 안전하게 단일 프로세스로 폴백.
    k = min(_worker_pool_size(), max(1, frame_count // _MIN_SEGMENT_FRAMES)) if frame_count > 0 else 1

    if k <= 1:
        _render_heat_sequential(input_path, output_path, out_w, out_h, ph, dh, fps, weak_cartoon, exercise)
        return

    segments = _plan_segments(frame_count, k)
    with tempfile.TemporaryDirectory() as tmpdir:
        seg_args = [
            (input_path, start, end, pad_start, out_w, out_h, ph, dh, fps, weak_cartoon, exercise,
             os.path.join(tmpdir, f"seg_{i}.mp4"))
            for i, (start, end, pad_start) in enumerate(segments)
        ]
        pool = multiprocessing.get_context("spawn").Pool(k, initializer=_heat_worker_init)
        try:
            results = pool.map(_render_heat_segment, seg_args)
        finally:
            pool.close()
            pool.join()

        total_processed = sum(r[0] for r in results)
        if total_processed != frame_count:
            raise RuntimeError(f"segment total mismatch: expected {frame_count}, got {total_processed}")

        seg_paths = [r[1] for r in results]
        _concat_and_mux(seg_paths, input_path, output_path)

    logger.info(
        "render_heat_video: %d frames across %d segments (weak_cartoon=%s) → %s",
        frame_count, k, weak_cartoon, output_path,
    )


def _render_heat_sequential(
    input_path: str, output_path: str, out_w: int, out_h: int, ph: int, dh: int, fps: float,
    weak_cartoon: bool, exercise: str | None,
) -> None:
    """단일 프로세스 순차 렌더링(짧은 영상용 — 구간 분할 오버헤드가 더 클 때)."""
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {input_path}")

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{out_w}x{out_h}",
        "-r", f"{fps:.6f}", "-i", "-",
        "-i", input_path,
        "-map", "0:v", "-map", "1:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "28",
        "-c:a", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    proc = subprocess.Popen(
        ffmpeg_cmd, stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    assert proc.stdin is not None

    # stderr를 계속 읽어 비워두지 않으면 ffmpeg 로그로 파이프 버퍼가 차서 ffmpeg가 멈추고,
    # 그러면 아래 stdin.write()도 함께 블로킹되어 영구 교착 상태에 빠진다(motion_fx.py와 동일 버그).
    stderr_chunks: list[bytes] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for chunk in iter(lambda: proc.stderr.read(4096), b""):
            stderr_chunks.append(chunk)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    processed = 0
    frame_idx = 0
    tracker = _PoseTracker(video_mode=True)
    state = _RenderState(ph, preset=preset_for_exercise(exercise))
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if (frame.shape[1], frame.shape[0]) != (out_w, out_h):
                frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
            small = cv2.resize(frame, (PW, ph), interpolation=cv2.INTER_AREA)
            if frame_idx % POSE_STRIDE == 0:
                det = cv2.resize(frame, (DET_W, dh), interpolation=cv2.INTER_AREA)
                heat = state.step(small, tracker.process(det, PW, ph, frame_gap=POSE_STRIDE))
            else:
                heat = state.step(small, None, hold=True)
            frame_idx += 1

            base = light_cartoonize(frame) if weak_cartoon else frame
            canvas = _overlay(base, heat)
            proc.stdin.write(canvas.tobytes())
            processed += 1
    finally:
        tracker.close()
        cap.release()
        proc.stdin.close()
        code = proc.wait()
        stderr_thread.join(timeout=5)

    if code != 0:
        stderr = b"".join(stderr_chunks).decode(errors="replace")
        raise RuntimeError(f"ffmpeg encode failed (exit {code}): {stderr[-500:]}")
    if processed == 0:
        raise ValueError("no frames decoded from input video")
    logger.info("render_heat_video: %d frames (weak_cartoon=%s) → %s", processed, weak_cartoon, output_path)
