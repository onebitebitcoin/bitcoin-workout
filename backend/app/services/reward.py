from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.reward import RewardPoint
from app.models.video import Video

POINTS_LIGHT_ACTIVITY = 0.25
POINTS_SWEATY_EXERCISE = 0.5
POINTS_PER_COMMENT = 0.01

LIGHT_ACTIVITY_LABEL = "가벼운 활동"


def points_for_tags(tags: list[str]) -> float:
    """Return upload points based on the main category tag.

    영상/이미지 인증 구분 없이 동일 요율로 적립한다.
    """
    is_light = bool(tags) and tags[0] == LIGHT_ACTIVITY_LABEL
    return POINTS_LIGHT_ACTIVITY if is_light else POINTS_SWEATY_EXERCISE
DAILY_MAX_UPLOADS = 20
REWARD_STATUS_QUEUED = "queued"
REWARD_STATUS_FIXED = "fixed"
REWARD_STATUS_REVOKED = "revoked"
UTC = ZoneInfo("UTC")
KST = ZoneInfo("Asia/Seoul")


def _parse_tz(tz_str: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, Exception):
        return UTC


def get_week_range(tz: ZoneInfo = UTC) -> tuple[datetime, datetime]:
    """Return (week_start_utc, week_end_utc) for the current ISO week.

    Reward settlement, limits, and leaderboards use the global UTC calendar.
    Pass a client timezone only for presentation-only calendar views.
    """
    now_client = datetime.now(tz)
    iso = now_client.isocalendar()
    monday = datetime.fromisocalendar(iso.year, iso.week, 1)
    monday_client = monday.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=tz)
    next_monday_client = monday_client + timedelta(weeks=1)
    week_start_utc = monday_client.astimezone(timezone.utc)
    week_end_utc = next_monday_client.astimezone(timezone.utc)
    return week_start_utc, week_end_utc


def get_month_range(tz: ZoneInfo = UTC) -> tuple[datetime, datetime]:
    """Return (month_start_utc, month_end_utc) for the current calendar month.

    Reward settlement, limits, and leaderboards use the global UTC calendar.
    Pass a client timezone only for presentation-only calendar views.
    """
    now_client = datetime.now(tz)
    month_start_client = now_client.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now_client.month == 12:
        next_month_client = month_start_client.replace(year=now_client.year + 1, month=1)
    else:
        next_month_client = month_start_client.replace(month=now_client.month + 1)
    return month_start_client.astimezone(timezone.utc), next_month_client.astimezone(timezone.utc)




def get_weekly_points(db: Session, user_id: int, tz: ZoneInfo = UTC) -> float:
    week_start_utc, week_end_utc = get_week_range(tz)
    result = (
        db.query(func.sum(RewardPoint.points))
        .filter(
            RewardPoint.user_id == user_id,
            RewardPoint.created_at >= week_start_utc,
            RewardPoint.created_at < week_end_utc,
            RewardPoint.status == REWARD_STATUS_FIXED,
        )
        .scalar()
    )
    return result or 0


def get_hashrate_week_range(tz: ZoneInfo = UTC) -> tuple[datetime, datetime]:
    """해시레이트용 이번 주 범위 — 월이 주 중간에 시작/종료되면 월 경계로 자른다.

    예: 7/2(수) 기준 ISO 주는 6/29(월) 시작이지만, 7월이 7/1에 시작했으므로 7/1부터 집계.
    """
    week_start, week_end = get_week_range(tz)
    month_start, month_end = get_month_range(tz)
    return max(week_start, month_start), min(week_end, month_end)


def hashrate_filters() -> list:
    """해시레이트 집계 조건 — 단일 원본.

    사용자 프로필(/users/me/hashrate)과 관리자 순위(/admin/hashrate)가 반드시
    같은 조건을 쓰도록 여기서만 정의한다. 관리자가 이 숫자를 보고 sats를
    정산하므로 두 화면의 불일치는 곧 정산 오류다.
    기준: 이번 주(월 경계 절단), queued+fixed 포함, revoked 제외.
    """
    week_start_utc, week_end_utc = get_hashrate_week_range(UTC)
    return [
        RewardPoint.created_at >= week_start_utc,
        RewardPoint.created_at < week_end_utc,
        RewardPoint.status != REWARD_STATUS_REVOKED,
    ]


def get_weekly_hashrate(db: Session, user_id: int) -> tuple[float, float]:
    """이번 주(월 경계 반영) (내 점수, 전체 점수) 반환 — 전체 대비 참여 비중 계산용."""
    base = db.query(func.sum(RewardPoint.points)).filter(*hashrate_filters())
    total = base.scalar() or 0.0
    mine = base.filter(RewardPoint.user_id == user_id).scalar() or 0.0
    return mine, total


def get_weekly_queued_points(db: Session, user_id: int) -> float:
    result = (
        db.query(func.sum(RewardPoint.points))
        .filter(
            RewardPoint.user_id == user_id,
            RewardPoint.status == REWARD_STATUS_QUEUED,
        )
        .scalar()
    )
    return result or 0


def _utc_today_start() -> datetime:
    """UTC midnight. Kept for non-reward daily dedupe paths such as view counting."""
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def get_daily_upload_window(tz: ZoneInfo = UTC) -> tuple[datetime, datetime]:
    """Return today's upload-limit window in the given timezone (default UTC)."""
    now_client = datetime.now(tz)
    today_start_client = now_client.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end_client = today_start_client + timedelta(days=1)
    return today_start_client.astimezone(timezone.utc), today_end_client.astimezone(timezone.utc)


def get_daily_upload_count(db: Session, user_id: int, tz: ZoneInfo = UTC) -> int:
    """Return today's upload count using the given timezone's reset window."""
    today_start, today_end = get_daily_upload_window(tz)
    return (
        db.query(Video)
        .filter(
            Video.user_id == user_id,
            Video.status == "active",
            Video.created_at >= today_start,
            Video.created_at < today_end,
        )
        .count()
    )



def settle_queued_rewards(db: Session, user_id: int | None = None) -> int:
    """Move upload rewards from queued to fixed after 24 hours from creation.

    Timezone-agnostic: uses UTC upload timestamp as the sole reference.
    Deleting a video before the 24h window revokes its points; after that they are kept.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    query = db.query(RewardPoint).filter(
        RewardPoint.status == REWARD_STATUS_QUEUED,
        RewardPoint.created_at <= cutoff,
    )
    if user_id is not None:
        query = query.filter(RewardPoint.user_id == user_id)

    rewards = query.all()
    for reward in rewards:
        reward.status = REWARD_STATUS_FIXED
    if rewards:
        db.flush()
    return len(rewards)


def revoke_queued_upload_reward(db: Session, video_id: int) -> int:
    """Retrieve queued upload points when the associated content is removed before settlement."""
    rewards = (
        db.query(RewardPoint)
        .filter(
            RewardPoint.reason == "upload",
            RewardPoint.reference_id == video_id,
            RewardPoint.status == REWARD_STATUS_QUEUED,
        )
        .all()
    )
    for reward in rewards:
        db.delete(reward)
    if rewards:
        db.flush()
    return len(rewards)


def add_points(
    db: Session,
    user_id: int,
    points: float,
    reason: str,
    reference_id: int | None = None,
) -> RewardPoint:
    rp = RewardPoint(
        user_id=user_id,
        points=points,
        reason=reason,
        reference_id=reference_id,
        status=REWARD_STATUS_QUEUED if reason == "upload" else REWARD_STATUS_FIXED,
    )
    db.add(rp)
    db.flush()
    return rp
