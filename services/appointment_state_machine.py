import json
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional


_CLINIC_DATA_PATH = Path(__file__).parent.parent / "data" / "clinic_data.json"


def _load_clinic_data() -> dict:
    with open(_CLINIC_DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _doctor_label(doctor: dict) -> str:
    return f"{doctor['name']} - {doctor['specialization']}"


def _date_label(value: date) -> str:
    return value.strftime("%A, %d %b %Y")


def _extract_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def is_appointment_intent(message: str) -> bool:
    normalized = _normalize(message)
    intent_phrases = [
        "appointment",
        "book",
        "booking",
        "schedule",
        "see doctor",
        "visit doctor",
        "need doctor",
    ]
    return any(phrase in normalized for phrase in intent_phrases)


@dataclass
class AppointmentStateMachine:
    state: str = "ASK_DOCTOR"
    doctor: Optional[dict] = None
    suggested_dates: list[date] = field(default_factory=list)
    selected_date: Optional[date] = None
    selected_time: Optional[str] = None
    patient_name: Optional[str] = None
    phone: Optional[str] = None
    saved: bool = False

    def handle(self, message: str) -> str:
        text = message.strip()

        if _normalize(text) in {"cancel", "stop", "reset", "start over"}:
            self.state = "CANCELLED"
            return "No problem. I have cancelled the appointment request."

        if self.state == "ASK_DOCTOR":
            return self._handle_doctor(text)
        if self.state == "ASK_DATE":
            return self._handle_date(text)
        if self.state == "ASK_TIME":
            return self._handle_time(text)
        if self.state == "ASK_PATIENT_NAME":
            return self._handle_patient_name(text)
        if self.state == "ASK_PHONE":
            return self._handle_phone(text)

        return "This appointment request is already complete. Our team will call you to confirm."

    def is_complete(self) -> bool:
        return self.state == "COMPLETE"

    def is_cancelled(self) -> bool:
        return self.state == "CANCELLED"

    def appointment_payload(self) -> dict:
        if not self.is_complete():
            raise ValueError("Appointment is not complete.")

        return {
            "patient": self.patient_name,
            "phone": self.phone,
            "doctor": _doctor_label(self.doctor),
            "date": _date_label(self.selected_date),
            "time": self.selected_time,
            "status": "Pending Confirmation",
        }

    def _handle_doctor(self, text: str) -> str:
        doctor = self._match_doctor(text)
        if not doctor:
            doctors = "\n".join(
                f"- {_doctor_label(item)}" for item in self._doctors()
            )
            return (
                "Sure, I can help with that. Which doctor or specialty would you prefer?\n\n"
                f"{doctors}"
            )

        self.doctor = doctor
        self.suggested_dates = self._next_available_dates(doctor)
        self.state = "ASK_DATE"

        options = "\n".join(
            f"{index}. {_date_label(day)}"
            for index, day in enumerate(self.suggested_dates, start=1)
        )
        return (
            f"{doctor['name']} is available on:\n"
            f"{options}\n"
            "Which date works best for you?"
        )

    def _handle_date(self, text: str) -> str:
        selected = self._parse_date_choice(text)
        if not selected:
            options = "\n".join(
                f"{index}. {_date_label(day)}"
                for index, day in enumerate(self.suggested_dates, start=1)
            )
            return (
                "Please choose one of these available dates:\n"
                f"{options}"
            )

        self.selected_date = selected
        self.state = "ASK_TIME"
        slots = self._slots_for_date(self.doctor, selected)

        options = "\n".join(
            f"{index}. {slot}" for index, slot in enumerate(slots, start=1)
        )
        return (
            f"Available slots on {_date_label(selected)}:\n"
            f"{options}\n"
            "Which slot would you prefer?"
        )

    def _handle_time(self, text: str) -> str:
        selected = self._parse_time_choice(text)
        if not selected:
            slots = self._slots_for_date(self.doctor, self.selected_date)
            options = "\n".join(
                f"{index}. {slot}" for index, slot in enumerate(slots, start=1)
            )
            return (
                "Please choose one of these available slots:\n"
                f"{options}"
            )

        self.selected_time = selected
        self.state = "ASK_PATIENT_NAME"
        return "May I have your full name?"

    def _handle_patient_name(self, text: str) -> str:
        if len(text) < 2 or _extract_digits(text):
            return "Please enter the patient's full name."

        self.patient_name = text
        self.state = "ASK_PHONE"
        return "And your 10-digit mobile number?"

    def _handle_phone(self, text: str) -> str:
        digits = _extract_digits(text)
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]

        if len(digits) != 10:
            return "Please enter a valid 10-digit mobile number."

        self.phone = digits
        self.state = "COMPLETE"
        return self._confirmation_message()

    def _confirmation_message(self) -> str:
        return (
            "Appointment Requested!\n"
            "----------------------\n"
            f"Patient : {self.patient_name}\n"
            f"Mobile  : {self.phone}\n"
            f"Doctor  : {_doctor_label(self.doctor)}\n"
            f"Date    : {_date_label(self.selected_date)}\n"
            f"Time    : {self.selected_time}\n"
            f"Fee     : Rs {self.doctor['consultation_fee']}\n"
            "----------------------\n"
            "Our team will call you to confirm. Thank you for choosing CarePlus!"
        )

    def _doctors(self) -> list[dict]:
        return _load_clinic_data()["clinic"]["doctors"]

    def _match_doctor(self, text: str) -> Optional[dict]:
        normalized = _normalize(text)
        if not normalized:
            return None

        for doctor in self._doctors():
            name = _normalize(doctor["name"])
            specialization = _normalize(doctor["specialization"])
            label = _normalize(_doctor_label(doctor))

            if name in normalized or specialization in normalized or label in normalized:
                return doctor

            name_parts = [part for part in name.split() if part not in {"dr"}]
            if any(part in normalized for part in name_parts):
                return doctor

            specialty_root = specialization.replace(" surgeon", "")
            if specialty_root and specialty_root in normalized:
                return doctor

        return None

    def _next_available_dates(self, doctor: dict, count: int = 3) -> list[date]:
        today = date.today()
        available = []

        for offset in range(0, 60):
            current = today + timedelta(days=offset)
            weekday = current.strftime("%A")
            schedule = doctor["schedule"].get(weekday, {})
            if schedule.get("available"):
                available.append(current)
                if len(available) == count:
                    break

        return available

    def _parse_date_choice(self, text: str) -> Optional[date]:
        normalized = _normalize(text)

        if normalized in {"earliest", "first", "soonest", "next available"}:
            return self.suggested_dates[0] if self.suggested_dates else None

        ordinal_choices = {
            "first": 0,
            "second": 1,
            "third": 2,
        }
        if normalized in ordinal_choices:
            index = ordinal_choices[normalized]
            if 0 <= index < len(self.suggested_dates):
                return self.suggested_dates[index]

        match = re.search(r"\b([1-3])\b", text)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(self.suggested_dates):
                return self.suggested_dates[index]

        for day in self.suggested_dates:
            if normalized in _normalize(_date_label(day)):
                return day

        for day in self.suggested_dates:
            weekday = day.strftime("%A").lower()
            day_number = day.strftime("%d").lstrip("0")
            if weekday in normalized or day_number in normalized:
                return day

        return None

    def _slots_for_date(self, doctor: dict, selected_date: date) -> list[str]:
        weekday = selected_date.strftime("%A")
        return doctor["schedule"][weekday]["slots"]

    def _parse_time_choice(self, text: str) -> Optional[str]:
        slots = self._slots_for_date(self.doctor, self.selected_date)
        normalized = _normalize(text)

        match = re.search(r"\b([1-5])\b", text)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(slots):
                return slots[index]

        for slot in slots:
            if _normalize(slot) in normalized:
                return slot

        compact_text = re.sub(r"\s+", "", text.lower())
        for slot in slots:
            compact_slot = re.sub(r"\s+", "", slot.lower())
            if compact_slot in compact_text:
                return slot

        return None
