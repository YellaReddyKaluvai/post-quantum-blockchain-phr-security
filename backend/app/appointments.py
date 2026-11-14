"""Appointment slots and guarded patient changes (hospital-local time)."""

import os
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
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
        raise HTTPException(
            422, "Use a local appointment time in HH:MM format."
        ) from exc
    if datetime.combine(day, value, clinic_zone()) <= datetime.now(clinic_zone()):
        raise HTTPException(
            422, "Appointment must be in the future (hospital local time)."
        )
    return value


class WorkingDay(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: str
    end: str

    @model_validator(mode="after")
    def valid_hours(self):
        for value in (self.start, self.end):
            parsed = time.fromisoformat(value)
            if parsed.tzinfo or parsed.second or parsed.microsecond:
                raise ValueError("Use HH:MM local time")
        if self.start >= self.end:
            raise ValueError("Start must precede end")
        self.start = time.fromisoformat(self.start).strftime("%H:%M")
        self.end = time.fromisoformat(self.end).strftime("%H:%M")
        return self


class Schedule(BaseModel):
    duration_minutes: int = Field(default=30, ge=5, le=240)
    days: list[WorkingDay] = Field(max_length=7)
    leave_dates: list[date] = Field(default_factory=list, max_length=366)

    @model_validator(mode="after")
    def unique_days(self):
        if len({d.weekday for d in self.days}) != len(self.days):
            raise ValueError("Use one working interval per weekday")
        return self


def doctor_lock(cur, doctor_id):
    cur.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
        ("appointment:doctor:" + str(doctor_id),),
    )


