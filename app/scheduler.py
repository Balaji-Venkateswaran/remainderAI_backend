from datetime import date
from apscheduler.schedulers.background import BackgroundScheduler

from app.db import SessionLocal
from app.models.reminder_orm import ReminderORM


def _log_due_reminders():
    today = date.today()
    db = SessionLocal()
    try:
        reminders = (
            db.query(ReminderORM)
            .filter(ReminderORM.completed.is_(False))
            .filter(ReminderORM.reminder_date <= today)
            .order_by(ReminderORM.reminder_date.asc())
            .all()
        )
        if not reminders:
            return
        for r in reminders:
            print(
                f"[REMINDER] {r.title} | {r.appliance_type} {r.brand} "
                f"| due {r.reminder_date} | id {r.id}"
            )
    finally:
        db.close()


def start_scheduler():
    scheduler = BackgroundScheduler()
    # Run daily at 09:00 local time
    scheduler.add_job(
        _log_due_reminders,
        trigger="cron",
        hour=9,
        minute=0
    )
    scheduler.start()
    return scheduler
