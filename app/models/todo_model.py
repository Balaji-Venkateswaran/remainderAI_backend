from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, root_validator, validator


_ALLOWED_SOURCES = {"todo", "local", "service", "calendar"}
_SOURCE_ALIASES = {
    "service center": "service",
    "service_center": "service",
    "local service": "local",
    "todos": "todo",
    "task": "todo",
    "tasks": "todo",
}


def _validate_due_date(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("dueDate is required")
    raw = value.strip()
    try:
        if "T" in raw:
            datetime.fromisoformat(raw)
        else:
            date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("dueDate must be ISO date or datetime") from exc
    return raw


def _normalize_source(value: str | None) -> str:
    normalized = (value or "todo").strip().lower()
    return _SOURCE_ALIASES.get(normalized, normalized)


class TodoBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    notes: Optional[str] = ""
    dueDate: str
    completed: bool = False
    due: bool = False
    source: str = "todo"

    @validator("title")
    def title_required(cls, value: str) -> str:
        trimmed = value.strip()
        if len(trimmed) < 3:
            raise ValueError("title must be at least 3 characters")
        return trimmed

    @validator("notes")
    def notes_length(cls, value: Optional[str]) -> str:
        text = value or ""
        if len(text) > 2000:
            raise ValueError("notes must be 2000 characters or less")
        return text

    @validator("source")
    def source_allowed(cls, value: str) -> str:
        normalized = _normalize_source(value)
        if normalized not in _ALLOWED_SOURCES:
            raise ValueError("source is not supported")
        return normalized

    @validator("dueDate")
    def due_date_required(cls, value: str) -> str:
        return _validate_due_date(value)


class TodoCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    notes: Optional[str] = ""
    dueDate: Optional[str] = None
    source: Optional[str] = "todo"

    @validator("title")
    def create_title_required(cls, value: str) -> str:
        trimmed = value.strip()
        if len(trimmed) < 3:
            raise ValueError("title must be at least 3 characters")
        return trimmed

    @validator("notes")
    def create_notes_length(cls, value: Optional[str]) -> str:
        text = value or ""
        if len(text) > 2000:
            raise ValueError("notes must be 2000 characters or less")
        return text

    @validator("source")
    def create_source_allowed(cls, value: Optional[str]) -> str:
        normalized = _normalize_source(value)
        if normalized not in _ALLOWED_SOURCES:
            raise ValueError("source is not supported")
        return normalized

    @validator("dueDate")
    def create_due_date_valid(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_due_date(value)


class TodoUpdate(BaseModel):
    dueDate: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None

    @validator("dueDate")
    def update_due_date_required(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_due_date(value)

    @validator("notes")
    def update_notes_length(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        if len(value) > 2000:
            raise ValueError("notes must be 2000 characters or less")
        return value

    @validator("source")
    def update_source_allowed(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = _normalize_source(value)
        if normalized not in _ALLOWED_SOURCES:
            raise ValueError("source is not supported")
        return normalized

    @root_validator(skip_on_failure=True)
    def update_payload_not_empty(cls, values):
        if (
            values.get("dueDate") is None
            and values.get("notes") is None
            and values.get("source") is None
        ):
            raise ValueError("At least one field is required")
        return values


class Todo(TodoBase):
    id: UUID = Field(default_factory=uuid4)
