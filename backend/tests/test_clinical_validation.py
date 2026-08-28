"""Input rules that protect clinical decisions.

Vitals and appointment dates steer real decisions, so the bounds are asserted
here rather than trusted. The point of each test is the *rejection*: a
validator that accepted everything would pass a happy-path-only suite.
"""

import pytest
from pydantic import ValidationError

from app.schemas import (
    CreateVitalsRequest,
    CreateNursingNoteRequest,
    CreateMedicationAdministrationRequest,
    CreateAppointmentRequest,
)


# ─── Vitals ──────────────────────────────────────────────────────────────────

def test_a_reading_is_required():
    """An empty submission would otherwise store a row asserting nothing."""
    with pytest.raises(ValidationError):
        CreateVitalsRequest()


def test_a_single_reading_is_enough():
    assert CreateVitalsRequest(spo2=98).spo2 == 98


def test_notes_alone_do_not_count_as_a_reading():
    with pytest.raises(ValidationError):
        CreateVitalsRequest(notes="patient resting")


@pytest.mark.parametrize("field,value", [
    ("spo2", 990),                     # fat-finger 99 -> 990
    ("spo2", -1),
    ("temperature_celsius", 450.0),    # 45.0 mistyped
    ("temperature_celsius", 4.0),
    ("heart_rate", 700),
    ("heart_rate", 0),
    ("blood_pressure_systolic", 3000),
    ("blood_pressure_diastolic", 5),
    ("respiratory_rate", 200),
    ("weight_kg", 0),
    ("weight_kg", -5),
    ("height_cm", 900),
])
def test_impossible_readings_are_rejected(field, value):
    with pytest.raises(ValidationError):
        CreateVitalsRequest(**{field: value})


@pytest.mark.parametrize("field,value", [
    ("spo2", 100),
    ("spo2", 88),
    ("temperature_celsius", 39.2),
    ("temperature_celsius", 35.0),
    ("heart_rate", 128),
    ("blood_pressure_systolic", 180),
    ("blood_pressure_diastolic", 60),
    ("respiratory_rate", 24),
    ("weight_kg", 70.5),
    ("height_cm", 170),
])
def test_clinically_abnormal_but_possible_readings_are_accepted(field, value):
    """Out-of-range is a flag for the doctor, not a reason to refuse entry.

    A febrile or hypoxic patient is exactly who needs recording.
    """
    assert CreateVitalsRequest(**{field: value}) is not None


# ─── Nursing notes ───────────────────────────────────────────────────────────

def test_note_type_is_constrained():
    with pytest.raises(ValidationError):
        CreateNursingNoteRequest(note_type="Whatever", content="x")


@pytest.mark.parametrize("note_type", ["Observation", "Care", "Incident"])
def test_valid_note_types(note_type):
    assert CreateNursingNoteRequest(note_type=note_type, content="Reviewed").note_type == note_type


def test_empty_note_is_rejected():
    with pytest.raises(ValidationError):
        CreateNursingNoteRequest(content="")


# ─── Medication administration ───────────────────────────────────────────────

@pytest.mark.parametrize("status", ["Administered", "Refused", "Held", "Missed"])
def test_valid_administration_outcomes(status):
    assert CreateMedicationAdministrationRequest(status=status).status == status


def test_unknown_administration_outcome_is_rejected():
    """"Refused" and "Missed" carry clinical weight; free text would lose it."""
    with pytest.raises(ValidationError):
        CreateMedicationAdministrationRequest(status="probably gave it")


# ─── Appointments ────────────────────────────────────────────────────────────

def test_appointment_cannot_be_booked_in_the_past():
    from datetime import date, timedelta
    with pytest.raises(ValidationError):
        CreateAppointmentRequest(
            doctor_id="00000000-0000-0000-0000-000000000000",
            department="Cardiology",
            appointment_date=date.today() - timedelta(days=1),
            appointment_time="10:00",
        )


def test_appointment_today_is_allowed():
    from datetime import date
    booking = CreateAppointmentRequest(
        doctor_id="00000000-0000-0000-0000-000000000000",
        department="Cardiology",
        appointment_date=date.today(),
        appointment_time="10:00",
    )
    assert booking.appointment_date == date.today()
