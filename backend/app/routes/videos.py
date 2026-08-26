import json
import os
import re
import tempfile
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, Query, UploadFile
from sqlalchemy.orm import Session, selectinload

from app.config import settings as app_settings
from app.database import get_db
from app.models.challenge import ChallengeParticipation
from app.models.comment import Comment
from app.models.notification import Notification
from app.models.post import Post
from app.models.post_like import PostLike
from app.models.post_view import PostView
from app.models.user import User
from app.models.video import Video
from sqlalchemy import func as sqlfunc
from app.routes.auth import get_active_user, get_current_user, get_optional_user
from app.routes.challenges import increment_challenge_upload
from app.schemas.video import (
    ConfirmUploadRequest,
    PostSchema,
    PostUpdateRequest,
    PresignedUrlRequest,
    PresignedUrlResponse,
    SubtitleLanguage,
)
from app.services import r2 as r2_service
from app.services.subtitles import sanitize_srt
from app.services.share_token import generate_share_token
from app.services.job_queue import enqueue_full_upload_pipeline, enqueue_image_merge_job, enqueue_merge_job, enqueue_multi_pipeline, enqueue_subtitle_extract_job, fail_job, get_job_status, reserve_job_id
from app.services.error_codes import (
    api_error,
    E_AUDIO_DURATION_INVALID,
    E_AUDIO_UPLOAD_FAILED,
    E_FILE_TOO_LARGE,
    E_FORBIDDEN,
    E_IMAGE_FORMAT_INVALID,
    E_IMAGE_TOO_LARGE,
    E_IMAGE_UPLOAD_FAILED,
    E_JOB_NOT_FOUND,
    E_POST_NOT_FOUND,
    E_QUEUE_FAILED,
    E_USER_NOT_FOUND,
    E_VIDEO_DURATION_INVALID,
    E_VIDEO_FORMAT_INVALID,
    E_VIDEO_NOT_FOUND,
    E_VIDEO_PROCESS_FAILED,
    E_VIDEO_TOO_LARGE,
)

logger = logging.getLogger(__name__)


def _assert_job_owner(job: dict, current_user: User) -> None:
    """Prevent users from reading another user's async job status.

    Legacy Redis job records created before this check may not include user_id;
    keep those readable until their 24h TTL expires to avoid breaking in-flight
    deployed jobs. All newly created job records include user_id.
    """
    job_user_id = job.get("user_id")
    if job_user_id in (None, ""):
        return
    if str(job_user_id) != str(current_user.id):
        raise api_error(404, E_JOB_NOT_FOUND, "요청한 작업을 찾을 수 없습니다")


async def _spool_upload_to_temp(upload: UploadFile, max_bytes: int, label: str) -> tuple[str, int]:
    """Copy an upload to a temp file with a hard byte limit.

    This keeps the public upload-pipeline contract unchanged while avoiding
    holding whole media files in API worker memory until BackgroundTasks run.
    """
    suffix = ""
    if upload.filename and "." in upload.filename:
        suffix = "." + upload.filename.rsplit(".", 1)[-1]
    fd, path = tempfile.mkstemp(prefix=f"stackhealth-{label}-", suffix=suffix)
    size = 0
    try:
        with os.fdopen(fd, "wb") as out:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise api_error(400, E_FILE_TOO_LARGE, f"{label} 파일이 너무 큽니다")
                out.write(chunk)
        return path, size
    except Exception:
        try:
            os.unlink(path)
        except OSError:
            pass
        raise

def _parse_tags(raw: str | None) -> list[str]:
    try:
        return json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []

router = APIRouter(prefix="/api/v1/videos", tags=["videos"])