def schedule_for(cur, doctor_id):
    cur.execute(
        "SELECT appointment_schedule FROM Users WHERE id=%s AND role='Doctor' AND status='Approved'",
        (doctor_id,),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Doctor unavailable.")
    if row["appointment_schedule"] is not None:
        return Schedule.model_validate(row["appointment_schedule"])
    return Schedule(
        days=[
            WorkingDay(
                weekday=i,
                start=f"{int(os.getenv('APPOINTMENT_START_HOUR','9')):02}:00",
                end=f"{int(os.getenv('APPOINTMENT_END_HOUR','17')):02}:00",
            )
            for i in range(7)
        ]
    )


def fits_schedule(schedule, day, clock, duration=None):
    if day in schedule.leave_dates:
        return False
    duration = duration or schedule.duration_minutes
    minute = clock.hour * 60 + clock.minute
    for work in schedule.days:
        start = time.fromisoformat(work.start)
        end = time.fromisoformat(work.end)
        lower = start.hour * 60 + start.minute
        upper = end.hour * 60 + end.minute
        if (
            work.weekday == day.weekday()
            and lower <= minute
            and minute + duration <= upper
        ):
            return (minute - lower) % schedule.duration_minutes == 0
    return False


def reserve_slot(cur, doctor_id, patient_id, day, clock, exclude=None):
    value = validate_future(day, str(clock))
    for key in sorted(["doctor:" + str(doctor_id), "patient:" + str(patient_id)]):
        cur.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            ("appointment:" + key,),
        )
    schedule = schedule_for(cur, doctor_id)
    if not fits_schedule(schedule, day, value):
        raise HTTPException(
            409,
            "Doctor is off duty, on leave, or the time is outside the appointment grid.",
        )
    cur.execute(
        """SELECT id FROM Appointments WHERE (doctor_id = %s OR patient_id = %s)
        AND status::text IN ('Pending', 'Scheduled', 'Confirmed') AND (%s::uuid IS NULL OR id <> %s::uuid)
        AND appointment_date + appointment_time < %s::date + %s::time + make_interval(mins => %s)
        AND appointment_date + appointment_time + make_interval(mins => duration_minutes) > %s::date + %s::time
        LIMIT 1""",
        (
            doctor_id,
            patient_id,
            exclude,
            exclude,
            day,
            value,
            schedule.duration_minutes,
            day,
            value,
        ),
    )
    if cur.fetchone():
        raise HTTPException(
            409,
            "This slot conflicts with an existing appointment. Choose another time.",
        )
    return schedule.duration_minutes


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
def slots(
    doctor_id: UUID, day: date = Query(...), session=Depends(require_role("Patient"))
):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        schedule = schedule_for(cur, doctor_id)
        cur.execute(
            """SELECT appointment_date, appointment_time,duration_minutes FROM Appointments
            WHERE (doctor_id=%s OR patient_id=%s) AND appointment_date BETWEEN %s::date-1 AND %s::date+1
            AND status::text IN ('Pending','Scheduled','Confirmed')""",
            (doctor_id, session["user_id"], day, day),
        )
        busy = [
            (
                datetime.combine(
                    r["appointment_date"], r["appointment_time"], clinic_zone()
                ),
                r["duration_minutes"],
            )
            for r in cur.fetchall()
        ]
    now = datetime.now(clinic_zone())
    available = []
    for minute in range(24 * 60):
        clock = time(minute // 60, minute % 60)
        slot = datetime.combine(day, clock, clinic_zone())
        if (
            slot > now
            and fits_schedule(schedule, day, clock)
            and not any(
                slot < b + timedelta(minutes=d)
                and b < slot + timedelta(minutes=schedule.duration_minutes)
                for b, d in busy
            )
        ):
            available.append(clock.strftime("%H:%M"))
    return {
        "timezone": str(clinic_zone()),
        "duration_minutes": schedule.duration_minutes,
        "slots": available,
    }


@router.post("/appointments/{appointment_id}/cancel")
def cancel(appointment_id: UUID, session=Depends(require_role("Patient"))):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """UPDATE Appointments SET status = 'Cancelled', updated_at = NOW()
            WHERE id = %s AND patient_id = %s AND status::text IN ('Pending','Scheduled','Confirmed')
            RETURNING doctor_id""",
            (appointment_id, session["user_id"]),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(
                409, "Appointment is unavailable or no longer cancellable."
            )
        if row["doctor_id"]:
            cur.execute(
                "INSERT INTO Notifications (user_id, notification_type, title, body) VALUES (%s, 'APPOINTMENT_CANCELLED', 'Patient cancelled appointment', 'A patient cancelled an appointment. Check your appointments list.')",
                (row["doctor_id"],),
            )
        conn.commit()
    return {"status": "success"}


@router.post("/appointments/{appointment_id}/reschedule")
def reschedule(
    appointment_id: UUID,
    body: RescheduleRequest,
    session=Depends(require_role("Patient")),
):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM Appointments WHERE id = %s AND patient_id = %s FOR UPDATE",
            (appointment_id, session["user_id"]),
        )
        row = cur.fetchone()
        if (
            not row
            or row["status"] not in ("Pending", "Scheduled", "Confirmed")
            or not row["doctor_id"]
        ):
            raise HTTPException(
                409, "Appointment is unavailable or no longer reschedulable."
            )
        cur.execute(
            "SELECT id FROM Users WHERE id = %s AND status = 'Approved'",
            (row["doctor_id"],),
        )
        if not cur.fetchone():
            raise HTTPException(409, "Doctor is unavailable.")
        duration = reserve_slot(
            cur,
            row["doctor_id"],
            session["user_id"],
            body.appointment_date,
            body.appointment_time,
            appointment_id,
        )
        cur.execute(
            "UPDATE Appointments SET appointment_date = %s, appointment_time = %s, duration_minutes = %s, status = 'Pending', updated_at = NOW() WHERE id = %s",
            (body.appointment_date, body.appointment_time, duration, appointment_id),
        )
        cur.execute(
            "INSERT INTO Notifications (user_id, notification_type, title, body) VALUES (%s, 'APPOINTMENT_REQUEST', 'Appointment rescheduled', 'A patient requested a new time. Please confirm the appointment.')",
            (row["doctor_id"],),
        )
        conn.commit()
    return {
        "status": "success",
        "message": "Rescheduled; awaiting doctor confirmation.",
    }


# Separate prefix for the doctor who owns the schedule.
doctor_router = APIRouter(prefix="/api/doctor", tags=["Doctor availability"])


@doctor_router.get("/schedule")
def get_schedule(session=Depends(require_role("Doctor"))):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        return schedule_for(cur, session["user_id"]).model_dump(mode="json")


@doctor_router.put("/schedule")
def save_schedule(body: Schedule, session=Depends(require_role("Doctor"))):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        doctor_lock(cur, session["user_id"])
        cur.execute(
            """SELECT appointment_date,appointment_time,duration_minutes FROM Appointments
            WHERE doctor_id=%s AND status::text IN ('Pending','Scheduled','Confirmed')
            AND appointment_date+appointment_time > %s""",
            (session["user_id"], datetime.now(clinic_zone()).replace(tzinfo=None)),
        )
        if any(
            not fits_schedule(
                body,
                r["appointment_date"],
                r["appointment_time"],
                r["duration_minutes"],
            )
            for r in cur.fetchall()
        ):
            raise HTTPException(
                409,
                "Existing future appointments conflict. Cancel or reschedule them before changing availability.",
            )
        cur.execute(
            "UPDATE Users SET appointment_schedule=%s::jsonb WHERE id=%s",
            (json.dumps(body.model_dump(mode="json")), session["user_id"]),
        )
        conn.commit()
    return {
        "message": "Availability saved. Existing appointments keep their booked duration."
    }
