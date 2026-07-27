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
import threading

import cv2
import numpy as np

logger = logging.getLogger(__name__)

LINE_BGR = np.array([45, 42, 48], np.float32)  # 카툰 윤곽선 (잉크)

# NlMeans 등 OpenCV 연산은 멀티스레드 확장성이 낮아(10코어 ~1.4x) 프레임 단위
# 프로세스 병렬화가 효과적이다. 워커는 OpenCV 내부 스레딩을 꺼서 과다구독을 막는다.
# WORKER_INSTANCES(동시에 띄운 worker.py 개수)로 나눠, 여러 인스턴스가 동시에 무거운
# job을 처리해도 총 프로세스 수가 코어 수를 넘지 않게 한다 (기본 1 = 인스턴스 1개).
_WORKER_INSTANCES = max(1, int(os.environ.get("WORKER_INSTANCES", "1")))
_WORKERS = max(1, ((os.cpu_count() or 4) - 2) // _WORKER_INSTANCES)
_CHUNK = 16  # 청크 단위 map: 전 프레임을 메모리에 들고 있지 않도록 제한


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

    # 셀 셰이딩: L만 6단계 소프트 양자화 (경계 깜빡임·밴딩 완화), 색은 부드럽게 유지
    lab = cv2.cvtColor(smooth, cv2.COLOR_BGR2LAB).astype(np.float32)
    lum = lab[:, :, 0]
    lab[:, :, 0] = 0.8 * (np.round(lum / 42.5) * 42.5) + 0.2 * lum
    cel = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2BGR)

    # 잉크 라인: DoG → 이진화 → 소성분 제거 → 살짝 두껍게 → 소프트 블렌드
    gray = cv2.cvtColor(den, cv2.COLOR_BGR2GRAY)
    g1 = cv2.GaussianBlur(gray, (0, 0), 1.4)
    g2 = cv2.GaussianBlur(gray, (0, 0), 3.0)
    _, line_mask = cv2.threshold(cv2.subtract(g1, g2), 4, 255, cv2.THRESH_BINARY)
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(line_mask, 8)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] < 14:
            line_mask[labels == i] = 0
    line_mask = cv2.dilate(line_mask, np.ones((2, 2), np.uint8))
    alpha = (cv2.GaussianBlur(line_mask, (3, 3), 0).astype(np.float32) / 255.0)[..., None]
    out = cel.astype(np.float32) * (1 - alpha) + LINE_BGR * alpha
    return out.astype(np.uint8)


def _worker_init() -> None:
    cv2.setNumThreads(1)


def _render_one(args: tuple[np.ndarray, float]) -> np.ndarray:
    frame, gamma = args
    return cartoon_frame(frame, gamma)


def cartoonize_video(input_path: str, output_path: str) -> None:
    """영상 전체를 카툰 변환한다. 원본 오디오 스트림은 그대로 보존(-c:a copy).

    프레임을 프로세스 풀로 병렬 렌더링하고, ffmpeg 2입력(raw 비디오 파이프 +
    원본 파일의 오디오)으로 재합성한다. 오디오가 없는 입력도 동작한다(0:a?).
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
    gamma_ema: float | None = None
    pool = mp.get_context("spawn").Pool(_WORKERS, initializer=_worker_init)
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
                g = adaptive_gamma(frame)
                gamma_ema = g if gamma_ema is None else 0.9 * gamma_ema + 0.1 * g
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
