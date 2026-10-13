"""The core flow, end to end, against a real database and real liboqs (spec §37).

Doctor → access request → patient approval → authorized access → lab request →
technician → secure report upload → storage → patient notification → patient
report access → AI/security monitoring → audit and incident handling.

Every other test in this suite exercises pure functions. This one drives the
real API through FastAPI's TestClient, with real ML-KEM-768 / ML-DSA-65 keys,
real AES-256-GCM ciphertext and a real Postgres schema — so it is the test that
says whether the parts are actually connected.

It needs a disposable database and liboqs, so it is opt-in:

    RUN_E2E=1 DATABASE_URL=postgresql://… python -m pytest tests/test_e2e_flow.py

CI runs it inside the backend Docker image (which builds liboqs) against a
Postgres service container. Without RUN_E2E it is skipped, never faked.
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1",
    reason="end-to-end flow needs RUN_E2E=1, a disposable DATABASE_URL and liboqs")

PASSWORD = "Str0ng-E2E-pass!"
# CI runs the flow a second time against a local anvil chain with PHR.sol
# deployed; these checks only make sense when a chain is really there.
ON_CHAIN = os.getenv("BLOCKCHAIN_ENABLED", "false").lower() == "true"


@pytest.fixture(scope="module")
def env():
    # Keep the run hermetic: no scheduled analysis, no chain, no hub.
    os.environ["SECURITY_ANALYSIS_INTERVAL_MINUTES"] = "0"
    os.environ.setdefault("BLOCKCHAIN_ENABLED", "false")
    from app.crypto_service import pqc_available
    if not pqc_available():
        pytest.skip("liboqs is not available; the flow cannot be run without real PQC")

    import psycopg
    from psycopg.rows import dict_row
    from fastapi.testclient import TestClient
    from app.main import app
    from app.security import hash_password, encrypt_data

    with TestClient(app) as client:          # runs startup: init.sql against the database
        db = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, autocommit=True)
        tag = uuid.uuid4().hex[:8]
        admin_id = f"ADM-E2E-{tag[:6]}"
        db.execute(
            """INSERT INTO Users (user_id, full_name, email, password_hash, role, gender,
                                  date_of_birth_encrypted, status)
               VALUES (%s, 'E2E Administrator', %s, %s, 'Administrator', 'Other', %s, 'Approved')""",
            (admin_id, f"admin-{tag}@e2e.example.com", hash_password(PASSWORD), encrypt_data("1980-01-01")))
        yield {"client": client, "db": db, "tag": tag, "admin_id": admin_id}
        db.close()


def _login(client, user_id, password=PASSWORD):
    r = client.post("/api/login", json={"user_id": user_id, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _register_and_approve(env, role, admin_headers, **extra):
    client, tag = env["client"], env["tag"]
    email = f"{role.lower().replace(' ', '')}-{tag}@e2e.example.com"
    body = {"full_name": f"E2E {role}", "email": email, "password": PASSWORD,
            "confirm_password": PASSWORD, "role": role, "gender": "Other",
            "date_of_birth": "1990-05-05", **extra}
    r = client.post("/api/register", json=body)
    assert r.status_code == 200, r.text
    pending = client.get("/api/admin/registrations/pending", headers=admin_headers).json()
    uid = next(p["id"] for p in pending if p["email"] == email)
    r = client.post(f"/api/admin/registrations/{uid}/approve", headers=admin_headers)
    assert r.status_code == 200, r.text
    return uid, r.json()["user_id"]


@pytest.fixture(scope="module")
def people(env):
    admin = _login(env["client"], env["admin_id"])
    patient_uuid, patient_pub = _register_and_approve(env, "Patient", admin, blood_group="O+")
    doctor_uuid, doctor_pub = _register_and_approve(env, "Doctor", admin,
                                                    specialization="Cardiology")
    _, tech_pub = _register_and_approve(env, "Lab Technician", admin)
    _, nurse_pub = _register_and_approve(env, "Nurse", admin)
    return {
        "admin": admin,
        "patient": _login(env["client"], patient_pub), "patient_uuid": patient_uuid,
        "patient_pub": patient_pub, "patient_email": f"patient-{env['tag']}@e2e.example.com",
        "doctor": _login(env["client"], doctor_pub), "doctor_uuid": doctor_uuid,
        "tech": _login(env["client"], tech_pub),
        "nurse": _login(env["client"], nurse_pub), "nurse_pub": nurse_pub,
    }


def _events(env, event_type, actor=None):
    q = "SELECT COUNT(*) AS n FROM SecurityEvents WHERE event_type = %s"
    args = [event_type]
    if actor:
        q += " AND actor_id = %s"
        args.append(actor)
    return env["db"].execute(q, args).fetchone()["n"]


def _patient_notices(c, headers):
    return {n["notification_type"] for n in c.get("/api/patient/notifications", headers=headers).json()}


def test_the_core_flow(env, people):
    c, db = env["client"], env["db"]
    P, D, T, A = people["patient"], people["doctor"], people["tech"], people["admin"]
    N = people["nurse"]
    pid, did = people["patient_uuid"], people["doctor_uuid"]

    # ── 1–2. Without a relationship or consent, the doctor gets nothing ──────
    assert c.get(f"/api/doctor/patients/{pid}", headers=D).status_code == 403
    r = c.post("/api/doctor/requests", headers=D,
               json={"patient_id": pid, "panel_code": "CBC", "clinical_notes": "Anaemia work-up"})
    assert r.status_code == 403, "ordering a test must not bypass consent"
    assert _events(env, "ACCESS_DENIED", did) >= 2

    # ── 3–5. Access request → patient notified → approval ────────────────────
    r = c.post("/api/doctor/access-requests", headers=D, json={
        "patient_id": pid, "purpose": "Reviewing your cardiac history before a planned procedure."})
    assert r.status_code == 200, r.text
    request_id = r.json()["request_id"]
    notes = c.get("/api/patient/notifications", headers=P).json()
    assert any(n["notification_type"] == "ACCESS_REQUEST" for n in notes)
    pending = c.get("/api/patient/access-requests", headers=P).json()
    assert any(x["request_id"] == request_id and x["status"] == "Pending" for x in pending)
    r = c.post(f"/api/patient/access-requests/{request_id}/approve", headers=P, json={})
    assert r.status_code == 200, r.text
    if ON_CHAIN:
        assert r.json()["consent_ledger"]["recorded_on"] == "ethereum"

    # ── 6–7. The backend now allows it — and only now ────────────────────────
    r = c.get(f"/api/doctor/patients/{pid}", headers=D)
    assert r.status_code == 200, r.text
    assert _events(env, "RECORD_ACCESS", did) >= 1

    # ── Nursing access is a care-team relationship, delegated by the doctor ──
    assert c.get(f"/api/nurse/patients/{pid}", headers=N).status_code == 403
    assert c.get("/api/nurse/patients/search?q=E2E", headers=N).json() == []
    r = c.post(f"/api/doctor/patients/{pid}/care-team", headers=D, json={
        "nurse_id": people["nurse_pub"], "reason": "Post-procedure observations overnight",
        "duration_hours": 24})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/nurse/patients/{pid}", headers=N).status_code == 200
    assert c.post(f"/api/nurse/patients/{pid}/vitals", headers=N,
                  json={"heart_rate": 72, "spo2": 98}).status_code == 200
    assert any(p["id"] == pid for p in c.get("/api/nurse/patients", headers=N).json())
    team = c.get("/api/patient/care-team", headers=P).json()
    assert [m["nurse_user_id"] for m in team] == [people["nurse_pub"]]
    # The admin's review list leaves out a pair that already has an assignment.
    r = c.get("/api/admin/care-team/suggestions", headers=A)
    assert r.status_code == 200
    assert not any(s["patient_id"] == pid and s["nurse_user_id"] == people["nurse_pub"] for s in r.json())

    # ── 8–9. Lab request reaches the laboratory ──────────────────────────────
    r = c.post("/api/doctor/requests", headers=D,
               json={"patient_id": pid, "panel_code": "CBC", "clinical_notes": "Anaemia work-up"})
    assert r.status_code == 200, r.text
    lab_request_id = r.json()["request_id"]
    queue = c.get("/api/lab-tech/requests", headers=T).json()
    assert any(q["id"] == lab_request_id for q in queue)
    assert c.post(f"/api/lab-tech/requests/{lab_request_id}/status", headers=T,
                  json={"status": "Accepted"}).status_code == 200

    # A different investigation cannot be filed against this order.
    r = c.post("/api/lab-tech/reports/create", headers=T, json={
        "request_id": lab_request_id, "panel_code": "LFT", "values": {"sgpt": 30}})
    assert r.status_code == 409

    # ── 10–13. Report upload through the security pipeline ───────────────────
    r = c.post("/api/lab-tech/reports/create", headers=T, json={
        "request_id": lab_request_id, "panel_code": "CBC",
        "values": {"hemoglobin": 13.2, "rbc_count": 4.6, "hematocrit": 40.1,
                   "wbc_count": 7.1, "platelet_count": 245}})
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["patient_user_id"] and report["signature_algorithm"] == "ML-DSA-65"
    assert report["kem_algorithm"] == "ML-KEM-768" and len(report["document_hash"]) == 64
    row = db.execute("SELECT patient_id, encrypted_document, digital_signature FROM LabReports "
                     "WHERE id = %s", (report["report_id"],)).fetchone()
    assert str(row["patient_id"]) == pid                       # bound to the right patient
    assert row["encrypted_document"] and row["digital_signature"]
    assert b"%PDF" not in row["encrypted_document"].encode()   # only ciphertext at rest
    if ON_CHAIN:
        assert report["anchored_on"] != "local-simulated" and report["blockchain_tx_hash"]
    if os.getenv("AWS_S3_ENDPOINT_URL"):
        # The cloud copy is exactly the ciphertext, and it is a real recovery
        # path: with the database copy gone the report is still released, and
        # still has to pass its integrity and signature checks to be.
        from app.storage_service import download_file_from_s3
        assert report["s3_key"]
        assert download_file_from_s3(report["s3_key"]) == row["encrypted_document"].encode("utf-8")
        db.execute("UPDATE LabReports SET encrypted_document = NULL WHERE id = %s", (report["report_id"],))
        r = c.get(f"/api/patient/lab-reports/{report['report_id']}/download", headers=P)
        assert r.status_code == 200 and r.content.startswith(b"%PDF")
        db.execute("UPDATE LabReports SET encrypted_document = %s WHERE id = %s",
                   (row["encrypted_document"], report["report_id"]))
    if os.getenv("IPFS_API_URL"):
        # What IPFS holds is exactly the ciphertext — never the report itself.
        from app.storage_service import fetch_from_ipfs
        assert fetch_from_ipfs(report["ipfs_cid"]) == row["encrypted_document"].encode("utf-8")
    assert _events(env, "LAB_REPORT_UPLOADED") >= 1

    # ── 14. Patient notified ─────────────────────────────────────────────────
    notes = c.get("/api/patient/notifications", headers=P).json()
    assert any(n["notification_type"] == "REPORT_READY" for n in notes)

    # ── 15–17. Patient opens it: decrypted, digest and signature verified ────
    r = c.get(f"/api/patient/lab-reports/{report['report_id']}/download", headers=P)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    v = c.get(f"/api/patient/lab-reports/{report['report_id']}/verify", headers=P).json()
    assert v["hash_matches"] is True and v["signature_valid"] is True
    if ON_CHAIN:
        assert v["blockchain_verified"] is True        # digest read back from the contract
    assert c.get(f"/api/doctor/reports/{report['report_id']}/download", headers=D).status_code == 200

    # ── Integrity: a changed digest is withheld and becomes an incident ──────
    original = db.execute("SELECT document_hash FROM LabReports WHERE id = %s",
                          (report["report_id"],)).fetchone()["document_hash"]
    db.execute("UPDATE LabReports SET document_hash = %s WHERE id = %s",
               ("0" * 64, report["report_id"]))
    r = c.get(f"/api/patient/lab-reports/{report['report_id']}/download", headers=P)
    assert r.status_code == 409
    assert db.execute("SELECT COUNT(*) AS n FROM SecurityIncidents "
                      "WHERE event_type = 'INTEGRITY_FAILURE' AND status = 'Open'").fetchone()["n"] >= 1
    assert "SECURITY_RECORD_WITHHELD" in _patient_notices(c, P)     # §27: the patient is told
    db.execute("UPDATE LabReports SET document_hash = %s WHERE id = %s",
               (original, report["report_id"]))

    # ── Withdrawal really blocks, and probing it raises an alert ─────────────
    assert c.post(f"/api/patient/consent/{did}/revoke", headers=P, json={}).status_code == 200
    for _ in range(3):
        assert c.get(f"/api/doctor/patients/{pid}", headers=D).status_code == 403
    assert db.execute("SELECT COUNT(*) AS n FROM SecurityAlerts WHERE source = 'ACCESS_CONTROL' "
                      "AND actor_id = %s", (did,)).fetchone()["n"] >= 1
    assert "SECURITY_ACCESS_REFUSED" in _patient_notices(c, P)
    # …and the nurse that doctor brought in loses access with them.
    assert c.get(f"/api/nurse/patients/{pid}", headers=N).status_code == 403

    # Asking again does not lift the withdrawal: it stands until the patient decides.
    r = c.post("/api/doctor/access-requests", headers=D, json={
        "patient_id": pid, "purpose": "Requesting renewed access for post-procedure follow-up."})
    assert r.status_code == 200, r.text
    assert c.get(f"/api/doctor/patients/{pid}", headers=D).status_code == 403

    if ON_CHAIN:
        # Someone with SQL access restores the doctor's consent behind the
        # application's back. The contract still records the withdrawal.
        db.execute("UPDATE Consent SET status = 'Authorized', prior_refusal = FALSE "
                   "WHERE patient_id = %s AND subject_user_id = %s", (pid, did))
        assert c.get(f"/api/doctor/patients/{pid}", headers=D).status_code == 403
        assert db.execute("SELECT COUNT(*) AS n FROM SecurityIncidents "
                          "WHERE event_type = 'CONSENT_LEDGER_MISMATCH'").fetchone()["n"] >= 1
        assert "SECURITY_CONSENT_ALTERED" in _patient_notices(c, P)
        db.execute("UPDATE Consent SET status = 'Pending', prior_refusal = TRUE "
                   "WHERE patient_id = %s AND subject_user_id = %s", (pid, did))

    # ── Emergency access: identity-verified, recorded, reviewed ──────────────
    r = c.post("/api/doctor/emergency-access", headers=D, json={
        "patient_id": pid, "reason": "Patient unresponsive in A&E; cardiac history needed now.",
        "duration_hours": 1, "password": "wrong-password"})
    assert r.status_code == 403
    r = c.post("/api/doctor/emergency-access", headers=D, json={
        "patient_id": pid, "reason": "Patient unresponsive in A&E; cardiac history needed now.",
        "duration_hours": 1, "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert r.json()["incident_ref"].startswith("INC-")
    if ON_CHAIN:
        assert r.json()["contract_tx_hash"]          # PHR.sol emergencyAccess()
    assert c.get(f"/api/doctor/patients/{pid}", headers=D).status_code == 200
    notes = c.get("/api/patient/notifications", headers=P).json()
    assert any(n["notification_type"] == "EMERGENCY_ACCESS" for n in notes)
    # Break-glass is personal: it does not reopen the chart to the nurse.
    assert c.get(f"/api/nurse/patients/{pid}", headers=N).status_code == 403

    # ── AI / security monitoring and incident handling ───────────────────────
    for event in ("LOGIN_SUCCESS", "RECORD_ACCESS", "CONSENT_EVENT", "EMERGENCY_ACCESS",
                  "ACCESS_DENIED", "LAB_REQUEST_CREATED", "LAB_REPORT_UPLOADED"):
        assert _events(env, event) >= 1, event
    assert c.post("/api/admin/security/analyze", headers=A).status_code == 200
    incidents = c.get("/api/admin/security/incidents", headers=A).json()["incidents"]
    kinds = {i["event_type"] for i in incidents}
    assert {"EMERGENCY_ACCESS", "INTEGRITY_FAILURE"} <= kinds
    target = next(i for i in incidents if i["event_type"] == "EMERGENCY_ACCESS" and i["status"] == "Open")
    r = c.post(f"/api/admin/security/incidents/{target['id']}", headers=A,
               json={"status": "Closed", "resolution": "Reviewed in E2E: genuine emergency.",
                     "verdict": "false_positive"})
    assert r.status_code == 200
    # The investigator's verdict becomes a training label for the federated classifier.
    assert r.json()["training_label"] == "benign"
    assert db.execute("SELECT label FROM SecurityLabels WHERE source_ref = %s",
                      (target["id"],)).fetchone()["label"] == 0
    assert c.get("/api/admin/security/policy", headers=A).status_code == 200

    # ── Audit trail ──────────────────────────────────────────────────────────
    actions = {r["action"] for r in db.execute("SELECT DISTINCT action FROM AdminAuditLogs").fetchall()}
    assert {"ACCESS_APPROVED", "LAB_TEST_REQUESTED", "LAB_REPORT_FINALIZED",
            "CONSENT_REVOKED", "EMERGENCY_ACCESS_DECLARED", "CARE_TEAM_ASSIGNED"} <= actions


def test_failed_sign_ins_reach_the_detector_and_alert(env, people):
    c, db = env["client"], env["db"]
    public_id = c.get("/api/auth/me", headers=people["doctor"]).json()["public_user_id"]
    for _ in range(5):
        assert c.post("/api/login", json={"user_id": public_id, "password": "nope"}).status_code == 401
    assert db.execute("SELECT COUNT(*) AS n FROM SecurityAlerts WHERE title LIKE %s",
                      (f"Repeated failed sign-ins — {public_id}%",)).fetchone()["n"] >= 1


@pytest.mark.skipif(not os.getenv("MAILPIT_API_URL"), reason="no mail server to read back from")
def test_the_approval_email_reaches_the_patient(env, people):
    """Delivered through a real SMTP exchange and read back from the mail server —
    not the application's own record that it sent something."""
    import json
    import urllib.parse
    import urllib.request
    api = os.environ["MAILPIT_API_URL"].rstrip("/")
    query = urllib.parse.quote(f'to:"{people["patient_email"]}"')
    with urllib.request.urlopen(f"{api}/api/v1/search?query={query}", timeout=10) as r:
        messages = json.loads(r.read())["messages"]
    approval = next(m for m in messages if "Approved" in m["Subject"])
    with urllib.request.urlopen(f"{api}/api/v1/message/{approval['ID']}", timeout=10) as r:
        body = json.loads(r.read())["Text"]
    assert people["patient_pub"] in body                 # the generated User ID, to the right person
    sent = env["db"].execute(
        "SELECT sent_status FROM EmailNotifications WHERE email_address = %s AND notification_type = 'APPROVAL'",
        (people["patient_email"],)).fetchone()
    assert sent["sent_status"] == "SENT"


