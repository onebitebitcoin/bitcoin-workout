from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session, selectinload, joinedload

from app.database import get_db
from app.models.challenge import ChallengeParticipation
from app.models.comment import Comment
from app.models.follow import Follow
from app.models.post import Post
from app.models.user import User
from app.models.video import Video
from app.routes.auth import get_active_user, get_optional_user
from app.routes.auth import get_current_user as get_required_user
from app.services.notification import create_notification
from app.services.referral import generate_referral_code
from app.services.error_codes import api_error, E_USER_NOT_FOUND, E_FORBIDDEN

router = APIRouter(prefix="/api/v1/users", tags=["users"])


class PublicUserSchema(BaseModel):
    id: int
    username: str
    avatar_url: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class PublicPostSchema(BaseModel):
    id: int
    cdn_url: str
    thumbnail_url: str | None = None
    subtitle_url: str | None = None
    subtitle_text: str | None = None
    subtitle_status: str = "skipped"
    like_count: int
    view_count: int
    comment_count: int
    caption: str | None
    created_at: datetime


class TitleSchema(BaseModel):
    title: str
    challenge_title: str
    completed_at: datetime


class ActiveChallengeSchema(BaseModel):
    challenge_id: int
    title: str
    upload_count: int
    condition_value: int


@router.get("/me/referral")
def get_my_referral(
    current_user: User = Depends(get_required_user),
    db: Session = Depends(get_db),
) -> dict:
    """내 초대 코드·링크·초대 수 반환 (보상 없음)."""
    if not current_user.referral_code:
        current_user.referral_code = generate_referral_code(db)
        db.commit()
    invited_count = (
        db.query(sqlfunc.count(User.id)).filter(User.referred_by_id == current_user.id).scalar() or 0
    )
    return {
        "data": {
            "referral_code": current_user.referral_code,
            "invited_count": invited_count,
        }
    }


@router.get("/me/stats")
def get_my_stats(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_required_user),
    db: Session = Depends(get_db),
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    _ = x_client_timezone  # Accepted for API compatibility.

    total_posts = (
        db.query(Post)
        .join(Post.video)
        .filter(
            Post.user_id == current_user.id,
            Video.status == "active",
        )
        .count()
    )

    return {
        "data": {
            "total_posts": total_posts,
        }
    }


