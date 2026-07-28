"""셀 셰이딩 카툰 렌더러 — 업로드 영상 필터.

video-editor 프로젝트에서 검증된 파이프라인 이식:
저조도 적응 감마 + CLAHE → L채널 셀 양자화 → DoG 잉크 라인.

backend(1프레임 미리보기)와 worker(전체 영상 변환, `cartoonize_video`)가 공유한다.
cv2/numpy 외 앱 의존성을 두지 않는다 — worker가 이 모듈을 단독 import한다.
"""

import logging
import multiprocessing as mp
import os
import subprocess
import tempfile
import threading

import cv2
import numpy as np

logger = logging.getLogger(__name__)

LINE_BGR = np.array([45, 42, 48], np.uint16)  # 카툰 윤곽선 (잉크)

# L채널 셀 양자화 LUT: 0.8*(round(L/42.5)*42.5) + 0.2*L — 6단계 소프트 양자화
_CEL_LUT = np.clip(
    0.8 * (np.round(np.arange(256, dtype=np.float32) / 42.5) * 42.5)
    + 0.2 * np.arange(256, dtype=np.float32),
    0,
    255,
).astype(np.uint8)

# NlMeans 등 OpenCV 연산은 멀티스레드 확장성이 낮아(10코어 ~1.4x) 프레임 단위
# 프로세스 병렬화가 효과적이다. 워커는 OpenCV 내부 스레딩을 꺼서 과다구독을 막는다.


def _worker_pool_size() -> int:
    """호출 시점의 병렬 프로세스 수. FFMPEG_ACTIVE_JOBS(현재 활성 잡 수 — worker.py가
    슬롯 획득 직후와 렌더 단계 진입 시 갱신)가 있으면 그 값으로, 없으면(단독 실행·테스트)
    WORKER_INSTANCES(정적 인스턴스 수)로 코어를 나눈다.

    잡마다 값이 바뀌므로 모듈 임포트 시점이 아니라 매 호출 시점에 읽는다 — 정적
    WORKER_INSTANCES 나눗셈은 "모든 인스턴스가 항상 바쁘다"고 가정해 잡이 하나뿐일
    때도 코어를 남겨뒀다(예: 8코어·2인스턴스 → 잡 1개뿐이어도 3개만 사용).

    한계: 이 값은 렌더 시작 시점의 스냅샷이다. 렌더가 도는 도중 다른 잡이 합류하면
    그 잡은 자기 시점 기준으로 풀을 잡으므로 일시적으로 총 프로세스 수가 코어 예산을
    넘을 수 있다(8코어·2잡 겹침 최악 6+3=9). CPU는 CFS가 나눠주므로 둘 다 느려질 뿐
    실패하지는 않는다 — 렌더 중 재조회로 풀을 줄이려면 이미 spawn된 프로세스를
    죽여야 해서 얻는 것보다 잃는 게 크다고 판단해 스냅샷으로 둔다.
    """
    active = os.environ.get("FFMPEG_ACTIVE_JOBS") or os.environ.get("WORKER_INSTANCES", "1")
    return max(1, ((os.cpu_count() or 4) - 2) // max(1, int(active)))


_CHUNK = 16  # 청크 단위 map: 전 프레임을 메모리에 들고 있지 않도록 제한
_MIN_SEGMENT_FRAMES = 90  # ~3초@30fps 미만은 분할 실익이 없음(프로세스 기동비용이 더 큼)
# 구간 경계 예열 프레임 수 — 감마 EMA 워밍업용. EMA가 `_GAMMA_SAMPLE_EVERY`마다만 갱신되므로
# 60프레임 ≈ 12회 갱신이 필요하다(24프레임이면 경계 감마가 최대 0.12 어긋나 밝기가 튄다).
# 예열 구간은 디코딩과 감마 계산만 하고 렌더는 건너뛴다. 반드시 본문과 같은 샘플링 주기를
# 써야 한다 — 주기가 다르면 EMA 응답이 달라져 예열을 늘려도 수렴하지 않는다.
_SEG_PAD_FRAMES = 60
_GAMMA_SAMPLE_EVERY = 5  # 감마 재계산 주기(프레임). 노출은 연속적이라 매 프레임 잴 필요가 없다


def adaptive_gamma(frame: np.ndarray) -> float:
    """저조도 프레임을 밝히는 감마를 평균 휘도에서 추정한다 (밝은 영상은 ~1.0)."""
    mean = float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean())
    if mean < 1.0:
        return 0.4
    # 평균 휘도를 ~115로 끌어올리는 감마: mean**g = 115
    g = np.log(115.0 / 255.0) / np.log(mean / 255.0)
    return float(np.clip(g, 0.4, 1.0))