def test_a_browser_session_is_an_httponly_cookie_and_ends_at_logout(env, people):
    """The browser's session: HttpOnly, refused cross-site without the header,
    and dead the moment it is logged out — or its owner is disabled."""
    from fastapi.testclient import TestClient
    from app.main import app
    nurse_pub = people["nurse_pub"]
    browser = TestClient(app)          # its own cookie jar; the app is already started
    r = browser.post("/api/login", json={"user_id": nurse_pub, "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "quantumcare_token=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert browser.get("/api/auth/me").status_code == 200          # the cookie alone, read-only
    # A state change on the cookie alone, as a forged cross-site form would send it.
    assert browser.post("/api/logout").status_code == 403
    bearer = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert browser.post("/api/logout", headers={"X-Requested-With": "QuantumCare"}).status_code == 200
    # Revoked: neither the cookie (were it replayed) nor the same token as Bearer works.
    browser.cookies.set("quantumcare_token", r.cookies["quantumcare_token"])
    assert browser.get("/api/auth/me").status_code == 401
    assert browser.get("/api/auth/me", headers=bearer).status_code == 401

    # Disabling a user ends their live sessions too.
    c, db = env["client"], env["db"]
    nurse_headers = _login(c, nurse_pub)
    nurse_uuid = c.get("/api/auth/me", headers=nurse_headers).json()["user_id"]
    assert c.post(f"/api/admin/users/{nurse_uuid}/disable", headers=people["admin"]).status_code == 200
    try:
        assert c.get("/api/auth/me", headers=nurse_headers).status_code == 401
    finally:
        assert c.post(f"/api/admin/users/{nurse_uuid}/enable", headers=people["admin"]).status_code == 200


def test_only_configured_origins_may_call_the_api_with_credentials(env):
    c = env["client"]
    evil = c.options("/api/auth/me", headers={"Origin": "https://evil.example",
                                              "Access-Control-Request-Method": "GET"})
    assert evil.headers.get("access-control-allow-origin") is None
    ok = c.options("/api/auth/me", headers={"Origin": "http://localhost:3000",
                                            "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
