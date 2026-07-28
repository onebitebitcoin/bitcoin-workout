"""운동열 렌더러(`app.services.muscle_heat`) 단위 + 영상 E2E 테스트."""

from __future__ import annotations

import itertools
import json
import shutil
import subprocess

import cv2
import numpy as np
import pytest

import app.services.muscle_heat as muscle_heat
from app.services.muscle_heat import (
    _PROBE_INTERVAL,
    _STREAK_GATE,
    PRESETS,
    PW,
    _muscle_layer,
    _plan_segments,
    _RenderState,
    _unrotate_norm,
    cartoon_base,
    heat_preview_frame,
    preset_for_exercise,
    render_heat_video,
)

_HAS_FFMPEG = shutil.which("ffmpeg") is not None


def _textured_frame(seed: int = 5, size: tuple[int, int] = (240, 320)) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.integers(40, 220, (*size, 3), dtype=np.uint8)
    return cv2.GaussianBlur(base, (5, 5), 0)


class TestPresetForExercise:
    """근육군 키(Gemini가 직접 고름) → 캡슐 프리셋 조회. 부위 오귀속 억제의 핵심."""

    def test_known_groups_map_to_presets(self):
        for group in PRESETS:
            assert preset_for_exercise(group) == PRESETS[group]

    def test_case_and_whitespace_insensitive(self):
        assert preset_for_exercise(" Legs ") == PRESETS["legs"]
        assert preset_for_exercise("ARMS") == PRESETS["arms"]

    def test_unknown_group_returns_none(self):
        # Gemini가 "unknown"이나 프리셋 밖 문자열을 뱉어도 조용히 무시된다 (부분일치 없음)
        assert preset_for_exercise("unknown") is None
        assert preset_for_exercise("meditation") is None
        assert preset_for_exercise("bench press") is None  # 운동명 자체는 더 이상 유효 입력이 아님

    def test_none_returns_none(self):
        assert preset_for_exercise(None) is None

    def test_squat_preset_excludes_arms(self):
        # 스쿼트 프리셋에 팔 근육군이 없어야 팔 오발화가 억제된다
        legs = PRESETS["legs"]
        assert "uarm" not in legs and "farm" not in legs and "delt" not in legs

    def test_core_preset_is_core_only(self):
        # 플랭크·싯업류 — 코어 캡슐만 살고 팔다리는 전부 억제
        assert PRESETS["core"] == {"core"}


class TestCartoonBase:
    def test_shape_and_no_mutation(self):
        frame = _textured_frame()
        original = frame.copy()
        out = cartoon_base(frame)
        assert out.shape == frame.shape
        assert np.array_equal(frame, original)

    def test_color_preserved(self):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :, 2] = 200  # 빨강 프레임
        out = cartoon_base(frame)
        center = out[120, 160]
        assert center[2] > center[0]  # 빨강 채널 우세 유지

    def test_matches_standalone_cartoon_filter(self):
        """"카툰+운동열"의 카툰 베이스는 카툰 단독 필터와 픽셀 단위로 같아야 한다 —
        예전엔 조합 전용 약한 구현을 써서 같은 이름의 두 필터 룩이 눈에 띄게 달랐다."""
        from app.services.cartoon import cartoon_frame

        frame = _textured_frame()
        assert np.array_equal(cartoon_base(frame, 0.8), cartoon_frame(frame, 0.8))


def _overhead_pose(ph: int = 200, pw: int = PW):
    """팔꿈치가 어깨보다 위 = 오버헤드 지지 자세. 무릎은 편 상태(하체 정적부하 미발동).

    `_RenderState.step`은 `_PoseTracker.process()` 출력 형태인 (그리드 좌표 pts, vis, seg)
    튜플을 받는다 — mediapipe 없이 좌표를 직접 지정해 정적 부하 로직을 단위 테스트한다.
    """
    coords = {
        0: (0.50, 0.15), 7: (0.47, 0.14), 8: (0.53, 0.14),
        11: (0.40, 0.35), 12: (0.60, 0.35),
        13: (0.35, 0.15), 14: (0.65, 0.15),
        15: (0.45, 0.05), 16: (0.55, 0.05),
        23: (0.42, 0.65), 24: (0.58, 0.65),
        25: (0.42, 0.85), 26: (0.58, 0.85),
        27: (0.42, 0.98), 28: (0.58, 0.98),
    }
    pts = {i: (0.5 * pw, 0.5 * ph) for i in range(33)}
    vis = {i: 0.0 for i in range(33)}
    for i, (u, v) in coords.items():
        pts[i] = (u * pw, v * ph)
        vis[i] = 0.9
    return pts, vis, None


