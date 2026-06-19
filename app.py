"""
CarePlus AI Receptionist — FastAPI Backend
"""
import csv
import io
from collections import Counter
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from services.appointment_service import (
    get_appointments,
    save_appointment,
    update_appointment_status,
)
from services.appointment_state_machine import (
    AppointmentStateMachine,
    is_appointment_intent,
)
from services.gemini_service import get_gemini_response
import uvicorn

app = FastAPI(title="CarePlus AI Receptionist", version="1.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory session store: session_id -> {"history": list, "booking": AppointmentStateMachine | None}
sessions: dict = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str


class AppointmentStatusUpdate(BaseModel):
    status: str


STATUS_OPTIONS = [
    "Pending Confirmation",
    "Confirmed",
    "Completed",
    "Cancelled",
]


def doctor_name(doctor: str) -> str:
    return doctor.split(" - ", 1)[0].strip() if doctor else "Unknown"


def sorted_appointments() -> list[dict]:
    return sorted(
        get_appointments(),
        key=lambda appointment: appointment.get("created_at", ""),
        reverse=True,
    )


def dashboard_context(request: Request) -> dict:
    appointments = sorted_appointments()
    today_token = datetime.now().strftime("%d %b %Y")
    doctor_counts = Counter(
        doctor_name(appointment.get("doctor", ""))
        for appointment in appointments
        if appointment.get("doctor")
    )

    doctors = sorted(
        {
            appointment.get("doctor", "")
            for appointment in appointments
            if appointment.get("doctor")
        }
    )
    dates = sorted(
        {
            appointment.get("date", "")
            for appointment in appointments
            if appointment.get("date")
        }
    )

    return {
        "request": request,
        "appointments": appointments,
        "doctor_summary": doctor_counts.most_common(),
        "doctors": doctors,
        "dates": dates,
        "status_options": STATUS_OPTIONS,
        "stats": {
            "total": len(appointments),
            "today": sum(
                today_token in appointment.get("date", "")
                for appointment in appointments
            ),
            "unique_doctors": len(doctors),
            "pending": sum(
                appointment.get("status") == "Pending Confirmation"
                for appointment in appointments
            ),
        },
    }


def get_session(session_id: str) -> dict:
    if session_id not in sessions:
        sessions[session_id] = {"history": [], "booking": None}
    return sessions[session_id]


def remember_exchange(session: dict, user_message: str, assistant_message: str) -> None:
    history = session["history"]
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": assistant_message})

    # Cap at last 20 exchanges (40 messages)
    if len(history) > 40:
        session["history"] = history[-40:]


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin.html", dashboard_context(request))


@app.get("/admin/export-csv")
async def export_appointments_csv():
    output = io.StringIO()
    fieldnames = ["Patient", "Phone", "Doctor", "Date", "Time", "Status", "Created At"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for appointment in sorted_appointments():
        writer.writerow({
            "Patient": appointment.get("patient", ""),
            "Phone": appointment.get("phone", ""),
            "Doctor": appointment.get("doctor", ""),
            "Date": appointment.get("date", ""),
            "Time": appointment.get("time", ""),
            "Status": appointment.get("status", ""),
            "Created At": appointment.get("created_at", ""),
        })

    filename = f"careplus-appointments-{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/admin/appointments/{created_at}/status")
async def update_admin_appointment_status(created_at: str, payload: AppointmentStatusUpdate):
    if payload.status not in STATUS_OPTIONS:
        raise HTTPException(status_code=400, detail="Invalid appointment status.")

    appointment = update_appointment_status(created_at, payload.status)
    if appointment is None:
        raise HTTPException(status_code=404, detail="Appointment not found.")

    return appointment


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    session = get_session(payload.session_id)
    history = session["history"]
    booking = session["booking"]

    if booking:
        reply = booking.handle(payload.message)
    elif is_appointment_intent(payload.message):
        booking = AppointmentStateMachine()
        session["booking"] = booking
        reply = booking.handle(payload.message)
    else:
        try:
            reply = get_gemini_response(history, payload.message)
        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")

    if booking and booking.is_complete() and not booking.saved:
        try:
            save_appointment(booking.appointment_payload())
            booking.saved = True
            session["booking"] = None
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Appointment save error: {str(e)}")

    if booking and booking.is_cancelled():
        session["booking"] = None

    remember_exchange(session, payload.message, reply)

    return ChatResponse(response=reply)


@app.delete("/chat/reset")
async def reset_chat(session_id: str = "default"):
    sessions.pop(session_id, None)
    return {"message": "Conversation reset successfully."}

@app.get("/admin/appointments")
async def admin_appointments():
    return JSONResponse(content=get_appointments())

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
