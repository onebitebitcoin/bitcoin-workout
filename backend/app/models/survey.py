from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import sql as expression
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False, server_default="[]")
    is_open: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        server_default=expression.true(),
    )
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    responses: Mapped[list[SurveyResponse]] = relationship(
        "SurveyResponse", back_populates="survey", cascade="all, delete-orphan"
    )

    def is_active(self) -> bool:
        if not self.is_open:
            return False
        if self.closes_at is None:
            return True
        # closes_at이 naive이면 UTC로 간주
        closes = self.closes_at
        if closes.tzinfo is None:
            closes = closes.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < closes


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    survey_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("surveys.id"), nullable=False, index=True
    )
    answers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    survey: Mapped[Survey] = relationship("Survey", back_populates="responses")