@router.get("/{user_id}/profile")
def get_user_profile(
    user_id: int,
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.is_banned:
        raise api_error(404, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")

    follower_count = db.query(sqlfunc.count(Follow.id)).filter(Follow.following_id == user_id).scalar() or 0
    following_count = db.query(sqlfunc.count(Follow.id)).filter(Follow.follower_id == user_id).scalar() or 0
    is_following = False
    if viewer and viewer.id != user_id:
        is_following = (
            db.query(Follow.id)
            .filter(Follow.follower_id == viewer.id, Follow.following_id == user_id)
            .first()
            is not None
        )

    post_count = (
        db.query(Post)
        .join(Post.video)
        .filter(Post.user_id == user_id, Video.status == "active")
        .count()
    )
    posts_raw = (
        db.query(Post)
        .join(Post.video)
        .filter(Post.user_id == user_id, Video.status == "active")
        .options(selectinload(Post.video))
        .order_by(Post.created_at.desc())
        .limit(50)
        .all()
    )
    post_ids = [p.id for p in posts_raw]
    comment_counts: dict[int, int] = {}
    if post_ids:
        comment_counts = dict(
            db.query(Comment.post_id, sqlfunc.count(Comment.id))
            .filter(Comment.post_id.in_(post_ids))
            .group_by(Comment.post_id)
            .all()
        )
    posts = [
        PublicPostSchema(
            id=p.id,
            cdn_url=p.video.cdn_url,
            thumbnail_url=p.thumbnail_url,
            subtitle_url=p.video.subtitle_url,
            subtitle_text=p.video.subtitle_text,
            subtitle_status=p.video.subtitle_status,
            like_count=p.like_count,
            view_count=p.view_count,
            comment_count=comment_counts.get(p.id, 0),
            caption=p.caption,
            created_at=p.created_at,
        )
        for p in posts_raw
    ]

    participations = (
        db.query(ChallengeParticipation)
        .filter(ChallengeParticipation.user_id == user_id)
        .options(joinedload(ChallengeParticipation.challenge))
        .all()
    )

    titles = [
        TitleSchema(
            title=p.challenge.reward_title,
            challenge_title=p.challenge.title,
            completed_at=p.completed_at,
        )
        for p in participations
        if p.completed_at is not None
    ]

    active_challenges = [
        ActiveChallengeSchema(
            challenge_id=p.challenge_id,
            title=p.challenge.title,
            upload_count=p.upload_count,
            condition_value=p.challenge.condition_value,
        )
        for p in participations
        if p.completed_at is None and p.challenge.is_active
    ]

    return {
        "data": {
            "user": PublicUserSchema.model_validate(user),
            "post_count": post_count,
            "posts": posts,
            "titles": titles,
            "active_challenges": active_challenges,
            "follower_count": follower_count,
            "following_count": following_count,
            "is_following": is_following,
        }
    }


# ---------------------------------------------------------------------------
# 팔로우 (MVP)
# ---------------------------------------------------------------------------

def _follow_user_summary(u: User, following_ids: set[int]) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "avatar_url": u.avatar_url,
        "profile_color": (u.app_settings or {}).get("profile_color"),
        "is_following": u.id in following_ids,
    }


@router.post("/{user_id}/follow")
def follow_user(
    user_id: int,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> dict:
    if user_id == current_user.id:
        raise api_error(400, E_FORBIDDEN, "자기 자신을 팔로우할 수 없습니다")
    target = db.query(User).filter(User.id == user_id).first()
    if not target or target.is_banned:
        raise api_error(404, E_USER_NOT_FOUND, "사용자를 찾을 수 없습니다")

    existing = (
        db.query(Follow)
        .filter(Follow.follower_id == current_user.id, Follow.following_id == user_id)
        .first()
    )
    if not existing:
        db.add(Follow(follower_id=current_user.id, following_id=user_id))
        create_notification(db, recipient_id=user_id, actor_id=current_user.id, type="follow")
        db.commit()

    follower_count = db.query(sqlfunc.count(Follow.id)).filter(Follow.following_id == user_id).scalar() or 0
    return {"data": {"is_following": True, "follower_count": follower_count}}


@router.delete("/{user_id}/follow")
def unfollow_user(
    user_id: int,
    current_user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> dict:
    existing = (
        db.query(Follow)
        .filter(Follow.follower_id == current_user.id, Follow.following_id == user_id)
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()

    follower_count = db.query(sqlfunc.count(Follow.id)).filter(Follow.following_id == user_id).scalar() or 0
    return {"data": {"is_following": False, "follower_count": follower_count}}


@router.get("/{user_id}/followers")
def list_followers(
    user_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
) -> dict:
    rows = (
        db.query(User)
        .join(Follow, Follow.follower_id == User.id)
        .filter(Follow.following_id == user_id, User.is_banned == False)  # noqa: E712
        .order_by(Follow.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    following_ids = _viewer_following_ids(db, viewer, [u.id for u in rows])
    return {"data": {"users": [_follow_user_summary(u, following_ids) for u in rows]}}


@router.get("/{user_id}/following")
def list_following(
    user_id: int,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    viewer: User | None = Depends(get_optional_user),
) -> dict:
    rows = (
        db.query(User)
        .join(Follow, Follow.following_id == User.id)
        .filter(Follow.follower_id == user_id, User.is_banned == False)  # noqa: E712
        .order_by(Follow.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    following_ids = _viewer_following_ids(db, viewer, [u.id for u in rows])
    return {"data": {"users": [_follow_user_summary(u, following_ids) for u in rows]}}


def _viewer_following_ids(db: Session, viewer: User | None, candidate_ids: list[int]) -> set[int]:
    """viewer가 candidate_ids 중 팔로우 중인 id 집합 (N+1 회피용 batch 조회)."""
    if not viewer or not candidate_ids:
        return set()
    rows = (
        db.query(Follow.following_id)
        .filter(Follow.follower_id == viewer.id, Follow.following_id.in_(candidate_ids))
        .all()
    )
    return {r[0] for r in rows}
