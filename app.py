"""
CarePlus AI Receptionist — FastAPI Backend
"""
import re
from services.appointment_service import save_appointment
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from services.gemini_service import get_gemini_response
from fastapi.responses import JSONResponse
from services.appointment_service import get_appointments
import uvicorn

app = FastAPI(title="CarePlus AI Receptionist", version="1.0.0")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# In-memory session store: session_id -> list of message dicts
sessions: dict = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    response: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    session_id = payload.session_id
    if session_id not in sessions:
        sessions[session_id] = []

    history = sessions[session_id]

    try:
        reply = get_gemini_response(history, payload.message)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI service error: {str(e)}")
    
    # Save completed appointment requests
    if "Appointment Requested!" in reply:
        try:
            patient_match = re.search(r"Patient\s*:\s*(.*)", reply)
            phone_match = re.search(r"Mobile\s*:\s*(.*)", reply)
            doctor_match = re.search(r"Doctor\s*:\s*(.*)", reply)
            date_match = re.search(r"Date\s*:\s*(.*)", reply)
            time_match = re.search(r"Time\s*:\s*(.*)", reply)

            if all([patient_match, phone_match, doctor_match, date_match, time_match]):
                save_appointment({
                    "patient": patient_match.group(1).strip(),
                    "phone": phone_match.group(1).strip(),
                    "doctor": doctor_match.group(1).strip(),
                    "date": date_match.group(1).strip(),
                    "time": time_match.group(1).strip(),
                    "status": "Pending Confirmation"
                })

        except Exception as e:
            print(f"Appointment save error: {e}")

    # Groq uses "assistant" role (not "model")
    history.append({"role": "user", "content": payload.message})
    history.append({"role": "assistant", "content": reply})

    # Cap at last 20 exchanges (40 messages)
    if len(history) > 40:
        sessions[session_id] = history[-40:]

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
