from sqlalchemy import Column, Integer, String, Text, UniqueConstraint

from app.db import Base


class CalendarEventSyncORM(Base):
    __tablename__ = "calendar_event_sync"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_provider_event"),
    )

    id = Column(Integer, primary_key=True)
    provider = Column(String, nullable=False)
    event_id = Column(String, nullable=False)
    calendar_id = Column(String, nullable=False)
    reminder_id = Column(String, nullable=False)
    event_updated = Column(Text, nullable=True)
