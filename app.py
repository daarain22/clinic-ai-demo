"""
CarePlus AI Receptionist — FastAPI Backend
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from services.appointment_service import get_appointments, save_appointment
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
