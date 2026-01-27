import json
import os
from datetime import datetime, timedelta, timezone
from typing import Iterable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.models.google_oauth_token_orm import GoogleOAuthTokenORM


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def _get_client_secret_file() -> str:
    return os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")


def get_google_oauth_flow(redirect_uri: str) -> Flow:
    client_secret = _get_client_secret_file()
    return Flow.from_client_secrets_file(
        client_secret,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )


def save_google_token(db: Session, token: dict):
    existing = (
        db.query(GoogleOAuthTokenORM)
        .filter(GoogleOAuthTokenORM.provider == "google")
        .first()
    )
    token_json = json.dumps(token)
    if existing:
        existing.token_json = token_json
    else:
        db.add(GoogleOAuthTokenORM(provider="google", token_json=token_json))
    db.commit()


def load_google_credentials(db: Session) -> Credentials | None:
    record = (
        db.query(GoogleOAuthTokenORM)
        .filter(GoogleOAuthTokenORM.provider == "google")
        .first()
    )
    if not record:
        return None

    token = json.loads(record.token_json)
    required_fields = ("token", "refresh_token", "token_uri", "client_id", "client_secret")
    if not all(token.get(field) for field in required_fields):
        return None

    creds = Credentials(
        token=token.get("token"),
        refresh_token=token.get("refresh_token"),
        token_uri=token.get("token_uri"),
        client_id=token.get("client_id"),
        client_secret=token.get("client_secret"),
        scopes=SCOPES
    )
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_google_token(db, json.loads(creds.to_json()))
    return creds


def build_calendar_client(creds: Credentials):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def parse_google_event_date(event: dict) -> datetime | None:
    start = event.get("start", {})
    if "dateTime" in start:
        raw = start["dateTime"]
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        return datetime.fromisoformat(raw)
    if "date" in start:
        return datetime.fromisoformat(start["date"]).replace(
            tzinfo=timezone.utc
        )
    return None


def fetch_calendar_list(client) -> Iterable[dict]:
    page_token = None
    while True:
        result = client.calendarList().list(pageToken=page_token).execute()
        for item in result.get("items", []):
            yield item
        page_token = result.get("nextPageToken")
        if not page_token:
            break


def fetch_events(client, calendar_id: str, days_ahead: int = 365):
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=1)).isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    page_token = None
    while True:
        result = (
            client.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token
            )
            .execute()
        )
        for item in result.get("items", []):
            yield item
        page_token = result.get("nextPageToken")
        if not page_token:
            break
