import os

from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import json
from sqlalchemy.orm import Session

from app.controllers.detect_controller import DetectController
from app.controllers.service_center_controller import ServiceCenterController
from app.controllers.model_catalog_controller import ModelCatalogController
from app.controllers.reminder_controller import ReminderController
from app.controllers.todo_controller import TodoController
from app.controllers.google_calendar_controller import GoogleCalendarController
from app.voice.router import router as voice_router
from app.models.reminder_model import Reminder
from app.models.todo_model import TodoCreate, TodoUpdate
from app.models.google_oauth_token_orm import GoogleOAuthTokenORM
from app.models.calendar_event_sync_orm import CalendarEventSyncORM
from app.models.todo_orm import TodoORM
from uuid import UUID


from datetime import date
from app.utils.service_date_calculator import calculate_next_service_date_llm
from app.db import Base, engine, get_db

from app.scheduler import start_scheduler

Base.metadata.create_all(bind=engine)

_scheduler = None

app = FastAPI(
    title="Smart Appliance AI",
    description="Gemini Vision ??? LLaVA-guided OpenStreetMap service center discovery",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(voice_router)


@app.on_event("startup")
def _start_scheduler():
    global _scheduler
    _scheduler = start_scheduler()


@app.on_event("shutdown")
def _stop_scheduler():
    if _scheduler:
        _scheduler.shutdown()

@app.get("/")
def home():
    return {
        "status": "running",
        "engine": "Gemini Vision + LLaVA + OpenStreetMap",
        "message": "Smart Appliance AI is running"
    }

@app.post("/detect-appliance", tags=["Appliance Detection"])
async def detect_appliance(image: UploadFile = File(...)):
 
    return await DetectController.detect_appliance(image)

@app.get("/find-service-centers", tags=["Service Centers"])
async def find_service_centers(
    appliance_type: str,
    brand: str
):

    return await ServiceCenterController.find_service_centers(
        appliance_type=appliance_type,
        brand=brand
    )

@app.get("/find-local-services", tags=["Local Services"])
async def find_local_services(
    query: str,
    lat: float | None = None,
    lon: float | None = None,
    limit_per_category: int = 3,
    radius_m: int = 6000
):
    return await ServiceCenterController.find_local_services_llm(
        query=query,
        user_lat=lat,
        user_lon=lon,
        limit_per_category=limit_per_category,
        radius_m=radius_m
    )

@app.get("/local-store-suggestions", tags=["Local Services"])
async def local_store_suggestions(
    query: str = "",
    limit: int = 8,
    db: Session = Depends(get_db)
):
    return TodoController.get_saved_local_store_suggestions(
        db=db,
        query=query,
        limit=limit
    )

@app.post("/detect-appliance-and-centers", tags=["Smart Flow"])
async def detect_appliance_and_centers(image: UploadFile = File(...)):
 
    detection_response = await DetectController.detect_appliance(image)

    if not hasattr(detection_response, "body"):
        return detection_response

    detected_json = json.loads(detection_response.body)

    if "error" in detected_json:
        return detected_json

    appliance_type = detected_json.get("applianceType", "")
    brand = detected_json.get("brand", "")

    if not appliance_type:
        return {
            "error": "Appliance type could not be detected from image"
        }

    centers_response = await ServiceCenterController.find_service_centers(
        appliance_type=appliance_type,
        brand=brand
    )

    centers_json = json.loads(centers_response.body)

    return {
        "applianceDetection": detected_json,
        "serviceCenters": centers_json.get("serviceCenters", [])
    }

@app.get("/get-models", tags=["Models"])
async def get_models(
    appliance_type: str,
    brand: str
):

    return ModelCatalogController.get_models(
        appliance_type=appliance_type,
        brand=brand
    )


@app.post("/reminders", tags=["Reminders"])
async def create_reminder(
    reminder: Reminder,
    db: Session = Depends(get_db)
):

    return ReminderController.create_reminder(reminder, db)

@app.get("/reminders", tags=["Reminders"])
async def get_reminders(db: Session = Depends(get_db)):
    return ReminderController.get_all_reminders(db)

@app.post("/todos", tags=["Todo List"])
async def create_todo(
    todo: TodoCreate,
    db: Session = Depends(get_db)
):
    return TodoController.create_todo(todo, db)

@app.get("/todos", tags=["Todo List"])
async def get_pending_todos(
    completed: bool | None = None,
    due: bool | None = None,
    source: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    return TodoController.get_todos(
        db,
        completed=completed,
        due=due,
        source=source,
        limit=limit,
        offset=offset
    )

@app.get("/todos/{todo_id}", tags=["Todo List"])
async def get_todo(
    todo_id: UUID,
    db: Session = Depends(get_db)
):
    todo = TodoController.get_todo(todo_id, db)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

@app.get("/todos/{todo_id}/share-link", tags=["Todo List"])
async def get_todo_share_link(
    todo_id: UUID,
    request: Request,
    db: Session = Depends(get_db)
):
    payload = TodoController.get_share_payload(todo_id, db)
    if not payload:
        raise HTTPException(status_code=404, detail="Todo not found")

    public_base_url = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")
    if public_base_url:
        share_url = f"{public_base_url}/shared/todos/{todo_id}"
    else:
        share_url = str(request.url_for("get_shared_todo", todo_id=str(todo_id)))

    return {
        "shareUrl": share_url,
        "todo": payload,
    }

@app.get("/shared/todos/{todo_id}", tags=["Todo Share"], name="get_shared_todo")
async def get_shared_todo(
    todo_id: UUID,
    db: Session = Depends(get_db)
):
    payload = TodoController.get_share_payload(todo_id, db)
    if not payload:
        raise HTTPException(status_code=404, detail="Todo not found")
    return payload

@app.put("/todos/{todo_id}/complete", tags=["Todo List"])
async def complete_todo(
    todo_id: UUID,
    db: Session = Depends(get_db)
):
    todo = TodoController.complete_todo(todo_id, db)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

@app.put("/todos/{todo_id}/incomplete", tags=["Todo List"])
async def mark_todo_incomplete(
    todo_id: UUID,
    db: Session = Depends(get_db)
):
    todo = TodoController.mark_incomplete(todo_id, db)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

@app.put("/todos/{todo_id}", tags=["Todo List"])
async def update_todo_due_date(
    todo_id: UUID,
    payload: TodoUpdate,
    db: Session = Depends(get_db)
):
    todo = TodoController.update_due_date(todo_id, payload, db)
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")
    return todo

@app.delete("/todos/{todo_id}", tags=["Todo List"])
async def delete_todo(
    todo_id: UUID,
    db: Session = Depends(get_db)
):
    deleted = TodoController.delete_todo(todo_id, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Todo not found")
    return {"deleted": True}

@app.put("/reminders/{reminder_id}/complete", tags=["Reminders"])
async def complete_reminder(
    reminder_id: UUID,
    db: Session = Depends(get_db)
):
    reminder = ReminderController.complete_reminder(reminder_id, db)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return reminder

@app.get("/google/oauth/start", tags=["Google Calendar"])
async def google_oauth_start():
    return GoogleCalendarController.get_auth_url()

@app.get("/google/oauth/callback", tags=["Google Calendar"])
async def google_oauth_callback(code: str, db: Session = Depends(get_db)):
    return GoogleCalendarController.handle_oauth_callback(code, db)

@app.post("/google/sync", tags=["Google Calendar"])
async def google_sync(db: Session = Depends(get_db)):
    return GoogleCalendarController.sync_all_calendars(db)

@app.post("/calculate-service-date-llm", tags=["Service Reminder (AI)"])
async def calculate_service_date_llm(
    applianceType: str,
    isNew: bool,
    purchaseDate: date | None = None,
    lastServiceDate: date | None = None,
    brand: str | None = None,
    model: str | None = None
):
    if isNew and not purchaseDate:
        return {"error": "purchaseDate is required for new appliance"}

    if not isNew and not lastServiceDate:
        return {"error": "lastServiceDate is required for old appliance"}

    base_date = purchaseDate if isNew else lastServiceDate

    result = calculate_next_service_date_llm(
        appliance_type=applianceType,
        base_date=base_date,
        brand=brand,
        model=model
    )

    return {
        "applianceType": applianceType,
        "baseDate": base_date,
        "suggestedIntervalMonths": result["intervalMonths"],
        "reason": result["reason"],
        "nextServiceDate": result["nextServiceDate"]
    }


