import json
import logging
import os
import re
import secrets
import subprocess
import tempfile
import time
import uuid

import boto3
from botocore.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import (
    DATABASE_URL,
    R2_ACCESS_KEY_ID,
    R2_ACCOUNT_ID,
    R2_BUCKET_NAME,
    R2_PUBLIC_URL,
    R2_SECRET_ACCESS_KEY,
)
from tasks.image_merge import run_image_merge
from tasks.subtitle import (
    ALIGNMENT_MAP,
    FONT_SIZE_MAP,
    MARGIN_V_MAP,
    SubtitleResult,
    burn_user_srt,
    subtitle_metrics_json,
)

logger = logging.getLogger(__name__)

_BASE62 = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _generate_share_token(user_id: int) -> str:
    ts_sec = int(time.time())
    rand = secrets.randbits(16)
    n = (ts_sec << 26) | ((user_id & 0x3FF) << 16) | rand
    chars: list[str] = []
    while n:
        chars.append(_BASE62[n % 62])
        n //= 62
    return "".join(reversed(chars))

_connect_args = {"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
_engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=_engine)


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _make_tmp(suffix: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        return f.name


def _probe_video_duration(path: str) -> float:
    """ffprobe로 비디오 파일의 길이(초)를 반환. 실패하면 0.0."""
    for extra in [
        ["-select_streams", "v:0", "-show_entries", "stream=duration"],
        ["-show_entries", "format=duration"],
    ]:
        result = subprocess.run(
            ["ffprobe", "-v", "error"] + extra + ["-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            raw = result.stdout.strip()
            if raw and raw != "N/A":
                try:
                    val = float(raw)
                    if val > 0:
                        return val
                except ValueError:
                    pass
    return 0.0


def _probe_audio_duration(path: str) -> float:
    """오디오 파일의 실제 길이(초)를 반환. 컨테이너 메타 → 디코드 패스 순으로 시도, 실패하면 0.0.

    MediaRecorder가 만든 webm은 컨테이너에 duration이 기록되지 않아 메타 probe가 N/A를 반환한다.
    그 경우 디코드 패스(ffmpeg -f null)로 실제 재생 길이를 측정한다.
    """
    for extra in (
        ["-show_entries", "format=duration"],
        ["-select_streams", "a:0", "-show_entries", "stream=duration"],
    ):
        result = subprocess.run(
            ["ffprobe", "-v", "error"] + extra + ["-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            raw = result.stdout.strip()
            if raw and raw != "N/A":
                try:
                    val = float(raw)
                    if val > 0:
                        return val
                except ValueError:
                    pass
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", path, "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
        matches = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
        if matches:
            h, m, s = matches[-1]
            total = int(h) * 3600 + int(m) * 60 + float(s)
            if total > 0:
                return total
    except Exception:
        pass
    return 0.0


def _audio_merge(r2, video_key: str, audio_key: str, duration: float, audio_suffix: str) -> str | None:
    """Audio+video merge. Returns merged r2_key or None on failure."""
    tmp_video = tmp_audio = tmp_output = None
    try:
        tmp_video = _make_tmp(".mp4")
        tmp_audio = _make_tmp(audio_suffix)
        tmp_output = _make_tmp(".mp4")

        resp = r2.get_object(Bucket=R2_BUCKET_NAME, Key=video_key)
        with open(tmp_video, "wb") as f:
            f.write(resp["Body"].read())

        resp = r2.get_object(Bucket=R2_BUCKET_NAME, Key=audio_key)
        with open(tmp_audio, "wb") as f:
            f.write(resp["Body"].read())

        video_duration = _probe_video_duration(tmp_video)
        probed_audio = _probe_audio_duration(tmp_audio)
        # 클라이언트가 보낸 audio_duration_sec(1초 단위 카운터)는 부정확하므로 실제 오디오를 probe한다.
        # probe 실패 시에만 클라이언트 값으로 fallback.
        audio_duration = probed_audio if probed_audio > 0 else duration
        output_duration = max(video_duration, audio_duration) if video_duration > 0 else audio_duration
        logger.info(
            "audio_merge: video=%.2fs audio=%.2fs(probed=%.2f client=%.2f) output=%.2fs",
            video_duration, audio_duration, probed_audio, duration, output_duration,
        )

        if video_duration > 0 and video_duration >= audio_duration:
            # video가 더 길거나 같음: audio는 재생 후 무음, video는 copy
            cmd = [
                "ffmpeg", "-y",
                "-i", tmp_video,
                "-i", tmp_audio,
                "-t", str(video_duration),
                "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
                "-map", "0:v:0", "-map", "1:a:0",
                "-movflags", "+faststart",
                tmp_output,
            ]
        else:
            # audio가 더 길거나 probe 실패: video를 루프, audio는 그대로
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", tmp_video,
                "-i", tmp_audio,
                "-t", str(output_duration),
                "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
                "-map", "0:v:0", "-map", "1:a:0",
                "-movflags", "+faststart",
                tmp_output,
            ]

        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg audio merge: {result.stderr.decode()[:500]}")

        merged_key = f"videos/merged-{uuid.uuid4()}.mp4"
        with open(tmp_output, "rb") as f:
            r2.put_object(Bucket=R2_BUCKET_NAME, Key=merged_key, Body=f, ContentType="video/mp4",
                          CacheControl="public, max-age=31536000, immutable")
        return merged_key
    except Exception as e:
        logger.warning("Audio merge failed: %s", e)
        return None
    finally:
        for tmp in [tmp_video, tmp_audio, tmp_output]:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)




def _extract_thumbnail(r2, video_key: str) -> str | None:
    """mp4 첫 프레임을 320px JPEG로 추출 (30KB 이하 보장) 후 R2에 업로드."""
    import io as _io
    from PIL import Image as _Image

    tmp_video = tmp_thumb = None
    try:
        tmp_video = _make_tmp(".mp4")
        tmp_thumb = _make_tmp(".jpg")

        resp = r2.get_object(Bucket=R2_BUCKET_NAME, Key=video_key)
        with open(tmp_video, "wb") as f:
            f.write(resp["Body"].read())

        duration = _probe_video_duration(tmp_video)
        seek = min(1.0, duration * 0.1) if duration > 0 else 0.0

        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(seek),
                "-i", tmp_video,
                "-vframes", "1",
                "-vf", "scale=240:-2",
                "-q:v", "5",
                tmp_thumb,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0 or not os.path.getsize(tmp_thumb):
            raise RuntimeError(f"ffmpeg thumbnail: {result.stderr.decode()[:300]}")

        # Pillow로 15KB 이하 보장 (품질 단계적 감소)
        img = _Image.open(tmp_thumb).convert("RGB")
        buf = _io.BytesIO()
        for quality in (70, 55, 45):
            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            if buf.tell() <= 15 * 1024:
                break
        buf.seek(0)

        thumb_key = f"thumbnails/t-{uuid.uuid4()}.jpg"
        r2.put_object(
            Bucket=R2_BUCKET_NAME,
            Key=thumb_key,
            Body=buf,
            ContentType="image/jpeg",
            CacheControl="public, max-age=31536000, immutable",
        )
        return thumb_key
    except Exception as e:
        logger.warning("Thumbnail extraction failed: %s", e)
        return None
    finally:
        for tmp in [tmp_video, tmp_thumb]:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)


def _probe_video_meta(path: str) -> dict:
    """ffprobe로 video_meta(width/height/fps/codec/duration_sec) 추출. 실패 시 빈 dict.

    subprocess.run도 반드시 try 안에 둔다 — 밖에 두면 TimeoutExpired/FileNotFoundError가
    그대로 전파되고, 이 함수를 부르는 `_apply_video_filter`의 except가 그걸 삼켜
    filter_status="failed"로 만든다. 즉 ffprobe 타임아웃 하나 때문에 이미 성공한 수 분짜리
    필터 렌더 결과물이 통째로 버려지고 compress 폴백으로 떨어진다.
    """
    try:
        meta_probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate,codec_name:format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=15,
        )
        probe_data = json.loads(meta_probe.stdout)
        stream = probe_data.get("streams", [{}])[0]
        fmt = probe_data.get("format", {})
        fps_raw = stream.get("r_frame_rate", "0/1")
        num, den = (fps_raw.split("/") + ["1"])[:2]
        fps = round(int(num) / max(int(den), 1), 1)
        return {
            "width": stream.get("width", 0),
            "height": stream.get("height", 0),
            "fps": fps,
            "codec": stream.get("codec_name", ""),
            "duration_sec": round(float(fmt.get("duration", 0)), 1),
        }
    except Exception:
        return {}


def _compress_video(r2, video_key: str, mute_video: bool = False) -> tuple[str, int, int, dict] | None:
    """Re-encode video to reduce file size (CRF 28, ultrafast).
    Returns (compressed_key, pre_bytes, post_bytes, video_meta) or None if no benefit / failure.
    """
    tmp_input = tmp_output = None
    try:
        tmp_input = _make_tmp(".mp4")
        tmp_output = _make_tmp(".mp4")

        resp = r2.get_object(Bucket=R2_BUCKET_NAME, Key=video_key)
        with open(tmp_input, "wb") as f:
            f.write(resp["Body"].read())

        pre_bytes = os.path.getsize(tmp_input)

        probe_a = subprocess.run(
            ["ffprobe", "-v", "quiet", "-select_streams", "a:0",
             "-show_entries", "stream=codec_type", "-of", "csv=p=0", tmp_input],
            capture_output=True, text=True, timeout=30,
        )
        has_audio = bool(probe_a.stdout.strip())

        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1,format=yuv420p"
        cmd = [
            "ffmpeg", "-y",
            "-i", tmp_input,
            "-vf", vf,
            "-vcodec", "libx264", "-crf", "28", "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
        ]
        cmd += ["-an"] if (mute_video or not has_audio) else ["-c:a", "aac", "-b:a", "96k"]
        cmd += ["-movflags", "+faststart", tmp_output]

        result = subprocess.run(cmd, capture_output=True, timeout=180)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg compress: {result.stderr.decode()[-800:]}")

        post_bytes = os.path.getsize(tmp_output)
        video_meta = _probe_video_meta(tmp_output)

        if post_bytes >= pre_bytes:
            logger.info("[compress] 압축 효과 없음 (%dB → %dB), 원본 유지", pre_bytes, post_bytes)
            return None

        compressed_key = f"videos/c-{uuid.uuid4()}.mp4"
        with open(tmp_output, "rb") as f:
            r2.put_object(Bucket=R2_BUCKET_NAME, Key=compressed_key, Body=f, ContentType="video/mp4",
                          CacheControl="public, max-age=31536000, immutable")
        return compressed_key, pre_bytes, post_bytes, video_meta
    except Exception as e:
        logger.warning("Video compression failed (using original): %s", e)
        return None
    finally:
        for tmp in [tmp_input, tmp_output]:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)


