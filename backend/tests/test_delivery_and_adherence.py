"""Reads that had no reader, and the authorization on the ones that did.

Two records were being produced correctly and delivered to nobody: imaging
studies, which only the uploading technician could open, and medication rounds,
which no endpoint returned at all. Both are covered here, along with the
scoping that decides who may see them.
"""

import inspect

from app.main import (
    _imaging_summary, _adherence_summary, _adherence_record,
    get_patient_imaging, get_doctor_imaging, get_doctor_imaging_image,
    get_patient_adherence, review_lab_report,
)


# ─── Imaging must never leak the payload into a list ─────────────────────────

def test_imaging_summary_excludes_the_image():
    """Listing studies must not decrypt them.

    Decrypting every study to render a list is both wasteful and needless
    exposure, so the summary carries a flag rather than the bytes.
    """
    row = {
        "id": "x", "encrypted_image": "CIPHERTEXT", "image_data": None,
        "scan_region": "Chest", "exam_type": "X-Ray",
        "signature_algorithm": "ML-DSA-65",
    }
    out = _imaging_summary(row)
    assert out["has_image"] is True
    assert "image_data" not in out
    assert "encrypted_image" not in out
    assert "encrypted_aes_key" not in out


def test_imaging_summary_reports_no_image_honestly():
    out = _imaging_summary({"id": "x", "encrypted_image": None, "image_data": None})
    assert out["has_image"] is False


# ─── Imaging authorization ───────────────────────────────────────────────────

def test_patient_imaging_is_scoped_to_the_owner():
    """A patient reaching another patient's study is the classic IDOR."""
    src = inspect.getsource(get_patient_imaging)
    assert "ir.patient_id = %s" in src


def test_doctor_imaging_uses_the_same_test_as_the_chart():
    """A doctor must not reach a scan for a patient whose chart they cannot open."""
    for fn in (get_doctor_imaging, get_doctor_imaging_image):
        src = inspect.getsource(fn)
        assert "_doctor_patient_authorization" in src
        assert "status_code=403" in src


def test_doctor_imaging_list_excludes_revoked_patients():
    src = inspect.getsource(get_doctor_imaging)
    assert "'Revoked', 'Rejected'" in src


# ─── Adherence ───────────────────────────────────────────────────────────────

def _rounds(**counts):
    out = []
    for status, n in counts.items():
        out += [{"status": status.capitalize()} for _ in range(n)]
    return out


def test_adherence_counts_every_outcome():
    s = _adherence_summary(_rounds(administered=7, refused=2, held=1, missed=3))
    assert s["total_rounds"] == 13
    assert (s["administered"], s["refused"], s["held"], s["missed"]) == (7, 2, 1, 3)


def test_refusals_are_surfaced_not_buried_in_a_percentage():
    """A 90% adherence rate reads as fine while hiding that every missing dose
    was an active refusal. Refusals get their own signal."""
    s = _adherence_summary(_rounds(administered=9, refused=1))
    assert s["adherence_percent"] == 90.0
    assert s["needs_attention"] is True


def test_full_adherence_needs_no_attention():
    s = _adherence_summary(_rounds(administered=6))
    assert s["adherence_percent"] == 100.0
    assert s["needs_attention"] is False


def test_held_doses_alone_do_not_raise_attention():
    """A held dose is a clinical decision, not a compliance failure."""
    s = _adherence_summary(_rounds(administered=8, held=2))
    assert s["needs_attention"] is False


def test_adherence_handles_no_rounds():
    s = _adherence_summary([])
    assert s["total_rounds"] == 0 and s["adherence_percent"] is None


def test_adherence_decrypts_the_medicine():
    """Prescriptions are encrypted at column level, so a raw read would show
    ciphertext where the drug name belongs."""
    src = inspect.getsource(_adherence_record)
    assert "_dec(r.get(\"medicine_name\"))" in src


def test_patient_adherence_is_scoped_to_self():
    src = inspect.getsource(get_patient_adherence)
    assert 'session["user_id"]' in src


# ─── Report review ───────────────────────────────────────────────────────────

def test_review_is_scoped_and_notifies():
    """The update previously matched on report id alone, so any doctor could
    mark any report in the system reviewed — for patients they had never met."""
    src = inspect.getsource(review_lab_report)
    assert "_doctor_may_read_report" in src
    assert "REPORT_REVIEWED" in src
    assert "WHERE id = %s\", (report_id,))" not in src.replace("\n", "")
