from datetime import date
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class TodoBase(BaseModel):
    title: str
    notes: Optional[str] = ""
    dueDate: date
    completed: bool = False
    due: bool = False


class TodoCreate(BaseModel):
    title: str
    notes: Optional[str] = ""
    dueDate: Optional[date] = None


class Todo(TodoBase):
    id: UUID = Field(default_factory=uuid4)