def run_full_pipeline(job: dict, status_callback=None) -> dict:
    """Full upload pipeline: optional merges → DB commit."""
    from app.models.post import Post
    from app.models.user import User
    from app.models.video import Video
    from app.routes.challenges import increment_challenge_upload
    from app.services.reward import DAILY_MAX_UPLOADS, add_points, get_daily_upload_count, points_for_tags

    start_time = time.time()
    r2 = _get_r2_client()
    current_key: str = job["r2_key"]
    final_proof_url: str | None = job.get("proof_cdn_url")
    user_id: int = int(job["user_id"])
    job_id: str = job["job_id"]

    has_audio_merged = False
    has_image_merged = False
    audio_merge_failed = False
    subtitle_status = "skipped"
    subtitle_url: str | None = None
    subtitle_text: str | None = None
    subtitle_error: str | None = None
    subtitle_metrics: str | None = None

    # 원본 키는 처리 전 값으로 고정 — 이후 current_key가 변해도 유지
    original_video_r2_key: str = job["r2_key"]
    audio_r2_key: str | None = job.get("audio_r2_key")
    original_audio_r2_key: str | None = audio_r2_key
    if audio_r2_key:
        if status_callback:
            status_callback("audio_merge")
        audio_content_type = job.get("audio_content_type", "audio/webm")
        audio_suffix = ".mp4" if audio_content_type == "audio/mp4" else ".webm"
        merged = _audio_merge(r2, current_key, audio_r2_key, float(job.get("audio_duration_sec", 0)), audio_suffix)
        if merged:
            current_key = merged
            has_audio_merged = True
            logger.info("[full-pipeline] job=%s audio merged → %s", job_id, current_key)
        else:
            # 오디오 머지 실패를 추적해 알림/잡 상태로 노출(조용한 보이스오버 유실 방지)
            audio_merge_failed = True
            logger.warning("[full-pipeline] job=%s 오디오 머지 실패 — 오디오 없이 진행", job_id)

    proof_r2_key: str | None = job.get("proof_r2_key")
    if proof_r2_key:
        if status_callback:
            status_callback("image_merge")
        final_proof_url = f"{R2_PUBLIC_URL}/{proof_r2_key}"
        try:
            merge_result = run_image_merge({"video_r2_key": current_key, "proof_r2_key": proof_r2_key})
        except Exception as e:
            raise RuntimeError("증거 사진 이미지 머지 실패 — 업로드 취소") from e
        if current_key != original_video_r2_key:
            try:
                r2.delete_object(Bucket=R2_BUCKET_NAME, Key=current_key)
            except Exception:
                pass
        current_key = merge_result["output_r2_key"]
        has_image_merged = True
        logger.info("[full-pipeline] job=%s proof merged → %s", job_id, current_key)

    pre_compress_key = current_key
    pre_size_bytes: int = 0
    post_size_bytes: int = 0
    video_meta: dict = {}
    compressed_key: str | None = None
    mute_video_audio = bool(job.get("mute_video_audio", False))
    if status_callback:
        status_callback("compress")
    compress_result = _compress_video(r2, current_key, mute_video=mute_video_audio)
    if compress_result:
        compressed_key, pre_size_bytes, post_size_bytes, video_meta = compress_result
        if pre_compress_key != original_video_r2_key:
            try:
                r2.delete_object(Bucket=R2_BUCKET_NAME, Key=pre_compress_key)
            except Exception:
                pass
        current_key = compressed_key
        logger.info("[full-pipeline] job=%s compressed → %s (%dB → %dB)", job_id, current_key, pre_size_bytes, post_size_bytes)

    # 일일 한도 체크 — 썸네일 추출 전에 검사해 orphan 방지
    if status_callback:
        status_callback("db_save")
    db = SessionLocal()
    try:
        if get_daily_upload_count(db, user_id) >= DAILY_MAX_UPLOADS:
            raise RuntimeError("하루 업로드 한도 초과")
    finally:
        db.close()

    if status_callback:
        status_callback("thumbnail")
    thumb_key = _extract_thumbnail(r2, current_key)
    thumbnail_cdn_url: str | None = f"{R2_PUBLIC_URL}/{thumb_key}" if thumb_key else None
    if thumb_key:
        logger.info("[full-pipeline] job=%s thumbnail → %s", job_id, thumb_key)

    if status_callback:
        status_callback("subtitle")
    pre_subtitle_key = current_key

    subtitle_srt_r2_key = job.get("subtitle_srt_r2_key")
    subtitle_font_size = FONT_SIZE_MAP.get(job.get("subtitle_size") or "small", 14)
    subtitle_alignment = ALIGNMENT_MAP.get(job.get("subtitle_position", "bottom"), 2)
    subtitle_margin_v = MARGIN_V_MAP.get(job.get("subtitle_position", "bottom"), 90)

    if subtitle_srt_r2_key:
        subtitle_result = burn_user_srt(
            r2, current_key, subtitle_srt_r2_key,
            font_size=subtitle_font_size,
            alignment=subtitle_alignment,
            margin_v=subtitle_margin_v,
        )
    else:
        subtitle_result = SubtitleResult(status="skipped", error="no user-provided subtitle")

    subtitle_status = subtitle_result.status
    subtitle_url = subtitle_result.subtitle_url
    subtitle_text = subtitle_result.subtitle_text
    subtitle_error = subtitle_result.error
    subtitle_metrics = subtitle_metrics_json(subtitle_result)
    if subtitle_status == "completed" and subtitle_result.burned_video_r2_key:
        current_key = subtitle_result.burned_video_r2_key
        if pre_subtitle_key != original_video_r2_key:
            try:
                r2.delete_object(Bucket=R2_BUCKET_NAME, Key=pre_subtitle_key)
            except Exception:
                pass
        logger.info("[full-pipeline] job=%s subtitle burn-in → %s", job_id, current_key)
    elif subtitle_status == "completed":
        subtitle_status = "failed"
        subtitle_error = "subtitle burn-in did not produce a video"
        logger.warning("[full-pipeline] job=%s subtitle failed — upload continues: %s", job_id, subtitle_error)
    elif subtitle_status == "failed":
        logger.warning("[full-pipeline] job=%s subtitle failed — upload continues: %s", job_id, subtitle_error)
    else:
        logger.info("[full-pipeline] job=%s subtitle skipped: %s", job_id, subtitle_error)

    if status_callback:
        status_callback("db_save")
    db = SessionLocal()
    try:
        cdn_url = f"{R2_PUBLIC_URL}/{current_key}"

        video = Video(
            user_id=user_id,
            r2_key=current_key,
            cdn_url=cdn_url,
            file_hash=job["file_hash"],
            duration_sec=min(60, max(5, int(job.get("duration_sec", 15)))),
            subtitle_url=subtitle_url,
            subtitle_text=subtitle_text,
            subtitle_status=subtitle_status,
            subtitle_error=subtitle_error,
            subtitle_metrics=subtitle_metrics,
            original_video_r2_key=original_video_r2_key,
            original_audio_r2_key=original_audio_r2_key,
        )
        db.add(video)
        db.flush()

        challenge_id = job.get("challenge_id")
        post = Post(
            video_id=video.id,
            user_id=user_id,
            caption=job.get("caption"),
            tags=json.dumps(job.get("tags", []), ensure_ascii=False),
            workout_start=job.get("workout_start"),
            workout_end=job.get("workout_end"),
            proof_image_url=final_proof_url,
            thumbnail_url=thumbnail_cdn_url,
            share_token=_generate_share_token(user_id),
            challenge_id=int(challenge_id) if challenge_id is not None else None,
        )
        db.add(post)
        db.flush()

        if challenge_id is not None:
            increment_challenge_upload(db, user_id, int(challenge_id))

        rp = add_points(
            db, user_id, points_for_tags(job.get("tags", [])), "upload",
            reference_id=video.id,
        )
        points_earned = rp.points if rp else 0.0

        user = db.query(User).filter(User.id == user_id).first()
        username = user.username if user else str(user_id)
        email = user.email if user else ""

        db.commit()
        elapsed_sec = time.time() - start_time
        if has_audio_merged and has_image_merged:
            merge_type = "video + audio + image"
        elif has_image_merged:
            merge_type = "video + image"
        elif has_audio_merged:
            merge_type = "video + audio"
        else:
            merge_type = "video"
        logger.info("[full-pipeline] job=%s 완료, post_id=%s points=%s elapsed=%.1fs", job_id, post.id, points_earned, elapsed_sec)
        return {
            "post_id": str(post.id),
            "cdn_url": cdn_url,
            "points_earned": str(points_earned),
            "username": username,
            "email": email or "",
            "elapsed_sec": round(elapsed_sec, 1),
            "pre_size_bytes": pre_size_bytes,
            "post_size_bytes": post_size_bytes,
            "video_meta": video_meta,
            "merge_type": merge_type,
            "audio_merge_failed": audio_merge_failed,
            "subtitle_status": subtitle_status,
            "subtitle_url": subtitle_url or "",
            "subtitle_text": subtitle_text or "",
            "subtitle_error": subtitle_error or "",
        }
    except Exception:
        # DB 실패 시 압축된 c- 파일이 R2에 고아로 남지 않도록 정리
        if compressed_key:
            try:
                r2.delete_object(Bucket=R2_BUCKET_NAME, Key=compressed_key)
                logger.info("[full-pipeline] job=%s 실패 — 고아 c- 파일 삭제: %s", job_id, compressed_key)
            except Exception:
                pass
        raise
    finally:
        db.close()
