"""Doctor access requests, and the authorization they are supposed to enforce.

The point of every test here is the *refusal*. An access-request feature that
records a decision without acting on it is theatre, and that is exactly what
was found: the patient chart computed a relationship check and then discarded
the result with `pass`, so any doctor could open any patient's record.
"""

import pytest
from pydantic import ValidationError

from app.schemas import CreateAccessRequest, AccessRequestDecision


def test_purpose_is_required():
    """The patient reads the purpose to decide. No purpose, no decision."""
    with pytest.raises(ValidationError):
        CreateAccessRequest(patient_id="00000000-0000-0000-0000-000000000000")


@pytest.mark.parametrize("weak", ["", "   ", "urgent", "need it", "pls", "access"])
def test_throwaway_purposes_are_rejected(weak):
    """Consent given on no information is not informed consent."""
    with pytest.raises(ValidationError):
        CreateAccessRequest(
            patient_id="00000000-0000-0000-0000-000000000000", purpose=weak
        )


def test_a_clinical_purpose_is_accepted():
    req = CreateAccessRequest(
        patient_id="00000000-0000-0000-0000-000000000000",
        purpose="Reviewing prior cardiac history before a scheduled procedure.",
    )
    assert req.requested_resource == "Full medical record"


def test_purpose_whitespace_is_normalised():
    """Padding must not be a way past the minimum length."""
    with pytest.raises(ValidationError):
        CreateAccessRequest(
            patient_id="00000000-0000-0000-0000-000000000000",
            purpose="   urgent      ",
        )


def test_decision_note_is_optional():
    assert AccessRequestDecision().note is None


def test_decision_note_is_bounded():
    with pytest.raises(ValidationError):
        AccessRequestDecision(note="x" * 501)


def test_rejected_consent_blocks_reads_in_the_predicate():
    """A rejection must block exactly as a revocation does.

    Regression guard: the SQL predicate originally matched only 'Revoked', so a
    patient who declined a request was still readable by that doctor.
    """
    from app.main import _CONSENT_REVOKED
    assert "'Revoked'" in _CONSENT_REVOKED and "'Rejected'" in _CONSENT_REVOKED


def test_chart_authorization_is_actually_enforced():
    """The discarded-result bug must not come back.

    The old handler ran a relationship query and then `pass`ed on the result.
    Any reintroduction of that pattern means an unrelated doctor can read a
    full chart, so the source itself is asserted on.
    """
    import inspect
    from app.main import get_doctor_patient_detail
    src = inspect.getsource(get_doctor_patient_detail)
    assert "_doctor_patient_authorization" in src
    assert "status_code=403" in src
    assert "let's allow it" not in src