@router.post("/presigned-url")
def get_presigned_url(
    req: PresignedUrlRequest,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> dict:
    if req.content_type not in r2_service.ALLOWED_CONTENT_TYPES:
        logger.warning(
            "Unsupported content type: %s from user_id=%s",
            req.content_type,
            current_user.id,
        )
        raise api_error(400, E_VIDEO_FORMAT_INVALID, f"지원하지 않는 파일 형식입니다: {req.content_type}")
    if req.file_size > r2_service.MAX_FILE_SIZE:
        raise api_error(400, E_VIDEO_TOO_LARGE, "파일이 너무 큽니다 (최대 100MB)")

    upload_url, r2_key = r2_service.generate_presigned_url(req.content_type, req.filename, current_user.id)
    return {"data": PresignedUrlResponse(upload_url=upload_url, r2_key=r2_key)}


@router.post("/upload")
async def upload_video(
    file: UploadFile = File(...),
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    """Server-side upload: receives file from browser, streams to R2.

    Avoids CORS preflight issues on Android/mobile.
    """
    content_type = file.content_type or "video/mp4"
    if content_type not in r2_service.ALLOWED_CONTENT_TYPES:
        raise api_error(400, E_VIDEO_FORMAT_INVALID, f"지원하지 않는 파일 형식입니다: {content_type}")

    logger.info("upload_video: user_id=%s filename=%s content_type=%s", current_user.id, file.filename, content_type)
    r2_key, cdn_url = r2_service.upload_fileobj(file.file, content_type, file.filename or "video.mp4", current_user.id)
    return {"data": {"r2_key": r2_key, "cdn_url": cdn_url}}


@router.post("/confirm")
def confirm_upload(
    req: ConfirmUploadRequest,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    if req.duration_sec < 10 or req.duration_sec > 60:
        raise api_error(400, E_VIDEO_DURATION_INVALID, "영상은 10~60초여야 합니다")

    expected_prefix = f"videos/{current_user.id}/"
    if not req.r2_key.startswith(expected_prefix):
        raise api_error(403, E_FORBIDDEN, "접근 권한이 없습니다")

    tags = req.tags or []

    cdn_url = r2_service.get_cdn_url(req.r2_key)

    video = Video(
        user_id=current_user.id,
        r2_key=req.r2_key,
        cdn_url=cdn_url,
        file_hash=req.r2_key,
        duration_sec=req.duration_sec,
        original_video_r2_key=req.r2_key,
    )
    db.add(video)
    db.flush()

    post = Post(
        video_id=video.id,
        user_id=current_user.id,
        caption=req.caption,
        tags=json.dumps(tags, ensure_ascii=False),
        workout_start=req.workout_start,
        workout_end=req.workout_end,
        proof_image_url=req.proof_image_url,
        share_token=generate_share_token(current_user.id),
        challenge_id=req.challenge_id,
    )
    db.add(post)
    db.flush()

    if req.challenge_id:
        increment_challenge_upload(db, current_user.id, req.challenge_id)

    db.commit()
    db.refresh(post)
    db.refresh(video)

    post_schema = PostSchema(
        id=post.id,
        video_id=post.video_id,
        user_id=post.user_id,
        caption=post.caption,
        tags=tags,
        like_count=post.like_count,
        view_count=post.view_count,
        comment_count=0,
        created_at=post.created_at,
        cdn_url=video.cdn_url,
        username=current_user.username,
        workout_start=post.workout_start,
        workout_end=post.workout_end,
        share_token=post.share_token,
        thumbnail_url=post.thumbnail_url,
        subtitle_url=video.subtitle_url,
        subtitle_text=video.subtitle_text,
        subtitle_status=video.subtitle_status,
        avatar_url=current_user.avatar_url,
        profile_color=(current_user.app_settings or {}).get("profile_color"),
        challenge_id=post.challenge_id,
    )
    return {"data": {"post": post_schema}}


@router.get("/my-posts")
def my_posts(
    week_offset: int = Query(0, ge=0),
    all: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    base_filter = (
        db.query(Post)
        .join(Post.video)
        .options(selectinload(Post.video))
        .filter(Post.user_id == current_user.id, Video.status == "active")
    )

    if all:
        posts = base_filter.order_by(Post.created_at.desc()).all()
        has_more = False
    else:
        now_utc = datetime.now(timezone.utc)
        monday_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now_utc.weekday())
        week_start_utc = monday_utc - timedelta(weeks=week_offset)
        week_end_utc = week_start_utc + timedelta(weeks=1)
        posts = (
            base_filter
            .filter(Post.created_at >= week_start_utc, Post.created_at < week_end_utc)
            .order_by(Post.created_at.desc())
            .all()
        )
        has_more = (
            db.query(Post)
            .join(Post.video)
            .filter(
                Post.user_id == current_user.id,
                Video.status == "active",
                Post.created_at < week_start_utc,
            )
            .first()
        ) is not None

    post_ids = [p.id for p in posts]
    comment_counts: dict[int, int] = {}
    if post_ids:
        comment_counts = dict(
            db.query(Comment.post_id, sqlfunc.count(Comment.id))
            .filter(Comment.post_id.in_(post_ids))
            .group_by(Comment.post_id)
            .all()
        )

    result = []
    for post in posts:
        tags = _parse_tags(post.tags)
        result.append(
            PostSchema(
                id=post.id,
                video_id=post.video_id,
                user_id=post.user_id,
                caption=post.caption,
                tags=tags,
                like_count=post.like_count,
                view_count=post.view_count,
                comment_count=comment_counts.get(post.id, 0),
                created_at=post.created_at,
                cdn_url=post.video.cdn_url,
                username=current_user.username,
                workout_start=post.workout_start,
                workout_end=post.workout_end,
                share_token=post.share_token,
                thumbnail_url=post.thumbnail_url,
                subtitle_url=post.video.subtitle_url,
                subtitle_text=post.video.subtitle_text,
                subtitle_status=post.video.subtitle_status,
                avatar_url=current_user.avatar_url,
                profile_color=(current_user.app_settings or {}).get("profile_color"),
                challenge_id=post.challenge_id,
            )
        )
    return {"data": {"posts": result, "has_more": has_more, "week_offset": week_offset}}


@router.get("/posts/share/{share_token}")
def get_post_by_share_token(
    share_token: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> dict:
    post = db.query(Post).filter(Post.share_token == share_token).first()
    if not post:
        raise api_error(404, E_VIDEO_NOT_FOUND, "영상을 찾을 수 없습니다")
    video = db.query(Video).filter(Video.id == post.video_id).first()
    if not video:
        raise api_error(404, E_VIDEO_NOT_FOUND, "영상을 찾을 수 없습니다")
    user = db.query(User).filter(User.id == post.user_id).first()
    if not user:
        raise api_error(404, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")
    tags = _parse_tags(post.tags)
    comment_count = db.query(sqlfunc.count(Comment.id)).filter(Comment.post_id == post.id).scalar() or 0
    is_liked = False
    if current_user:
        is_liked = db.query(PostLike).filter(PostLike.post_id == post.id, PostLike.user_id == current_user.id).first() is not None
    post_schema = PostSchema(
        id=post.id,
        video_id=post.video_id,
        user_id=post.user_id,
        caption=post.caption,
        tags=tags,
        like_count=post.like_count,
        view_count=post.view_count,
        comment_count=comment_count,
        is_liked=is_liked,
        created_at=post.created_at,
        cdn_url=video.cdn_url,
        username=user.username,
        workout_start=post.workout_start,
        workout_end=post.workout_end,
        share_token=post.share_token,
        thumbnail_url=post.thumbnail_url,
        subtitle_url=video.subtitle_url,
        subtitle_text=video.subtitle_text,
        subtitle_status=video.subtitle_status,
        avatar_url=user.avatar_url,
        profile_color=(user.app_settings or {}).get("profile_color"),
        challenge_id=post.challenge_id,
    )
    return {"data": {"post": post_schema}}


@router.get("/posts/{post_id}")
def get_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> dict:
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise api_error(404, E_VIDEO_NOT_FOUND, "영상을 찾을 수 없습니다")
    video = db.query(Video).filter(Video.id == post.video_id).first()
    if not video:
        raise api_error(404, E_VIDEO_NOT_FOUND, "영상을 찾을 수 없습니다")
    user = db.query(User).filter(User.id == post.user_id).first()
    if not user:
        raise api_error(404, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")
    tags = _parse_tags(post.tags)
    comment_count = db.query(sqlfunc.count(Comment.id)).filter(Comment.post_id == post.id).scalar() or 0
    post_schema = PostSchema(
        id=post.id,
        video_id=post.video_id,
        user_id=post.user_id,
        caption=post.caption,
        tags=tags,
        like_count=post.like_count,
        view_count=post.view_count,
        comment_count=comment_count,
        created_at=post.created_at,
        cdn_url=video.cdn_url,
        username=user.username,
        workout_start=post.workout_start,
        workout_end=post.workout_end,
        share_token=post.share_token,
        thumbnail_url=post.thumbnail_url,
        subtitle_url=video.subtitle_url,
        subtitle_text=video.subtitle_text,
        subtitle_status=video.subtitle_status,
        avatar_url=user.avatar_url,
        profile_color=(user.app_settings or {}).get("profile_color"),
        challenge_id=post.challenge_id,
    )
    return {"data": {"post": post_schema}}


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@router.patch("/posts/{post_id}")
def update_post(
    post_id: int,
    req: PostUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """본인(또는 admin) 게시물의 캡션·태그·활동 시간 수정.

    영상·자막(burn-in)·썸네일은 변경하지 않는다.
    """
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise api_error(404, E_POST_NOT_FOUND, "게시물을 찾을 수 없습니다")
    if post.user_id != current_user.id and not current_user.is_admin:
        raise api_error(403, E_FORBIDDEN, "이 작업을 수행할 권한이 없습니다")

    fields = req.model_dump(exclude_unset=True)

    if "caption" in fields:
        caption = fields["caption"]
        if caption is not None and len(caption) > 140:
            raise api_error(400, E_VIDEO_FORMAT_INVALID, "설명은 140자 이하여야 합니다")
        post.caption = caption

    for time_field in ("workout_start", "workout_end"):
        if time_field in fields:
            value = fields[time_field]
            if value is not None and value != "" and not _TIME_RE.match(value):
                raise api_error(400, E_VIDEO_DURATION_INVALID, "시간 형식이 올바르지 않습니다 (HH:MM)")
            setattr(post, time_field, value or None)

    if "tags" in fields and fields["tags"] is not None:
        new_tags = [t for t in fields["tags"] if isinstance(t, str) and t.strip()]
        post.tags = json.dumps(new_tags, ensure_ascii=False)

    db.commit()
    db.refresh(post)

    video = db.query(Video).filter(Video.id == post.video_id).first()
    user = db.query(User).filter(User.id == post.user_id).first()
    comment_count = db.query(sqlfunc.count(Comment.id)).filter(Comment.post_id == post.id).scalar() or 0
    post_schema = PostSchema(
        id=post.id,
        video_id=post.video_id,
        user_id=post.user_id,
        caption=post.caption,
        tags=_parse_tags(post.tags),
        like_count=post.like_count,
        view_count=post.view_count,
        comment_count=comment_count,
        created_at=post.created_at,
        cdn_url=video.cdn_url if video else "",
        username=user.username if user else "",
        workout_start=post.workout_start,
        workout_end=post.workout_end,
        share_token=post.share_token,
        thumbnail_url=post.thumbnail_url,
        subtitle_url=video.subtitle_url if video else None,
        subtitle_text=video.subtitle_text if video else None,
        subtitle_status=video.subtitle_status if video else "skipped",
        avatar_url=user.avatar_url if user else None,
        profile_color=(user.app_settings or {}).get("profile_color") if user else None,
        challenge_id=post.challenge_id,
    )
    return {"data": {"post": post_schema}}


@router.delete("/posts/{post_id}")
def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise api_error(404, E_POST_NOT_FOUND, "게시물을 찾을 수 없습니다")
    if post.user_id != current_user.id and not current_user.is_admin:
        raise api_error(403, E_FORBIDDEN, "이 작업을 수행할 권한이 없습니다")

    video = db.query(Video).filter(Video.id == post.video_id).first()

    db.query(Notification).filter(Notification.post_id == post_id).delete()
    db.query(PostView).filter(PostView.post_id == post_id).delete()
    db.query(PostLike).filter(PostLike.post_id == post_id).delete()
    db.query(Comment).filter(Comment.post_id == post_id).delete()

    if post.challenge_id:
        participation = (
            db.query(ChallengeParticipation)
            .filter(
                ChallengeParticipation.challenge_id == post.challenge_id,
                ChallengeParticipation.user_id == post.user_id,
            )
            .first()
        )
        if participation and participation.upload_count > 0:
            participation.upload_count -= 1
            if participation.completed_at is not None and participation.upload_count < participation.challenge.condition_value:
                participation.completed_at = None

    db.delete(post)
    if video:
        db.delete(video)
    db.commit()

    if video:
        try:
            r2_service.delete_object(video.r2_key)
        except Exception:
            pass  # R2 deletion failure is non-fatal

    return {"data": {"deleted": post_id}}


@router.post("/merge-audio")
async def merge_audio(
    video_r2_key: str = Form(...),
    audio_duration_sec: int = Form(...),
    audio: UploadFile = File(...),
    current_user: User = Depends(get_active_user),
) -> dict:
    """오디오+비디오 병합 잡을 외부 워커 큐에 등록한다."""
    if not video_r2_key.startswith(f"videos/{current_user.id}/"):
        raise api_error(403, E_FORBIDDEN, "접근 권한이 없습니다")

    if audio_duration_sec <= 0 or audio_duration_sec > 65:
        raise api_error(400, E_AUDIO_DURATION_INVALID, "오디오 길이를 확인해주세요")

    logger.info("merge_audio enqueue: user_id=%s video_r2_key=%s", current_user.id, video_r2_key)

    content_type = audio.content_type or "audio/webm"
    ext = "mp4" if content_type == "audio/mp4" else "webm"
    audio_r2_key = f"audio/{uuid.uuid4()}.{ext}"

    try:
        audio_bytes = await audio.read()
        client = r2_service.get_r2_client()
        client.put_object(
            Bucket=app_settings.r2_bucket_name,
            Key=audio_r2_key,
            Body=audio_bytes,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
    except Exception as e:
        logger.error("오디오 R2 업로드 실패: %s", e)
        raise api_error(500, E_AUDIO_UPLOAD_FAILED, "오디오 업로드에 실패했습니다. 잠시 후 다시 시도해주세요")

    job_payload = {
        "user_id": current_user.id,
        "video_r2_key": video_r2_key,
        "audio_r2_key": audio_r2_key,
        "audio_duration_sec": audio_duration_sec,
        "audio_content_type": content_type,
    }

    try:
        job_id = enqueue_merge_job(job_payload)
    except Exception as e:
        logger.error("Redis 큐 실패: %s", e)
        raise api_error(500, E_QUEUE_FAILED, "영상 처리 요청에 실패했습니다. 잠시 후 다시 시도해주세요")

    return {"data": {"job_id": job_id, "status": "processing"}}


@router.get("/merge-job/{job_id}")
def get_merge_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """merge-audio / merge-proof 잡 상태를 폴링한다."""
    job = get_job_status(job_id)  # 로컬 스토어 → Redis 순 확인, 예외 없음

    if job is None:
        raise api_error(404, E_JOB_NOT_FOUND, "요청한 작업을 찾을 수 없습니다")
    _assert_job_owner(job, current_user)

    return {
        "data": {
            "job_id": job_id,
            "status": job.get("status", "unknown"),
            "r2_key": job.get("output_r2_key", ""),
            "cdn_url": job.get("cdn_url", ""),
            "proof_image_url": job.get("proof_image_url", ""),
            "error": "영상 처리에 실패했습니다. 다시 시도해주세요." if job.get("status") == "failed" else "",
        }
    }


ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB


@router.post("/upload-proof")
async def upload_proof_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_active_user),
) -> dict:
    """증거 이미지를 R2에 업로드하고 proof_r2_key를 반환한다."""
    content_type = file.content_type or "image/jpeg"
    if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
        raise api_error(400, E_IMAGE_FORMAT_INVALID, f"지원하지 않는 이미지 형식입니다: {content_type}")

    image_bytes = await file.read()
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise api_error(400, E_IMAGE_TOO_LARGE, "이미지가 너무 큽니다 (최대 10MB)")

    ext = "jpg" if "jpeg" in content_type or "jpg" in content_type else "png"
    proof_r2_key = f"proof/{current_user.id}/{uuid.uuid4()}.{ext}"

    try:
        r2_client = r2_service.get_r2_client()
        r2_client.put_object(
            Bucket=app_settings.r2_bucket_name,
            Key=proof_r2_key,
            Body=image_bytes,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
    except Exception as e:
        logger.error("증거 이미지 R2 업로드 실패: %s", e)
        raise api_error(500, E_IMAGE_UPLOAD_FAILED, "이미지 업로드에 실패했습니다. 잠시 후 다시 시도해주세요")

    proof_cdn_url = f"{app_settings.r2_public_url.rstrip('/')}/{proof_r2_key}"
    logger.info("upload_proof: user_id=%s key=%s", current_user.id, proof_r2_key)
    return {"data": {"proof_r2_key": proof_r2_key, "proof_cdn_url": proof_cdn_url}}


@router.post("/merge-proof")
def merge_proof(
    video_r2_key: str = Form(...),
    proof_r2_key: str = Form(...),
    current_user: User = Depends(get_active_user),
) -> dict:
    """증거 이미지를 비디오 끝에 3초 슬라이드로 붙인다."""
    if not video_r2_key.startswith(f"videos/{current_user.id}/"):
        raise api_error(403, E_FORBIDDEN, "접근 권한이 없습니다")
    if not proof_r2_key.startswith(f"proof/{current_user.id}/"):
        raise api_error(403, E_FORBIDDEN, "접근 권한이 없습니다")

    logger.info("merge_proof: user_id=%s video=%s proof=%s", current_user.id, video_r2_key, proof_r2_key)
    try:
        job_id = enqueue_image_merge_job(video_r2_key, proof_r2_key, current_user.id)
    except Exception as e:
        logger.error("proof merge 큐 등록 실패: %s", e)
        raise api_error(500, E_VIDEO_PROCESS_FAILED, "영상 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요")
    return {"data": {"job_id": job_id, "status": "processing"}}



@router.post("/transcribe-subtitles")
async def transcribe_subtitles(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
    audio: UploadFile | None = File(None),
    language: str = Form("ko"),
    subtitle_language: SubtitleLanguage = Form("ko"),
    current_user: User = Depends(get_active_user),
) -> dict:
    """파일을 R2에 올리고 자막 추출 잡을 큐에 등록. job_id 즉시 반환.

    영상(file) 또는 오디오(audio) 중 최소 하나가 있어야 한다. 둘 다 있으면 오디오 우선.
    이미지만 업로드한 멀티 케이스에서 녹음만으로 자막을 만들 때 file 없이 호출된다.
    subtitle_language (ko|en|auto, 기본 ko) 로 Whisper 언어를 지정한다.
    legacy `language` 파라미터가 있으면 subtitle_language보다 우선 적용된다.
    """
    if file is None and audio is None:
        raise api_error(400, E_VIDEO_FORMAT_INVALID, "영상 또는 오디오가 필요합니다")

    # subtitle_language가 명시된 경우 우선 사용, 그 외 legacy language 필드 사용
    effective_language: str = subtitle_language if subtitle_language != "ko" else (language or "ko")

    video_path: str | None = None
    video_ct: str | None = None
    if file is not None:
        content_type = file.content_type or "video/mp4"
        if content_type not in r2_service.ALLOWED_CONTENT_TYPES:
            raise api_error(400, E_VIDEO_FORMAT_INVALID, f"지원하지 않는 파일 형식입니다: {content_type}")
        video_path, _ = await _spool_upload_to_temp(file, r2_service.MAX_FILE_SIZE, "자막영상")
        video_ct = content_type

    audio_path: str | None = None
    audio_ct: str | None = None
    if audio is not None:
        audio_path, _ = await _spool_upload_to_temp(audio, r2_service.MAX_FILE_SIZE, "자막오디오")
        audio_ct = audio.content_type

    job_id = reserve_job_id(current_user.id, job_type="subtitle-extract")
    background_tasks.add_task(
        _r2_upload_and_enqueue_subtitle,
        job_id, video_path, video_ct,
        audio_path, audio_ct, current_user.id, effective_language,
    )
    return {"data": {"job_id": job_id}}


@router.get("/subtitle-job/{job_id}")
async def get_subtitle_job(
    job_id: str,
    current_user: User = Depends(get_active_user),
) -> dict:
    """자막 추출 잡 상태 + 결과 폴링."""
    job = get_job_status(job_id)
    if not job:
        raise api_error(404, E_JOB_NOT_FOUND, "요청한 작업을 찾을 수 없습니다")
    _assert_job_owner(job, current_user)
    raw_metrics = job.get("metrics")
    try:
        metrics = json.loads(raw_metrics) if raw_metrics else None
    except (ValueError, TypeError):
        metrics = None
    return {"data": {
        "status": job.get("status"),
        "srt": job.get("srt", ""),
        "plain_text": job.get("plain_text", ""),
        "error": job.get("error", ""),
        "metrics": metrics,
    }}

# ---------------------------------------------------------------------------
# 자막 추출 비동기 헬퍼
# ---------------------------------------------------------------------------

def _r2_upload_and_enqueue_subtitle(
    job_id: str,
    video_path: str | None,
    video_content_type: str | None,
    audio_path: str | None,
    audio_content_type: str | None,
    user_id: int,
    language: str,
) -> None:
    temp_paths = [p for p in (video_path, audio_path) if p]
    try:
        r2_client = r2_service.get_r2_client()
        video_r2_key: str | None = None
        if video_path:
            video_r2_key = f"subtitle-tmp/{uuid.uuid4()}.mp4"
            with open(video_path, "rb") as f:
                r2_client.put_object(
                    Bucket=app_settings.r2_bucket_name,
                    Key=video_r2_key,
                    Body=f,
                    ContentType=video_content_type or "video/mp4",
                    CacheControl="private, max-age=3600",
                )

        audio_r2_key: str | None = None
        if audio_path and audio_content_type:
            ext = "mp4" if "mp4" in audio_content_type else "webm"
            audio_r2_key = f"subtitle-tmp/{uuid.uuid4()}-audio.{ext}"
            with open(audio_path, "rb") as f:
                r2_client.put_object(
                    Bucket=app_settings.r2_bucket_name,
                    Key=audio_r2_key,
                    Body=f,
                    ContentType=audio_content_type,
                    CacheControl="private, max-age=3600",
                )

        enqueue_subtitle_extract_job(
            video_r2_key=video_r2_key,
            audio_r2_key=audio_r2_key,
            language=language,
            user_id=user_id,
            job_id=job_id,
        )
    except Exception as e:
        logger.exception("subtitle R2 upload failed for job %s: %s", job_id, e)
        fail_job(job_id, str(e))
    finally:
        for p in temp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# MQ 방식 전체 업로드 파이프라인
# ---------------------------------------------------------------------------

def _r2_upload_and_enqueue(
    job_id: str,
    video_path: str,
    video_content_type: str,
    video_filename: str,
    audio_path: str | None,
    audio_content_type: str,
    proof_path: str | None,
    proof_content_type: str | None,
    user_id: int,
    duration_sec: int,
    caption: str | None,
    tags_list: list[str],
    challenge_id: int | None,
    workout_start: str | None,
    workout_end: str | None,
    audio_duration_sec: int,
    subtitle_srt: str | None,
    subtitle_size: str | None,
    subtitle_position: str | None,
    mute_video_audio: bool = False,
    subtitle_language: str = "ko",
) -> None:
    temp_paths = [p for p in (video_path, audio_path, proof_path) if p]
    try:
        with open(video_path, "rb") as video_file:
            r2_key, _cdn_url = r2_service.upload_fileobj(
                video_file, video_content_type, video_filename, user_id
            )

        audio_r2_key: str | None = None
        if audio_path:
            audio_ext = "mp4" if "mp4" in audio_content_type else "webm"
            with open(audio_path, "rb") as audio_file:
                audio_r2_key, _ = r2_service.upload_fileobj(
                    audio_file, audio_content_type, f"audio.{audio_ext}", user_id
                )

        proof_r2_key: str | None = None
        proof_cdn_url: str | None = None
        if proof_path and proof_content_type:
            ext = "jpg" if "jpeg" in proof_content_type or "jpg" in proof_content_type else "png"
            proof_r2_key = f"proof/{user_id}/{uuid.uuid4()}.{ext}"
            r2_client = r2_service.get_r2_client()
            with open(proof_path, "rb") as proof_file:
                r2_client.put_object(
                    Bucket=app_settings.r2_bucket_name,
                    Key=proof_r2_key,
                    Body=proof_file,
                    ContentType=proof_content_type,
                    CacheControl="public, max-age=31536000, immutable",
                )
            proof_cdn_url = f"{app_settings.r2_public_url.rstrip('/')}/{proof_r2_key}"

        subtitle_srt_r2_key: str | None = None
        if subtitle_srt:
            cleaned_srt = sanitize_srt(subtitle_srt)
            subtitle_srt_r2_key = f"subtitles/{user_id}/{uuid.uuid4()}.srt"
            r2_client = r2_service.get_r2_client()
            r2_client.put_object(
                Bucket=app_settings.r2_bucket_name,
                Key=subtitle_srt_r2_key,
                Body=cleaned_srt.encode("utf-8"),
                ContentType="application/x-subrip; charset=utf-8",
                CacheControl="private, max-age=86400",
            )

        enqueue_full_upload_pipeline(
            job_id=job_id,
            r2_key=r2_key,
            file_hash=r2_key,
            duration_sec=duration_sec,
            caption=caption,
            tags=tags_list,
            challenge_id=challenge_id,
            workout_start=workout_start,
            workout_end=workout_end,
            user_id=user_id,
            audio_r2_key=audio_r2_key,
            audio_duration_sec=audio_duration_sec,
            audio_content_type=audio_content_type,
            proof_r2_key=proof_r2_key,
            proof_cdn_url=proof_cdn_url,
            subtitle_srt_r2_key=subtitle_srt_r2_key,
            subtitle_size=subtitle_size,
            subtitle_position=subtitle_position,
            mute_video_audio=mute_video_audio,
            subtitle_language=subtitle_language,
        )
    except Exception as e:
        logger.error("Background R2 upload failed job_id=%s: %s", job_id, e)
        fail_job(job_id, str(e))
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


@router.post("/upload-pipeline")
async def upload_pipeline(
    file: UploadFile = File(...),
    duration_sec: int = Form(...),
    caption: str | None = Form(None),
    tags: str = Form("[]"),
    challenge_id: int | None = Form(None),
    workout_start: str | None = Form(None),
    workout_end: str | None = Form(None),
    audio: UploadFile | None = File(None),
    audio_duration_sec: int = Form(0),
    proof_image: UploadFile | None = File(None),
    subtitle_srt: str | None = Form(None),
    subtitle_size: str | None = Form(None),
    subtitle_position: str | None = Form(None),
    subtitle_language: SubtitleLanguage = Form("ko"),
    mute_video: bool = Form(False),
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = ...,
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    """파일 수신 즉시 job_id 반환. R2 업로드 + 처리는 백그라운드에서 실행."""
    if duration_sec < 10 or duration_sec > 60:
        raise api_error(400, E_VIDEO_DURATION_INVALID, "영상은 10~60초여야 합니다")

    content_type = file.content_type or "video/mp4"
    if content_type not in r2_service.ALLOWED_CONTENT_TYPES:
        raise api_error(400, E_VIDEO_FORMAT_INVALID, f"지원하지 않는 파일 형식입니다: {content_type}")

    tags_list = _parse_tags(tags)

    video_path, _video_size = await _spool_upload_to_temp(file, r2_service.MAX_FILE_SIZE, "영상")

    audio_path: str | None = None
    audio_content_type = "audio/webm"
    if audio is not None:
        audio_content_type = audio.content_type or "audio/webm"
        audio_path, _audio_size = await _spool_upload_to_temp(audio, r2_service.MAX_FILE_SIZE, "오디오")

    proof_path: str | None = None
    proof_content_type: str | None = None
    if proof_image is not None:
        proof_content_type = proof_image.content_type or "image/jpeg"
        if proof_content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise api_error(400, E_IMAGE_FORMAT_INVALID, f"지원하지 않는 이미지 형식입니다: {proof_content_type}")
        proof_path, _proof_size = await _spool_upload_to_temp(proof_image, MAX_IMAGE_SIZE, "이미지")

    temp_paths = [p for p in (video_path, audio_path, proof_path) if p]
    try:
        # job_id 선점: 응답 전에 Redis에 등록해 폴링 가능하게
        job_id = reserve_job_id(current_user.id)
    except Exception:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass
        raise
    logger.info("upload_pipeline: user_id=%s job_id=%s", current_user.id, job_id)

    background_tasks.add_task(
        _r2_upload_and_enqueue,
        job_id=job_id,
        video_path=video_path,
        video_content_type=content_type,
        video_filename=file.filename or "video.mp4",
        audio_path=audio_path,
        audio_content_type=audio_content_type,
        proof_path=proof_path,
        proof_content_type=proof_content_type,
        user_id=current_user.id,
        duration_sec=duration_sec,
        caption=caption,
        tags_list=tags_list,
        challenge_id=challenge_id,
        workout_start=workout_start,
        workout_end=workout_end,
        audio_duration_sec=audio_duration_sec,
        subtitle_srt=subtitle_srt,
        subtitle_size=subtitle_size,
        subtitle_position=subtitle_position,
        mute_video_audio=mute_video,
        subtitle_language=subtitle_language,
    )

    return {"data": {"job_id": job_id, "status": "processing"}}


@router.get("/upload-job/{job_id}")
def get_upload_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """upload-pipeline 잡 상태 폴링 엔드포인트."""
    job = get_job_status(job_id)
    if job is None:
        raise api_error(404, E_JOB_NOT_FOUND, "요청한 작업을 찾을 수 없습니다")
    _assert_job_owner(job, current_user)

    status = job.get("status", "unknown")
    share_token = ""
    if status == "completed":
        post_id = job.get("post_id", "")
        if post_id:
            try:
                post = db.query(Post).filter(Post.id == int(post_id)).first()
                if post:
                    share_token = post.share_token
            except (ValueError, TypeError):
                share_token = ""

    return {
        "data": {
            "job_id": job_id,
            "status": status,
            "pipeline_step": job.get("pipeline_step", ""),
            "cdn_url": job.get("cdn_url", ""),
            "post_id": job.get("post_id", ""),
            "share_token": share_token,
            "audio_merge_failed": job.get("audio_merge_failed", "") == "True",
            "subtitle_status": job.get("subtitle_status", ""),
            "subtitle_url": job.get("subtitle_url", ""),
            "subtitle_text": job.get("subtitle_text", ""),
            "subtitle_error": job.get("subtitle_error", ""),
            "error": "영상 처리에 실패했습니다. 다시 시도해주세요." if status == "failed" else "",
        }
    }


# ---------------------------------------------------------------------------
# 다중 미디어 업로드 (영상 ≤1 + 이미지 ≤5) — 신규 멀티 경로
# 기존 /upload-pipeline 은 그대로 두고 별도 경로로 신설한다.
# ---------------------------------------------------------------------------

MAX_MEDIA_IMAGES = 5


def _r2_upload_and_enqueue_multi(
    job_id: str,
    spooled: list[tuple[str, str, str, str]],  # (kind, path, content_type, filename)
    audio_path: str | None,
    audio_content_type: str,
    user_id: int,
    caption: str | None,
    tags_list: list[str],
    challenge_id: int | None,
    workout_start: str | None,
    workout_end: str | None,
    audio_duration_sec: int,
    subtitle_srt: str | None,
    subtitle_text: str | None,
    subtitle_size: str | None,
    subtitle_position: str | None,
    subtitle_language: str,
    mute_video_audio: bool,
    video_filter: str | None = None,
) -> None:
    temp_paths = [p for _, p, _, _ in spooled] + ([audio_path] if audio_path else [])
    try:
        items: list[dict] = []
        for kind, path, content_type, filename in spooled:
            with open(path, "rb") as fobj:
                r2_key, _ = r2_service.upload_fileobj(fobj, content_type, filename, user_id)
            items.append({"kind": kind, "r2_key": r2_key})

        audio_r2_key: str | None = None
        if audio_path:
            audio_ext = "mp4" if "mp4" in audio_content_type else "webm"
            with open(audio_path, "rb") as audio_file:
                audio_r2_key, _ = r2_service.upload_fileobj(
                    audio_file, audio_content_type, f"audio.{audio_ext}", user_id
                )

        subtitle_srt_r2_key: str | None = None
        if subtitle_srt:
            cleaned_srt = sanitize_srt(subtitle_srt)
            subtitle_srt_r2_key = f"subtitles/{user_id}/{uuid.uuid4()}.srt"
            r2_client = r2_service.get_r2_client()
            r2_client.put_object(
                Bucket=app_settings.r2_bucket_name,
                Key=subtitle_srt_r2_key,
                Body=cleaned_srt.encode("utf-8"),
                ContentType="application/x-subrip; charset=utf-8",
                CacheControl="private, max-age=86400",
            )

        enqueue_multi_pipeline(
            items,
            user_id=user_id,
            caption=caption,
            tags=tags_list,
            challenge_id=challenge_id,
            workout_start=workout_start,
            workout_end=workout_end,
            audio_r2_key=audio_r2_key,
            audio_duration_sec=audio_duration_sec,
            audio_content_type=audio_content_type,
            subtitle_srt_r2_key=subtitle_srt_r2_key,
            # SRT(영상음성/녹음 결과)가 있으면 그것을 우선, 없을 때만 텍스트 후기 사용
            subtitle_text=None if subtitle_srt_r2_key else subtitle_text,
            subtitle_size=subtitle_size,
            subtitle_position=subtitle_position,
            subtitle_language=subtitle_language,
            mute_video_audio=mute_video_audio,
            video_filter=video_filter,
            job_id=job_id,
        )
    except Exception as e:
        logger.error("Background multi R2 upload failed job_id=%s: %s", job_id, e)
        fail_job(job_id, str(e))
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


MAX_PREVIEW_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB — canvas 캡처 프레임 1장
PREVIEW_MAX_WIDTH = 1280
ALLOWED_VIDEO_FILTERS = {"cartoon", "heat", "cartoon_heat", "footsteps"}


def _render_filter_preview(raw: bytes, video_filter: str) -> bytes:
    """프레임 1장 → 필터 적용 JPEG 바이트. 순수 CPU 바운드 — 반드시 threadpool에서 호출한다.

    "heat"는 MediaPipe 포즈 검출까지 도는 무거운 경로(실측 0.7~0.9초/호출)라, 이벤트
    루프에서 직접 돌리면 그동안 API 전체가 멈춘다.
    """
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise api_error(400, E_IMAGE_FORMAT_INVALID, "이미지를 디코드할 수 없습니다")

    h, w = img.shape[:2]
    if w > PREVIEW_MAX_WIDTH:
        img = cv2.resize(
            img, (PREVIEW_MAX_WIDTH, int(h * PREVIEW_MAX_WIDTH / w)), interpolation=cv2.INTER_AREA
        )

    if video_filter == "cartoon":
        from app.services.cartoon import adaptive_gamma, cartoon_frame

        out = cartoon_frame(img, adaptive_gamma(img))
    elif video_filter == "footsteps":
        from app.services.motion_fx import footsteps_preview_frame

        out = footsteps_preview_frame(img)
    else:
        from app.services.muscle_heat import heat_preview_frame

        out = heat_preview_frame(img, weak_cartoon=video_filter == "cartoon_heat")

    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise api_error(500, E_VIDEO_PROCESS_FAILED, "미리보기 생성에 실패했습니다")
    return buf.tobytes()


@router.post("/filter-preview")
async def filter_preview(
    frame: UploadFile = File(...),
    video_filter: str = Form("cartoon"),
    current_user: User = Depends(get_active_user),
):
    """업로드 미리보기: 프레임 1장에 영상 필터를 적용해 JPEG로 반환한다.

    워커 파이프라인과 동일한 렌더러(`app.services.cartoon`, `app.services.muscle_heat`)를
    사용하므로 미리보기 룩과 최종 결과물이 일치한다. "heat"/"cartoon_heat"는 프레임 1장만
    받으므로 움직임 신호가 없어 정적 부하(오버헤드 지지·깊은 무릎 굽힘)만 반영된다 — 실제
    영상에서는 동작에 따라 열이 더 진해진다.
    """
    from fastapi.responses import Response
    from starlette.concurrency import run_in_threadpool

    if video_filter not in ALLOWED_VIDEO_FILTERS:
        raise api_error(400, E_VIDEO_FORMAT_INVALID, f"지원하지 않는 필터입니다: {video_filter}")

    raw = await frame.read()
    if len(raw) == 0:
        raise api_error(400, E_IMAGE_FORMAT_INVALID, "빈 파일입니다")
    if len(raw) > MAX_PREVIEW_IMAGE_SIZE:
        raise api_error(413, E_IMAGE_TOO_LARGE, "미리보기 프레임이 너무 큽니다 (최대 10MB)")

    jpeg = await run_in_threadpool(_render_filter_preview, raw, video_filter)
    return Response(content=jpeg, media_type="image/jpeg")


@router.post("/upload-multi")
async def upload_multi(
    files: list[UploadFile] = File(...),
    items_meta: str = Form(...),
    caption: str | None = Form(None),
    tags: str = Form("[]"),
    challenge_id: int | None = Form(None),
    workout_start: str | None = Form(None),
    workout_end: str | None = Form(None),
    audio: UploadFile | None = File(None),
    audio_duration_sec: int = Form(0),
    subtitle_srt: str | None = Form(None),
    subtitle_text: str | None = Form(None),
    subtitle_size: str | None = Form(None),
    subtitle_position: str | None = Form(None),
    subtitle_language: SubtitleLanguage = Form("ko"),
    mute_video: bool = Form(False),
    video_filter: str | None = Form(None),
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = ...,
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    """다중 미디어(영상 ≤1 + 이미지 ≤5)를 순서대로 받아 합성 파이프라인에 등록한다.

    items_meta: JSON 배열 `[{"kind": "image"|"video"}, ...]` — files 순서와 1:1 대응.
    video_filter: 합성본 전체에 적용할 영상 필터. "cartoon"(카툰) / "heat"(신체 열감 강조) /
        "cartoon_heat"(약한 카툰 위에 신체 열감 강조) 중 하나.
    파일 수신 즉시 job_id 반환, R2 업로드 + 처리는 백그라운드.
    """
    if video_filter is not None and video_filter not in ALLOWED_VIDEO_FILTERS:
        raise api_error(400, E_VIDEO_FORMAT_INVALID, f"지원하지 않는 필터입니다: {video_filter}")
    try:
        meta = json.loads(items_meta)
    except (json.JSONDecodeError, TypeError):
        raise api_error(400, E_VIDEO_FORMAT_INVALID, "items_meta 형식이 올바르지 않습니다")

    if not isinstance(meta, list) or not files or len(meta) != len(files):
        raise api_error(400, E_VIDEO_FORMAT_INVALID, "items_meta와 파일 수가 일치하지 않습니다")

    kinds = [str(m.get("kind")) if isinstance(m, dict) else "" for m in meta]
    n_video = sum(1 for k in kinds if k == "video")
    n_image = sum(1 for k in kinds if k == "image")
    if n_video > 1:
        raise api_error(400, E_VIDEO_FORMAT_INVALID, "영상은 1개까지만 업로드할 수 있습니다")
    if n_image > MAX_MEDIA_IMAGES:
        raise api_error(400, E_IMAGE_FORMAT_INVALID, f"이미지는 최대 {MAX_MEDIA_IMAGES}장까지 업로드할 수 있습니다")
    if n_video + n_image != len(files) or (n_video + n_image) == 0:
        raise api_error(400, E_VIDEO_FORMAT_INVALID, "지원하지 않는 미디어 구성입니다")

    tags_list = _parse_tags(tags)

    spooled: list[tuple[str, str, str, str]] = []  # (kind, path, content_type, filename)
    audio_path: str | None = None
    audio_content_type = "audio/webm"
    try:
        for upload, kind in zip(files, kinds):
            content_type = upload.content_type or ("video/mp4" if kind == "video" else "image/jpeg")
            if kind == "video":
                if content_type not in r2_service.ALLOWED_CONTENT_TYPES:
                    raise api_error(400, E_VIDEO_FORMAT_INVALID, f"지원하지 않는 영상 형식입니다: {content_type}")
                path, _ = await _spool_upload_to_temp(upload, r2_service.MAX_FILE_SIZE, "영상")
            elif kind == "image":
                if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
                    raise api_error(400, E_IMAGE_FORMAT_INVALID, f"지원하지 않는 이미지 형식입니다: {content_type}")
                path, _ = await _spool_upload_to_temp(upload, MAX_IMAGE_SIZE, "이미지")
            else:
                raise api_error(400, E_VIDEO_FORMAT_INVALID, f"알 수 없는 미디어 종류: {kind}")
            spooled.append((kind, path, content_type, upload.filename or f"{kind}"))

        if audio is not None:
            audio_content_type = audio.content_type or "audio/webm"
            audio_path, _ = await _spool_upload_to_temp(audio, r2_service.MAX_FILE_SIZE, "오디오")

        job_id = reserve_job_id(current_user.id, job_type="multi-pipeline")
    except Exception:
        for _, p, _, _ in spooled:
            try:
                os.unlink(p)
            except OSError:
                pass
        if audio_path:
            try:
                os.unlink(audio_path)
            except OSError:
                pass
        raise

    logger.info("upload_multi: user_id=%s job_id=%s items=%d", current_user.id, job_id, len(spooled))

    background_tasks.add_task(
        _r2_upload_and_enqueue_multi,
        job_id=job_id,
        spooled=spooled,
        audio_path=audio_path,
        audio_content_type=audio_content_type,
        user_id=current_user.id,
        caption=caption,
        tags_list=tags_list,
        challenge_id=challenge_id,
        workout_start=workout_start,
        workout_end=workout_end,
        audio_duration_sec=audio_duration_sec,
        subtitle_srt=subtitle_srt,
        subtitle_text=subtitle_text,
        subtitle_size=subtitle_size,
        subtitle_position=subtitle_position,
        subtitle_language=subtitle_language,
        mute_video_audio=mute_video,
        video_filter=video_filter,
    )

    return {"data": {"job_id": job_id, "status": "processing"}}
