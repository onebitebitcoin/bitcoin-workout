"""다중 미디어 업로드 파이프라인 (영상 ≤1 + 이미지 ≤N).

기존 `run_full_pipeline`(단일 영상 경로)은 일절 수정하지 않는다.
이 모듈은 `full_pipeline`의 검증된 헬퍼(_audio_merge / _compress_video /
_extract_thumbnail / _generate_share_token / SessionLocal / _get_r2_client)를
import 재사용하고, compose 단계와 텍스트→자막 생성만 새로 추가한다.

흐름: compose(순서대로 concat) → [60초 컷] → audio_merge → compress
      → daily limit → thumbnail → subtitle(SRT 또는 텍스트) → db_save
"""

import json
import logging
import time
import uuid

from config import R2_BUCKET_NAME, R2_PUBLIC_URL
from tasks.compose import _probe_duration, compose_items
from tasks.full_pipeline import (
    SessionLocal,
    _audio_merge,
    _compress_video,
    _extract_thumbnail,
    _generate_share_token,
    _get_r2_client,
)
from tasks.subtitle import (
    ALIGNMENT_MAP,
    FONT_SIZE_MAP,
    MARGIN_V_MAP,
    SUBTITLE_MAX_CHARS_MAP,
    SubtitleResult,
    build_srt_from_text,
    burn_user_srt,
    subtitle_metrics_json,
)

logger = logging.getLogger(__name__)

MAX_COMPOSED_SECONDS = 60


def _delete_quietly(r2, key: str) -> None:
    try:
        r2.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
    except Exception:
        pass


def _apply_video_filter(r2, video_key: str, video_filter: str) -> str | None:
    """합성 영상에 필터(카툰/운동열 강조)를 적용해 새 R2 키를 반환. 실패 시 None (원본 유지).

    backend와 동일한 렌더러(`app.services.cartoon`, `app.services.muscle_heat`)를 사용해
    미리보기 룩과 최종 결과물을 일치시킨다.
    """
    import os
    import tempfile
    import uuid as _uuid

    tmp_input = tmp_output = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_input = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp_output = f.name

        resp = r2.get_object(Bucket=R2_BUCKET_NAME, Key=video_key)
        with open(tmp_input, "wb") as f:
            f.write(resp["Body"].read())

        if video_filter == "cartoon":
            from app.services.cartoon import cartoonize_video

            cartoonize_video(tmp_input, tmp_output)
        else:
            from app.services.exercise_classify import classify_exercise
            from app.services.muscle_heat import render_heat_video

            # 운동 종목을 판별해 근육군 프리셋을 적용 — 부위 오귀속(스쿼트 팔 오발화 등) 억제.
            # 실패/키없음이면 None → 프리셋 없이 진행(기존 동작).
            exercise = classify_exercise(tmp_input)
            render_heat_video(
                tmp_input, tmp_output,
                weak_cartoon=video_filter == "cartoon_heat",
                exercise=exercise,
            )

        filtered_key = f"videos/f-{_uuid.uuid4()}.mp4"
        with open(tmp_output, "rb") as f:
            r2.put_object(Bucket=R2_BUCKET_NAME, Key=filtered_key, Body=f, ContentType="video/mp4",
                          CacheControl="public, max-age=31536000, immutable")
        return filtered_key
    except Exception as e:
        logger.warning("Video filter(%s) failed (using original): %s", video_filter, e)
        return None
    finally:
        for tmp in [tmp_input, tmp_output]:
            if tmp and os.path.exists(tmp):
                os.unlink(tmp)