class TestUnrotateNorm:
    """회전 폴백의 좌표 역매핑 검증 — 이미지 코너를 회전시켰다 되돌리면 원위치여야 한다."""

    @pytest.mark.parametrize("rot_idx", [0, 1, 2, 3])
    def test_roundtrip_via_cv2(self, rot_idx):
        # 실제 cv2.rotate로 마커 픽셀을 회전시킨 뒤, 회전 좌표를 역매핑해 원좌표와 비교
        rots = [None, cv2.ROTATE_90_CLOCKWISE, cv2.ROTATE_90_COUNTERCLOCKWISE, cv2.ROTATE_180]
        h, w = 60, 100
        for ox, oy in [(10, 5), (90, 50), (30, 40)]:
            img = np.zeros((h, w), np.uint8)
            img[oy, ox] = 255
            rimg = img if rots[rot_idx] is None else cv2.rotate(img, rots[rot_idx])
            ry, rx = np.unravel_index(rimg.argmax(), rimg.shape)
            rh, rw = rimg.shape
            u, v = _unrotate_norm(rx / (rw - 1), ry / (rh - 1), rot_idx)
            assert abs(u * (w - 1) - ox) < 1.0, f"rot={rot_idx} x: {u*(w-1)} != {ox}"
            assert abs(v * (h - 1) - oy) < 1.0, f"rot={rot_idx} y: {v*(h-1)} != {oy}"


class TestRenderStateConvergence:
    """단일 프레임 프리뷰(`heat_preview_frame`)가 오버레이 하한(lo=0.12)을 못 넘어
    열이 아예 안 보이던 버그의 회귀 테스트. 같은 정적 자세를 유지하면 EMA가
    수렴해 열이 보여야 한다."""

    def test_single_step_stays_below_overlay_threshold(self):
        state = _RenderState(ph=200)
        dummy = np.zeros((200, PW, 3), np.uint8)
        heat = state.step(dummy, _overhead_pose())
        assert heat.max() < 0.12  # 수렴 전: 오버레이에서 안 보임 (수정 전 버그 상태)

    def test_repeated_steps_converge_above_overlay_threshold(self):
        state = _RenderState(ph=200)
        dummy = np.zeros((200, PW, 3), np.uint8)
        heat = None
        for _ in range(12):
            heat = state.step(dummy, _overhead_pose())
        assert heat.max() > 0.12  # 수렴 후: 오버레이에서 보임


def _hip_angle_pose(angle_deg: float, ph: int = 200, pw: int = PW):
    """어깨(11)-엉덩이(23,vertex)-무릎(25) 각도를 지정한 최소 포즈.

    gluteL 캡슐(드라이버 hipL 단일, aux 없음)만 활성화해 각속도 정규화(stride)를
    다른 신호(이동속도 보조, 정적부하 플로어)와 분리해 테스트하기 위한 헬퍼.
    각도가 180°에 가까우면 무릎이 펴진 상태 — `_static_load_floors`의 깊은 무릎
    굽힘 플로어(<110°)를 피해 순수 각속도 신호만 측정한다.
    """
    vis = {i: 0.0 for i in range(33)}
    pts = {i: (0.5 * pw, 0.5 * ph) for i in range(33)}
    pts[11] = (0.5 * pw, 0.20 * ph)  # 어깨
    pts[23] = (0.5 * pw, 0.55 * ph)  # 엉덩이(각도 꼭짓점)
    rad = np.radians(angle_deg)
    knee_len = 0.30 * ph
    pts[25] = (pts[23][0] + knee_len * np.sin(rad), pts[23][1] - knee_len * np.cos(rad))
    pts[12] = (0.5 * pw + 1, 0.20 * ph)  # mid_sho 계산용(직접 인덱싱되므로 키 필요)
    pts[24] = (0.5 * pw + 1, 0.55 * ph)  # mid_hip 계산용
    for i in (11, 12, 23, 24, 25):
        vis[i] = 0.9
    return pts, vis


