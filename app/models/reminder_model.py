from pydantic import BaseModel, Field
from datetime import date
from typing import Optional
from uuid import UUID, uuid4


class Reminder(BaseModel):
    id: UUID = Field(default_factory=uuid4)

    applianceType: str
    brand: str
    model: Optional[str] = ""
    reminderDate: date
    title: str
    notes: Optional[str] = ""
    completed: bool = False
