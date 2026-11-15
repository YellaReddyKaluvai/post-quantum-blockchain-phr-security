"""Regression checks for completion workflows."""

import base64
import io
import json
import os
import zipfile
from datetime import date, time, timedelta
import pytest
from pydantic import ValidationError
from app.attachments import Attachment, envelope
from app.appointments import Schedule, WorkingDay, fits_schedule
from app.schemas import CreateDocumentRequest


def test_schedule_hours_grid_leave_duration():
    s = Schedule(
        duration_minutes=45,
        days=[WorkingDay(weekday=0, start="09:00", end="12:00")],
        leave_dates=[date(2030, 1, 14)],
    )
    assert fits_schedule(s, date(2030, 1, 7), time(9, 45))
    for day, clock in [
        (date(2030, 1, 7), time(9, 30)),
        (date(2030, 1, 7), time(11, 45)),
        (date(2030, 1, 8), time(9)),
        (date(2030, 1, 14), time(9)),
    ]:
        assert not fits_schedule(s, day, clock)
    assert not fits_schedule(s, date(2030, 1, 7), time(11, 15), duration=60)
    with pytest.raises(ValidationError):
        Schedule(days=s.days * 2)
    with pytest.raises(ValidationError):
        WorkingDay(weekday=0, start="17:00", end="09:00")


def test_pdf_envelope_roundtrip_and_invalid_files():
    raw = b"%PDF-1.7\nfixture"
    a = Attachment(filename="report.pdf", data_base64=base64.b64encode(raw).decode())
    assert base64.b64decode(json.loads(envelope(a))["data_base64"]) == raw
    assert CreateDocumentRequest(
        patient_id="x", document_name="Report", document_type="Other", attachment=a
    ).content == envelope(a)
    with pytest.raises(ValidationError):
        CreateDocumentRequest(
            patient_id="x",
            document_name="Report",
            document_type="Other",
            attachment=a,
            content="ambiguous",
        )
    for filename, data in [
        ("../report.pdf", a.data_base64),
        ("report.pdf", base64.b64encode(b"<script>x</script>").decode()),
        ("report.pdf", "!invalid"),
    ]:
        with pytest.raises(ValueError):
            envelope(Attachment(filename=filename, data_base64=data))


def test_docx_rejects_macro_and_traversal():
    for extra in ("", "word/vbaProject.bin", "../outside"):
        f = io.BytesIO()
        with zipfile.ZipFile(f, "w") as z:
            for path in ["[Content_Types].xml", "word/document.xml"] + (
                [extra] if extra else []
            ):
                z.writestr(path, b"test")
        a = Attachment(
            filename="report.docx", data_base64=base64.b64encode(f.getvalue()).decode()
        )
        if extra:
            with pytest.raises(ValueError):
                envelope(a)
        else:
            assert json.loads(envelope(a))["mime"].endswith("document")


def test_refresh_cookie_attributes(monkeypatch):
    from fastapi import Response
    from types import SimpleNamespace
    from app import account_completion as c

    monkeypatch.setattr(
        c,
        "get_settings",
        lambda: SimpleNamespace(
            SESSION_COOKIE_SAMESITE="none", SESSION_COOKIE_SECURE=False
        ),
    )
    r = Response()
    c.cookie(r, c.REFRESH_COOKIE, "synthetic", 60)
    assert all(
        x in r.headers["set-cookie"] for x in ["HttpOnly", "Secure", "SameSite=none"]
    )


from test_completed_workflows import live

LIVE = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1", reason="requires PostgreSQL/liboqs"
)


@LIVE
def test_refresh_rotation_and_replay(live):
    from fastapi.testclient import TestClient
    from app.main import app
    from test_completed_workflows import PASSWORD

    _, db, people = live
    p = people["Patient"]
    with TestClient(app) as browser:
        r = browser.post(
            "/api/login", json={"user_id": p["user_id"], "password": PASSWORD}
        )
        assert r.status_code == 200, r.text
        old = browser.cookies.get("quantumcare_refresh")
        assert old
        assert browser.post("/api/auth/refresh").status_code == 403
        r = browser.post(
            "/api/auth/refresh", headers={"X-Requested-With": "QuantumCare"}
        )
        assert r.status_code == 200, r.text
        assert browser.cookies.get("quantumcare_refresh") != old
        assert (
            browser.post(
                "/api/auth/refresh",
                headers={
                    "X-Requested-With": "QuantumCare",
                    "Cookie": "quantumcare_refresh=" + old,
                },
            ).status_code
            == 401
        )
        assert browser.get("/api/auth/me").status_code == 401