class TestMuscleLayerStrideNormalization:
    """POSE_STRIDE로 포즈 추론을 격프레임 건너뛸 때, `_muscle_layer`의 stride 인자가
    누적 델타(원시 각도차)를 프레임당으로 되돌려 단일 프레임 검출과 동일한 effort를
    내는지 검증 — P6(perf 리포트)의 핵심 정합성 요구사항."""

    def test_double_delta_with_stride_two_matches_single_delta_stride_one(self):
        step_deg = np.degrees(0.020)  # DB_ANG_LOW(0.010)~K_ANG(0.030) 사이 — 데드밴드/포화 회피
        pts0, vis0 = _hip_angle_pose(179.0)
        pts1, vis1 = _hip_angle_pose(179.0 - step_deg)       # 1프레임 후(stride=1 비교 대상)
        pts2, vis2 = _hip_angle_pose(179.0 - 2 * step_deg)   # 2프레임 후(stride=2 비교 대상)
        angs0 = {name: muscle_heat._joint_angle(pts0, vis0, name) for name in muscle_heat.ANGLES}

        eff_ema_s1: dict[str, float] = {}
        _muscle_layer(pts1, vis1, None, 200, PW, pts0, angs0, eff_ema_s1, None, stride=1)

        eff_ema_s2: dict[str, float] = {}
        _muscle_layer(pts2, vis2, None, 200, PW, pts0, angs0, eff_ema_s2, None, stride=2)

        # eff_ema 초기값이 0이므로 저장된 값 = ema_alpha(stride) * raw_effort —
        # 계수를 되나눠 EMA 보정과 분리한 raw effort끼리 비교한다(여기서 보려는 건
        # 각속도 델타 정규화이고, EMA 계수 보정은 TestEmaAlphaStrideCompensation 담당).
        raw_s1 = eff_ema_s1["gluteL"] / muscle_heat._ema_alpha(1)
        raw_s2 = eff_ema_s2["gluteL"] / muscle_heat._ema_alpha(2)

        assert raw_s1 > 0.0  # 데드밴드 위 — 유의미한 신호인지 사전 확인
        assert raw_s2 == pytest.approx(raw_s1, rel=1e-6)

    def test_stride_one_without_normalization_would_double_count(self):
        # 위 테스트의 대조군: stride 보정을 안 하면(=stride=1로 2프레임분 델타를 넣으면)
        # 값이 달라져야 한다 — 정규화가 실제로 결과에 영향을 준다는 것 자체를 확인.
        step_deg = np.degrees(0.020)
        pts0, vis0 = _hip_angle_pose(179.0)
        pts2, vis2 = _hip_angle_pose(179.0 - 2 * step_deg)
        angs0 = {name: muscle_heat._joint_angle(pts0, vis0, name) for name in muscle_heat.ANGLES}

        eff_ema_correct: dict[str, float] = {}
        _muscle_layer(pts2, vis2, None, 200, PW, pts0, angs0, eff_ema_correct, None, stride=2)

        eff_ema_unnormalized: dict[str, float] = {}
        _muscle_layer(pts2, vis2, None, 200, PW, pts0, angs0, eff_ema_unnormalized, None, stride=1)

        assert eff_ema_unnormalized["gluteL"] > eff_ema_correct["gluteL"]

    def test_detection_dropout_recovery_does_not_spike_vs_continuous(self):
        """리뷰 회귀 재현: 검출이 여러 프레임 연속으로 실패했다가 복귀할 때,
        `_RenderState.frames_since_pose`가 고정 POSE_STRIDE 대신 실제 경과 프레임 수를
        추적해야 복귀 프레임의 effort가 폭발하지 않는다. 이 테스트는 `_RenderState.step()`
        전체(고정 stride였다면 실패했을 경로)를 통해 검증한다 — `_muscle_layer` 단위
        테스트만으로는 gap==stride인 경우만 보고 이 경로를 놓친다."""
        step_deg = np.degrees(0.020)

        # 연속 검출: 매 프레임 성공(hold 없음) — 정상상태 effort
        steady = _RenderState(ph=200)
        dummy = np.zeros((200, PW, 3), np.uint8)
        angle = 179.0
        for _ in range(6):
            pts, vis = _hip_angle_pose(angle)
            steady.step(dummy, (pts, vis, None))
            angle -= step_deg
        steady_eff = steady.eff_ema["gluteL"]
        assert steady_eff > 0.0  # 사전 확인

        # 드롭아웃 후 복귀: 같은 각속도로 진행하다가 중간에 14프레임 미검출(pose=None,
        # hold=False — 실제 검출 실패) 후 복귀. frames_since_pose가 15로 정확히 추적되면
        # 복귀 프레임의 effort가 steady_eff와 같은 자릿수여야 한다(포화로 튀지 않음).
        recovering = _RenderState(ph=200)
        angle = 179.0
        for _ in range(3):
            pts, vis = _hip_angle_pose(angle)
            recovering.step(dummy, (pts, vis, None))
            angle -= step_deg
        for _ in range(14):
            recovering.step(dummy, None, hold=False)
            angle -= step_deg  # 실제로는 계속 진행 중이지만 검출을 못 하는 상황을 흉내
        pts, vis = _hip_angle_pose(angle)
        recovering.step(dummy, (pts, vis, None))
        recovered_eff = recovering.eff_ema["gluteL"]

        # 고정 stride=2였다면 14프레임 누적 델타를 2로만 나눠 완전 포화(0.45 근처)했을 것.
        # frames_since_pose=15로 정확히 나누면 steady_eff와 같은 자릿수에 머문다.
        assert recovered_eff < steady_eff * 3  # 여유를 둔 상한 — 포화(0.45)와는 확실히 구분됨


