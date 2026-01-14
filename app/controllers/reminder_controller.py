from datetime import date
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.reminder_model import Reminder
from app.models.reminder_orm import ReminderORM

class ReminderController:

    @staticmethod
    def _to_schema(reminder: ReminderORM) -> Reminder:
        return Reminder(
            id=reminder.id,
            applianceType=reminder.appliance_type,
            brand=reminder.brand,
            model=reminder.model,
            reminderDate=reminder.reminder_date,
            title=reminder.title,
            notes=reminder.notes,
            completed=reminder.completed
        )

    @staticmethod
    def create_reminder(reminder: Reminder, db: Session):
        if reminder.reminderDate < date.today():
            return {
                "error": "Reminder date must be today or a future date"
            }

        record = ReminderORM(
            id=str(reminder.id),
            appliance_type=reminder.applianceType,
            brand=reminder.brand,
            model=reminder.model or "",
            reminder_date=reminder.reminderDate,
            title=reminder.title,
            notes=reminder.notes or "",
            completed=reminder.completed
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return ReminderController._to_schema(record)

    @staticmethod
    def get_all_reminders(db: Session) -> List[Reminder]:
        reminders = (
            db.query(ReminderORM)
            .order_by(ReminderORM.reminder_date.asc())
            .all()
        )
        return [ReminderController._to_schema(r) for r in reminders]

    @staticmethod
    def get_pending_todos(db: Session) -> List[Reminder]:
        today = date.today()
        reminders = (
            db.query(ReminderORM)
            .filter(ReminderORM.completed.is_(False))
            .filter(ReminderORM.reminder_date <= today)
            .order_by(ReminderORM.reminder_date.asc())
            .all()
        )
        return [ReminderController._to_schema(r) for r in reminders]

    @staticmethod
    def complete_reminder(reminder_id: UUID, db: Session):
        reminder = db.get(ReminderORM, str(reminder_id))
        if not reminder:
            return None
        reminder.completed = True
        db.commit()
        db.refresh(reminder)
        return ReminderController._to_schema(reminder)
        return None