@LIVE
def test_email_verification_one_time(live):
    from app.account_security import token_digest
    from test_completed_workflows import PASSWORD

    client, db, people = live
    p = people["Patient"]
    token = "verification-test-" + os.urandom(20).hex()
    db.execute(
        "UPDATE Users SET email_verification_required=TRUE,email_verified_at=NULL WHERE id=%s",
        (p["id"],),
    )
    db.execute(
        "INSERT INTO EmailVerificationTokens VALUES (%s,%s,NOW()+INTERVAL '1 hour')",
        (token_digest(token), p["id"]),
    )
    try:
        assert (
            client.post(
                "/api/login", json={"user_id": p["user_id"], "password": PASSWORD}
            ).status_code
            == 403
        )
        assert (
            client.post("/api/auth/email/verify", json={"token": token}).status_code
            == 200
        )
        assert (
            client.post("/api/auth/email/verify", json={"token": token}).status_code
            == 400
        )
        assert (
            client.post(
                "/api/login", json={"user_id": p["user_id"], "password": PASSWORD}
            ).status_code
            == 200
        )
    finally:
        db.execute(
            "UPDATE Users SET email_verification_required=FALSE WHERE id=%s", (p["id"],)
        )


@LIVE
def test_booking_enforces_doctor_schedule(live):
    client, db, people = live
    d = people["Doctor"]
    p = people["Patient"]
    day = date.today() + timedelta(days=50)
    body = {
        "days": [{"weekday": day.weekday(), "start": "10:00", "end": "12:00"}],
        "duration_minutes": 60,
        "leave_dates": [],
    }
    assert (
        client.put("/api/doctor/schedule", headers=d["headers"], json=body).status_code
        == 200
    )
    slots = client.get(
        f"/api/patient/doctors/{d['id']}/slots",
        params={"day": str(day)},
        headers=p["headers"],
    ).json()
    assert slots["slots"] == ["10:00", "11:00"]
    request = {
        "doctor_id": str(d["id"]),
        "department": "General",
        "appointment_date": str(day),
        "appointment_time": "09:00",
        "notes": "",
    }
    assert (
        client.post(
            "/api/patient/appointments", headers=p["headers"], json=request
        ).status_code
        == 409
    )
    request["appointment_time"] = "10:00"
    r = client.post("/api/patient/appointments", headers=p["headers"], json=request)
    assert r.status_code == 200, r.text
    body["leave_dates"] = [str(day)]
    assert (
        client.put("/api/doctor/schedule", headers=d["headers"], json=body).status_code
        == 409
    )


@LIVE
def test_attachment_migration_preserves_payload_and_signature(live):
    from test_completed_workflows import PASSWORD

    client, db, people = live
    p = people["Patient"]
    d = people["Doctor"]
    db.execute(
        "INSERT INTO Consent (patient_id,subject_user_id,subject_role) VALUES (%s,%s,'Doctor') ON CONFLICT DO NOTHING",
        (p["id"], d["id"]),
    )
    attachment = {
        "filename": "referral.pdf",
        "data_base64": base64.b64encode(b"%PDF-1.7\nSynthetic").decode(),
    }
    r = client.post(
        "/api/doctor/documents",
        headers=d["headers"],
        json={
            "patient_id": str(p["id"]),
            "document_name": "Attachment",
            "document_type": "Other",
            "attachment": attachment,
        },
    )
    assert r.status_code == 200, r.text
    ident = r.json()["document_id"]
    read = f"/api/patient/documents/{ident}/content"
    old = db.execute(
        "SELECT recipient_key_version,document_hash,digital_signature,encrypted_content FROM MedicalDocuments WHERE id=%s",
        (ident,),
    ).fetchone()
    assert (
        client.post(
            "/api/auth/keys/rotate", headers=p["headers"], json={"password": PASSWORD}
        ).status_code
        == 200
    )
    r = client.post(
        "/api/auth/keys/migrate-records",
        headers=p["headers"],
        json={"password": PASSWORD, "version": old["recipient_key_version"]},
    )
    assert r.status_code == 200, r.text
    new = db.execute(
        "SELECT recipient_key_version,document_hash,digital_signature,encrypted_content FROM MedicalDocuments WHERE id=%s",
        (ident,),
    ).fetchone()
    assert (
        new["recipient_key_version"] > old["recipient_key_version"]
        and new["encrypted_content"] != old["encrypted_content"]
    )
    assert (
        new["document_hash"] == old["document_hash"]
        and new["digital_signature"] == old["digital_signature"]
    )
    assert (
        client.post(
            "/api/auth/keys/revoke",
            headers=p["headers"],
            json={"password": PASSWORD, "version": old["recipient_key_version"]},
        ).status_code
        == 200
    )
    result = client.get(read, headers=p["headers"])
    assert result.status_code == 200, result.text
    assert (
        json.loads(result.json()["content"])["data_base64"] == attachment["data_base64"]
    )