class TestRenderStateHold:
    """hold=True(POSE_STRIDE 스킵 프레임)는 마지막 근육 캔버스를 재사용해야 하고,
    pose=None(진짜 검출 실패)은 여전히 0으로 즉시 폴백해야 한다 — 둘을 혼동하면
    스킵 프레임마다 열이 깜빡이거나(hold 없이) 사람이 실제로 사라져도 열이 안 꺼지는(hold
    오적용) 두 가지 회귀가 생긴다."""

    def test_hold_reuses_last_muscle_canvas(self):
        state = _RenderState(ph=200)
        dummy = np.zeros((200, PW, 3), np.uint8)
        state.step(dummy, _overhead_pose())  # 정적 부하로 muscle 캔버스 채움
        held_muscle = state.last_muscle.copy()
        assert held_muscle.max() > 0  # 사전 확인: 실제로 뭔가 그려졌는지

        state.step(dummy, None, hold=True)
        assert np.array_equal(state.last_muscle, held_muscle)  # hold는 캔버스를 바꾸지 않음
        assert state.e_ema.max() > 0  # 0으로 꺼지지 않고 이전 근육 캔버스가 계속 반영됨

    def test_true_detection_failure_still_zeroes_immediately(self):
        state = _RenderState(ph=200)
        dummy = np.zeros((200, PW, 3), np.uint8)
        state.step(dummy, _overhead_pose())
        assert state.last_muscle.max() > 0

        state.step(dummy, None, hold=False)  # 진짜 미검출 — freeze 아님
        assert state.last_muscle.max() == 0

    def test_hold_does_not_advance_prev_gray_or_frames_since_pose_resets_on_success(self):
        """hold 프레임은 frames_since_pose를 누적만 하고 prev_gray를 갱신하지 않는다 —
        다음 검출 성공 시 frames_since_pose가 실제 경과 프레임 수(hold 횟수+1)와 일치하고,
        검출 즉시 1로 리셋되는지 확인한다."""
        state = _RenderState(ph=200)
        dummy = np.zeros((200, PW, 3), np.uint8)
        state.step(dummy, _overhead_pose())
        assert state.frames_since_pose == 1
        gray_after_detect = state.prev_gray.copy()

        state.step(dummy, None, hold=True)
        state.step(dummy, None, hold=True)
        assert state.frames_since_pose == 3  # 검출 후 hold 2회
        assert np.array_equal(state.prev_gray, gray_after_detect)  # hold는 prev_gray를 안 건드림

        state.step(dummy, _overhead_pose())
        assert state.frames_since_pose == 1  # 검출 성공 즉시 리셋


