from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.comment import Comment
from app.models.notification import Notification
from app.models.post import Post
from app.models.user import User
from app.routes.auth import get_current_user
from app.services.timeframe import parse_tz
from app.services.notification import create_notification
from app.services.error_codes import (
    api_error,
    E_BANNED,
    E_COMMENT_DAILY_LIMIT,
    E_COMMENT_NOT_FOUND,
    E_COMMENT_TOO_LONG,
    E_COMMENT_TOO_SHORT,
    E_FORBIDDEN,
    E_POST_NOT_FOUND,
)

router = APIRouter(prefix="/api/v1/feed", tags=["comments"])

DAILY_COMMENT_LIMIT = 10
MIN_COMMENT_LENGTH = 5


def _get_daily_comment_count(db: Session, user_id: int, tz: ZoneInfo = ZoneInfo("UTC")) -> int:
    from datetime import datetime, timezone
    now_client = datetime.now(tz)
    today_start_client = now_client.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end_client = today_start_client + timedelta(days=1)
    today_start = today_start_client.astimezone(timezone.utc)
    today_end = today_end_client.astimezone(timezone.utc)
    return (
        db.query(Comment)
        .filter(
            Comment.user_id == user_id,
            Comment.created_at >= today_start,
            Comment.created_at < today_end,
        )
        .count()
    )


class CreateCommentRequest(BaseModel):
    content: str
    parent_id: int | None = None


def _serialize_comment(c: Comment) -> dict:
    return {
        "id": c.id,
        "post_id": c.post_id,
        "user_id": c.user_id,
        "parent_id": c.parent_id,
        "username": c.user.username if c.user else "",
        "avatar_url": c.user.avatar_url if c.user else None,
        "profile_color": (c.user.app_settings or {}).get("profile_color") if c.user else None,
        "content": c.content,
        "created_at": c.created_at.isoformat(),
    }


@router.get("/{post_id}/comments")
def list_comments(post_id: int, db: Session = Depends(get_db)) -> dict:
    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise api_error(404, E_POST_NOT_FOUND, "게시물을 찾을 수 없습니다")
    comments = (
        db.query(Comment)
        .filter(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
        .all()
    )
    # 최상위 댓글은 top-level, 답글은 부모의 replies 배열에 평면적으로 묶는다 (1-depth).
    parents: list[dict] = []
    replies_by_parent: dict[int, list[dict]] = {}
    for c in comments:
        item = _serialize_comment(c)
        if c.parent_id is None:
            item["replies"] = []
            parents.append(item)
        else:
            replies_by_parent.setdefault(c.parent_id, []).append(item)
    for parent in parents:
        parent["replies"] = replies_by_parent.get(parent["id"], [])
    return {"data": {"comments": parents}}


@router.post("/{post_id}/comments")
def create_comment(
    post_id: int,
    body: CreateCommentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    x_client_timezone: str = Header(default="UTC"),
) -> dict:
    if current_user.is_banned:
        raise api_error(403, E_BANNED, "계정이 정지된 상태입니다")
    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise api_error(404, E_POST_NOT_FOUND, "게시물을 찾을 수 없습니다")
    content = body.content.strip()
    if len(content) < MIN_COMMENT_LENGTH:
        raise api_error(422, E_COMMENT_TOO_SHORT, f"댓글은 {MIN_COMMENT_LENGTH}자 이상 입력해주세요")
    if len(content) > 500:
        raise api_error(422, E_COMMENT_TOO_LONG, "댓글은 500자 이하로 입력해주세요")
    if _get_daily_comment_count(db, current_user.id, parse_tz(x_client_timezone)) >= DAILY_COMMENT_LIMIT:
        raise api_error(429, E_COMMENT_DAILY_LIMIT, f"하루에 댓글은 {DAILY_COMMENT_LIMIT}개까지 작성할 수 있습니다")
    # 대댓글 처리: parent_id가 있으면 부모 댓글을 검증하고 1-depth로 평면화한다.
    resolved_parent_id: int | None = None
    recipient_id = post.user_id
    if body.parent_id is not None:
        parent_comment = (
            db.query(Comment)
            .filter(Comment.id == body.parent_id, Comment.post_id == post_id)
            .first()
        )
        if parent_comment is None:
            raise api_error(404, E_COMMENT_NOT_FOUND, "댓글을 찾을 수 없습니다")
        # 답글의 답글은 최상위 부모로 평면화 (1-depth 유지)
        resolved_parent_id = parent_comment.parent_id or parent_comment.id
        # 알림은 실제로 답한 상대(직속 부모 작성자)에게 보낸다.
        recipient_id = parent_comment.user_id
    comment = Comment(
        post_id=post_id,
        user_id=current_user.id,
        content=content,
        parent_id=resolved_parent_id,
    )
    db.add(comment)
    db.flush()
    create_notification(db, recipient_id=recipient_id, actor_id=current_user.id, type="comment", post_id=post_id, comment_id=comment.id)
    db.commit()
    db.refresh(comment)
    return {"data": {"comment": _serialize_comment(comment)}}


@router.delete("/{post_id}/comments/{comment_id}")
def delete_comment(
    post_id: int,
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    comment = db.query(Comment).filter(
        Comment.id == comment_id, Comment.post_id == post_id
    ).first()
    if comment is None:
        raise api_error(404, E_COMMENT_NOT_FOUND, "댓글을 찾을 수 없습니다")
    if comment.user_id != current_user.id and not current_user.is_admin:
        raise api_error(403, E_FORBIDDEN, "이 작업을 수행할 권한이 없습니다")
    # 삭제 대상: 본인 댓글 + (최상위 댓글이면) 딸린 답글 전체
    targets = [comment]
    if comment.parent_id is None:
        children = db.query(Comment).filter(Comment.parent_id == comment.id).all()
        targets.extend(children)
    for c in targets:
        # notifications FK 정리 (PostgreSQL FK 제약 위반 방지)
        db.query(Notification).filter(Notification.comment_id == c.id).delete()
        db.delete(c)
    db.commit()
    return {"data": {"deleted": True}}
