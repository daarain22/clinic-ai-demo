import json
from pathlib import Path
from datetime import datetime

APPOINTMENTS_FILE = Path("data/appointments.json")


def get_appointments():
    if not APPOINTMENTS_FILE.exists():
        return []

    with open(APPOINTMENTS_FILE, "r") as f:
        return json.load(f)


def save_appointment(appointment):
    appointments = get_appointments()

    appointment["created_at"] = datetime.now().isoformat()

    appointments.append(appointment)

    with open(APPOINTMENTS_FILE, "w") as f:
        json.dump(appointments, f, indent=2)

    return appointment