class _FakeDetectResult:
    """mediapipe 없이 _PoseTracker 게이트 로직만 구동하기 위한 최소 결과 객체."""

    def __init__(self, has_pose: bool) -> None:
        self.pose_landmarks = [[object()] * 33] if has_pose else []
        self.segmentation_masks = None


def _tracker_with_fake_detect(schedule: list[bool]):
    """schedule[비디오 프레임 인덱스] = 검출 성공 여부. 실제 _PoseTracker에 가짜 detect를 주입한다.

    반환: (tracker, set_frame, probe_log) — probe_log에는 (fail_streak, rot_idx) 튜플이 쌓인다.
    """
    tracker = muscle_heat._PoseTracker(video_mode=True)
    probe_log: list[tuple[int, int]] = []
    cursor = {"frame": 0}

    def fake_detect(det_bgr, rot_idx, frame_gap=1):
        probe_log.append((tracker._fail_streak, rot_idx))
        return _FakeDetectResult(schedule[cursor["frame"]])

    tracker._detect = fake_detect
    tracker._extract = lambda result, rot, gw, gh: ("POSE", {}, None)
    return tracker, cursor, probe_log


class TestPoseTrackerFrameDomainGates:
    """_STREAK_GATE/_GAP_TOLERANCE/_PROBE_INTERVAL은 전부 비디오 프레임 단위 상수다.
    POSE_STRIDE로 추론을 건너뛰어도 스트릭이 frame_gap을 누적하므로 게이트의 wall-clock
    의미가 stride와 무관하게 유지되어야 한다 — stride로 나눈 파생 상수를 쓰던 이전 구현은
    정수 나눗셈 손실과 '나누는 걸 잊은 상수'(_PROBE_INTERVAL) 문제가 있었다."""

    @pytest.mark.parametrize("stride", [1, 2, 3])
    def test_heat_activates_after_streak_gate_video_frames_regardless_of_stride(self, stride):
        schedule = [True] * 60
        tracker, cursor, _ = _tracker_with_fake_detect(schedule)

        activated_at = None
        dummy = np.zeros((10, 10, 3), np.uint8)
        for f in range(0, len(schedule), stride):
            cursor["frame"] = f
            if tracker.process(dummy, PW, 100, frame_gap=stride) is not None:
                activated_at = f
                break

        # 활성화 시점이 _STREAK_GATE 비디오 프레임 격자 근처여야 한다 — 첫 호출부터 gap을
        # 통째로 더하므로 최대 stride만큼 이르고, 격자 스냅으로 최대 stride만큼 늦을 수 있다.
        # 핵심은 stride배로 늘어나지 않는 것(파생 상수 방식의 회귀 시나리오).
        assert activated_at is not None
        assert _STREAK_GATE - stride <= activated_at < _STREAK_GATE + stride

    @pytest.mark.parametrize("stride", [1, 2])
    def test_rotation_probe_cadence_is_video_frame_based(self, stride):
        schedule = [False] * 60  # 사람 없는 영상 — 계속 미검출
        tracker, cursor, probe_log = _tracker_with_fake_detect(schedule)

        dummy = np.zeros((10, 10, 3), np.uint8)
        for f in range(0, len(schedule), stride):
            cursor["frame"] = f
            tracker.process(dummy, PW, 100, frame_gap=stride)

        # rot != 0 호출이 회전 프로브. 프로브가 일어난 시점의 fail_streak(=경과 비디오 프레임)
        probe_frames = sorted({fs for fs, rot in probe_log if rot != 0})
        # 첫 실패 직후 1회 + 이후 _PROBE_INTERVAL 프레임 간격 — 간격이 stride에 비례해
        # 늘어나면(미스케일 회귀) 이 상한을 넘는다.
        gaps = [b - a for a, b in itertools.pairwise(probe_frames)]
        assert gaps, "프로브가 한 번밖에 안 일어났다"
        assert max(gaps) <= _PROBE_INTERVAL + stride


