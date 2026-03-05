from datetime import date, datetime
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.todo_model import Todo, TodoCreate, TodoUpdate
from app.models.todo_orm import TodoORM


class TodoController:

    @staticmethod
    def _normalize_due_date(raw: str | None) -> str:
        if not raw:
            return date.today().isoformat()
        try:
            if "T" in raw:
                parsed = datetime.fromisoformat(raw)
                return parsed.isoformat(timespec="minutes")
            parsed_date = date.fromisoformat(raw)
            return parsed_date.isoformat()
        except ValueError:
            return date.today().isoformat()

    @staticmethod
    def _extract_due_day(raw: str | None) -> date | None:
        if not raw:
            return None
        try:
            if "T" in raw:
                return datetime.fromisoformat(raw).date()
            return date.fromisoformat(raw)
        except ValueError:
            return None

    @staticmethod
    def _to_schema(todo: TodoORM) -> Todo:
        return Todo(
            id=todo.id,
            title=todo.title,
            notes=todo.notes,
            dueDate=todo.due_date,
            completed=todo.completed,
            due=todo.due,
            source=todo.source
        )

    @staticmethod
    def create_todo(todo: TodoCreate, db: Session) -> Todo:
        due_date = TodoController._normalize_due_date(todo.dueDate)
        due_day = TodoController._extract_due_day(due_date)
        is_due_today = due_day == date.today()
        record = TodoORM(
            title=todo.title,
            notes=todo.notes or "",
            due_date=due_date,
            completed=False,
            due=is_due_today,
            source=todo.source or "todo"
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return TodoController._to_schema(record)

    @staticmethod
    def get_todos(
        db: Session,
        completed: bool | None = None,
        due: bool | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Todo]:
        query = db.query(TodoORM)
        if completed is not None:
            query = query.filter(TodoORM.completed.is_(completed))
        if due is not None:
            query = query.filter(TodoORM.due.is_(due))
        normalized_source = TodoController._normalize_source(source)
        if normalized_source:
            query = query.filter(TodoORM.source == normalized_source)
        query = (
            query
            .order_by(TodoORM.completed.asc())
            .order_by(TodoORM.due.desc())
            .order_by(TodoORM.due_date.asc())
        )
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        todos = query.all()
        return [TodoController._to_schema(t) for t in todos]

    @staticmethod
    def complete_todo(todo_id: UUID, db: Session) -> Todo | None:
        todo = db.get(TodoORM, str(todo_id))
        if not todo:
            return None
        todo.completed = True
        todo.due = True
        db.commit()
        db.refresh(todo)
        return TodoController._to_schema(todo)

    @staticmethod
    def mark_incomplete(todo_id: UUID, db: Session) -> Todo | None:
        todo = db.get(TodoORM, str(todo_id))
        if not todo:
            return None
        todo.completed = False
        due_day = TodoController._extract_due_day(todo.due_date)
        todo.due = due_day <= date.today() if due_day else False
        db.commit()
        db.refresh(todo)
        return TodoController._to_schema(todo)

    @staticmethod
    def update_due_date(
        todo_id: UUID,
        payload: TodoUpdate,
        db: Session
    ) -> Todo | None:
        todo = db.get(TodoORM, str(todo_id))
        if not todo:
            return None
        if payload.dueDate is not None:
            normalized = TodoController._normalize_due_date(payload.dueDate)
            todo.due_date = normalized
            due_day = TodoController._extract_due_day(normalized)
            todo.due = True if todo.completed else (due_day <= date.today() if due_day else False)
        if payload.notes is not None:
            todo.notes = payload.notes
        if payload.source is not None:
            todo.source = payload.source
        db.commit()
        db.refresh(todo)
        return TodoController._to_schema(todo)

    @staticmethod
    def delete_todo(todo_id: UUID, db: Session) -> bool:
        todo = db.get(TodoORM, str(todo_id))
        if not todo:
            return False
        db.delete(todo)
        db.commit()
        return True

    @staticmethod
    def _normalize_source(source: str | None) -> str | None:
        if not source:
            return None
        normalized = source.strip().lower()
        if normalized in {"service center", "service_center"}:
            return "service"
        if normalized in {"todos", "task", "tasks"}:
            return "todo"
        return normalized
