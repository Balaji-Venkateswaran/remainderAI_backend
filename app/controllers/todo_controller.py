from datetime import date, datetime
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.todo_model import Todo, TodoCreate
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
            due=todo.due
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
            due=is_due_today
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
        limit: int = 100,
        offset: int = 0
    ) -> List[Todo]:
        query = db.query(TodoORM)
        if completed is not None:
            query = query.filter(TodoORM.completed.is_(completed))
        if due is not None:
            query = query.filter(TodoORM.due.is_(due))
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
