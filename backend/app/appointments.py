"""Appointment slots and guarded patient changes (hospital-local time)."""
import os
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from psycopg.rows import dict_row
from app.database import get_db
from app.security import require_role

router = APIRouter(prefix="/api/patient", tags=["Appointments"])
SLOT_MINUTES = 30


def clinic_zone():
    return ZoneInfo(os.getenv("HOSPITAL_TIMEZONE", "Asia/Kolkata"))


def validate_future(day: date, clock: str) -> time:
    try:
        value = time.fromisoformat(clock)
        if value.tzinfo or value.second or value.microsecond:
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(422, "Use a local appointment time in HH:MM format.") from exc
    if datetime.combine(day, value, clinic_zone()) <= datetime.now(clinic_zone()):
        raise HTTPException(422, "Appointment must be in the future (hospital local time).")
    return value


def reserve_slot(cur, doctor_id, patient_id, day, clock, exclude=None):
    value = validate_future(day, str(clock))
    # Stable ordering avoids deadlock when two patient/doctor pairs overlap.
    for key in sorted(["doctor:" + str(doctor_id), "patient:" + str(patient_id)]):
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("appointment:" + key,))
    cur.execute("""SELECT id FROM Appointments WHERE (doctor_id = %s OR patient_id = %s)
        AND status::text IN ('Pending', 'Scheduled', 'Confirmed') AND (%s::uuid IS NULL OR id <> %s::uuid)
        AND appointment_date + appointment_time < %s::date + %s::time + INTERVAL '30 minutes'
        AND appointment_date + appointment_time + INTERVAL '30 minutes' > %s::date + %s::time
        LIMIT 1""", (doctor_id, patient_id, exclude, exclude, day, value, day, value))
    if cur.fetchone():
        raise HTTPException(409, "This slot conflicts with an existing appointment. Choose another time.")


class RescheduleRequest(BaseModel):
    appointment_date: date
    appointment_time: str

    @field_validator("appointment_time")
    @classmethod
    def valid_time(cls, value):
        parsed = time.fromisoformat(value)
        if parsed.tzinfo or parsed.second or parsed.microsecond:
            raise ValueError("Use HH:MM")
        return parsed.isoformat(timespec="minutes")


@router.get("/doctors/{doctor_id}/slots")
def slots(doctor_id: UUID, day: date = Query(...), session=Depends(require_role("Patient"))):
    # Suggestions only: the booking transaction rechecks availability atomically.
    start = int(os.getenv("APPOINTMENT_START_HOUR", "9"))
    end = int(os.getenv("APPOINTMENT_END_HOUR", "17"))
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id FROM Users WHERE id = %s AND role = 'Doctor' AND status = 'Approved'", (doctor_id,))
        if not cur.fetchone():
            raise HTTPException(404, "Doctor not available.")
        cur.execute("""SELECT appointment_date, appointment_time FROM Appointments
            WHERE (doctor_id = %s OR patient_id = %s) AND appointment_date BETWEEN %s::date - 1 AND %s::date + 1
            AND status::text IN ('Pending', 'Scheduled', 'Confirmed')""", (doctor_id, session["user_id"], day, day))
        busy = [datetime.combine(r["appointment_date"], r["appointment_time"], clinic_zone()) for r in cur.fetchall()]
    now = datetime.now(clinic_zone())
    available = []
    for minutes in range(start * 60, end * 60, SLOT_MINUTES):
        slot = datetime.combine(day, time(minutes // 60, minutes % 60), clinic_zone())
        if slot > now and not any(slot < b + timedelta(minutes=SLOT_MINUTES) and b < slot + timedelta(minutes=SLOT_MINUTES) for b in busy):
            available.append(slot.strftime("%H:%M"))
    return {"timezone": str(clinic_zone()), "duration_minutes": SLOT_MINUTES, "slots": available}


@router.post("/appointments/{appointment_id}/cancel")
def cancel(appointment_id: UUID, session=Depends(require_role("Patient"))):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""UPDATE Appointments SET status = 'Cancelled', updated_at = NOW()
            WHERE id = %s AND patient_id = %s AND status::text IN ('Pending','Scheduled','Confirmed')
            RETURNING doctor_id""", (appointment_id, session["user_id"]))
        row = cur.fetchone()
        if not row:
            raise HTTPException(409, "Appointment is unavailable or no longer cancellable.")
        if row["doctor_id"]:
            cur.execute("INSERT INTO Notifications (user_id, notification_type, title, body) VALUES (%s, 'APPOINTMENT_CANCELLED', 'Patient cancelled appointment', 'A patient cancelled an appointment. Check your appointments list.')", (row["doctor_id"],))
        conn.commit()
    return {"status": "success"}


@router.post("/appointments/{appointment_id}/reschedule")
def reschedule(appointment_id: UUID, body: RescheduleRequest, session=Depends(require_role("Patient"))):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM Appointments WHERE id = %s AND patient_id = %s FOR UPDATE", (appointment_id, session["user_id"]))
        row = cur.fetchone()
        if not row or row["status"] not in ("Pending", "Scheduled", "Confirmed") or not row["doctor_id"]:
            raise HTTPException(409, "Appointment is unavailable or no longer reschedulable.")
        cur.execute("SELECT id FROM Users WHERE id = %s AND status = 'Approved'", (row["doctor_id"],))
        if not cur.fetchone():
            raise HTTPException(409, "Doctor is unavailable.")
        reserve_slot(cur, row["doctor_id"], session["user_id"], body.appointment_date, body.appointment_time, appointment_id)
        cur.execute("UPDATE Appointments SET appointment_date = %s, appointment_time = %s, status = 'Pending', updated_at = NOW() WHERE id = %s",
                    (body.appointment_date, body.appointment_time, appointment_id))
        cur.execute("INSERT INTO Notifications (user_id, notification_type, title, body) VALUES (%s, 'APPOINTMENT_REQUEST', 'Appointment rescheduled', 'A patient requested a new time. Please confirm the appointment.')", (row["doctor_id"],))
        conn.commit()
    return {"status": "success", "message": "Rescheduled; awaiting doctor confirmation."}
