from sqlalchemy import Column, Integer, String, Text, UniqueConstraint

from app.db import Base


class CalendarEventTodoSyncORM(Base):
    __tablename__ = "calendar_event_todo_sync"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_provider_event_todo"),
    )

    id = Column(Integer, primary_key=True)
    provider = Column(String, nullable=False)
    event_id = Column(String, nullable=False)
    calendar_id = Column(String, nullable=False)
    todo_id = Column(String, nullable=False)
    event_updated = Column(Text, nullable=True)
