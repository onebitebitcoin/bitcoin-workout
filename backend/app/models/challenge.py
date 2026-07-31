from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reward_title: Mapped[str] = mapped_column(String(80), nullable=False)
    condition_value: Mapped[int] = mapped_column(Integer, nullable=False)  # uploads required
    goal_description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    recruit_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recruit_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    categories: Mapped[list] = mapped_column(JSON, default=list, nullable=False, server_default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    creator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image_thumb_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    bitcoin_reward_sats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    participations: Mapped[list[ChallengeParticipation]] = relationship(
        "ChallengeParticipation", back_populates="challenge"
    )


class ChallengeParticipation(Base):
    __tablename__ = "challenge_participations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    challenge_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("challenges.id"), nullable=False
    )
    upload_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="challenge_participations")  # noqa: F821
    challenge: Mapped[Challenge] = relationship("Challenge", back_populates="participations")
