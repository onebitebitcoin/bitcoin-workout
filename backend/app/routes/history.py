from calendar import monthrange
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.post import Post
from app.models.user import User
from app.models.video import Video
from app.routes.auth import get_current_user as get_required_user

router = APIRouter(prefix="/api/v1/history", tags=["history"])


def _to_local_date(dt: datetime, tz: ZoneInfo) -> str:
    """Convert UTC datetime to local date string YYYY-MM-DD."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).strftime("%Y-%m-%d")


def _compute_streak(workout_dates: set[str], today_local: str) -> int:
    """Count consecutive days ending at today or yesterday (local time).
    If today has no workout yet, start from yesterday so the streak
    doesn't drop to 0 just because the day hasn't been completed yet.
    """
    today = datetime.strptime(today_local, "%Y-%m-%d").date()
    start = today if today_local in workout_dates else today - timedelta(days=1)
    streak = 0
    current = start
    while True:
        date_str = current.strftime("%Y-%m-%d")
        if date_str not in workout_dates:
            break
        streak += 1
        current -= timedelta(days=1)
    return streak


@router.get("")
def get_history(
    year: int | None = None,
    month: int | None = None,
    timezone_name: str | None = Query(None, alias="timezone"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_required_user),
) -> dict:
    try:
        tz = ZoneInfo(timezone_name) if timezone_name else ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz)

    if year is None:
        year = now_local.year
    if month is None:
        month = now_local.month

    last_day = monthrange(year, month)[1]

    # Convert user's month boundaries to UTC for querying
    month_start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=tz)
    month_end_local = datetime(year, month, last_day, 23, 59, 59, tzinfo=tz)
    month_start_utc = month_start_local.astimezone(timezone.utc)
    month_end_utc = month_end_local.astimezone(timezone.utc)

    posts = (
        db.query(Post)
        .join(Post.video)
        .filter(
            Post.user_id == current_user.id,
            Video.status == "active",
            Post.created_at >= month_start_utc,
            Post.created_at <= month_end_utc,
        )
        .order_by(Post.created_at.asc())
        .all()
    )

    workout_days: dict[str, list[dict]] = defaultdict(list)
    for post in posts:
        date_str = _to_local_date(post.created_at, tz)
        pd = datetime.strptime(date_str, "%Y-%m-%d")
        if pd.year == year and pd.month == month:
            workout_days[date_str].append(
                {
                    "id": post.id,
                    "cdn_url": post.video.cdn_url,
                    "thumbnail_url": post.thumbnail_url,
                    "like_count": post.like_count,
                    "view_count": post.view_count,
                    "caption": post.caption,
                }
            )

    all_dates = (
        db.query(Post.created_at)
        .join(Post.video)
        .filter(
            Post.user_id == current_user.id,
            Video.status == "active",
        )
        .all()
    )
    all_workout_dates = {_to_local_date(row[0], tz) for row in all_dates}

    today_local_str = now_local.strftime("%Y-%m-%d")
    streak = _compute_streak(all_workout_dates, today_local_str)

    return {
        "data": {
            "year": year,
            "month": month,
            "streak": streak,
            "total_days": len(workout_days),
            "workout_days": dict(workout_days),
        }
    }
