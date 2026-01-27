import json
import os
from datetime import date, datetime
import uuid

from sqlalchemy.orm import Session

from app.models.todo_orm import TodoORM
from app.models.calendar_event_todo_sync_orm import CalendarEventTodoSyncORM
from app.utils.google_calendar import (
    build_calendar_client,
    fetch_calendar_list,
    fetch_events,
    get_google_oauth_flow,
    load_google_credentials,
    parse_google_event_date,
    save_google_token
)
from app.utils.reminder_notes import generate_event_notes


class GoogleCalendarController:
    PROVIDER = "google"

    @staticmethod
    def get_auth_url():
        try:
            redirect_uri = os.getenv(
                "GOOGLE_REDIRECT_URI",
                "http://127.0.0.1:8000/google/oauth/callback"
            )
            flow = get_google_oauth_flow(redirect_uri)
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent"
            )
            return {"authUrl": auth_url}
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def handle_oauth_callback(code: str, db: Session):
        try:
            redirect_uri = os.getenv(
                "GOOGLE_REDIRECT_URI",
                "http://127.0.0.1:8000/google/oauth/callback"
            )
            flow = get_google_oauth_flow(redirect_uri)
            flow.fetch_token(code=code)
            save_google_token(db, json.loads(flow.credentials.to_json()))
            return {"status": "ok"}
        except Exception as exc:
            return {"error": str(exc)}

    @staticmethod
    def sync_all_calendars(db: Session):
        creds = load_google_credentials(db)
        if not creds:
            return {
                "error": "Google OAuth not connected or refresh token missing"
            }

        client = build_calendar_client(creds)
        local_tz = datetime.now().astimezone().tzinfo
        synced = 0
        today = datetime.now(local_tz).date()

        for cal in fetch_calendar_list(client):
            calendar_id = cal.get("id")
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

                if "date" in start_meta:
                    reminder_date = start_meta["date"]
                else:
                    local_start = start_dt.astimezone(local_tz).replace(tzinfo=None)
                    reminder_date = local_start.isoformat(timespec="minutes")
                title = event.get("summary") or "Calendar Event"
                description = event.get("description")
                notes = generate_event_notes(title, description)
                due_day = GoogleCalendarController._extract_due_day(reminder_date)

                if mapping:
                    todo = db.get(TodoORM, mapping.todo_id)
                    if todo:
                        todo.title = title
                        todo.notes = notes
                        todo.due_date = reminder_date
                        todo.due = due_day == today
                    else:
                        todo = TodoORM(
                            id=str(uuid.uuid4()),
                            title=title,
                            notes=notes,
                            due_date=reminder_date,
                            completed=False,
                            due=due_day == today
                        )
                        db.add(todo)
                        db.flush()
                        mapping.todo_id = todo.id
                else:
                    todo = TodoORM(
                        id=str(uuid.uuid4()),
                        title=title,
                        notes=notes,
                        due_date=reminder_date,
                        completed=False,
                        due=due_day == today
                    )
                    db.add(todo)
                    db.flush()
                    mapping = CalendarEventTodoSyncORM(
                        provider=GoogleCalendarController.PROVIDER,
                        event_id=event_id,
                        calendar_id=calendar_id,
                        todo_id=todo.id,
                        event_updated=event_updated
                    )
                    db.add(mapping)

                if mapping:
                    mapping.event_updated = event_updated

                synced += 1

        db.commit()
        return {"synced": synced}

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