def _enhance(frame: np.ndarray, gamma: float = 1.0, clip: float = 2.0) -> np.ndarray:
    """저조도 대응 전처리: 감마 리프트 + CLAHE(L채널).

    NlMeans 디노이즈는 이후 bilateral filter + 셀 양자화가 잔여 노이즈를 마저
    뭉개버려 최종 출력에 거의 기여하지 않아 제거함(벤치마크: 프레임당 최대 ~65% 단축).
    """
    if gamma < 0.99:
        lut = (np.linspace(0, 1, 256) ** gamma * 255).astype(np.uint8)
        frame = cv2.LUT(frame, lut)
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    light, a, b = cv2.split(lab)
    light = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8)).apply(light)
    return cv2.cvtColor(cv2.merge([light, a, b]), cv2.COLOR_LAB2BGR)


def cartoon_frame(frame: np.ndarray, gamma: float = 1.0) -> np.ndarray:
    """셀 셰이딩 카툰: 저조도 보정 + 적응 채도 + L채널 셀 양자화 + DoG 잉크 라인."""
    h, w = frame.shape[:2]
    den = _enhance(frame, gamma=gamma)

    # 적응 채도: 이미 쨍한 프레임은 덜 올린다
    hsv = cv2.cvtColor(den, cv2.COLOR_BGR2HSV)
    boost = 1.0 + 0.5 * max(0.0, 1.0 - float(hsv[:, :, 1].mean()) / 120.0)
    hsv[:, :, 1] = np.clip(hsv[:, :, 1].astype(np.float32) * boost, 0, 255).astype(np.uint8)
    sat = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    small = cv2.resize(sat, (max(2, w // 2), max(2, h // 2)), interpolation=cv2.INTER_AREA)
    small = cv2.bilateralFilter(small, 9, 75, 75)
    smooth = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    # 셀 셰이딩: L만 6단계 소프트 양자화 (경계 깜빡임·밴딩 완화), 색은 부드럽게 유지.
    # L은 uint8이라 양자화식이 256개 값의 순수 함수 — 전체 이미지를 float32로 올리는 대신
    # 미리 만든 LUT를 태운다(결과 동일, ~63% 단축).
    lab = cv2.cvtColor(smooth, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = cv2.LUT(np.ascontiguousarray(lab[:, :, 0]), _CEL_LUT)
    cel = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    # 잉크 라인: DoG → 이진화 → 소성분 제거 → 살짝 두껍게 → 소프트 블렌드
    gray = cv2.cvtColor(den, cv2.COLOR_BGR2GRAY)
    g1 = cv2.GaussianBlur(gray, (0, 0), 1.4)
    g2 = cv2.GaussianBlur(gray, (0, 0), 3.0)
    _, line_mask = cv2.threshold(cv2.subtract(g1, g2), 4, 255, cv2.THRESH_BINARY)
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    _, labels, stats, _ = cv2.connectedComponentsWithStats(line_mask, 8)
    # 컴포넌트별 Python 루프(`labels == i`)는 성분 수만큼 전체 이미지를 훑어
    # 1080x1920·성분 800개 기준 프레임당 ~330ms(전체의 60%)를 잡아먹었다.
    # 면적 조건을 라벨 LUT로 바꿔 한 번의 인덱싱으로 처리한다(결과는 픽셀 단위 동일).
    keep = stats[:, cv2.CC_STAT_AREA] >= 14
    keep[0] = False  # 배경 라벨
    line_mask = np.where(keep[labels], np.uint8(255), np.uint8(0))
    line_mask = cv2.dilate(line_mask, np.ones((2, 2), np.uint8))
    # half-res(σ/면적임계 절반 재조정)로 계산하는 실험을 실측했으나 텍스트/세부선이
    # 점묘화·단절되는 화질 저하가 뚜렷해 폐기했다(ponytail: 속도보다 화질 우선, 재시도 시
    # DoG 입력을 half-res로 낮추지 말고 connectedComponents 단계만 최적화할 것).
    # 소프트 블렌드를 uint16 정수 연산으로 처리 (float32 대비 ~27% 단축).
    # 반올림 방식 차이로 float 버전과 최대 1레벨 오차가 날 수 있으나 육안 식별 불가.
    alpha = cv2.GaussianBlur(line_mask, (3, 3), 0).astype(np.uint16)[..., None]
    out = (cel.astype(np.uint16) * (255 - alpha) + LINE_BGR * alpha) // 255
    return out.astype(np.uint8)


def _worker_init() -> None:
    cv2.setNumThreads(1)


def _render_one(args: tuple[np.ndarray, float]) -> np.ndarray:
    frame, gamma = args
    return cartoon_frame(frame, gamma)


def _sample_gamma(frame: np.ndarray, gamma_ema: float | None, frame_idx: int) -> float:
    """감마를 `_GAMMA_SAMPLE_EVERY` 프레임마다만 재계산하고 EMA로 스무딩한다.

    `adaptive_gamma`는 프레임 전체를 그레이로 변환해 평균을 내므로 공짜가 아닌데,
    노출은 연속적으로 변하고 EMA가 이미 스무딩하고 있어 매 프레임 잴 필요가 없다.
    (샘플링 주기가 길어진 만큼 EMA 추종이 느려지는데, 이는 깜빡임 억제에 오히려 유리하다.)
    """
    if gamma_ema is not None and frame_idx % _GAMMA_SAMPLE_EVERY:
        return gamma_ema
    g = adaptive_gamma(frame)
    return g if gamma_ema is None else 0.9 * gamma_ema + 0.1 * g


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


def _render_cartoon_segment(args: tuple) -> tuple[int, str]:
    """구간 하나를 카툰 변환해 비디오 전용(오디오 없음) mp4로 저장. (프레임 수, seg_path) 반환.

    pad_start부터 읽어 감마 EMA를 예열시키고 start 이후 프레임만 ffmpeg에 쓴다 —
    구간 경계에서 EMA가 0부터 다시 쌓이며 밝기가 튀는 것을 막기 위함.
    """
    input_path, start, end, pad_start, out_w, out_h, fps, seg_path = args
    cv2.setNumThreads(1)
    # x264 -threads auto는 코어당 ~1.5개 프레임 스레드를 띄운다. 구간마다 인코더가 하나씩
    # 떠서(k개) 렌더 프로세스 수와 별개로 코어를 오버섭스크립션한다 — 2로 고정.

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {input_path}")
    if pad_start > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, pad_start)

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

    processed = 0
    gamma_ema: float | None = None
    frame_idx = pad_start
    try:
        while frame_idx < end:
            ok, frame = cap.read()
            if not ok:
                break
            if (frame.shape[1], frame.shape[0]) != (out_w, out_h):
                frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
            gamma_ema = _sample_gamma(frame, gamma_ema, frame_idx - pad_start)
            if frame_idx >= start:
                proc.stdin.write(cartoon_frame(frame, gamma_ema).tobytes())
                processed += 1
            frame_idx += 1
    finally:
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


def cartoonize_video(input_path: str, output_path: str) -> None:
    """영상 전체를 카툰 변환한다. 원본 오디오 스트림은 그대로 보존(-c:a copy).

    프레임 수가 `_MIN_SEGMENT_FRAMES` 이상이면 영상을 `_worker_pool_size()`개 구간으로 나눠
    프로세스 풀로 병렬 렌더링한다 — 카툰 변환은 프레임 단위로 독립적이라 구간별로 디코딩·렌더링·
    인코딩을 통째로 병렬화할 수 있고, 그러면 부모 프로세스가 홀로 하던 디코딩과 raw 파이프
    쓰기(1080x1920 기준 프레임당 6.2MB)까지 함께 분산된다.
    짧은 영상은 구간 분할 실익이 없어 기존 프레임 단위 병렬 경로를 그대로 쓴다.
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {input_path}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    # yuv420p는 짝수 해상도 필요
    out_w, out_h = w - w % 2, h - h % 2
    if out_w < 2 or out_h < 2:
        cap.release()
        raise ValueError(f"video too small: {w}x{h}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # 컨테이너가 프레임 수를 신뢰할 수 없게 보고하면(0 이하) 안전하게 프레임 병렬로 폴백.
    k = min(_worker_pool_size(), max(1, frame_count // _MIN_SEGMENT_FRAMES)) if frame_count > 0 else 1
    if k <= 1:
        _cartoonize_frame_parallel(input_path, output_path, out_w, out_h, fps)
        return

    try:
        segments = _plan_segments(frame_count, k)
        with tempfile.TemporaryDirectory() as tmpdir:
            seg_args = [
                (input_path, start, end, pad_start, out_w, out_h, fps,
                 os.path.join(tmpdir, f"seg_{i}.mp4"))
                for i, (start, end, pad_start) in enumerate(segments)
            ]
            pool = mp.get_context("spawn").Pool(k)
            try:
                results = pool.map(_render_cartoon_segment, seg_args)
            finally:
                pool.terminate()
                pool.join()
            _concat_and_mux([p for _, p in results], input_path, output_path)
    except Exception:
        # 구간 분할은 컨테이너가 보고한 프레임 수에 의존한다 — 값이 부정확하면 구간이
        # 어긋나 실패한다. 프레임 병렬 경로는 EOF까지 읽으므로 그 영향을 받지 않는다.
        # 잡 전체를 실패시키는 대신 느리지만 확실한 경로로 되돌린다.
        logger.warning(
            "cartoonize_video: 구간 병렬 실패 → 프레임 병렬로 폴백 (frames=%d, k=%d)",
            frame_count, k, exc_info=True,
        )
        _cartoonize_frame_parallel(input_path, output_path, out_w, out_h, fps)
        return

    processed = sum(n for n, _ in results)
    logger.info(
        "cartoonize_video: %d frames in %d segments → %s", processed, len(segments), output_path
    )


def _cartoonize_frame_parallel(
    input_path: str, output_path: str, out_w: int, out_h: int, fps: float
) -> None:
    """짧은 영상용 경로: 프레임을 프로세스 풀로 병렬 렌더링하고 단일 ffmpeg로 인코딩한다.

    ffmpeg 2입력(raw 비디오 파이프 + 원본 파일의 오디오)으로 재합성한다.
    오디오가 없는 입력도 동작한다(1:a?).
    """
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise ValueError(f"cannot open video: {input_path}")

    # -threads 2: 이 경로는 아래에서 _worker_pool_size()개 렌더 프로세스를 동시에 띄운다
    # (구간 병렬과 동일한 오버섭스크립션 — x264 auto는 코어당 ~1.5스레드).
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{out_w}x{out_h}",
        "-r", f"{fps:.6f}", "-i", "-",
        "-i", input_path,
        "-map", "0:v", "-map", "1:a?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "28", "-threads", "2",
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
    read_idx = 0
    gamma_ema: float | None = None
    pool = mp.get_context("spawn").Pool(_worker_pool_size(), initializer=_worker_init)
    try:
        while True:
            batch: list[tuple[np.ndarray, float]] = []
            while len(batch) < _CHUNK:
                ok, frame = cap.read()
                if not ok:
                    break
                if (frame.shape[1], frame.shape[0]) != (out_w, out_h):
                    frame = cv2.resize(frame, (out_w, out_h), interpolation=cv2.INTER_AREA)
                # 감마 EMA: 프레임별 노출 변화로 밝기가 깜빡이지 않게 스무딩
                gamma_ema = _sample_gamma(frame, gamma_ema, read_idx)
                read_idx += 1
                batch.append((frame, gamma_ema))
            if not batch:
                break
            for canvas in pool.map(_render_one, batch):
                proc.stdin.write(canvas.tobytes())
                processed += 1
    finally:
        pool.terminate()
        pool.join()
        cap.release()
        proc.stdin.close()
        code = proc.wait()
        stderr_thread.join(timeout=5)

    if code != 0:
        stderr = b"".join(stderr_chunks).decode(errors="replace")
        raise RuntimeError(f"ffmpeg encode failed (exit {code}): {stderr[-500:]}")
    if processed == 0:
        raise ValueError("no frames decoded from input video")
    logger.info("cartoonize_video: %d frames → %s", processed, output_path)
