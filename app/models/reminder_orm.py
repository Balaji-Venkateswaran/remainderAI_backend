import uuid
from sqlalchemy import Boolean, Column, Date, String

from app.db import Base


class ReminderORM(Base):
    __tablename__ = "reminders"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    appliance_type = Column(String, nullable=False)
    brand = Column(String, nullable=False)
    model = Column(String, nullable=True)
    reminder_date = Column(Date, nullable=False)
    title = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    completed = Column(Boolean, default=False, nullable=False)
