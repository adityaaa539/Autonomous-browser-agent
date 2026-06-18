import uuid
from datetime import datetime, UTC
from sqlalchemy import String, Enum, JSON, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from db.database import Base

class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    prompt: Mapped[str] = mapped_column(String, nullable=False)
    start_url: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("queued", "running", "done", "failed", name="task_status"),
        default="queued",
        nullable=False
    )
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    steps_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False
    )
