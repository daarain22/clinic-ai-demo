"""
Groq AI service for CarePlus Clinic AI Receptionist.
Handles clinic FAQs only; appointment booking is handled by Python state.
"""

import json
import os
from pathlib import Path

from groq import Groq


_CLINIC_DATA_PATH = Path(__file__).parent.parent / "data" / "clinic_data.json"

with open(_CLINIC_DATA_PATH, "r", encoding="utf-8") as f:
    CLINIC_DATA = json.load(f)

CLINIC_JSON_STR = json.dumps(CLINIC_DATA, indent=2)

SYSTEM_PROMPT = f"""
You are Aria, the AI Receptionist for CarePlus Multispeciality Clinic, Mysore.
You are warm, professional, concise, and knowledgeable.

Your job is to answer clinic-related questions only.

You can answer:
- Doctors and specialties
- Consultation fees
- Clinic timings
- Insurance accepted
- Location
- Services offered

Important rules:
- Do not collect appointment details.
- Do not ask for patient name, phone number, date, or time slot.
- If the user wants to book an appointment, respond exactly:
  "Sure, I can help with that. Let me start the appointment booking process."
- Use only the clinic information below.
- Never invent information.
- Keep responses concise and professional.

Clinic data:
{CLINIC_JSON_STR}
"""


def get_gemini_response(conversation_history: list, user_message: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is not set.")

    client = Groq(api_key=api_key)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(conversation_history[-10:])
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        max_tokens=250,
        temperature=0.2,
        top_p=0.8,
        stream=False,
    )

    return response.choices[0].message.content.strip()
