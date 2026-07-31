from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_
from sqlalchemy import func as sqlfunc
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import SessionLocal, get_db
from app.models.challenge import ChallengeParticipation
from app.models.comment import Comment
from app.models.follow import Follow
from app.models.post import Post
from app.models.reward import RewardPoint
from app.models.user import User
from app.models.video import Video
from app.routes.auth import get_active_user, get_optional_user
from app.routes.auth import get_current_user as get_required_user
from app.services.error_codes import E_FORBIDDEN, E_USER_NOT_FOUND, api_error
from app.services.notification import create_notification
from app.services.referral import generate_referral_code
from app.services.reward import (
    KST,
    REWARD_STATUS_FIXED,
    REWARD_STATUS_QUEUED,
    UTC,
    _parse_tz,
    get_month_range,
    get_week_range,
    get_weekly_hashrate,
    get_weekly_points,
    get_weekly_queued_points,
    settle_queued_rewards,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def _settle_rewards_background(user_id: int) -> None:
    db = SessionLocal()
    try:
        settled = settle_queued_rewards(db, user_id)
        if settled:
            db.commit()
    finally:
        db.close()


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


@router.get("/me/hashrate")
def get_my_hashrate(
    current_user: User = Depends(get_required_user),
    db: Session = Depends(get_db),
) -> dict:
    """이번 주 해시레이트(전체 점수 대비 내 점수 비중 %) 반환."""
    my_points, total_points = get_weekly_hashrate(db, current_user.id)
    percent = (my_points / total_points * 100) if total_points > 0 else 0.0
    return {
        "data": {
            "my_points": round(my_points, 2),
            "total_points": round(total_points, 2),
            "percent": round(percent, 1),
        }
    }


@router.get("/me/stats")
def get_my_stats(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_required_user),
    db: Session = Depends(get_db),
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    _ = x_client_timezone  # Accepted for API compatibility; reward totals use UTC globally.
    background_tasks.add_task(_settle_rewards_background, current_user.id)

    total_posts = (
        db.query(Post)
        .join(Post.video)
        .filter(
            Post.user_id == current_user.id,
            Video.status == "active",
        )
        .count()
    )

    total_points = (
        db.query(sqlfunc.sum(RewardPoint.points))
        .filter(
            RewardPoint.user_id == current_user.id,
            RewardPoint.points > 0,
            RewardPoint.status == REWARD_STATUS_FIXED,
        )
        .scalar()
        or 0
    )

    queued_points = (
        db.query(sqlfunc.sum(RewardPoint.points))
        .filter(
            RewardPoint.user_id == current_user.id,
            RewardPoint.points > 0,
            RewardPoint.status == REWARD_STATUS_QUEUED,
        )
        .scalar()
        or 0
    )

    week_points = get_weekly_points(db, current_user.id, UTC)
    week_queued = get_weekly_queued_points(db, current_user.id)

    return {
        "data": {
            "total_posts": total_posts,
            "total_points": round(float(total_points), 2),
            "queued_points": round(float(queued_points), 2),
            "week_points": round(float(week_points), 2),
            "week_queued_points": round(float(week_queued), 2),
        }
    }


@router.get("/me/weekly-points")
def get_my_weekly_points(
    current_user: User = Depends(get_required_user),
    db: Session = Depends(get_db),
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    client_tz = _parse_tz(x_client_timezone)
    week_start_utc, week_end_utc = get_week_range(UTC)

    # 계산 기준은 글로벌 UTC 주간이며, 표시용 날짜만 클라이언트 타임존으로 변환한다.
    start_date = week_start_utc.astimezone(client_tz).date().isoformat()
    end_date = (week_end_utc - timedelta(microseconds=1)).astimezone(client_tz).date().isoformat()
    week_number = week_start_utc.isocalendar().week

    records = (
        db.query(RewardPoint)
        .filter(
            RewardPoint.user_id == current_user.id,
            or_(
                and_(
                    RewardPoint.created_at >= week_start_utc,
                    RewardPoint.created_at < week_end_utc,
                    RewardPoint.status == REWARD_STATUS_FIXED,
                ),
                RewardPoint.status == REWARD_STATUS_QUEUED,
            ),
            RewardPoint.points > 0,
        )
        .order_by(RewardPoint.created_at.desc())
        .all()
    )

    total_points = sum(r.points for r in records if r.status == REWARD_STATUS_FIXED)

    def to_client_date(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(client_tz).date().isoformat()

    def to_utc_iso(dt: datetime) -> str:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    items = [
        {
            "date": to_client_date(r.created_at),
            "settles_at": to_utc_iso(r.created_at + timedelta(hours=24)) if r.status == REWARD_STATUS_QUEUED else None,
            "points": round(float(r.points), 2),
            "source": r.reason,
            "post_id": r.reference_id,
            "queued": r.status == REWARD_STATUS_QUEUED,
        }
        for r in records
    ]

    return {
        "data": {
            "week_number": week_number,
            "start_date": start_date,
            "end_date": end_date,
            "total_points": round(float(total_points), 2),
            "items": items,
        }
    }


@router.get("/me/monthly-points")
def get_my_monthly_points(
    current_user: User = Depends(get_required_user),
    db: Session = Depends(get_db),
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    _ = x_client_timezone  # Accepted for API compatibility; reward totals use UTC globally.
    month_start, month_end = get_month_range(UTC)

    month_points = (
        db.query(sqlfunc.sum(RewardPoint.points))
        .filter(
            RewardPoint.user_id == current_user.id,
            RewardPoint.points > 0,
            RewardPoint.status == REWARD_STATUS_FIXED,
            RewardPoint.created_at >= month_start,
            RewardPoint.created_at < month_end,
        )
        .scalar()
        or 0
    )

    return {
        "data": {
            "month_points": round(float(month_points), 2),
        }
    }


@router.get("/leaderboard")
def get_leaderboard(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=50),
    search: str = Query(""),
    period: str = Query("week"),  # "week" | "all"
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    _ = x_client_timezone  # Accepted for API compatibility; leaderboard periods use KST globally.

    point_join_cond = [
        RewardPoint.user_id == User.id,
        RewardPoint.points > 0,
        RewardPoint.status == REWARD_STATUS_FIXED,
    ]
    if period == "week":
        week_start_utc, week_end_utc = get_week_range(KST)
        point_join_cond.append(RewardPoint.created_at >= week_start_utc)
        point_join_cond.append(RewardPoint.created_at < week_end_utc)
    elif period == "month":
        month_start_utc, month_end_utc = get_month_range(KST)
        point_join_cond.append(RewardPoint.created_at >= month_start_utc)
        point_join_cond.append(RewardPoint.created_at < month_end_utc)

    base_query = (
        db.query(
            User,
            sqlfunc.coalesce(sqlfunc.sum(RewardPoint.points), 0).label("total_points"),
        )
        .outerjoin(RewardPoint, and_(*point_join_cond))
        .filter(User.is_banned.is_(False))
        .group_by(User.id)
    )

    if search:
        base_query = base_query.filter(User.username.ilike(f"%{search}%"))

    count_query = db.query(sqlfunc.count(User.id)).filter(User.is_banned.is_(False))
    if search:
        count_query = count_query.filter(User.username.ilike(f"%{search}%"))
    total: int = count_query.scalar() or 0

    offset = (page - 1) * limit

    rows = (
        base_query
        .order_by(sqlfunc.coalesce(sqlfunc.sum(RewardPoint.points), 0).desc(), User.id.asc())
        .offset(offset)
        .limit(limit + 1)
        .all()
    )

    has_next = len(rows) > limit
    rows = rows[:limit]

    return {
        "data": [
            {
                "rank": offset + idx + 1,
                "user_id": user.id,
                "username": user.username,
                "avatar_url": user.avatar_url,
                "total_points": round(float(total_points or 0), 1),
            }
            for idx, (user, total_points) in enumerate(rows)
        ],
        "total": total,
        "page": page,
        "limit": limit,
        "has_next": has_next,
        "period": period,
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
        .filter(Follow.following_id == user_id, User.is_banned == False)
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
        .filter(Follow.follower_id == user_id, User.is_banned == False)
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