def run_multi_pipeline(job: dict, status_callback=None) -> dict:
    """다중 미디어 업로드 파이프라인."""
    from app.models.post import Post
    from app.models.user import User
    from app.models.video import Video
    from app.routes.challenges import increment_challenge_upload
    from app.services.reward import DAILY_MAX_UPLOADS, add_points, get_daily_upload_count, points_for_tags

    start_time = time.time()
    r2 = _get_r2_client()
    job_id: str = job["job_id"]
    user_id: int = int(job["user_id"])
    items: list[dict] = job.get("items", [])
    if not items:
        raise RuntimeError("업로드할 미디어가 없습니다")

    mute_video_audio = bool(job.get("mute_video_audio", False))

    # 1) compose — 순서대로 이어붙이기
    if status_callback:
        status_callback("compose")
    composed_key, total_duration = compose_items(r2, items, mute_video=mute_video_audio)
    original_video_r2_key = composed_key
    current_key = composed_key
    logger.info("[multi-pipeline] job=%s composed → %s (%.2fs)", job_id, composed_key, total_duration)

    # 2) 60초 컷
    if total_duration > MAX_COMPOSED_SECONDS + 0.5:
        _delete_quietly(r2, composed_key)
        raise RuntimeError(f"최종 영상이 {MAX_COMPOSED_SECONDS}초를 초과합니다 ({total_duration:.1f}s)")

    has_audio_merged = False
    audio_merge_failed = False

    # 3) audio merge — 녹음 오디오를 합쳐진 영상 전체에 입힘 (기존 헬퍼 재사용)
    audio_r2_key: str | None = job.get("audio_r2_key")
    original_audio_r2_key: str | None = audio_r2_key
    if audio_r2_key:
        if status_callback:
            status_callback("audio_merge")
        audio_content_type = job.get("audio_content_type", "audio/webm")
        audio_suffix = ".mp4" if audio_content_type == "audio/mp4" else ".webm"
        merged = _audio_merge(r2, current_key, audio_r2_key, float(job.get("audio_duration_sec", 0)), audio_suffix)
        if merged:
            if current_key != original_video_r2_key:
                _delete_quietly(r2, current_key)
            current_key = merged
            has_audio_merged = True
            logger.info("[multi-pipeline] job=%s audio merged → %s", job_id, current_key)
        else:
            audio_merge_failed = True
            logger.warning("[multi-pipeline] job=%s 오디오 머지 실패 — 오디오 없이 진행", job_id)

    # 4) compress
    pre_size_bytes = 0
    post_size_bytes = 0
    video_meta: dict = {}
    compressed_key: str | None = None
    pre_compress_key = current_key
    if status_callback:
        status_callback("compress")
    compress_result = _compress_video(r2, current_key, mute_video=mute_video_audio)
    if compress_result:
        compressed_key, pre_size_bytes, post_size_bytes, video_meta = compress_result
        if pre_compress_key != original_video_r2_key:
            _delete_quietly(r2, pre_compress_key)
        current_key = compressed_key
        logger.info("[multi-pipeline] job=%s compressed → %s", job_id, current_key)

    # 4.5) video filter — 카툰/운동열 강조 등. 실패해도 원본으로 계속 진행 (subtitle과 동일한 정책)
    filter_status = "skipped"
    video_filter = job.get("video_filter")
    if video_filter in ("cartoon", "heat", "cartoon_heat"):
        if status_callback:
            status_callback("filter")
        pre_filter_key = current_key
        filtered_key = _apply_video_filter(r2, current_key, video_filter)
        if filtered_key:
            if pre_filter_key != original_video_r2_key:
                _delete_quietly(r2, pre_filter_key)
            current_key = filtered_key
            filter_status = "completed"
            logger.info("[multi-pipeline] job=%s %s filter → %s", job_id, video_filter, current_key)
        else:
            filter_status = "failed"
            logger.warning("[multi-pipeline] job=%s %s filter failed — 원본으로 진행", job_id, video_filter)

    # 5) 일일 한도 체크 (썸네일 전)
    if status_callback:
        status_callback("db_save")
    db = SessionLocal()
    try:
        if get_daily_upload_count(db, user_id) >= DAILY_MAX_UPLOADS:
            raise RuntimeError("하루 업로드 한도 초과")
    finally:
        db.close()

    # 6) thumbnail
    if status_callback:
        status_callback("thumbnail")
    thumb_key = _extract_thumbnail(r2, current_key)
    thumbnail_cdn_url: str | None = f"{R2_PUBLIC_URL}/{thumb_key}" if thumb_key else None

    # 7) subtitle — 사용자 SRT(영상음성/녹음) 또는 텍스트 후기
    if status_callback:
        status_callback("subtitle")
    subtitle_status = "skipped"
    subtitle_url: str | None = None
    subtitle_text: str | None = None
    subtitle_error: str | None = None
    subtitle_metrics: str | None = None
    pre_subtitle_key = current_key

    subtitle_size = job.get("subtitle_size") or "small"
    font_size = FONT_SIZE_MAP.get(subtitle_size, 14)
    alignment = ALIGNMENT_MAP.get(job.get("subtitle_position", "bottom"), 2)
    margin_v = MARGIN_V_MAP.get(job.get("subtitle_position", "bottom"), 90)

    subtitle_srt_r2_key = job.get("subtitle_srt_r2_key")
    text_subtitle = (job.get("subtitle_text") or "").strip()

    if not subtitle_srt_r2_key and text_subtitle:
        # 텍스트 후기 → 현재 영상 길이에 균등 분배한 SRT 생성 후 R2 저장
        measured = _probe_duration_safe(r2, current_key) or total_duration
        generated_srt = build_srt_from_text(
            text_subtitle, measured, max_chars=SUBTITLE_MAX_CHARS_MAP.get(subtitle_size, 12)
        )
        if generated_srt.strip():
            subtitle_srt_r2_key = f"subtitles/{user_id}/{uuid.uuid4()}.srt"
            r2.put_object(
                Bucket=R2_BUCKET_NAME, Key=subtitle_srt_r2_key,
                Body=generated_srt.encode("utf-8"),
                ContentType="application/x-subrip; charset=utf-8",
                CacheControl="private, max-age=86400",
            )

    if subtitle_srt_r2_key:
        result = burn_user_srt(
            r2, current_key, subtitle_srt_r2_key,
            font_size=font_size, alignment=alignment, margin_v=margin_v,
        )
    else:
        result = SubtitleResult(status="skipped", error="no subtitle provided")

    subtitle_status = result.status
    subtitle_url = result.subtitle_url
    subtitle_text = result.subtitle_text
    subtitle_error = result.error
    subtitle_metrics = subtitle_metrics_json(result)
    if subtitle_status == "completed" and result.burned_video_r2_key:
        current_key = result.burned_video_r2_key
        if pre_subtitle_key != original_video_r2_key:
            _delete_quietly(r2, pre_subtitle_key)
        logger.info("[multi-pipeline] job=%s subtitle burn-in → %s", job_id, current_key)
    elif subtitle_status == "completed":
        subtitle_status = "failed"
        subtitle_error = "subtitle burn-in did not produce a video"
        logger.warning("[multi-pipeline] job=%s subtitle failed — upload continues", job_id)
    elif subtitle_status == "failed":
        logger.warning("[multi-pipeline] job=%s subtitle failed — upload continues: %s", job_id, subtitle_error)

    # 8) db_save
    if status_callback:
        status_callback("db_save")
    db = SessionLocal()
    try:
        cdn_url = f"{R2_PUBLIC_URL}/{current_key}"
        final_duration = min(MAX_COMPOSED_SECONDS, max(3, int(round(total_duration))))

        video = Video(
            user_id=user_id,
            r2_key=current_key,
            cdn_url=cdn_url,
            file_hash=current_key,
            duration_sec=final_duration,
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
            proof_image_url=None,  # 멀티 경로: proof 개념 폐기, 이미지는 합쳐진 영상에 포함
            thumbnail_url=thumbnail_cdn_url,
            share_token=_generate_share_token(user_id),
            challenge_id=int(challenge_id) if challenge_id is not None else None,
        )
        db.add(post)
        db.flush()

        if challenge_id is not None:
            increment_challenge_upload(db, user_id, int(challenge_id))

        has_video = any(it.get("kind") == "video" for it in items)
        rp = add_points(
            db, user_id,
            points_for_tags(job.get("tags", []), has_video=has_video),
            "upload", reference_id=video.id,
        )
        points_earned = rp.points if rp else 0.0

        user = db.query(User).filter(User.id == user_id).first()
        username = user.username if user else str(user_id)
        email = user.email if user else ""

        db.commit()
        elapsed_sec = time.time() - start_time
        n_images = sum(1 for it in items if it.get("kind") == "image")
        merge_type = f"multi({'video+' if has_video else ''}{n_images}img)"
        if has_audio_merged:
            merge_type += " + audio"
        logger.info("[multi-pipeline] job=%s 완료 post_id=%s points=%s elapsed=%.1fs",
                    job_id, post.id, points_earned, elapsed_sec)
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
            "filter_status": filter_status,
        }
    except Exception:
        if compressed_key:
            _delete_quietly(r2, compressed_key)
            logger.info("[multi-pipeline] job=%s 실패 — 고아 압축본 삭제: %s", job_id, compressed_key)
        raise
    finally:
        db.close()


def _probe_duration_safe(r2, video_key: str) -> float:
    """R2의 영상을 임시 다운로드해 길이를 측정. 실패 시 0.0."""
    import os
    import tempfile
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tmp = f.name
        resp = r2.get_object(Bucket=R2_BUCKET_NAME, Key=video_key)
        with open(tmp, "wb") as f:
            f.write(resp["Body"].read())
        return _probe_duration(tmp)
    except Exception:
        return 0.0
    finally:
        if tmp and os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
