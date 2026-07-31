from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (
        Index("ix_videos_user_status_created", "user_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    r2_key: Mapped[str] = mapped_column(String, nullable=False)
    cdn_url: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str] = mapped_column(String, nullable=False)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subtitle_url: Mapped[str | None] = mapped_column(String, nullable=True)
    subtitle_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtitle_status: Mapped[str] = mapped_column(String(20), default="skipped", nullable=False)
    subtitle_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtitle_metrics: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_video_r2_key: Mapped[str | None] = mapped_column(String, nullable=True)
    original_audio_r2_key: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="videos")  # noqa: F821
    post: Mapped[Post | None] = relationship("Post", back_populates="video", uselist=False)  # noqa: F821