@LIVE
def test_mfa_recovery_requires_two_admins_and_one_time_link(live, monkeypatch):
    import uuid
    from app import account_completion as completion
    from app.security import encrypt_data, hash_password
    from app.account_security import token_digest
    from test_completed_workflows import PASSWORD

    client, db, people = live
    p = people["Patient"]
    admins = []
    # Synthetic MFA factors for disposable administrators; each code can be consumed once.
    for _ in range(2):
        uid = uuid.uuid4().hex[:10]
        row = db.execute(
            "INSERT INTO Users (user_id,full_name,email,password_hash,role,gender,date_of_birth_encrypted,status,mfa_secret_encrypted) VALUES (%s,'Recovery Admin',%s,%s,'Administrator','Other',%s,'Approved',%s) RETURNING id",
            (
                uid,
                uid + "@example.com",
                hash_password(PASSWORD),
                encrypt_data("1980-01-01"),
                encrypt_data("JBSWY3DPEHPK3PXP"),
            ),
        ).fetchone()
        codes = [uuid.uuid4().hex for i in range(5)]
        for code in codes:
            db.execute(
                "INSERT INTO MfaRecoveryCodes VALUES (%s,%s)",
                (row["id"], token_digest(code)),
            )
        login = client.post(
            "/api/login", json={"user_id": uid, "password": PASSWORD, "otp": codes[0]}
        )
        assert login.status_code == 200, login.text
        admins.append(
            (
                row["id"],
                {"Authorization": "Bearer " + login.json()["access_token"]},
                codes,
            )
        )
    db.execute(
        "UPDATE Users SET mfa_secret_encrypted=%s WHERE id=%s",
        (encrypt_data("JBSWY3DPEHPK3PXP"), p["id"]),
    )
    delivered = []
    monkeypatch.setattr(
        completion, "send_link", lambda address, token, *args: delivered.append(token)
    )
    a, b = admins
    result = client.post(
        "/api/auth/admin/mfa-recovery",
        headers=a[1],
        json={
            "password": PASSWORD,
            "otp": a[2][1],
            "user_id": str(p["id"]),
            "evidence_reference": "Synthetic identity case 001",
        },
    )
    assert result.status_code == 200, result.text
    case = result.json()["id"]
    assert (
        client.post(
            f"/api/auth/admin/mfa-recovery/{case}/approve",
            headers=a[1],
            json={"password": PASSWORD, "otp": a[2][2]},
        ).status_code
        == 403
    )
    result = client.post(
        f"/api/auth/admin/mfa-recovery/{case}/approve",
        headers=b[1],
        json={"password": PASSWORD, "otp": b[2][1]},
    )
    assert result.status_code == 200, result.text
    assert len(delivered) == 1
    result = client.post(
        "/api/auth/mfa/recover",
        json={"token": delivered[0], "new_password": "Recovered-Test-Password-123!"},
    )
    assert result.status_code == 200, result.text
    assert (
        client.post(
            "/api/auth/mfa/recover",
            json={
                "token": delivered[0],
                "new_password": "Recovered-Test-Password-123!",
            },
        ).status_code
        == 400
    )
    assert client.get("/api/auth/me", headers=p["headers"]).status_code == 401
    assert (
        db.execute(
            "SELECT mfa_secret_encrypted FROM Users WHERE id=%s", (p["id"],)
        ).fetchone()["mfa_secret_encrypted"]
        is None
    )
