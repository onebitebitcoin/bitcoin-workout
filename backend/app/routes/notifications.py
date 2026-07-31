from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.routes.auth import get_current_user
from app.services.error_codes import E_NOTIFICATION_NOT_FOUND, api_error

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


def _serialize(n: Notification, actors: dict[int, User]) -> dict:
    actor = actors.get(n.actor_id)
    return {
        "id": n.id,
        "type": n.type,
        "post_id": n.post_id,
        "comment_id": n.comment_id,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat(),
        "actor": {
            "id": actor.id if actor else n.actor_id,
            "username": actor.username if actor else "",
            "avatar_url": actor.avatar_url if actor else None,
            "profile_color": (actor.app_settings or {}).get("profile_color") if actor else None,
        },
    }


@router.get("")
def list_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """내 알림 최신순 50건."""
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    # actor 일괄 조회 (N+1 회피)
    actor_ids = {n.actor_id for n in rows}
    actors: dict[int, User] = {}
    if actor_ids:
        actor_rows = db.query(User).filter(User.id.in_(actor_ids)).all()
        actors = {u.id: u for u in actor_rows}

    return {"data": {"notifications": [_serialize(n, actors) for n in rows]}}


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """안 읽은 알림 개수 (폴링 전용 경량 엔드포인트)."""
    count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)
        .count()
    )
    return {"data": {"count": count}}


@router.post("/read-all")
def read_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """내 알림 전체 읽음 처리."""
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == False)
        .values(is_read=True)
    )
    db.commit()
    return {"data": {"updated": result.rowcount}}


@router.post("/{notification_id}/read")
def read_one(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """단건 알림 읽음 처리."""
    n = db.query(Notification).filter(Notification.id == notification_id).first()
    if n is None or n.user_id != current_user.id:
        raise api_error(404, E_NOTIFICATION_NOT_FOUND, "알림을 찾을 수 없습니다")
    n.is_read = True
    db.commit()
    return {"data": {"read": True}}