class TestEmaAlphaStrideCompensation:
    """per-캡슐 eff_ema는 검출 프레임에서만 갱신되므로, stride만큼 갱신 빈도가 줄어든 것을
    계수로 보정해야 wall-clock 시정수가 유지된다."""

    def test_stride_one_is_unchanged(self):
        assert muscle_heat._ema_alpha(1) == pytest.approx(muscle_heat._EFF_EMA_ALPHA)

    @pytest.mark.parametrize("stride", [2, 3, 4])
    def test_compensated_alpha_matches_repeated_application(self, stride):
        # stride회 연속 적용한 잔여 비율과, 보정 계수 1회 적용의 잔여 비율이 같아야 한다.
        residual_repeated = (1 - muscle_heat._EFF_EMA_ALPHA) ** stride
        residual_single = 1 - muscle_heat._ema_alpha(stride)
        assert residual_single == pytest.approx(residual_repeated)


class TestHeatPreviewFrame:
    """사람이 없는 합성 프레임 — 포즈 미검출 그레이스풀 폴백 검증."""

    def test_no_pose_returns_unchanged_shape(self):
        frame = _textured_frame()
        out = heat_preview_frame(frame, weak_cartoon=False)
        assert out.shape == frame.shape
        assert out.dtype == np.uint8

    def test_no_pose_with_cartoon_base(self):
        frame = _textured_frame()
        out = heat_preview_frame(frame, weak_cartoon=True)
        assert out.shape == frame.shape

    def test_does_not_mutate_input(self):
        frame = _textured_frame()
        original = frame.copy()
        heat_preview_frame(frame, weak_cartoon=False)
        assert np.array_equal(frame, original)

    def test_exercise_param_accepted(self):
        # exercise 프리셋 인자(근육군 키)가 preview 경로를 통과해도 크래시 없이 동작
        frame = _textured_frame()
        out = heat_preview_frame(frame, weak_cartoon=False, exercise="legs")
        assert out.shape == frame.shape


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not installed")
class TestRenderHeatVideo:
    @pytest.fixture()
    def sample_with_audio(self, tmp_path):
        """1초 테스트 영상(합성 패턴, 사람 없음) + 사인파 오디오."""
        path = tmp_path / "in.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=10",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                str(path),
            ],
            check=True, timeout=60,
        )
        return path

    @pytest.mark.parametrize("weak_cartoon", [False, True])
    def test_frames_and_audio_preserved(self, sample_with_audio, tmp_path, weak_cartoon):
        out = tmp_path / f"out_{weak_cartoon}.mp4"
        render_heat_video(str(sample_with_audio), str(out), weak_cartoon=weak_cartoon)
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,nb_frames",
             "-of", "json", str(out)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        import json

        streams = json.loads(probe.stdout)["streams"]
        types = {s["codec_type"] for s in streams}
        assert types == {"video", "audio"}, f"streams: {streams}"
        video_stream = next(s for s in streams if s["codec_type"] == "video")
        assert int(video_stream["nb_frames"]) == 10  # 1초 x 10fps

    def test_invalid_input_raises(self, tmp_path):
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(b"not a video")
        with pytest.raises((ValueError, RuntimeError)):
            render_heat_video(str(bad), str(tmp_path / "out.mp4"), weak_cartoon=False)


