from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler

from app.db import SessionLocal
from sqlalchemy import or_

from app.controllers.google_calendar_controller import GoogleCalendarController
from app.models.todo_orm import TodoORM


def _mark_due_todos():
    today = date.today()
    db = SessionLocal()
    try:
        db.query(TodoORM).filter(
            or_(
                TodoORM.completed.is_(True),
                TodoORM.due_date != today
            )
        ).update(
            {TodoORM.due: False},
            synchronize_session=False
        )
        due_todos = (
            db.query(TodoORM)
            .filter(TodoORM.completed.is_(False))
            .filter(TodoORM.due_date == today)
            .all()
        )
        for todo in due_todos:
            todo.due = True
        db.commit()
    finally:
        db.close()


def _sync_google_calendar():
    db = SessionLocal()
    try:
        GoogleCalendarController.sync_all_calendars(db)
    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        _mark_due_todos,
        trigger="cron",
        hour=9,
        minute=0
    )
    scheduler.add_job(
        _sync_google_calendar,
        trigger="interval",
        minutes=5
    )
    scheduler.start()
    return scheduler
