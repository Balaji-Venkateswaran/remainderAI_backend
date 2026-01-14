import json
import os
from datetime import datetime
import uuid

from sqlalchemy.orm import Session

from app.models.reminder_orm import ReminderORM
from app.models.calendar_event_sync_orm import CalendarEventSyncORM
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
                "error": "Google OAuth not connected"
            }

        client = build_calendar_client(creds)
        local_tz = datetime.now().astimezone().tzinfo
        synced = 0

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

                event_updated = event.get("updated")
                mapping = (
                    db.query(CalendarEventSyncORM)
                    .filter(CalendarEventSyncORM.provider == GoogleCalendarController.PROVIDER)
                    .filter(CalendarEventSyncORM.event_id == event_id)
                    .first()
                )

                if mapping and mapping.event_updated == event_updated:
                    continue

                reminder_date = start_dt.astimezone(local_tz).date()
                title = event.get("summary") or "Calendar Event"
                description = event.get("description")
                notes = generate_event_notes(title, description)

                if mapping:
                    reminder = db.get(ReminderORM, mapping.reminder_id)
                    if reminder:
                        reminder.title = title
                        reminder.notes = notes
                        reminder.reminder_date = reminder_date
                        reminder.model = cal.get("summary", "")
                    else:
                        reminder = ReminderORM(
                            id=str(uuid.uuid4()),
                            appliance_type="calendar",
                            brand="google",
                            model=cal.get("summary", ""),
                            reminder_date=reminder_date,
                            title=title,
                            notes=notes,
                            completed=False
                        )
                        db.add(reminder)
                        db.flush()
                        mapping.reminder_id = reminder.id
                else:
                    reminder = ReminderORM(
                        id=str(uuid.uuid4()),
                        appliance_type="calendar",
                        brand="google",
                        model=cal.get("summary", ""),
                        reminder_date=reminder_date,
                        title=title,
                        notes=notes,
                        completed=False
                    )
                    db.add(reminder)
                    db.flush()
                    mapping = CalendarEventSyncORM(
                        provider=GoogleCalendarController.PROVIDER,
                        event_id=event_id,
                        calendar_id=calendar_id,
                        reminder_id=reminder.id,
                        event_updated=event_updated
                    )
                    db.add(mapping)

                if mapping:
                    mapping.event_updated = event_updated

                synced += 1

        db.commit()
        return {"synced": synced}