class TestPlanSegments:
    """구간 병렬처리 분할 로직 — 나머지 프레임 처리, pad 클램핑, k<=1 폴백을 검증."""

    def test_k_le_1_returns_single_segment(self):
        assert _plan_segments(100, 1) == [(0, 100, 0)]
        assert _plan_segments(100, 0) == [(0, 100, 0)]

    def test_even_split_with_pad(self):
        # pad는 `_SEG_PAD_FRAMES`(감마 EMA 예열 길이)에서 파생되므로 상수로부터 계산한다 —
        # 하드코딩하면 예열 길이를 조정할 때마다 무관한 테스트가 깨진다.
        pad = muscle_heat._SEG_PAD_FRAMES
        assert _plan_segments(120, 3) == [
            (0, 40, 0),
            (40, 80, max(0, 40 - pad)),
            (80, 120, max(0, 80 - pad)),
        ]

    def test_segments_cover_all_frames_without_gap_or_overlap(self):
        segs = _plan_segments(100, 3)
        starts = [s for s, _, _ in segs]
        ends = [e for _, e, _ in segs]
        assert starts[0] == 0
        assert ends[-1] == 100
        assert starts[1:] == ends[:-1]  # 다음 구간 시작 == 이전 구간 끝 (gap/overlap 없음)

    def test_remainder_goes_to_last_segment(self):
        segs = _plan_segments(100, 3)  # 100 // 3 == 33
        assert [e - s for s, e, _ in segs] == [33, 33, 34]

    def test_pad_never_negative_and_first_segment_unpadded(self):
        segs = _plan_segments(10, 5)  # base=2 << _SEG_PAD_FRAMES — pad가 음수로 새지 않아야 한다
        assert segs[0][2] == 0
        assert all(pad >= 0 for _, _, pad in segs)


@pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not installed")
class TestRenderHeatVideoParallel:
    """`_MIN_SEGMENT_FRAMES`를 낮추고 `_worker_pool_size`를 고정해 구간 병렬 경로를 강제로 태우는 E2E 테스트."""

    @pytest.fixture()
    def longer_sample_with_audio(self, tmp_path):
        """2초 테스트 영상(합성 패턴, 사람 없음) + 사인파 오디오 — 병렬 경로를 태울 만큼 길다."""
        path = tmp_path / "in_long.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                str(path),
            ],
            check=True, timeout=60,
        )
        return path

    @pytest.mark.parametrize("weak_cartoon", [False, True])
    def test_parallel_path_preserves_frames_and_audio(
        self, longer_sample_with_audio, tmp_path, weak_cartoon, monkeypatch,
    ):
        monkeypatch.setattr(muscle_heat, "_MIN_SEGMENT_FRAMES", 5)
        monkeypatch.setattr(muscle_heat, "_worker_pool_size", lambda: 2)
        assert len(_plan_segments(20, 2)) == 2  # 이 설정으로 실제 k=2가 나오는지 사전 확인

        out = tmp_path / f"out_parallel_{weak_cartoon}.mp4"
        render_heat_video(str(longer_sample_with_audio), str(out), weak_cartoon=weak_cartoon)

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,nb_frames",
             "-of", "json", str(out)],
            check=True, capture_output=True, text=True, timeout=30,
        )
        streams = json.loads(probe.stdout)["streams"]
        types = {s["codec_type"] for s in streams}
        assert types == {"video", "audio"}, f"streams: {streams}"
        video_stream = next(s for s in streams if s["codec_type"] == "video")
        assert int(video_stream["nb_frames"]) == 20  # 2초 x 10fps, 구간 분할 후에도 총 프레임수 보존

    def test_invalid_input_raises_in_parallel_path_too(self, tmp_path, monkeypatch):
        monkeypatch.setattr(muscle_heat, "_MIN_SEGMENT_FRAMES", 1)
        monkeypatch.setattr(muscle_heat, "_worker_pool_size", lambda: 2)
        bad = tmp_path / "bad.mp4"
        bad.write_bytes(b"not a video")
        with pytest.raises((ValueError, RuntimeError)):
            render_heat_video(str(bad), str(tmp_path / "out.mp4"), weak_cartoon=False)
