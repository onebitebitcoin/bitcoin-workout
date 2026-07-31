import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.admin_log import AdminLog
from app.models.app_links import AppLinks
from app.models.challenge import Challenge, ChallengeParticipation
from app.models.comment import Comment
from app.models.notification import Notification
from app.models.post import Post
from app.models.post_like import PostLike
from app.models.post_view import PostView
from app.models.reward import RewardPoint
from app.models.user import User
from app.models.video import Video
from app.schemas.video import VideoSchema
from app.services import r2 as r2_service
from app.services.error_codes import (
    E_ADMIN_API_KEY_DELETE,
    E_ADMIN_REQUIRED,
    E_ADMIN_SELF_DELETE,
    E_AUTH_INVALID_TOKEN,
    E_AUTH_REQUIRED,
    E_UPLOAD_URL_FAILED,
    E_USER_NOT_FOUND,
    E_VIDEO_NOT_FOUND,
    api_error,
)
from app.services.reward import (
    REWARD_STATUS_FIXED,
    UTC,
    get_week_range,
    hashrate_filters,
    revoke_queued_upload_reward,
    settle_queued_rewards,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin(
    request: Request,
    x_admin_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    # CI/CD 서버-to-서버: X-Admin-Key 헤더로 인증
    if x_admin_key and x_admin_key == settings.admin_secret_key:
        return None

    # 일반 브라우저: Bearer JWT 인증
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise api_error(401, E_AUTH_REQUIRED, "인증이 필요합니다")
    from app.services.auth import decode_token, get_user_by_id
    user_id = decode_token(auth.removeprefix("Bearer "))
    if user_id is None:
        raise api_error(401, E_AUTH_INVALID_TOKEN, "유효하지 않은 토큰입니다")
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_admin:
        raise api_error(403, E_ADMIN_REQUIRED, "관리자 권한이 필요합니다")
    return user


@router.get("/videos")
def list_videos(
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    offset = (page - 1) * limit
    base_q = db.query(Video)

    total: int = base_q.count()

    videos = (
        base_q
        .order_by(Video.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    video_ids = [v.id for v in videos]
    video_user_ids = [v.user_id for v in videos]
    video_users_map = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(video_user_ids)).all()
    } if video_user_ids else {}
    thumbnail_map: dict[int, str | None] = dict(
        db.query(Post.video_id, Post.thumbnail_url)
        .filter(Post.video_id.in_(video_ids))
        .all()
    ) if video_ids else {}

    result = [
        {
            "id": v.id,
            "user_id": v.user_id,
            "username": video_users_map[v.user_id].username if v.user_id in video_users_map else "",
            "r2_key": v.r2_key,
            "cdn_url": v.cdn_url,
            "thumbnail_url": thumbnail_map.get(v.id),
            "duration_sec": v.duration_sec,
            "status": v.status,
            "created_at": v.created_at.isoformat(),
        }
        for v in videos
    ]
    return {"data": {"videos": result, "total": total, "page": page, "limit": limit}}


@router.patch("/videos/{video_id}/reject")
def reject_video(
    video_id: int,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise api_error(404, E_VIDEO_NOT_FOUND, "영상을 찾을 수 없습니다")

    revoke_queued_upload_reward(db, video.id)
    video.status = "rejected"
    db.commit()
    db.refresh(video)
    return {"data": {"video": VideoSchema.model_validate(video)}}


@router.delete("/videos/{video_id}")
def delete_video(
    video_id: int,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    video = db.query(Video).filter(Video.id == video_id).first()
    if video is None:
        raise api_error(404, E_VIDEO_NOT_FOUND, "영상을 찾을 수 없습니다")

    r2_key = video.r2_key
    revoke_queued_upload_reward(db, video.id)

    post = db.query(Post).filter(Post.video_id == video_id).first()
    if post:
        db.query(Notification).filter(Notification.post_id == post.id).delete()
        db.query(PostView).filter(PostView.post_id == post.id).delete()
        db.query(PostLike).filter(PostLike.post_id == post.id).delete()
        db.query(Comment).filter(Comment.post_id == post.id).delete()
        db.delete(post)
    db.delete(video)

    log = AdminLog(
        action="video_delete",
        target_type="video",
        target_id=video_id,
        detail=r2_key,
    )
    db.add(log)
    db.commit()

    try:
        r2_service.delete_object(r2_key)
    except Exception:
        pass

    return {"data": {"video_id": video_id}}


@router.get("/users")
def list_users(
    page: int = 1,
    limit: int = 20,
    search: str = "",
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    settled_count = settle_queued_rewards(db)
    if settled_count:
        db.commit()

    query = db.query(User)
    if search:
        query = query.filter(
            or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            )
        )

    total = query.count()
    offset = (page - 1) * limit
    users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    user_ids = [u.id for u in users]

    video_counts: dict = {}
    point_totals: dict = {}
    challenge_counts: dict = {}
    referred_counts: dict = {}
    inviter_names: dict = {}
    if user_ids:
        video_counts = dict(
            db.query(Video.user_id, func.count(Video.id))
            .filter(Video.user_id.in_(user_ids), Video.status == "active")
            .group_by(Video.user_id)
            .all()
        )
        point_totals = dict(
            db.query(RewardPoint.user_id, func.sum(RewardPoint.points))
            .filter(
                RewardPoint.user_id.in_(user_ids),
                RewardPoint.status == REWARD_STATUS_FIXED,
            )
            .group_by(RewardPoint.user_id)
            .all()
        )
        challenge_counts = dict(
            db.query(ChallengeParticipation.user_id, func.count(ChallengeParticipation.id))
            .filter(ChallengeParticipation.user_id.in_(user_ids))
            .group_by(ChallengeParticipation.user_id)
            .all()
        )
        # 이 유저들이 각각 데려온 가입자 수 (referred_by_id == 이 유저)
        referred_counts = dict(
            db.query(User.referred_by_id, func.count(User.id))
            .filter(User.referred_by_id.in_(user_ids))
            .group_by(User.referred_by_id)
            .all()
        )
        # 이 유저들을 초대한 사람(inviter)의 username
        inviter_ids = {u.referred_by_id for u in users if u.referred_by_id is not None}
        if inviter_ids:
            inviter_names = dict(
                db.query(User.id, User.username).filter(User.id.in_(inviter_ids)).all()
            )

    def _auth_provider(u: User) -> str:
        if u.oauth_provider == "google":
            return "google"
        if u.oauth_provider == "lnauth":
            return "lightning"
        return "email"

    result = [
        {
            "id": u.id,
            "email": u.email,
            "username": u.username,
            "lightning_address": u.lightning_address,
            "is_banned": u.is_banned,
            "is_admin": u.is_admin,
            "auth_provider": _auth_provider(u),
            "video_count": video_counts.get(u.id, 0),
            "total_points": point_totals.get(u.id, 0),
            "challenge_count": challenge_counts.get(u.id, 0),
            "referred_count": referred_counts.get(u.id, 0),
            "referred_by_username": inviter_names.get(u.referred_by_id) if u.referred_by_id else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]
    return {"data": {"users": result, "total": total, "page": page, "limit": limit, "has_next": offset + limit < total}}


@router.patch("/users/{user_id}/ban")
def toggle_ban(
    user_id: int,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise api_error(404, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")
    user.is_banned = not user.is_banned
    log = AdminLog(
        action="ban_toggle",
        target_type="user",
        target_id=user_id,
        detail=f"is_banned={user.is_banned}",
    )
    db.add(log)
    db.commit()
    db.refresh(user)
    return {"data": {"user_id": user_id, "is_banned": user.is_banned}}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User | None = Depends(require_admin),
) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise api_error(404, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")
    if admin is not None and user.id == admin.id:
        raise api_error(400, E_ADMIN_SELF_DELETE, "자신의 계정은 삭제할 수 없습니다")
    # X-Admin-Key (admin=None) cannot delete admin accounts — no self-identity check possible
    if admin is None and user.is_admin:
        raise api_error(400, E_ADMIN_API_KEY_DELETE, "API 키로는 관리자 계정을 삭제할 수 없습니다")

    # 영상 R2 키 수집 후 DB 삭제
    videos = db.query(Video).filter(Video.user_id == user_id).all()
    r2_keys = [v.r2_key for v in videos]

    video_ids = [v.id for v in videos]
    db.query(Notification).filter(
        or_(Notification.user_id == user_id, Notification.actor_id == user_id)
    ).delete(synchronize_session=False)
    if video_ids:
        post_id_subq = db.query(Post.id).filter(Post.video_id.in_(video_ids))
        db.query(PostView).filter(PostView.post_id.in_(post_id_subq)).delete(synchronize_session=False)
        db.query(PostLike).filter(PostLike.post_id.in_(post_id_subq)).delete(synchronize_session=False)
        db.query(Comment).filter(Comment.post_id.in_(post_id_subq)).delete(synchronize_session=False)
        db.query(Post).filter(Post.video_id.in_(video_ids)).delete(synchronize_session=False)
        db.query(Video).filter(Video.user_id == user_id).delete(synchronize_session=False)

    db.query(Comment).filter(Comment.user_id == user_id).delete(synchronize_session=False)
    db.query(RewardPoint).filter(RewardPoint.user_id == user_id).delete(synchronize_session=False)
    db.query(ChallengeParticipation).filter(ChallengeParticipation.user_id == user_id).delete(synchronize_session=False)
    # 타 게시물에 누른 좋아요/조회 행 삭제 (FK: post_like.user_id, post_view.user_id)
    db.query(PostLike).filter(PostLike.user_id == user_id).delete(synchronize_session=False)
    db.query(PostView).filter(PostView.user_id == user_id).delete(synchronize_session=False)
    # 생성한 챌린지 creator_id NULL 처리 (챌린지 자체는 보존)
    db.query(Challenge).filter(Challenge.creator_id == user_id).update(
        {"creator_id": None}, synchronize_session=False
    )

    log = AdminLog(
        action="user_delete",
        target_type="user",
        target_id=user_id,
        detail=user.username,
    )
    db.add(log)
    db.delete(user)
    db.commit()

    for key in r2_keys:
        try:
            r2_service.delete_object(key)
        except Exception:
            pass

    return {"data": {"user_id": user_id}}


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    settled_count = settle_queued_rewards(db, user_id)
    if settled_count:
        db.commit()

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise api_error(404, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")

    videos = (
        db.query(Video)
        .filter(Video.user_id == user_id)
        .order_by(Video.created_at.desc())
        .limit(20)
        .all()
    )

    participations = (
        db.query(ChallengeParticipation)
        .filter(ChallengeParticipation.user_id == user_id)
        .order_by(ChallengeParticipation.joined_at.desc())
        .all()
    )

    total_points = (
        db.query(func.sum(RewardPoint.points))
        .filter(
            RewardPoint.user_id == user_id,
            RewardPoint.status == REWARD_STATUS_FIXED,
        )
        .scalar()
        or 0
    )

    return {
        "data": {
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "lightning_address": user.lightning_address,
                "is_banned": user.is_banned,
                "is_admin": user.is_admin,
                "created_at": user.created_at.isoformat(),
            },
            "videos": [
                {
                    "id": v.id,
                    "cdn_url": v.cdn_url,
                    "status": v.status,
                    "created_at": v.created_at.isoformat(),
                }
                for v in videos
            ],
            "challenges": [
                {
                    "challenge_id": p.challenge_id,
                    "title": p.challenge.title if p.challenge else "",
                    "upload_count": p.upload_count,
                    "condition_value": p.challenge.condition_value if p.challenge else 0,
                    "completed": p.completed_at is not None,
                    "joined_at": p.joined_at.isoformat(),
                }
                for p in participations
            ],
            "total_points": round(float(total_points), 2),
        }
    }


@router.get("/challenges")
def admin_list_challenges(
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    challenges = db.query(Challenge).order_by(Challenge.created_at.desc()).all()

    creator_ids = list({c.creator_id for c in challenges if c.creator_id})
    creator_map: dict[int, User] = {}
    if creator_ids:
        creator_map = {u.id: u for u in db.query(User).filter(User.id.in_(creator_ids)).all()}

    participant_counts: dict[int, int] = dict(
        db.query(ChallengeParticipation.challenge_id, func.count(ChallengeParticipation.id))
        .group_by(ChallengeParticipation.challenge_id)
        .all()
    )

    return {
        "data": {
            "challenges": [
                {
                    "id": c.id,
                    "title": c.title,
                    "creator_username": creator_map[c.creator_id].username if c.creator_id and c.creator_id in creator_map else None,
                    "is_active": c.is_active,
                    "participant_count": participant_counts.get(c.id, 0),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "end_date": c.end_date.isoformat() if c.end_date else None,
                }
                for c in challenges
            ],
            "total": len(challenges),
        }
    }


@router.get("/hashrate")
def admin_hashrate(
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    """이번 주 활동 사용자별 포인트·비중(%) 목록.

    프로필 해시레이트(/users/me/hashrate)와 동일 기준 — 집계 조건은
    hashrate_filters() 단일 원본을 공유한다.
    """
    rows = (
        db.query(
            RewardPoint.user_id,
            User.username,
            func.sum(RewardPoint.points).label("points"),
            func.sum(case((RewardPoint.reason == "upload", 1), else_=0)).label("upload_count"),
            func.sum(
                case(
                    (RewardPoint.reason == "comment", 1),
                    (RewardPoint.reason == "comment_revoke", -1),
                    else_=0,
                )
            ).label("comment_count"),
        )
        .join(User, User.id == RewardPoint.user_id)
        .filter(*hashrate_filters())
        .group_by(RewardPoint.user_id, User.username)
        .order_by(func.sum(RewardPoint.points).desc(), RewardPoint.user_id.asc())
        .all()
    )
    # ponytail: 페이지네이션 없음 — 주간 활동 사용자 규모가 수십 명 수준. 수백 명 넘으면 추가.
    total = float(sum(row.points for row in rows))
    items = [
        {
            "rank": idx + 1,
            "user_id": row.user_id,
            "username": row.username,
            "points": round(float(row.points), 2),
            "upload_count": int(row.upload_count),
            "comment_count": int(row.comment_count),
            "percent": round(float(row.points) / total * 100, 1) if total > 0 else 0.0,
        }
        for idx, row in enumerate(rows)
    ]
    return {"data": {"items": items, "total_points": round(total, 2)}}


@router.get("/hashrate/{user_id}")
def admin_hashrate_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    """이번 주 특정 사용자의 활동 상세 — 업로드 영상·댓글 목록 (포인트 항목 기준)."""
    target = db.get(User, user_id)
    if target is None:
        raise api_error(404, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")

    rows = (
        db.query(RewardPoint)
        .filter(RewardPoint.user_id == user_id, *hashrate_filters())
        .order_by(RewardPoint.created_at.desc())
        .all()
    )

    # ponytail: 주간 개인 활동은 수십 건 수준이라 건별 조회로 충분. 느려지면 일괄 join.
    uploads = []
    comments = []
    for rp in rows:
        if rp.reason == "upload":
            video = db.get(Video, rp.reference_id) if rp.reference_id else None
            post = video.post if video else None
            uploads.append({
                "post_id": post.id if post else None,
                "caption": post.caption if post else None,
                "tags": json.loads(post.tags) if post and post.tags else [],
                "thumbnail_url": post.thumbnail_url if post else None,
                "share_token": post.share_token if post else None,
                "points": rp.points,
                "status": rp.status,
                "created_at": rp.created_at,
            })
        elif rp.reason in ("comment", "comment_revoke"):
            comment = db.get(Comment, rp.reference_id) if rp.reference_id else None
            comments.append({
                "content": comment.content if comment else None,  # None = 삭제된 댓글
                "post_id": comment.post_id if comment else None,
                "points": rp.points,
                "created_at": rp.created_at,
            })

    total = float(sum(rp.points for rp in rows))
    return {
        "data": {
            "user_id": user_id,
            "username": target.username,
            "total_points": round(total, 2),
            "uploads": uploads,
            "comments": comments,
        }
    }


@router.get("/weekly-summary")
def weekly_summary(
    page: int = 1,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    _ = x_client_timezone  # Accepted for API compatibility; admin settlement uses UTC globally.
    week_start_utc, week_end_utc = get_week_range(UTC)

    settled_count = settle_queued_rewards(db)
    if settled_count:
        db.commit()

    base_query = (
        db.query(
            RewardPoint.user_id,
            User.username,
            func.sum(RewardPoint.points).label("weekly_points"),
        )
        .join(User, User.id == RewardPoint.user_id)
        .filter(
            RewardPoint.created_at >= week_start_utc,
            RewardPoint.created_at < week_end_utc,
            RewardPoint.status == REWARD_STATUS_FIXED,
            User.is_banned.is_(False),
        )
        .group_by(RewardPoint.user_id, User.username)
    )

    total_users: int = base_query.count()

    offset = (page - 1) * limit
    rows = (
        base_query
        .order_by(func.sum(RewardPoint.points).desc(), RewardPoint.user_id.asc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )

    has_next = len(rows) > limit
    rows = rows[:limit]

    items = [
        {
            "rank": offset + idx + 1,
            "user_id": row.user_id,
            "username": row.username,
            "weekly_points": row.weekly_points,
        }
        for idx, row in enumerate(rows)
    ]

    return {
        "data": {
            "items": items,
            "page": page,
            "has_next": has_next,
            "total_users": total_users,
        }
    }


class AppLinksRequest(BaseModel):
    android_url: str | None = None
    ios_url: str | None = None


class AppUploadUrlRequest(BaseModel):
    platform: Literal["android", "ios"]
    filename: str
    content_type: str


class AppUploadConfirmRequest(BaseModel):
    platform: Literal["android", "ios"]
    cdn_url: str
    filename: str


def _app_links_data(links: AppLinks | None) -> dict:
    if not links:
        return {"android_url": None, "ios_url": None, "android_filename": None, "ios_filename": None}
    return {
        "android_url": links.android_url,
        "ios_url": links.ios_url,
        "android_filename": links.android_filename,
        "ios_filename": links.ios_filename,
    }


@router.get("/app-links")
def get_app_links(
    db: Session = Depends(get_db),
) -> dict:
    links = db.query(AppLinks).first()
    return {"data": _app_links_data(links)}


@router.put("/app-links")
def update_app_links(
    body: AppLinksRequest,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    links = db.query(AppLinks).first()
    if not links:
        links = AppLinks()
        db.add(links)
    links.android_url = body.android_url or None
    links.ios_url = body.ios_url or None
    links.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(links)
    return {"data": _app_links_data(links)}


@router.post("/app-links/upload-url")
def get_app_upload_url(
    body: AppUploadUrlRequest,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    try:
        upload_url, r2_key = r2_service.generate_apk_presigned_url(
            body.content_type, body.filename, body.platform
        )
    except Exception as exc:
        raise api_error(500, E_UPLOAD_URL_FAILED, "업로드를 시작할 수 없습니다. 잠시 후 다시 시도해주세요") from exc
    cdn_url = r2_service.get_cdn_url(r2_key)
    return {"data": {"upload_url": upload_url, "r2_key": r2_key, "cdn_url": cdn_url}}


@router.post("/app-links/confirm-upload")
def confirm_app_upload(
    body: AppUploadConfirmRequest,
    db: Session = Depends(get_db),
    _: User | None = Depends(require_admin),
) -> dict:
    links = db.query(AppLinks).first()
    if not links:
        links = AppLinks()
        db.add(links)
    if body.platform == "android":
        links.android_url = body.cdn_url
        links.android_filename = body.filename
    else:
        links.ios_url = body.cdn_url
        links.ios_filename = body.filename
    links.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(links)
    return {"data": _app_links_data(links)}
