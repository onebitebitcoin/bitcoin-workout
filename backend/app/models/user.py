from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    username: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String, nullable=True)
    oauth_sub: Mapped[str | None] = mapped_column(String, nullable=True)
    lightning_address: Mapped[str | None] = mapped_column(String, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    app_settings: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    # 친구 초대 (보상 없음 — 링크/집계 전용)
    referral_code: Mapped[str | None] = mapped_column(String, unique=True, nullable=True, index=True)
    referred_by_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    videos: Mapped[list["Video"]] = relationship("Video", back_populates="user")  # noqa: F821
    posts: Mapped[list["Post"]] = relationship("Post", back_populates="user")  # noqa: F821
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="user")  # noqa: F821
    challenge_participations: Mapped[list["ChallengeParticipation"]] = relationship(  # noqa: F821
        "ChallengeParticipation", back_populates="user"
    )
