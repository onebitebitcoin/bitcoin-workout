from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("videos.id"), unique=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    caption: Mapped[str | None] = mapped_column(String(140), nullable=True)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array string
    workout_start: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM"
    workout_end: Mapped[str | None] = mapped_column(String(5), nullable=True)    # "HH:MM"
    proof_image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String, nullable=True)
    challenge_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("challenges.id"), nullable=True, index=True)
    share_token: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    like_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user: Mapped[User] = relationship("User", back_populates="posts")  # noqa: F821
    video: Mapped[Video] = relationship("Video", back_populates="post")  # noqa: F821
    comments: Mapped[list[Comment]] = relationship("Comment", back_populates="post")  # noqa: F821
