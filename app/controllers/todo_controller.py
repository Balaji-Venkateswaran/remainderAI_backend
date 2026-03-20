from datetime import date, datetime
from typing import Any, Iterable, List
from uuid import UUID

from sqlalchemy.orm import Query, Session

from app.models.todo_model import Todo, TodoCreate, TodoUpdate
from app.models.todo_orm import TodoORM
from app.utils.local_todo_helper import (
    append_unique_line,
    build_group_line,
    extract_note_lines,
    local_category_title,
    safe_notes,
    try_parse_json_notes,
)


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
            notes=safe_notes(todo.notes),
            dueDate=todo.due_date,
            completed=todo.completed,
            due=todo.due,
            source=todo.source,
        )

    @staticmethod
    def _base_day_source_query(db: Session, due_day: date, source: str) -> Query:
        day_key = due_day.isoformat()
        return (
            db.query(TodoORM)
            .filter(TodoORM.completed.is_(False))
            .filter(TodoORM.source == source)
            .filter(TodoORM.due_date.startswith(day_key))
        )

    @staticmethod
    def _find_existing_group(
        db: Session,
        source: str,
        due_day: date | None,
        incoming_title: str,
        local_title: str | None,
    ) -> TodoORM | None:
        if not due_day:
            return None

        query = TodoController._base_day_source_query(db, due_day, source)

        if source == "todo":
            normalized_title = incoming_title.strip().lower()
            for candidate in query.all():
                if (candidate.title or "").strip().lower() == normalized_title:
                    return candidate
            return None

        if source == "local":
            return query.filter(TodoORM.title == (local_title or "Shopping")).first()

        return query.first()

    @staticmethod
    def create_todo(todo: TodoCreate, db: Session) -> Todo:
        due_date = TodoController._normalize_due_date(todo.dueDate)
        due_day = TodoController._extract_due_day(due_date)
        is_due_today = due_day == date.today()
        source = todo.source or "todo"

        local_title = None
        if source == "local":
            local_title = local_category_title(f"{todo.title} {todo.notes or ''}")

        existing = TodoController._find_existing_group(
            db=db,
            source=source,
            due_day=due_day,
            incoming_title=todo.title,
            local_title=local_title,
        )

        if existing:
            line = build_group_line(todo.title, todo.notes)
            existing.notes = append_unique_line(existing.notes, line)
            if source == "local":
                existing.title = local_title or "Shopping"
            existing.due = is_due_today
            db.commit()
            db.refresh(existing)
            return TodoController._to_schema(existing)

        record_title = local_title if source == "local" else todo.title
        record_notes = todo.notes or ""
        if source == "local":
            record_notes = build_group_line(todo.title, todo.notes)

        record = TodoORM(
            title=record_title,
            notes=record_notes,
            due_date=due_date,
            completed=False,
            due=is_due_today,
            source=source,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return TodoController._to_schema(record)

    @staticmethod
    def _format_bullet_lines(lines: Iterable[str]) -> str:
        return "\n".join(f"- {line}" for line in lines)

    @staticmethod
    def _reclassify_local_todos(db: Session) -> None:
        local_rows = (
            db.query(TodoORM)
            .filter(TodoORM.completed.is_(False))
            .filter(TodoORM.source == "local")
            .all()
        )
        changed = False

        for row in local_rows:
            parsed_notes = try_parse_json_notes(row.notes)
            if isinstance(parsed_notes, dict) and parsed_notes.get("type") == "localService":
                continue

            lines = extract_note_lines(row.notes)
            if not lines:
                if row.title and row.title != "Shopping":
                    continue
                category = local_category_title(row.title or "")
                if category != row.title:
                    row.title = category
                    changed = True
                continue

            grouped: dict[str, list[str]] = {}
            for line in lines:
                category = local_category_title(line)
                grouped.setdefault(category, []).append(line)

            due_day = TodoController._extract_due_day(row.due_date)
            day_key = due_day.isoformat() if due_day else None

            if len(grouped) == 1:
                target_title = next(iter(grouped.keys()))
                target_notes = TodoController._format_bullet_lines(grouped[target_title])

                if day_key:
                    target = (
                        db.query(TodoORM)
                        .filter(TodoORM.completed.is_(False))
                        .filter(TodoORM.source == "local")
                        .filter(TodoORM.due_date.startswith(day_key))
                        .filter(TodoORM.title == target_title)
                        .first()
                    )
                    if target and target.id != row.id:
                        for line in grouped[target_title]:
                            target.notes = append_unique_line(target.notes, f"- {line}")
                        db.delete(row)
                        changed = True
                        continue

                if row.title != target_title:
                    row.title = target_title
                    changed = True
                if (row.notes or "").strip() != target_notes.strip():
                    row.notes = target_notes
                    changed = True
                continue

            if not day_key:
                continue

            keep_title = row.title if row.title in grouped else None
            if keep_title:
                keep_notes = TodoController._format_bullet_lines(grouped.pop(keep_title))
                if (row.notes or "").strip() != keep_notes.strip():
                    row.notes = keep_notes
                    changed = True

            for title, category_lines in grouped.items():
                target = (
                    db.query(TodoORM)
                    .filter(TodoORM.completed.is_(False))
                    .filter(TodoORM.source == "local")
                    .filter(TodoORM.due_date.startswith(day_key))
                    .filter(TodoORM.title == title)
                    .first()
                )

                if target and target.id != row.id:
                    for line in category_lines:
                        target.notes = append_unique_line(target.notes, f"- {line}")
                    changed = True
                else:
                    db.add(
                        TodoORM(
                            title=title,
                            notes=TodoController._format_bullet_lines(category_lines),
                            due_date=row.due_date,
                            completed=False,
                            due=row.due,
                            source="local",
                        )
                    )
                    changed = True

            if keep_title is None:
                db.delete(row)
                changed = True

        if changed:
            db.commit()

    @staticmethod
    def get_todos(
        db: Session,
        completed: bool | None = None,
        due: bool | None = None,
        source: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Todo]:
        TodoController._reclassify_local_todos(db)

        query = db.query(TodoORM)
        if completed is not None:
            query = query.filter(TodoORM.completed.is_(completed))
        if due is not None:
            query = query.filter(TodoORM.due.is_(due))

        normalized_source = TodoController._normalize_source(source)
        if normalized_source:
            query = query.filter(TodoORM.source == normalized_source)

        query = (
            query.order_by(TodoORM.completed.asc())
            .order_by(TodoORM.due.desc())
            .order_by(TodoORM.due_date.asc())
        )

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        return [TodoController._to_schema(todo) for todo in query.all()]

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
    def update_due_date(todo_id: UUID, payload: TodoUpdate, db: Session) -> Todo | None:
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
    def get_todo(todo_id: UUID, db: Session) -> Todo | None:
        todo = db.get(TodoORM, str(todo_id))
        if not todo:
            return None
        return TodoController._to_schema(todo)

    @staticmethod
    def get_share_payload(todo_id: UUID, db: Session) -> dict[str, Any] | None:
        todo = db.get(TodoORM, str(todo_id))
        if not todo:
            return None

        return {
            "id": todo.id,
            "title": todo.title,
            "notes": safe_notes(todo.notes),
            "dueDate": todo.due_date,
            "completed": todo.completed,
            "due": todo.due,
            "source": todo.source,
        }

    @staticmethod
    def _safe_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def get_saved_local_store_suggestions(
        db: Session,
        query: str,
        limit: int = 8,
    ) -> dict[str, list[dict[str, Any]]]:
        rows = (
            db.query(TodoORM)
            .filter(TodoORM.source == "local")
            .all()
        )

        normalized_query = (query or "").strip().lower()
        buckets: dict[str, dict[str, Any]] = {}

        for row in rows:
            parsed = try_parse_json_notes(row.notes)
            if not isinstance(parsed, dict):
                continue
            if parsed.get("type") != "localService":
                continue

            name = TodoController._safe_text(parsed.get("name"))
            label = TodoController._safe_text(parsed.get("label")) or "store"
            address = TodoController._safe_text(parsed.get("address"))
            map_url = TodoController._safe_text(parsed.get("mapUrl"))
            latitude = parsed.get("latitude")
            longitude = parsed.get("longitude")
            items = parsed.get("items")
            item_text = " ".join(str(item).strip() for item in items) if isinstance(items, list) else ""

            haystack = " ".join(
                value.lower()
                for value in [name, label, address, item_text]
                if value
            )
            if normalized_query and normalized_query not in haystack:
                continue

            key = f"{name.lower()}|{address.lower()}"
            if key not in buckets:
                buckets[key] = {
                    "label": label,
                    "name": name or "Store",
                    "address": address or "Address unavailable",
                    "mapUrl": map_url,
                    "latitude": latitude if isinstance(latitude, (int, float)) else None,
                    "longitude": longitude if isinstance(longitude, (int, float)) else None,
                    "_count": 1,
                    "_last_due_date": row.due_date or "",
                }
            else:
                buckets[key]["_count"] += 1
                if (row.due_date or "") > buckets[key]["_last_due_date"]:
                    buckets[key]["_last_due_date"] = row.due_date or ""

        ranked = sorted(
            buckets.values(),
            key=lambda value: (value["_count"], value["_last_due_date"]),
            reverse=True,
        )

        suggestions: list[dict[str, Any]] = []
        for entry in ranked[: max(1, limit)]:
            suggestions.append(
                {
                    "label": entry["label"],
                    "name": entry["name"],
                    "address": entry["address"],
                    "mapUrl": entry["mapUrl"],
                    "latitude": entry["latitude"],
                    "longitude": entry["longitude"],
                    "usageCount": entry["_count"],
                    "isFavorite": entry["_count"] >= 1,
                }
            )

        return {"suggestions": suggestions}

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
