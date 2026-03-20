import json
import os
from datetime import date, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.calendar_event_todo_sync_orm import CalendarEventTodoSyncORM
from app.models.todo_orm import TodoORM
from app.utils.google_calendar import (
    build_calendar_client,
    fetch_calendar_list,
    fetch_events,
    get_google_oauth_flow,
    load_google_credentials,
    parse_google_event_date,
    save_google_token,
)
from app.utils.reminder_notes import generate_event_notes


class GoogleCalendarController:
    PROVIDER = "google"
    DEFAULT_REDIRECT_URI = "http://127.0.0.1:8000/google/oauth/callback"

    @staticmethod
    def _redirect_uri() -> str:
        return os.getenv("GOOGLE_REDIRECT_URI", GoogleCalendarController.DEFAULT_REDIRECT_URI)

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
    def _upsert_todo_for_event(
        db: Session,
        mapping: CalendarEventTodoSyncORM | None,
        event_id: str,
        calendar_id: str,
        event_updated: str | None,
        title: str,
        notes: str,
        due_date: str,
        is_due_today: bool,
    ) -> None:
        if mapping:
            todo = db.get(TodoORM, mapping.todo_id)
            if not todo:
                todo = TodoORM(
                    id=str(uuid4()),
                    title=title,
                    notes=notes,
                    due_date=due_date,
                    completed=False,
                    due=is_due_today,
                    source="calendar",
                )
                db.add(todo)
                db.flush()
                mapping.todo_id = todo.id
            else:
                todo.title = title
                todo.notes = notes
                todo.due_date = due_date
                todo.due = is_due_today
                todo.source = "calendar"
        else:
            todo = TodoORM(
                id=str(uuid4()),
                title=title,
                notes=notes,
                due_date=due_date,
                completed=False,
                due=is_due_today,
                source="calendar",
            )
            db.add(todo)
            db.flush()

            mapping = CalendarEventTodoSyncORM(
                provider=GoogleCalendarController.PROVIDER,
                event_id=event_id,
                calendar_id=calendar_id,
                todo_id=todo.id,
                event_updated=event_updated,
            )
            db.add(mapping)

        mapping.event_updated = event_updated

    @staticmethod
    def get_auth_url():
        try:
            flow = get_google_oauth_flow(GoogleCalendarController._redirect_uri())
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            return {"authUrl": auth_url}
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def handle_oauth_callback(code: str, db: Session):
        try:
            flow = get_google_oauth_flow(GoogleCalendarController._redirect_uri())
            flow.fetch_token(code=code)
            save_google_token(db, json.loads(flow.credentials.to_json()))
            return {"status": "ok"}
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def sync_all_calendars(db: Session):
        creds = load_google_credentials(db)
        if not creds:
            return {"error": "Google OAuth not connected or refresh token missing"}

        client = build_calendar_client(creds)
        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is None:
            local_tz = datetime.now().astimezone().tzinfo

        today = datetime.now(local_tz).date()
        synced = 0

        for calendar in fetch_calendar_list(client):
            calendar_id = calendar.get("id")
            if not calendar_id:
                continue

            for event in fetch_events(client, calendar_id):
                event_id = event.get("id")
                if not event_id:
                    continue

                start_dt = parse_google_event_date(event)
                if not start_dt:
                    continue

                start_meta = event.get("start", {})
                event_updated = event.get("updated")
                mapping = (
                    db.query(CalendarEventTodoSyncORM)
                    .filter(CalendarEventTodoSyncORM.provider == GoogleCalendarController.PROVIDER)
                    .filter(CalendarEventTodoSyncORM.event_id == event_id)
                    .first()
                )

                if mapping and mapping.event_updated == event_updated:
                    continue

                if isinstance(start_meta, dict) and "date" in start_meta:
                    reminder_date = str(start_meta["date"])
                else:
                    local_start = start_dt.astimezone(local_tz).replace(tzinfo=None)
                    reminder_date = local_start.isoformat(timespec="minutes")

                title = event.get("summary") or "Calendar Event"
                description = event.get("description")
                notes = generate_event_notes(title, description)
                due_day = GoogleCalendarController._extract_due_day(reminder_date)

                GoogleCalendarController._upsert_todo_for_event(
                    db=db,
                    mapping=mapping,
                    event_id=event_id,
                    calendar_id=calendar_id,
                    event_updated=event_updated,
                    title=title,
                    notes=notes,
                    due_date=reminder_date,
                    is_due_today=due_day == today,
                )
                synced += 1

        db.commit()
        return {"synced": synced}
