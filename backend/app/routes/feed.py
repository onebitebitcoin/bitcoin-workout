import json

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.comment import Comment
from app.models.post import Post
from app.models.post_like import PostLike
from app.models.post_view import PostView
from app.models.video import Video
from app.models.user import User
from app.routes.auth import get_current_user, get_optional_user
from app.schemas.video import PostSchema
from app.services.timeframe import today_start
from app.services.notification import create_notification
from app.services.error_codes import (
    api_error,
    E_POST_NOT_FOUND,
)

router = APIRouter(prefix="/api/v1/feed", tags=["feed"])


def _post_to_schema(
    post: Post,
    comment_counts: dict,
    liked_post_ids: set,
) -> PostSchema:
    tags_raw = post.tags or "[]"
    try:
        tags = json.loads(tags_raw)
    except (json.JSONDecodeError, TypeError):
        tags = []
    return PostSchema(
        id=post.id,
        video_id=post.video_id,
        user_id=post.user_id,
        caption=post.caption,
        tags=tags,
        like_count=post.like_count,
        view_count=post.view_count,
        comment_count=comment_counts.get(post.id, 0),
        is_liked=post.id in liked_post_ids,
        created_at=post.created_at,
        cdn_url=post.video.cdn_url,
        username=post.user.username,
        workout_start=post.workout_start,
        workout_end=post.workout_end,
        share_token=post.share_token,
        thumbnail_url=post.thumbnail_url,
        subtitle_url=post.video.subtitle_url,
        subtitle_text=post.video.subtitle_text,
        subtitle_status=post.video.subtitle_status,
        avatar_url=post.user.avatar_url,
        profile_color=(post.user.app_settings or {}).get("profile_color"),
        challenge_id=post.challenge_id,
    )


@router.get("")
def get_feed(
    cursor: int | None = None,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> dict:
    limit = min(limit, 20)
    query = (
        db.query(Post)
        .join(Post.video)
        .filter(Video.status == "active")
        .options(selectinload(Post.video), selectinload(Post.user))
        .order_by(Post.id.desc())
    )
    if cursor is not None:
        query = query.filter(Post.id < cursor)

    posts = query.limit(limit + 1).all()
    has_more = len(posts) > limit
    posts = posts[:limit]

    next_cursor = posts[-1].id if has_more and posts else None
    viewer_id = current_user.id if current_user else None

    post_ids = [p.id for p in posts]
    comment_counts: dict = {}
    liked_post_ids: set = set()

    if post_ids:
        comment_counts = dict(
            db.query(Comment.post_id, func.count(Comment.id))
            .filter(Comment.post_id.in_(post_ids))
            .group_by(Comment.post_id)
            .all()
        )
        if viewer_id:
            liked_rows = (
                db.query(PostLike.post_id)
                .filter(
                    PostLike.user_id == viewer_id,
                    PostLike.post_id.in_(post_ids),
                )
                .all()
            )
            liked_post_ids = {r.post_id for r in liked_rows}

    return {
        "data": {
            "posts": [_post_to_schema(p, comment_counts, liked_post_ids) for p in posts],
            "next_cursor": next_cursor,
        }
    }


@router.post("/{post_id}/like")
def like_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise api_error(404, E_POST_NOT_FOUND, "게시물을 찾을 수 없습니다")

    existing_like = (
        db.query(PostLike)
        .filter(PostLike.user_id == current_user.id, PostLike.post_id == post_id)
        .first()
    )

    if existing_like:
        db.delete(existing_like)
        db.execute(update(Post).where(Post.id == post_id).values(like_count=case((Post.like_count > 0, Post.like_count - 1), else_=0)))
        db.commit()
        db.refresh(post)
        return {"data": {"liked": False, "like_count": post.like_count}}

    try:
        db.add(PostLike(user_id=current_user.id, post_id=post_id))
        db.execute(update(Post).where(Post.id == post_id).values(like_count=Post.like_count + 1))
        create_notification(db, recipient_id=post.user_id, actor_id=current_user.id, type="like", post_id=post_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        db.refresh(post)
        return {"data": {"liked": True, "like_count": post.like_count}}
    db.refresh(post)
    return {"data": {"liked": True, "like_count": post.like_count}}


@router.post("/{post_id}/view")
def view_post(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    post = db.query(Post).filter(Post.id == post_id).first()
    if post is None:
        raise api_error(404, E_POST_NOT_FOUND, "게시물을 찾을 수 없습니다")

    today_start_utc = today_start()
    already_viewed = (
        db.query(PostView)
        .filter(
            PostView.user_id == current_user.id,
            PostView.post_id == post_id,
            PostView.created_at >= today_start_utc,
        )
        .first()
    )

    if not already_viewed:
        try:
            db.add(PostView(user_id=current_user.id, post_id=post_id))
            db.flush()
            db.execute(update(Post).where(Post.id == post_id).values(view_count=Post.view_count + 1))
        except IntegrityError:
            db.rollback()
            db.refresh(post)
            return {"data": {"view_count": post.view_count}}

    db.commit()
    db.refresh(post)
    return {"data": {"view_count": post.view_count}}
