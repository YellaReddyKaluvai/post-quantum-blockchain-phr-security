"""Column encryption for diagnoses and prescriptions.

These were the last record types stored as plaintext columns. Unlike reports,
they are relational rows read by several roles at once — a patient, their
doctor, and a nurse on a medication round — so the per-patient ML-KEM wrapping
used for documents would make them unreadable to the staff who need them.
They use the same AES-256-CBC column encryption that already protects date of
birth and blood group.

The honest limit, asserted here so it is not overstated elsewhere: this
defends the database at rest, not a compromised application server, because
the application holds the key.
"""

import pytest

from app.security import encrypt_data, decrypt_data


def test_round_trip():
    for text in ["Type 2 Diabetes Mellitus", "Metformin", "500mg", "Twice daily"]:
        assert decrypt_data(encrypt_data(text)) == text


def test_ciphertext_does_not_contain_the_plaintext():
    """The property that matters for a stolen database dump."""
    stored = encrypt_data("Type 2 Diabetes Mellitus")
    assert "Diabetes" not in stored
    assert "Mellitus" not in stored


def test_same_text_encrypts_differently_each_time():
    """A random IV per write. Without it, identical diagnoses across patients
    would produce identical ciphertext, leaking who shares a condition."""
    a = encrypt_data("Hypertension")
    b = encrypt_data("Hypertension")
    assert a != b
    assert decrypt_data(a) == decrypt_data(b) == "Hypertension"


def test_plaintext_passes_through_unchanged():
    """Rows written before encryption must still read correctly, which is what
    makes the migration safe to run against a live database."""
    legacy = "Hypertension"
    assert decrypt_data(legacy) == legacy


def test_text_containing_a_colon_is_not_mistaken_for_ciphertext():
    """Clinical notes routinely contain colons. A shape-based guess at whether
    a value is encrypted would corrupt them; the migration decrypts to decide."""
    note = "Plan: review in 6 weeks; target HbA1c: 7.0"
    assert decrypt_data(note) == note


def test_migration_guard_detects_already_encrypted_values():
    """Re-running the migration must not double-encrypt."""
    def already_encrypted(v): return bool(v) and decrypt_data(v) != v

    assert already_encrypted(encrypt_data("Metformin")) is True
    assert already_encrypted("Metformin") is False
    assert already_encrypted("Plan: review in 6 weeks") is False
    assert already_encrypted("") is False


@pytest.mark.parametrize("value", ["", None])
def test_empty_values_are_left_alone(value):
    """Optional clinical fields stay NULL rather than becoming ciphertext of
    an empty string, so 'not recorded' stays distinguishable from 'blank'."""
    from app.main import _enc, _dec
    assert _enc(value) == value
    assert _dec(value) == value


def test_encrypted_field_lists_cover_content_but_not_keys_or_dates():
    """Dates and foreign keys must stay readable: every ORDER BY and JOIN
    depends on them, and nothing sorts or filters on the clinical text."""
    from app.main import DIAGNOSIS_ENCRYPTED_FIELDS, PRESCRIPTION_ENCRYPTED_FIELDS

    for f in ("id", "patient_id", "doctor_id", "visit_date", "created_at"):
        assert f not in DIAGNOSIS_ENCRYPTED_FIELDS
    for f in ("id", "patient_id", "doctor_id", "prescribed_date"):
        assert f not in PRESCRIPTION_ENCRYPTED_FIELDS

    assert "title" in DIAGNOSIS_ENCRYPTED_FIELDS
    assert "symptoms" in DIAGNOSIS_ENCRYPTED_FIELDS
    assert "medicine_name" in PRESCRIPTION_ENCRYPTED_FIELDS
    assert "dosage" in PRESCRIPTION_ENCRYPTED_FIELDS
