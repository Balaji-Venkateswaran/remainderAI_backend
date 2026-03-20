import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import Resource, build
from sqlalchemy.orm import Session

from app.models.google_oauth_token_orm import GoogleOAuthTokenORM


SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
GOOGLE_PROVIDER = "google"


def _get_client_secret_file() -> str:
    return os.getenv("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")


def get_google_oauth_flow(redirect_uri: str) -> Flow:
    return Flow.from_client_secrets_file(
        _get_client_secret_file(),
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


def save_google_token(db: Session, token: dict[str, Any]) -> None:
    record = (
        db.query(GoogleOAuthTokenORM)
        .filter(GoogleOAuthTokenORM.provider == GOOGLE_PROVIDER)
        .first()
    )

    token_json = json.dumps(token)
    if record:
        record.token_json = token_json
    else:
        db.add(GoogleOAuthTokenORM(provider=GOOGLE_PROVIDER, token_json=token_json))

    db.commit()


def _load_token_record(db: Session) -> GoogleOAuthTokenORM | None:
    return (
        db.query(GoogleOAuthTokenORM)
        .filter(GoogleOAuthTokenORM.provider == GOOGLE_PROVIDER)
        .first()
    )


def _build_credentials(token: dict[str, Any]) -> Credentials | None:
    required_fields = ("token", "refresh_token", "token_uri", "client_id", "client_secret")
    if not all(token.get(field) for field in required_fields):
        return None

    return Credentials(
        token=token.get("token"),
        refresh_token=token.get("refresh_token"),
        token_uri=token.get("token_uri"),
        client_id=token.get("client_id"),
        client_secret=token.get("client_secret"),
        scopes=SCOPES,
    )


def load_google_credentials(db: Session) -> Credentials | None:
    record = _load_token_record(db)
    if not record:
        return None

    try:
        token = json.loads(record.token_json)
    except json.JSONDecodeError:
        return None

    if not isinstance(token, dict):
        return None

    creds = _build_credentials(token)
    if not creds:
        return None

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            save_google_token(db, json.loads(creds.to_json()))
        except Exception:
            return None

    return creds


def build_calendar_client(creds: Credentials) -> Resource:
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def parse_google_event_date(event: dict[str, Any]) -> datetime | None:
    start = event.get("start", {})
    if not isinstance(start, dict):
        return None

    if "dateTime" in start:
        raw = str(start["dateTime"])
        if raw.endswith("Z"):
            raw = raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    if "date" in start:
        try:
            return datetime.fromisoformat(str(start["date"])).replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    return None


def fetch_calendar_list(client: Resource) -> Iterator[dict[str, Any]]:
    page_token: str | None = None
    while True:
        result = client.calendarList().list(pageToken=page_token).execute()
        for item in result.get("items", []):
            if isinstance(item, dict):
                yield item

        page_token = result.get("nextPageToken")
        if not page_token:
            break


def fetch_events(client: Resource, calendar_id: str, days_ahead: int = 365) -> Iterator[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    time_min = (now - timedelta(days=1)).isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    page_token: str | None = None
    while True:
        result = (
            client.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
            )
            .execute()
        )

        for item in result.get("items", []):
            if isinstance(item, dict):
                yield item

        page_token = result.get("nextPageToken")
        if not page_token:
            break
