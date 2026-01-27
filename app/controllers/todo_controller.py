from datetime import date
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.todo_model import Todo, TodoCreate
from app.models.todo_orm import TodoORM


class TodoController:

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
        due_date = todo.dueDate or date.today()
        is_due_today = due_date == date.today()
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
        todo.due = todo.due_date <= date.today()
        db.commit()
        db.refresh(todo)
        return TodoController._to_schema(todo)
