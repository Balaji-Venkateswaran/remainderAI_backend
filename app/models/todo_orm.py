import uuid
from sqlalchemy import Boolean, Column, Date, String

from app.db import Base


class TodoORM(Base):
    __tablename__ = "todos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False)
    notes = Column(String, nullable=True)
    due_date = Column(Date, nullable=False)
    completed = Column(Boolean, default=False, nullable=False)
    due = Column(Boolean, default=False, nullable=False)
