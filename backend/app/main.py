import hashlib
import secrets
import json
import logging
import math
import os
from fastapi import FastAPI, Depends, HTTPException, Query, Request, Response, status, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from datetime import datetime, date, timedelta, timezone
from typing import Optional
import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

from app.schemas import (
    RegistrationRequest, LoginRequest, RegistrationResponse, LoginResponse, 
    PendingRegistration, AdminActionRequest, AdminActionResponse,
    RejectRequest, DashboardStats, UserDetail, AuditLogEntry, SecurityStats,
    PatientProfile, PatientDashboardSummary, DiagnosisRecord, LabReportItem,
    PatientInfoSection, MedicalSummarySection, ReportsSummarySection,
    AppointmentsSummarySection, PatientActivityItem,
    PrescriptionRecord, ConsultationRecord, AppointmentRecord, NotificationItem,
    AvailableDoctorItem, CreateAppointmentRequest,
    PatientSecurityInfo, DoctorProfile, DoctorDashboardSummary, DoctorPatientListItem,
    CreateDiagnosisRequest, CreatePrescriptionRequest, CreateConsultationRequest,
    MedicalDocumentItem, CreateDocumentRequest, DoctorAppointmentItem,
    LabTechProfile, LabTechDashboardSummary, LabTestRequestItem,
    CreateLabTestRequest, CreateStructuredLabReportRequest,
    CreateImagingReportRequest, ImagingReportItem,
    LabPanelSummary, FinalizedReportResponse, ReportVerification,
    ConsentEntry, RevokeConsentRequest, EmergencyAccessRequest, EmergencyAccessRecord,
    CreateAccessRequest, AccessRequestDecision, AccessRequestRecord,
    ZkpProofRequest,
    RegisterPeerRequest, PeerSubmissionRequest,
    PatientDocumentItem,
    NurseProfile, NurseDashboardSummary, NursePatientListItem,
    PatientVitalsRecord, CreateVitalsRequest, NursingNoteRecord, CreateNursingNoteRequest,
    ActivePrescriptionForNurse, MedicationAdministrationRecord, CreateMedicationAdministrationRequest,
    NursePatientDetail,
    StepUpRequest, IncidentUpdateRequest,
    CareTeamAssignRequest, CareTeamMember,
)
from app.config import configuration_warnings, get_settings
from app.database import get_db, init_db
from app.security import (
    hash_password, verify_password, encrypt_data, decrypt_data,
    create_session_token, get_current_session, require_role, require_permission,
    SESSION_COOKIE_NAME
)
from app.crypto_service import (
    generate_mlkem_keypair, generate_mldsa_keypair, verify_mldsa_signature,
    encapsulate_aes_key, decapsulate_aes_key, sign_document_hash,
    derive_aes_key, encrypt_document, decrypt_document, sha256_hex,
    pqc_available, PQCUnavailableError, ML_KEM_ALG, ML_DSA_ALG,
)
from app.email_service import send_and_log_email, retry_failed_email, send_admin_notification
from app.user_id_service import generate_user_id, generate_report_number
from app.rbac import get_permissions_for_role, normalize_role
from app.storage_service import (
    store_encrypted_document, download_file_from_s3, storage_status, StorageError,
    ipfs_status, fetch_from_ipfs, is_ipfs_configured, IPFSError,
)
from app import ipfs_replication
from app import ai_security as aisec
from app import security_response as secresp
from app import risk_engine, consent_ledger, federation

from app.audit_service import log_admin_action
from app.anchor_service import anchor_document
from app.lab_catalog import (
    get_panel, list_panels, apply_computed, interpretation_for, analytes_of,
)
from app.report_pdf import build_report_pdf

app = FastAPI(title="PQC Hospital IAM API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(psycopg.errors.InvalidTextRepresentation)
def handle_malformed_identifier(request: Request, exc: psycopg.errors.InvalidTextRepresentation):
    """Turn a malformed identifier into a clear 400 rather than a 500.

    A non-UUID path parameter or an unknown enum value reaches Postgres and
    raises "invalid input syntax". Surfacing that as a 500 is wrong twice
    over: it claims the server failed when in fact the request was malformed,
    and it makes genuine server faults harder to spot in the logs.

    The database's own message is deliberately not echoed back — it names
    internal types and columns.
    """
    logger.warning("Malformed identifier or value in %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=400,
        content={"detail": "Malformed identifier or filter value in the request."},
    )


@app.on_event("startup")
def on_startup():
    for warning in configuration_warnings(get_settings()):
        logger.warning("INSECURE CONFIGURATION: %s", warning)
    init_db()
    _start_background_analysis()


def _start_background_analysis() -> None:
    """Run local anomaly detection on a schedule (spec §19).

    Detection used to happen only when an administrator pressed "Analyse", so
    an insider sweeping records at 03:00 went unnoticed until someone thought
    to look. SECURITY_ANALYSIS_INTERVAL_MINUTES sets the cadence (default 30);
    0 turns it off. The inline risk gate covers the access path between runs.
    """
    import threading
    import time as _time

    try:
        minutes = int(os.getenv("SECURITY_ANALYSIS_INTERVAL_MINUTES", "30"))
    except ValueError:
        minutes = 30
    if minutes <= 0:
        return

    def _loop():
        while True:
            _time.sleep(minutes * 60)
            try:
                result = _run_security_analysis(hours=24)
                logger.info("Scheduled security analysis: %s", result.get("risk_breakdown"))
            except Exception as exc:  # noqa: BLE001 - keep the schedule alive
                logger.error("Scheduled security analysis failed: %s", exc)

    threading.Thread(target=_loop, name="security-analysis", daemon=True).start()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/auth/step-up")
def step_up_verification(req: StepUpRequest, request: Request,
                         session: dict = Depends(get_current_session)):
    """Re-enter the password when the risk policy asks for it (spec §23).

    A MEDIUM/HIGH risk score under a "verify" policy answers 428 until the user
    proves, again, that they are who the session says. A stolen session token
    cannot do that; the person at the keyboard can, in a few seconds.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT password_hash FROM Users WHERE id = %s", (user_uuid,))
            row = cur.fetchone()
            if not row or not verify_password(req.password, row["password_hash"]):
                secresp.failed_login(cur, user_id=user_uuid,
                                     public_user_id=session.get("public_user_id"),
                                     role=session.get("role"), ip_address=_client_ip(request))
                conn.commit()
                # 403, not 401: a wrong re-entry must not log the user out.
                raise HTTPException(status_code=403, detail="Password incorrect.")
            risk_engine.record_step_up(cur, user_uuid)
            aisec.record_security_event(
                cur, actor_id=user_uuid, actor_public_id=session.get("public_user_id"),
                actor_role=session.get("role"), event_type="STEP_UP_VERIFIED",
                resource="step_up", ip_address=_client_ip(request))
            conn.commit()
    return {"status": "verified",
            "valid_for_minutes": risk_engine.policy()["step_up_minutes"]}

@app.post("/api/register", response_model=RegistrationResponse)
def register(request: RegistrationRequest):
    if request.password != request.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    with get_db() as conn:
        with conn.cursor() as cur:
            # Check if email exists
            cur.execute("SELECT id FROM Users WHERE email = %s", (request.email,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="Email already registered")
            
            # Hash password and encrypt sensitive fields
            pwd_hash = hash_password(request.password)
            dob_enc = encrypt_data(request.date_of_birth)
            blood_group_enc = encrypt_data(request.blood_group) if request.blood_group else None
            
            # Insert into Users
            cur.execute("""
                INSERT INTO Users (full_name, email, password_hash, role, gender, date_of_birth_encrypted, blood_group_encrypted, specialization, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Pending')
                RETURNING id
            """, (
                request.full_name, request.email, pwd_hash, request.role, request.gender,
                dob_enc, blood_group_enc, request.specialization
            ))
            new_id = cur.fetchone()[0]
            conn.commit()
            
    # Notify admin
    send_admin_notification({
        "full_name": request.full_name,
        "email": request.email,
        "role": request.role
    })
            
    return {"message": "Registration submitted successfully. Pending admin approval."}

@app.post("/api/login", response_model=LoginResponse)
def login(request: LoginRequest, response: Response):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE user_id = %s", (request.user_id,))
            user = cur.fetchone()

            if not user:
                # Unattributable, but still a security event: sign-in attempts
                # against IDs that do not exist are how enumeration looks.
                secresp.failed_login(cur, user_id=None, public_user_id=None, role=None)
                conn.commit()
                raise HTTPException(status_code=401, detail="Invalid User ID or Password.")
            
            if user["status"] == "Pending":
                raise HTTPException(status_code=403, detail="Your registration is currently under administrator verification.")
            if user["status"] == "Rejected":
                raise HTTPException(status_code=403, detail="Your registration request was not approved.")
            if user["status"] == "Disabled":
                raise HTTPException(status_code=403, detail="Your account has been disabled. Contact administrator.")
                
            if not verify_password(request.password, user["password_hash"]):
                # Log failed attempt
                cur.execute("INSERT INTO AuthLogs (user_id, public_user_id, action) VALUES (%s, %s, %s)",
                            (user["id"], user["user_id"], "LOGIN_FAILED"))
                # AuthLogs is not read by the detector; this event is.
                secresp.failed_login(cur, user_id=str(user["id"]), public_user_id=user["user_id"],
                                     role=user["role"])
                conn.commit()
                raise HTTPException(status_code=401, detail="Invalid User ID or Password.")
            
            # Create session token
            token_payload = {
                "user_id": str(user["id"]),
                "public_user_id": user["user_id"],
                "role": user["role"],
                "email": user["email"],
                "full_name": user["full_name"]
            }
            token, expires_at = create_session_token(token_payload)
            
            # Store session
            cur.execute("""
                INSERT INTO Sessions (user_id, token_hash, role, expires_at)
                VALUES (%s, %s, %s, %s)
            """, (user["id"], hash_password(token), user["role"], expires_at))
            
            # Log successful login
            cur.execute("INSERT INTO AuthLogs (user_id, public_user_id, action) VALUES (%s, %s, %s)",
                        (user["id"], user["user_id"], "LOGIN_SUCCESS"))
            aisec.record_security_event(
                cur, actor_id=str(user["id"]), actor_public_id=user["user_id"],
                actor_role=user["role"], event_type="LOGIN_SUCCESS", resource="login")
            conn.commit()
            
    response.set_cookie(SESSION_COOKIE_NAME, token, httponly=True, secure=False, samesite="lax", path="/")
    
    permissions = list(get_permissions_for_role(user["role"]))
    
    return {
        "access_token": token,
        "user_id": str(user["id"]),
        "public_user_id": user["user_id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "permissions": permissions
    }

@app.post("/api/logout")
def logout(response: Response, session: dict = Depends(get_current_session)):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO AuthLogs (user_id, action) VALUES (%s, %s)", (session["user_id"], "LOGOUT"))
            conn.commit()
            
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return {"status": "success"}

@app.get("/api/auth/me")
def get_me(session: dict = Depends(get_current_session)):
    return session

@app.get("/api/admin/registrations/pending")
def get_pending_registrations(session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE status = 'Pending' ORDER BY created_at DESC")
            rows = cur.fetchall()
            
    results = []
    for row in rows:
        results.append({
            "id": str(row["id"]),
            "full_name": row["full_name"],
            "email": row["email"],
            "role": row["role"],
            "gender": row["gender"],
            "date_of_birth": decrypt_data(row["date_of_birth_encrypted"]),
            "blood_group": decrypt_data(row["blood_group_encrypted"]) if row["blood_group_encrypted"] else None,
            "specialization": row["specialization"],
            "created_at": row["created_at"],
            "status": row["status"]
        })
    return results

@app.get("/api/admin/registrations")
def get_all_registrations(session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users ORDER BY created_at DESC")
            rows = cur.fetchall()
            
    results = []
    for row in rows:
        results.append({
            "id": str(row["id"]),
            "full_name": row["full_name"],
            "email": row["email"],
            "role": row["role"],
            "gender": row["gender"],
            "date_of_birth": decrypt_data(row["date_of_birth_encrypted"]),
            "blood_group": decrypt_data(row["blood_group_encrypted"]) if row["blood_group_encrypted"] else None,
            "specialization": row["specialization"],
            "created_at": row["created_at"],
            "status": row["status"]
        })
    return results

@app.post("/api/admin/registrations/{user_uuid}/approve", response_model=AdminActionResponse)
def approve_registration(user_uuid: str, request: Request, session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Registration not found")
            
            if user["status"] != "Pending":
                raise HTTPException(status_code=400, detail="Registration is not pending")
                
            new_user_id = generate_user_id(user["role"])
            
            kem_pub, kem_priv = generate_mlkem_keypair()
            dsa_pub, dsa_priv = generate_mldsa_keypair()
            
            cur.execute("""
                UPDATE Users 
                SET status = 'Approved', user_id = %s, approved_at = CURRENT_TIMESTAMP, approved_by = %s,
                    mlkem_public_key = %s, mlkem_private_key_encrypted = %s,
                    mldsa_public_key = %s, mldsa_private_key_encrypted = %s
                WHERE id = %s
            """, (
                new_user_id, session["user_id"],
                kem_pub, kem_priv, dsa_pub, dsa_priv,
                user_uuid
            ))
            conn.commit()
            
        # Log admin action
        log_admin_action(
            conn, session["user_id"], session.get("public_user_id"),
            "REGISTRATION_APPROVED", user_uuid, new_user_id,
            request.client.host if request else None,
            {"role": user["role"]}
        )

        # Send and log approval email
        email_res = send_and_log_email(
            conn,
            user_uuid,
            user["email"],
            user["full_name"],
            "APPROVAL",
            user_id_gen=new_user_id
        )
            
    if email_res["sent_status"] == "FAILED":
        return {
            "message": "Account approved successfully, but email delivery failed. Please retry sending the notification.",
            "user_id": new_user_id,
            "email_sent": False
        }
    
    return {
        "message": f"Registration Approved Successfully\nUser ID Generated: {new_user_id}\nApproval email sent successfully.",
        "user_id": new_user_id,
        "email_sent": True
    }

@app.post("/api/admin/registrations/{user_uuid}/reject", response_model=AdminActionResponse)
def reject_registration(
    user_uuid: str,
    request: Request,
    body: RejectRequest = Body(default=RejectRequest()),
    session: dict = Depends(require_role("Administrator"))
):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Registration not found")
            
            if user["status"] != "Pending":
                raise HTTPException(status_code=400, detail="Registration is not pending")
                
            cur.execute(
                "UPDATE Users SET status = 'Rejected', rejection_reason = %s WHERE id = %s",
                (body.reason, user_uuid)
            )
            conn.commit()

        # Log admin action
        details = {"role": user["role"]}
        if body.reason:
            details["reason"] = body.reason
        log_admin_action(
            conn, session["user_id"], session.get("public_user_id"),
            "REGISTRATION_REJECTED", user_uuid, user.get("user_id"),
            request.client.host if request else None,
            details
        )

        # Send and log rejection email
        email_res = send_and_log_email(
            conn,
            user_uuid,
            user["email"],
            user["full_name"],
            "REJECTION",
            reason=body.reason
        )
            
    if email_res["sent_status"] == "FAILED":
        return {
            "message": "Registration Rejected Successfully, but email delivery failed. Please retry sending the notification.",
            "email_sent": False
        }
    
    return {
        "message": "Registration Rejected Successfully\nRejection notification sent to registered email.",
        "email_sent": True
    }

@app.get("/api/dashboard/{dashboard_role}")
def dashboard_gate(dashboard_role: str, session: dict = Depends(get_current_session)):
    allowed_role = normalize_role(session["role"])
    if dashboard_role.lower() not in {allowed_role.lower().replace(" ", ""), allowed_role.lower().replace(" ", "-")}:
        raise HTTPException(status_code=403, detail="Forbidden.")
    return {"status": "success", "dashboard_role": dashboard_role, "session": session}


# ─── Admin Dashboard Endpoints ───────────────────────────────────────────────

@app.get("/api/admin/dashboard/stats")
def get_dashboard_stats(session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # User counts by role and status
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE role = 'Patient') as patients,
                    COUNT(*) FILTER (WHERE role = 'Doctor') as doctors,
                    COUNT(*) FILTER (WHERE role = 'Nurse') as nurses,
                    COUNT(*) FILTER (WHERE role = 'Lab Technician') as lab_techs,
                    COUNT(*) FILTER (WHERE status = 'Pending') as pending,
                    COUNT(*) FILTER (WHERE status = 'Approved') as approved,
                    COUNT(*) FILTER (WHERE status = 'Rejected') as rejected,
                    COUNT(*) FILTER (WHERE status = 'Disabled') as disabled
                FROM Users
            """)
            user_stats = cur.fetchone()

            # Active sessions
            cur.execute("SELECT COUNT(*) as cnt FROM Sessions WHERE expires_at > NOW() AND is_active = TRUE")
            active_sessions = cur.fetchone()["cnt"]

            # PQC keys generated
            cur.execute("SELECT COUNT(*) as cnt FROM Users WHERE mlkem_public_key IS NOT NULL")
            pqc_keys = cur.fetchone()["cnt"]

    return DashboardStats(
        total_users=user_stats["total"],
        total_patients=user_stats["patients"],
        total_doctors=user_stats["doctors"],
        total_nurses=user_stats["nurses"],
        total_lab_technicians=user_stats["lab_techs"],
        pending_requests=user_stats["pending"],
        approved_users=user_stats["approved"],
        rejected_users=user_stats["rejected"],
        disabled_users=user_stats["disabled"],
        active_sessions=active_sessions,
        pqc_keys_generated=pqc_keys
    )


@app.get("/api/admin/dashboard/recent-activity")
def get_recent_activity(session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, admin_user_id, action, target_public_user_id, details, created_at
                FROM AdminAuditLogs
                ORDER BY created_at DESC
                LIMIT 20
            """)
            rows = cur.fetchall()

    return [
        AuditLogEntry(
            id=str(row["id"]),
            admin_user_id=row["admin_user_id"],
            action=row["action"],
            target_public_user_id=row["target_public_user_id"],
            details=row["details"],
            created_at=row["created_at"]
        )
        for row in rows
    ]


@app.get("/api/admin/users")
def list_users(
    role: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    # Bounded at the edge: a negative page produced a negative SQL OFFSET and
    # surfaced as a 500, and an unbounded per_page let one request ask for the
    # entire table.
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
    session: dict = Depends(require_role("Administrator"))
):
    conditions = []
    params = []

    if role:
        conditions.append("role = %s")
        params.append(role)
    if status:
        conditions.append("status = %s")
        params.append(status)
    if search:
        conditions.append("(user_id ILIKE %s OR full_name ILIKE %s OR email ILIKE %s)")
        search_pattern = f"%{search}%"
        params.extend([search_pattern, search_pattern, search_pattern])

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Total count
            cur.execute(f"SELECT COUNT(*) as cnt FROM Users {where_clause}", params)
            total = cur.fetchone()["cnt"]

            # Paginated results
            offset = (page - 1) * per_page
            cur.execute(
                f"""SELECT id, user_id, full_name, email, role, gender, status, created_at
                    FROM Users {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s""",
                params + [per_page, offset]
            )
            rows = cur.fetchall()

    total_pages = math.ceil(total / per_page) if per_page > 0 else 0

    users = [
        {
            "id": str(row["id"]),
            "user_id": row["user_id"],
            "full_name": row["full_name"],
            "email": row["email"],
            "role": row["role"],
            "gender": row["gender"],
            "status": row["status"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        }
        for row in rows
    ]

    return {
        "users": users,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    }


@app.get("/api/admin/users/{user_uuid}")
def get_user_detail(user_uuid: str, session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserDetail(
        id=str(user["id"]),
        user_id=user["user_id"],
        full_name=user["full_name"],
        email=user["email"],
        role=user["role"],
        gender=user["gender"],
        date_of_birth=decrypt_data(user["date_of_birth_encrypted"]) if user["date_of_birth_encrypted"] else None,
        blood_group=decrypt_data(user["blood_group_encrypted"]) if user["blood_group_encrypted"] else None,
        specialization=user["specialization"],
        status=user["status"],
        rejection_reason=user.get("rejection_reason"),
        has_mlkem_keys=user["mlkem_public_key"] is not None,
        has_mldsa_keys=user["mldsa_public_key"] is not None,
        created_at=user["created_at"],
        approved_at=user["approved_at"]
    )


@app.post("/api/admin/users/{user_uuid}/disable")
def disable_user(user_uuid: str, request: Request, session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, user_id, status, role FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            if user["status"] != "Approved":
                raise HTTPException(status_code=400, detail="Only approved users can be disabled")

            cur.execute("UPDATE Users SET status = 'Disabled' WHERE id = %s", (user_uuid,))
            conn.commit()

        log_admin_action(
            conn, session["user_id"], session.get("public_user_id"),
            "USER_DISABLED", user_uuid, user["user_id"],
            request.client.host if request else None,
            {"role": user["role"]}
        )

    return {"message": "User account has been disabled"}


@app.post("/api/admin/users/{user_uuid}/enable")
def enable_user(user_uuid: str, request: Request, session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, user_id, status, role FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            if user["status"] != "Disabled":
                raise HTTPException(status_code=400, detail="Only disabled users can be re-enabled")

            cur.execute("UPDATE Users SET status = 'Approved' WHERE id = %s", (user_uuid,))
            conn.commit()

        log_admin_action(
            conn, session["user_id"], session.get("public_user_id"),
            "USER_ENABLED", user_uuid, user["user_id"],
            request.client.host if request else None,
            {"role": user["role"]}
        )

    return {"message": "User account has been re-enabled"}


@app.get("/api/admin/audit-logs")
def get_audit_logs(
    action: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    session: dict = Depends(require_role("Administrator"))
):
    conditions = []
    params = []

    if action:
        conditions.append("action = %s")
        params.append(action)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT COUNT(*) as cnt FROM AdminAuditLogs {where_clause}", params)
            total = cur.fetchone()["cnt"]

            offset = (page - 1) * per_page
            cur.execute(
                f"""SELECT id, admin_user_id, action, target_public_user_id, details, created_at
                    FROM AdminAuditLogs {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s""",
                params + [per_page, offset]
            )
            rows = cur.fetchall()

    total_pages = math.ceil(total / per_page) if per_page > 0 else 0

    logs = [
        AuditLogEntry(
            id=str(row["id"]),
            admin_user_id=row["admin_user_id"],
            action=row["action"],
            target_public_user_id=row["target_public_user_id"],
            details=row["details"],
            created_at=row["created_at"]
        )
        for row in rows
    ]

    return {
        "logs": [log.model_dump() for log in logs],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    }


@app.get("/api/admin/security/stats")
def get_security_stats(session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Failed login attempts in last 24 hours
            cur.execute("""
                SELECT COUNT(*) as cnt FROM AuthLogs 
                WHERE action = 'LOGIN_FAILED' AND created_at > NOW() - INTERVAL '24 hours'
            """)
            failed_logins = cur.fetchone()["cnt"]

            # Disabled accounts
            cur.execute("SELECT COUNT(*) as cnt FROM Users WHERE status = 'Disabled'")
            disabled = cur.fetchone()["cnt"]

            # Active sessions
            cur.execute("SELECT COUNT(*) as cnt FROM Sessions WHERE expires_at > NOW() AND is_active = TRUE")
            active_sessions = cur.fetchone()["cnt"]

            # Total PQC keypairs
            cur.execute("SELECT COUNT(*) as cnt FROM Users WHERE mlkem_public_key IS NOT NULL")
            total_pqc = cur.fetchone()["cnt"]

            # Active crypto identities
            cur.execute("SELECT COUNT(*) as cnt FROM Users WHERE mlkem_public_key IS NOT NULL AND status = 'Approved'")
            active_crypto = cur.fetchone()["cnt"]

    return SecurityStats(
        failed_login_attempts_24h=failed_logins,
        disabled_accounts=disabled,
        active_sessions=active_sessions,
        total_pqc_keypairs=total_pqc,
        active_crypto_identities=active_crypto
    )


@app.get("/api/admin/users/{user_uuid}/emails")
def get_user_emails(user_uuid: str, session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, user_id, email_address, notification_type, email_subject, email_content, sent_status, sent_timestamp, error_message, created_at
                FROM EmailNotifications
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_uuid,))
            rows = cur.fetchall()
            
    return [
        {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]) if row["user_id"] else None,
            "email_address": row["email_address"],
            "notification_type": row["notification_type"],
            "email_subject": row["email_subject"],
            "email_content": row["email_content"],
            "sent_status": row["sent_status"],
            "sent_timestamp": row["sent_timestamp"].isoformat() if row["sent_timestamp"] else None,
            "error_message": row["error_message"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        }
        for row in rows
    ]


@app.post("/api/admin/emails/{notification_id}/resend")
def resend_failed_email_endpoint(notification_id: str, session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        res = retry_failed_email(conn, notification_id)
        
    if res["sent_status"] == "FAILED":
        raise HTTPException(status_code=400, detail=f"Failed to resend email: {res['error_message']}")

    return {"message": "Email resent successfully", "status": res["sent_status"]}


@app.get("/api/admin/emergency-access")
def list_all_emergency_access(session: dict = Depends(require_role("Administrator"))):
    """Every break-glass declaration, for review.

    Emergency access is not prevented at the point of use, so this listing is
    the control that makes it accountable. Active declarations are surfaced
    first because those are the ones still exposing a record right now.
    """
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT e.*,
                       p.full_name AS patient_name, p.user_id AS patient_user_id,
                       d.full_name AS requester_name, d.user_id AS requester_user_id
                FROM EmergencyAccess e
                JOIN Users p ON p.id = e.patient_id
                JOIN Users d ON d.id = e.requester_id
                ORDER BY (e.expires_at > NOW()) DESC, e.created_at DESC
            """)
            rows = cur.fetchall()
    return [_emergency_record(r) for r in rows]


@app.get("/api/admin/storage/status")
def get_storage_status(session: dict = Depends(require_role("Administrator"))):
    """Live cloud-storage health, plus how many reports actually have a cloud copy.

    ``reports_without_cloud_copy`` counts reports whose S3 upload did not
    happen. Those are still readable (the database copy is authoritative) but
    have no off-database redundancy, so the number should be visible rather
    than assumed to be zero.
    """
    status = storage_status()

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE s3_key IS NOT NULL) AS with_cloud_copy,
                       COUNT(*) FILTER (WHERE s3_key IS NULL) AS without_cloud_copy
                FROM LabReports
            """)
            counts = cur.fetchone()

    status["reports_total"] = counts["total"]
    status["reports_with_cloud_copy"] = counts["with_cloud_copy"]
    status["reports_without_cloud_copy"] = counts["without_cloud_copy"]
    return status


@app.get("/api/admin/blockchain/status")
def get_blockchain_status(session: dict = Depends(require_role("Administrator"))):
    """Live state of the audit-anchor chain, plus a real-vs-simulated breakdown.

    Surfaces honestly whether anchors are actually reaching a chain: if the node
    is unreachable the system keeps working, but anchors are only locally
    simulated and that must be visible rather than silently assumed.
    """
    from app.chain_client import get_chain_client

    settings = get_settings()
    client = get_chain_client()

    connected = client is not None
    chain_info: dict = {
        "enabled": settings.BLOCKCHAIN_ENABLED,
        "connected": connected,
        "network": settings.BLOCKCHAIN_NETWORK_NAME,
        "rpc_url": settings.BLOCKCHAIN_RPC_URL,
        "chain_id": settings.BLOCKCHAIN_CHAIN_ID,
        "contract_address": settings.BLOCKCHAIN_CONTRACT_ADDRESS or None,
        "explorer_url": settings.BLOCKCHAIN_EXPLORER_URL or None,
    }

    if connected:
        try:
            chain_info["latest_block"] = client.web3.eth.block_number
            chain_info["onchain_audit_entries"] = client.audit_trail_count()
        except Exception as exc:
            logger.error("Failed reading chain state: %s", exc)
            chain_info["connected"] = False

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE anchored_on <> 'local-simulated') AS on_chain,
                       COUNT(*) FILTER (WHERE anchored_on = 'local-simulated') AS simulated
                FROM DocumentAnchors
            """)
            counts = cur.fetchone()

            cur.execute("""
                SELECT document_type, action, tx_hash, anchored_on, block_number,
                       report_id_public, created_at
                FROM DocumentAnchors ORDER BY created_at DESC LIMIT 10
            """)
            recent = cur.fetchall()

    chain_info["anchors"] = {
        "total": counts["total"],
        "on_chain": counts["on_chain"],
        "simulated": counts["simulated"],
    }
    chain_info["recent_anchors"] = [{
        "document_type": r["document_type"],
        "action": r["action"],
        "tx_hash": r["tx_hash"],
        "anchored_on": r["anchored_on"],
        "block_number": r["block_number"],
        "report_id_public": r["report_id_public"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in recent]

    return chain_info


# ─── Patient Dashboard Endpoints ─────────────────────────────────────────────

@app.get("/api/patient/profile")
def get_patient_profile(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return PatientProfile(
        id=str(user["id"]),
        user_id=user["user_id"],
        full_name=user["full_name"],
        email=user["email"],
        role=user["role"],
        gender=user["gender"],
        date_of_birth=decrypt_data(user["date_of_birth_encrypted"]) if user["date_of_birth_encrypted"] else None,
        blood_group=decrypt_data(user["blood_group_encrypted"]) if user["blood_group_encrypted"] else None,
        status=user["status"],
        created_at=user["created_at"],
        approved_at=user["approved_at"]
    )


@app.get("/api/patient/dashboard/summary")
def get_patient_dashboard_summary(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # User info
            cur.execute("SELECT * FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
            
            # Latest diagnosis
            cur.execute("SELECT d.title, u.full_name as doctor_name FROM Diagnoses d LEFT JOIN Users u ON d.doctor_id = u.id WHERE d.patient_id = %s ORDER BY d.visit_date DESC LIMIT 1", (user_uuid,))
            latest_diag = cur.fetchone()
            
            # Latest prescription
            cur.execute("SELECT p.medicine_name, p.dosage FROM Prescriptions p WHERE p.patient_id = %s ORDER BY p.prescribed_date DESC LIMIT 1", (user_uuid,))
            latest_rx = cur.fetchone()
            
            # Reports summary
            cur.execute("SELECT COUNT(*) as total, COUNT(*) FILTER (WHERE status = 'Pending') as pending FROM LabReports WHERE patient_id = %s", (user_uuid,))
            report_stats = cur.fetchone()
            
            cur.execute("SELECT report_name, upload_date FROM LabReports WHERE patient_id = %s ORDER BY upload_date DESC LIMIT 1", (user_uuid,))
            latest_report = cur.fetchone()
            
            # Upcoming appointment
            cur.execute("SELECT a.appointment_date, a.appointment_time, a.department, a.status, u.full_name as doctor_name FROM Appointments a LEFT JOIN Users u ON a.doctor_id = u.id WHERE a.patient_id = %s AND a.appointment_date >= CURRENT_DATE AND a.status = 'Scheduled' ORDER BY a.appointment_date ASC, a.appointment_time ASC LIMIT 1", (user_uuid,))
            upcoming = cur.fetchone()
            
            # Previous visit
            cur.execute("SELECT a.appointment_date, a.appointment_time, a.department, a.status, u.full_name as doctor_name FROM Appointments a LEFT JOIN Users u ON a.doctor_id = u.id WHERE a.patient_id = %s AND a.status = 'Completed' ORDER BY a.appointment_date DESC LIMIT 1", (user_uuid,))
            previous = cur.fetchone()
            
            # Assigned doctor (from latest consultation)
            cur.execute("SELECT u.full_name FROM DoctorConsultations dc JOIN Users u ON dc.doctor_id = u.id WHERE dc.patient_id = %s ORDER BY dc.consultation_date DESC LIMIT 1", (user_uuid,))
            assigned_doc = cur.fetchone()
            
            # Recent activities from Notifications
            cur.execute("SELECT title, body, created_at FROM Notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 5", (user_uuid,))
            activities = cur.fetchall()

    return PatientDashboardSummary(
        full_name=user["full_name"],
        patient_info=PatientInfoSection(
            name=user["full_name"],
            user_id=user["user_id"],
            blood_group=decrypt_data(user["blood_group_encrypted"]) if user.get("blood_group_encrypted") else None,
            assigned_doctor=assigned_doc["full_name"] if assigned_doc else None,
        ),
        medical_summary=MedicalSummarySection(
            latest_diagnosis=_dec(latest_diag["title"]) if latest_diag else None,
            current_treatment=f"{_dec(latest_rx['medicine_name'])} ({_dec(latest_rx['dosage'])})" if latest_rx else None,
            latest_prescription=_dec(latest_rx["medicine_name"]) if latest_rx else None,
        ),
        reports_summary=ReportsSummarySection(
            total=report_stats["total"],
            pending=report_stats["pending"],
            latest_report=latest_report["report_name"] if latest_report else None,
            latest_report_date=latest_report["upload_date"] if latest_report else None,
        ),
        appointments_summary=AppointmentsSummarySection(
            upcoming_date=upcoming["appointment_date"] if upcoming else None,
            upcoming_time=str(upcoming["appointment_time"]) if upcoming and upcoming["appointment_time"] else None,
            upcoming_doctor=upcoming["doctor_name"] if upcoming else None,
            upcoming_department=upcoming["department"] if upcoming else None,
            previous_visit_date=previous["appointment_date"] if previous else None,
            previous_doctor=previous["doctor_name"] if previous else None,
        ),
        recent_activities=[
            PatientActivityItem(
                title=a["title"],
                description=a["body"],
                created_at=a["created_at"],
            )
            for a in activities
        ],
    )


@app.get("/api/patient/medical-records")
def get_patient_medical_records(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT d.*, u.full_name as doctor_name
                FROM Diagnoses d
                LEFT JOIN Users u ON d.doctor_id = u.id
                WHERE d.patient_id = %s
                ORDER BY d.visit_date DESC
            """, (user_uuid,))
            rows = cur.fetchall()
    return [_diagnosis_record(r) for r in rows]


@app.get("/api/patient/medical-records/{record_id}")
def get_patient_medical_record_detail(record_id: str, session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT d.*, u.full_name as doctor_name
                FROM Diagnoses d LEFT JOIN Users u ON d.doctor_id = u.id
                WHERE d.id = %s AND d.patient_id = %s
            """, (record_id, user_uuid))
            r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Record not found")
    return _diagnosis_record(r)


@app.get("/api/patient/lab-reports")
def get_patient_lab_reports(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT lr.*, u.full_name as uploaded_by_name
                FROM LabReports lr LEFT JOIN Users u ON lr.uploaded_by = u.id
                WHERE lr.patient_id = %s ORDER BY lr.upload_date DESC
            """, (user_uuid,))
            rows = cur.fetchall()
    return [LabReportItem(
        id=str(r["id"]), report_name=r["report_name"], report_type=r["report_type"],
        report_id_public=r["report_id_public"], findings=r["findings"],
        normal_range=r["normal_range"], status=r["status"],
        uploaded_by_name=r["uploaded_by_name"], upload_date=r["upload_date"]
    ) for r in rows]


@app.get("/api/patient/lab-reports/{report_id}")
def get_patient_lab_report_detail(report_id: str, session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT lr.*, u.full_name as uploaded_by_name
                FROM LabReports lr LEFT JOIN Users u ON lr.uploaded_by = u.id
                WHERE lr.id = %s AND lr.patient_id = %s
            """, (report_id, user_uuid))
            r = cur.fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    return LabReportItem(
        id=str(r["id"]), report_name=r["report_name"], report_type=r["report_type"],
        report_id_public=r["report_id_public"], findings=r["findings"],
        normal_range=r["normal_range"], status=r["status"],
        uploaded_by_name=r["uploaded_by_name"], upload_date=r["upload_date"]
    )


@app.get("/api/patient/lab-reports/{report_id}/download")
def download_patient_lab_report(report_id: str, request: Request, session: dict = Depends(require_role("Patient"))):
    """Release the patient's own report as a decrypted PDF.

    Ownership is enforced in the query itself (``patient_id = session user``),
    so a patient cannot fetch another patient's report by guessing its id.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_REPORT_SELECT + " WHERE lr.id = %s AND lr.patient_id = %s",
                        (report_id, user_uuid))
            report = cur.fetchone()

        if not report:
            raise HTTPException(status_code=404, detail="Report not found")

        # Previously a failed signature only logged a warning and the report was
        # released anyway. An unverifiable report is not shown as trusted.
        pdf_bytes = _release_verified(
            conn, session, lambda: _decrypt_report_pdf(report), report,
            resource=f"LabReport {report.get('report_id_public') or report_id}",
            patient_id=str(user_uuid))
        with conn.cursor(row_factory=dict_row) as cur:
            _record_access(cur, session, patient_id=str(user_uuid), resource="lab_report",
                           basis="own record")
            conn.commit()

        anchor_document(
            conn, document_type="LabReport", document_id=str(report["id"]),
            document_hash=report.get("document_hash") or "", action="PATIENT_ACCESSED_REPORT",
            patient_id=str(user_uuid), actor_id=user_uuid,
            actor_public_id=session.get("public_user_id"),
            report_id_public=report.get("report_id_public"),
        )
        log_admin_action(
            conn, user_uuid, session.get("public_user_id"),
            "PATIENT_DOWNLOADED_REPORT", str(user_uuid), session.get("public_user_id"),
            request.client.host if request and request.client else None,
            {"report_id": str(report["id"]), "report_no": report.get("report_id_public")},
        )

    filename = f"{report.get('report_id_public') or 'report'}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/api/patient/lab-reports/{report_id}/verify", response_model=ReportVerification)
def verify_patient_lab_report(report_id: str, session: dict = Depends(require_role("Patient"))):
    """Let the patient confirm their report is authentic and unaltered."""
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_REPORT_SELECT + " WHERE lr.id = %s AND lr.patient_id = %s",
                        (report_id, user_uuid))
            report = cur.fetchone()
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        return _verify_and_record(conn, session, report)


@app.get("/api/patient/prescriptions")
def get_patient_prescriptions(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT p.*, u.full_name as doctor_name
                FROM Prescriptions p LEFT JOIN Users u ON p.doctor_id = u.id
                WHERE p.patient_id = %s ORDER BY p.prescribed_date DESC
            """, (user_uuid,))
            rows = cur.fetchall()
    return [_prescription_record(r) for r in rows]


@app.get("/api/patient/consultations")
def get_patient_consultations(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT dc.*, u.full_name as doctor_name, u.specialization as doctor_specialization
                FROM DoctorConsultations dc LEFT JOIN Users u ON dc.doctor_id = u.id
                WHERE dc.patient_id = %s ORDER BY dc.consultation_date DESC
            """, (user_uuid,))
            rows = cur.fetchall()
    return [ConsultationRecord(
        id=str(r["id"]), consultation_date=r["consultation_date"],
        symptoms=r["symptoms"], diagnosis_summary=r["diagnosis_summary"],
        doctor_notes=r["doctor_notes"], doctor_name=r["doctor_name"],
        doctor_specialization=r["doctor_specialization"]
    ) for r in rows]


@app.get("/api/patient/appointments")
def get_patient_appointments(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT a.*, u.full_name as doctor_name
                FROM Appointments a LEFT JOIN Users u ON a.doctor_id = u.id
                WHERE a.patient_id = %s ORDER BY a.appointment_date DESC, a.appointment_time DESC
            """, (user_uuid,))
            rows = cur.fetchall()
    return [AppointmentRecord(
        id=str(r["id"]), doctor_name=r["doctor_name"], department=r["department"],
        appointment_date=r["appointment_date"],
        appointment_time=str(r["appointment_time"]) if r["appointment_time"] else None,
        status=r["status"], notes=r["notes"]
    ) for r in rows]


@app.get("/api/patient/documents")
def get_patient_documents(session: dict = Depends(require_role("Patient"))):
    """Documents written about this patient by their clinicians.

    Discharge summaries, referral letters and medical certificates are written
    *about* the patient, so the patient can read them. This completes the
    workflow the doctor side already implements: authored, secured, and then
    actually reachable by the person it concerns.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT m.*, d.full_name AS doctor_name, d.specialization
                FROM MedicalDocuments m
                LEFT JOIN Users d ON m.doctor_id = d.id
                WHERE m.patient_id = %s
                ORDER BY m.created_at DESC
            """, (user_uuid,))
            rows = cur.fetchall()

    return [PatientDocumentItem(
        id=str(r["id"]),
        document_name=r["document_name"],
        document_type=r["document_type"],
        doctor_name=r["doctor_name"],
        doctor_specialization=r["specialization"],
        status=r["status"],
        created_at=r["created_at"],
        has_content=bool(r.get("encrypted_content") or r.get("content")),
        document_hash=r.get("document_hash"),
        kem_algorithm=r.get("kem_algorithm"),
        signature_algorithm=r.get("signature_algorithm"),
        blockchain_tx_hash=r.get("blockchain_tx_hash"),
    ) for r in rows]


@app.get("/api/patient/documents/{document_id}/content")
def get_patient_document_content(
    document_id: str,
    request: Request,
    session: dict = Depends(require_role("Patient")),
):
    """Decrypt one document written about this patient.

    Scoped to their own records by patient_id, so a document id alone is not
    enough to read someone else's. Access is logged like every other release
    of a medical document.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT m.*, u.mlkem_private_key_encrypted,
                       a.mldsa_public_key AS signer_mldsa_public_key
                FROM MedicalDocuments m
                JOIN Users u ON m.patient_id = u.id
                LEFT JOIN Users a ON a.id = m.doctor_id
                WHERE m.id = %s AND m.patient_id = %s
            """, (document_id, user_uuid))
            r = cur.fetchone()

        if not r:
            raise HTTPException(status_code=404, detail="Document not found")

        released = _release_verified(conn, session, lambda: _decrypt_medical_document(r), r,
                                     resource=f"MedicalDocument {document_id}",
                                     patient_id=str(user_uuid))

        log_admin_action(
            conn, user_uuid, session.get("public_user_id"),
            "PATIENT_READ_DOCUMENT", user_uuid, session.get("public_user_id"),
            request.client.host if request and request.client else None,
            {"document_id": str(document_id), "document_name": r["document_name"]},
        )

    return released


@app.get("/api/patient/consent")
def get_patient_consent(session: dict = Depends(require_role("Patient"))):
    """Every clinician with a relationship to this patient, and their access status.

    The list is derived from real clinical contact rather than a separate
    grant list, so a patient sees exactly who can reach their records and why.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT u.id, u.user_id, u.full_name, u.specialization,
                       rel.relationship,
                       c.status AS consent_status, c.revoked_at,
                       (SELECT MAX(e.expires_at) FROM EmergencyAccess e
                         WHERE e.patient_id = %s AND e.requester_id = u.id
                           AND e.expires_at > NOW()) AS emergency_until
                FROM (
                    SELECT doctor_id, 'Recorded a diagnosis' AS relationship FROM Diagnoses WHERE patient_id = %s
                    UNION
                    SELECT doctor_id, 'Held a consultation' FROM DoctorConsultations WHERE patient_id = %s
                    UNION
                    SELECT doctor_id, 'Appointment booked' FROM Appointments WHERE patient_id = %s
                    UNION
                    SELECT doctor_id, 'Ordered a laboratory test' FROM LabTestRequests WHERE patient_id = %s
                ) rel
                JOIN Users u ON u.id = rel.doctor_id AND u.role = 'Doctor'
                LEFT JOIN Consent c
                       ON c.patient_id = %s AND c.subject_user_id = u.id
                WHERE rel.doctor_id IS NOT NULL
                ORDER BY u.full_name
            """, (user_uuid, user_uuid, user_uuid, user_uuid, user_uuid, user_uuid))
            rows = cur.fetchall()

    # One doctor can match several relationships; keep the first and note it.
    seen: dict[str, ConsentEntry] = {}
    for r in rows:
        key = str(r["id"])
        if key in seen:
            continue
        seen[key] = ConsentEntry(
            doctor_id=key,
            doctor_user_id=r["user_id"],
            doctor_name=r["full_name"],
            specialization=r["specialization"],
            relationship=r["relationship"],
            status="Revoked" if r["consent_status"] == "Revoked" else "Authorized",
            revoked_at=r["revoked_at"],
            emergency_override_until=r["emergency_until"],
        )
    return list(seen.values())


@app.post("/api/patient/consent/{doctor_id}/revoke")
def revoke_patient_consent(
    doctor_id: str,
    request: Request,
    body: RevokeConsentRequest = Body(default=RevokeConsentRequest()),
    session: dict = Depends(require_role("Patient")),
):
    """Withdraw a doctor's access to this patient's records.

    This genuinely blocks reads — see ``_doctor_access_blocked``. It does not
    erase history: the doctor's past diagnoses and notes remain part of the
    medical record, because a record of care given cannot be unwritten.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, full_name FROM Users WHERE id = %s AND role = 'Doctor'", (doctor_id,))
            doctor = cur.fetchone()
            if not doctor:
                raise HTTPException(status_code=404, detail="Doctor not found")

            cur.execute("""
                INSERT INTO Consent (patient_id, subject_user_id, subject_role, status, scope, revoked_at)
                VALUES (%s, %s, 'Doctor', 'Revoked', %s, NOW())
                ON CONFLICT (patient_id, subject_user_id, subject_role)
                DO UPDATE SET status = 'Revoked', revoked_at = NOW(), scope = EXCLUDED.scope
                RETURNING consent_id
            """, (user_uuid, doctor_id, json.dumps({"reason": body.reason} if body.reason else {})))
            consent_id = cur.fetchone()["consent_id"]

            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'CONSENT_REVOKED', 'Record access withdrawn',
                        'A patient has withdrawn your access to their records. Emergency access remains available and is audited.')
            """, (doctor_id,))
            # The withdrawal goes on-chain too, so a later database edit that
            # quietly restores the doctor's access disagrees with the ledger.
            ledger = consent_ledger.record(cur, consent_id=str(consent_id),
                                           patient_id=str(user_uuid), doctor_id=str(doctor_id),
                                           authorized=False)
            aisec.record_security_event(
                cur, actor_id=user_uuid, actor_public_id=session.get("public_user_id"),
                actor_role="Patient", event_type="CONSENT_EVENT",
                subject_patient_id=str(user_uuid), resource="CONSENT_REVOKED",
                metadata={"ledger": ledger["recorded_on"]})
            conn.commit()

        log_admin_action(
            conn, user_uuid, session.get("public_user_id"),
            "CONSENT_REVOKED", doctor_id, None,
            request.client.host if request and request.client else None,
            {"doctor": doctor["full_name"], "reason": body.reason},
        )

    return {"status": "success",
            "message": f"Dr. {doctor['full_name']} can no longer access your records.",
            "consent_ledger": ledger}


@app.post("/api/patient/consent/{doctor_id}/grant")
def grant_patient_consent(
    doctor_id: str,
    request: Request,
    session: dict = Depends(require_role("Patient")),
):
    """Restore a previously revoked doctor's access."""
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, full_name FROM Users WHERE id = %s AND role = 'Doctor'", (doctor_id,))
            doctor = cur.fetchone()
            if not doctor:
                raise HTTPException(status_code=404, detail="Doctor not found")

            cur.execute("""
                INSERT INTO Consent (patient_id, subject_user_id, subject_role, status, granted_at, revoked_at)
                VALUES (%s, %s, 'Doctor', 'Authorized', NOW(), NULL)
                ON CONFLICT (patient_id, subject_user_id, subject_role)
                DO UPDATE SET status = 'Authorized', granted_at = NOW(), revoked_at = NULL,
                              prior_refusal = FALSE
                RETURNING consent_id
            """, (user_uuid, doctor_id))
            consent_id = cur.fetchone()["consent_id"]

            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'CONSENT_GRANTED', 'Record access restored',
                        'A patient has restored your access to their records.')
            """, (doctor_id,))
            ledger = consent_ledger.record(cur, consent_id=str(consent_id),
                                           patient_id=str(user_uuid), doctor_id=str(doctor_id),
                                           authorized=True)
            aisec.record_security_event(
                cur, actor_id=user_uuid, actor_public_id=session.get("public_user_id"),
                actor_role="Patient", event_type="CONSENT_EVENT",
                subject_patient_id=str(user_uuid), resource="CONSENT_GRANTED",
                metadata={"ledger": ledger["recorded_on"]})
            conn.commit()

        log_admin_action(
            conn, user_uuid, session.get("public_user_id"),
            "CONSENT_GRANTED", doctor_id, None,
            request.client.host if request and request.client else None,
            {"doctor": doctor["full_name"]},
        )

    return {"status": "success",
            "message": f"Dr. {doctor['full_name']}'s access has been restored.",
            "consent_ledger": ledger}


@app.get("/api/patient/vitals")
def get_patient_vitals(session: dict = Depends(require_role("Patient"))):
    """A patient's own nurse-recorded vitals.

    These are observations about the patient, so the patient can read them.
    Nursing notes are deliberately not exposed here: they are clinical
    handover between staff and are surfaced to the treating doctor instead.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT v.*, n.full_name AS nurse_name FROM PatientVitals v
                LEFT JOIN Users n ON v.nurse_id = n.id
                WHERE v.patient_id = %s ORDER BY v.recorded_at DESC LIMIT 50
            """, (user_uuid,))
            rows = cur.fetchall()
    return [_vitals_record(r) for r in rows]


@app.get("/api/patient/doctors")
def get_available_doctors(session: dict = Depends(require_role("Patient"))):
    """List active doctors a patient can request an appointment with."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, full_name, specialization
                FROM Users
                WHERE role = 'Doctor' AND status = 'Approved'
                ORDER BY full_name ASC
            """)
            rows = cur.fetchall()
    return [AvailableDoctorItem(id=str(r["id"]), full_name=r["full_name"], specialization=r["specialization"]) for r in rows]


@app.post("/api/patient/appointments")
def create_patient_appointment(req: CreateAppointmentRequest, session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id, full_name FROM Users WHERE id = %s AND role = 'Doctor' AND status = 'Approved'", (req.doctor_id,))
            doctor = cur.fetchone()
            if not doctor:
                raise HTTPException(status_code=404, detail="Selected doctor is not available.")

            cur.execute("""
                INSERT INTO Appointments (patient_id, doctor_id, department, appointment_date, appointment_time, status, notes)
                VALUES (%s, %s, %s, %s, %s, 'Pending', %s)
                RETURNING id
            """, (user_uuid, req.doctor_id, req.department, req.appointment_date, req.appointment_time, req.notes))
            appointment_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'APPOINTMENT_REQUEST', 'New Appointment Request',
                        'A patient has requested an appointment on ' || %s || ' at ' || %s || '.')
            """, (req.doctor_id, str(req.appointment_date), req.appointment_time))
            conn.commit()

    return {"status": "success", "appointment_id": str(appointment_id), "message": f"Appointment requested with Dr. {doctor['full_name']}. Awaiting confirmation."}


@app.get("/api/patient/notifications")
def get_patient_notifications(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT * FROM Notifications
                WHERE user_id = %s ORDER BY created_at DESC
            """, (user_uuid,))
            rows = cur.fetchall()
    return [NotificationItem(
        id=str(r["notification_id"]), notification_type=r["notification_type"],
        title=r["title"], body=r["body"],
        read_at=r["read_at"], created_at=r["created_at"]
    ) for r in rows]


@app.post("/api/patient/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE Notifications SET read_at = CURRENT_TIMESTAMP
                WHERE notification_id = %s AND user_id = %s AND read_at IS NULL
            """, (notification_id, user_uuid))
            conn.commit()
    return {"status": "success"}


@app.post("/api/patient/notifications/clear")
def clear_patient_notifications(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM Notifications WHERE user_id = %s AND read_at IS NOT NULL
            """, (user_uuid,))
            conn.commit()
    return {"status": "success"}


@app.get("/api/patient/security")
def get_patient_security_info(session: dict = Depends(require_role("Patient"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT user_id, status, mlkem_public_key, created_at FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
            
            cur.execute("""
                SELECT created_at, ip_address FROM AuthLogs
                WHERE user_id = %s AND action = 'LOGIN_SUCCESS'
                ORDER BY created_at DESC LIMIT 1
            """, (user_uuid,))
            last_login = cur.fetchone()
            
            cur.execute("""
                SELECT COUNT(*) as cnt FROM Sessions
                WHERE user_id = %s AND expires_at > NOW() AND is_active = TRUE
            """, (user_uuid,))
            active_sessions = cur.fetchone()["cnt"]
    
    return PatientSecurityInfo(
        user_id=user["user_id"] if user else None,
        account_status=user["status"] if user else "Unknown",
        last_login=last_login["created_at"] if last_login else None,
        last_login_ip=str(last_login["ip_address"]) if last_login and last_login["ip_address"] else None,
        active_sessions=active_sessions,
        pqc_protection_enabled=user["mlkem_public_key"] is not None if user else False,
        account_created=user["created_at"] if user else None
    )

# ─── Doctor Dashboard Endpoints ──────────────────────────────────────────────

@app.get("/api/doctor/profile")
def get_doctor_profile(session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Doctor not found")
    return DoctorProfile(
        id=str(user["id"]),
        user_id=user["user_id"],
        full_name=user["full_name"],
        email=user["email"],
        role=user["role"],
        gender=user["gender"],
        specialization=user["specialization"],
        status=user["status"],
        created_at=user["created_at"]
    )

@app.get("/api/doctor/dashboard/summary")
def get_doctor_dashboard_summary(session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Patients assigned to this doctor (via past diagnoses, consultations, or appointments)
            cur.execute("""
                SELECT COUNT(DISTINCT patient_id) as cnt FROM (
                    SELECT patient_id FROM Diagnoses WHERE doctor_id = %s
                    UNION
                    SELECT patient_id FROM DoctorConsultations WHERE doctor_id = %s
                    UNION
                    SELECT patient_id FROM Appointments WHERE doctor_id = %s
                ) as assigned
            """, (user_uuid, user_uuid, user_uuid))
            assigned_patients = cur.fetchone()["cnt"]

            # Today's appointments
            cur.execute("SELECT COUNT(*) as cnt FROM Appointments WHERE doctor_id = %s AND appointment_date = CURRENT_DATE", (user_uuid,))
            todays_appointments = cur.fetchone()["cnt"]

            # Pending reports (for patients assigned to this doctor)
            cur.execute("""
                SELECT COUNT(DISTINCT lr.id) as cnt FROM LabReports lr
                JOIN (
                    SELECT patient_id FROM Diagnoses WHERE doctor_id = %s
                    UNION SELECT patient_id FROM Appointments WHERE doctor_id = %s
                ) as assigned ON lr.patient_id = assigned.patient_id
                WHERE lr.status = 'Pending'
            """, (user_uuid, user_uuid))
            pending_reports = cur.fetchone()["cnt"]

            # Recent diagnoses today
            cur.execute("SELECT COUNT(*) as cnt FROM Diagnoses WHERE doctor_id = %s AND visit_date = CURRENT_DATE", (user_uuid,))
            recent_diagnoses = cur.fetchone()["cnt"]

            # Recent activities (Notifications)
            cur.execute("SELECT title, body, created_at FROM Notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 5", (user_uuid,))
            activities = cur.fetchall()

    return DoctorDashboardSummary(
        total_assigned_patients=assigned_patients,
        todays_appointments=todays_appointments,
        pending_reports=pending_reports,
        recent_diagnoses=recent_diagnoses,
        recent_activities=[{"title": a["title"], "body": a["body"], "created_at": a["created_at"].isoformat() if a["created_at"] else None} for a in activities]
    )

@app.get("/api/doctor/patients")
def get_doctor_patients(session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT DISTINCT u.*, 
                (SELECT MAX(visit_date) FROM Diagnoses WHERE patient_id = u.id AND doctor_id = %s) as last_visit
                FROM Users u
                JOIN (
                    SELECT patient_id FROM Diagnoses WHERE doctor_id = %s
                    UNION
                    SELECT patient_id FROM DoctorConsultations WHERE doctor_id = %s
                    UNION
                    SELECT patient_id FROM Appointments WHERE doctor_id = %s
                ) as assigned ON u.id = assigned.patient_id
                WHERE u.role = 'Patient'
            """, (user_uuid, user_uuid, user_uuid, user_uuid))
            rows = cur.fetchall()

    return [DoctorPatientListItem(
        id=str(r["id"]),
        user_id=r["user_id"],
        full_name=r["full_name"],
        gender=r["gender"],
        blood_group=decrypt_data(r["blood_group_encrypted"]) if r.get("blood_group_encrypted") else None,
        last_visit_date=r["last_visit"],
        status=r["status"]
    ) for r in rows]

@app.get("/api/doctor/patients/search")
def search_doctor_patients(q: str, session: dict = Depends(require_role("Doctor"))):
    """Optimized patient search for Doctor portal. Returns max 20 results via ILIKE for scalability."""
    if len(q) < 2:
        return []
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, user_id, full_name, email, gender
                FROM Users
                WHERE role = 'Patient' AND status = 'Approved'
                  AND (full_name ILIKE %s OR user_id ILIKE %s OR email ILIKE %s)
                ORDER BY full_name ASC
                LIMIT 20
            """, (f"%{q}%", f"%{q}%", f"%{q}%"))
            rows = cur.fetchall()
    return [{"id": str(r["id"]), "user_id": r["user_id"], "full_name": r["full_name"], "email": r["email"], "gender": r["gender"]} for r in rows]

@app.get("/api/doctor/patients/{patient_id}")
def get_doctor_patient_detail(patient_id: str, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s AND role = 'Patient'", (patient_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Patient not found")

            # Authorization, not decoration. This check previously computed a
            # relationship and then discarded the result, so any doctor could
            # open any patient's chart. A doctor with neither a treating
            # relationship nor consent is refused, and told how to ask.
            allowed, basis = _doctor_patient_authorization(cur, user_uuid, patient_id)
            if not allowed:
                _deny(cur, session, resource="patient_chart", reason=basis,
                      patient_id=str(patient_id),
                      detail=("You do not have access to this patient's record — "
                              f"{basis}. Request access from the patient to proceed."))
            decision = _security_gate(cur, session, resource="patient_chart",
                                      patient_id=str(patient_id))
            log_admin_action(
                conn, user_uuid, session.get("public_user_id"),
                "DOCTOR_READ_PATIENT_RECORD", str(patient_id), user.get("user_id"),
                details={"basis": basis, "risk_level": decision.level},
            )
            # Feed the AI security layer (§18). Behavioural metadata only —
            # which record, by whom, when — never the clinical content itself.
            _record_access(cur, session, patient_id=str(patient_id), resource="patient_chart",
                           basis=basis, decision=decision)

            cur.execute("SELECT * FROM Diagnoses WHERE patient_id = %s ORDER BY visit_date DESC LIMIT 5", (patient_id,))
            diagnoses = cur.fetchall()

            cur.execute("SELECT * FROM Prescriptions WHERE patient_id = %s ORDER BY prescribed_date DESC LIMIT 5", (patient_id,))
            prescriptions = cur.fetchall()

            # Nursing observations. Recording vitals is only useful if the
            # treating clinician can read them — previously these were visible
            # solely to the nurse who entered them, so the doctor received the
            # abnormal-vitals alert but could not open the reading behind it.
            cur.execute("""
                SELECT v.*, n.full_name AS nurse_name FROM PatientVitals v
                LEFT JOIN Users n ON v.nurse_id = n.id
                WHERE v.patient_id = %s ORDER BY v.recorded_at DESC LIMIT 10
            """, (patient_id,))
            vitals = cur.fetchall()

            cur.execute("""
                SELECT nn.*, n.full_name AS nurse_name FROM NursingNotes nn
                LEFT JOIN Users n ON nn.nurse_id = n.id
                WHERE nn.patient_id = %s ORDER BY nn.created_at DESC LIMIT 10
            """, (patient_id,))
            nursing_notes = cur.fetchall()

    return {
        "profile": {
            "id": str(user["id"]),
            "user_id": user["user_id"],
            "full_name": user["full_name"],
            "email": user["email"],
            "gender": user["gender"],
            "date_of_birth": decrypt_data(user["date_of_birth_encrypted"]) if user.get("date_of_birth_encrypted") else None,
            "blood_group": decrypt_data(user["blood_group_encrypted"]) if user.get("blood_group_encrypted") else None,
        },
        "diagnoses": [_diagnosis_record(r) for r in diagnoses],
        "prescriptions": [_prescription_record(r) for r in prescriptions],
        "vitals": [_vitals_record(v) for v in vitals],
        "nursing_notes": [
            NursingNoteRecord(
                id=str(n["id"]), note_type=n["note_type"], content=n["content"],
                created_at=n["created_at"], nurse_name=n["nurse_name"],
            ) for n in nursing_notes
        ],
    }

def _require_write_access(cur, session: dict, patient_id: str, kind: str) -> None:
    """Writing to a chart needs the same entitlement as reading it (spec §34).

    These writes previously had no check at all — and because a diagnosis is
    itself a "treating relationship", writing one for any patient then unlocked
    that patient's whole chart. A doctor must already be treating, or have the
    patient's consent, before adding to their record.
    """
    allowed, basis = _doctor_patient_authorization(cur, session["user_id"], patient_id)
    if not allowed:
        _deny(cur, session, resource=kind, reason=basis, patient_id=str(patient_id),
              detail=f"You cannot add a {kind} to this patient's record — {basis}.")


@app.post("/api/doctor/patients/{patient_id}/diagnosis")
def create_diagnosis(patient_id: str, req: CreateDiagnosisRequest, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _require_write_access(cur, session, patient_id, "diagnosis")
            cur.execute("""
                INSERT INTO Diagnoses (patient_id, doctor_id, title, description, symptoms, doctor_notes, recommended_tests, visit_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (patient_id, user_uuid, _enc(req.title), _enc(req.description), _enc(req.symptoms),
                  _enc(req.doctor_notes), _enc(req.recommended_tests), req.visit_date))
            conn.commit()
    return {"status": "success"}

@app.post("/api/doctor/patients/{patient_id}/prescription")
def create_prescription(patient_id: str, req: CreatePrescriptionRequest, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _require_write_access(cur, session, patient_id, "prescription")
            cur.execute("""
                INSERT INTO Prescriptions (patient_id, doctor_id, medicine_name, dosage, frequency, duration, instructions, prescribed_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (patient_id, user_uuid, _enc(req.medicine_name), _enc(req.dosage), _enc(req.frequency),
                  _enc(req.duration), _enc(req.instructions), req.prescribed_date))
            conn.commit()
    return {"status": "success"}

@app.post("/api/doctor/patients/{patient_id}/consultation")
def create_consultation(patient_id: str, req: CreateConsultationRequest, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _require_write_access(cur, session, patient_id, "consultation")
            cur.execute("""
                INSERT INTO DoctorConsultations (patient_id, doctor_id, consultation_date, symptoms, diagnosis_summary, doctor_notes)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (patient_id, user_uuid, req.consultation_date, req.symptoms, req.diagnosis_summary, req.doctor_notes))
            conn.commit()
    return {"status": "success"}

@app.get("/api/doctor/reports")
def get_doctor_reports(session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Same rule as _doctor_patient_authorization: a treating relationship
            # or consent, and no withdrawal unless break-glass is live. The list
            # previously ignored withdrawals, so a revoked doctor still saw
            # every finding in it.
            cur.execute("""
                SELECT lr.*, u.full_name as patient_name, u.user_id as patient_user_id
                FROM LabReports lr
                JOIN Users u ON lr.patient_id = u.id
                WHERE (lr.doctor_id = %(d)s
                   OR EXISTS (SELECT 1 FROM Diagnoses d
                               WHERE d.patient_id = lr.patient_id AND d.doctor_id = %(d)s)
                   OR EXISTS (SELECT 1 FROM DoctorConsultations c
                               WHERE c.patient_id = lr.patient_id AND c.doctor_id = %(d)s)
                   OR EXISTS (SELECT 1 FROM Appointments a
                               WHERE a.patient_id = lr.patient_id AND a.doctor_id = %(d)s)
                   OR EXISTS (SELECT 1 FROM LabTestRequests r
                               WHERE r.patient_id = lr.patient_id AND r.doctor_id = %(d)s)
                   OR EXISTS (SELECT 1 FROM Consent k
                               WHERE k.patient_id = lr.patient_id AND k.subject_user_id = %(d)s
                                 AND k.subject_role = 'Doctor' AND k.status = 'Authorized'))
                  AND (NOT EXISTS (SELECT 1 FROM Consent x
                                    WHERE x.patient_id = lr.patient_id AND x.subject_user_id = %(d)s
                                      AND x.status IN ('Revoked', 'Rejected'))
                       OR EXISTS (SELECT 1 FROM EmergencyAccess e
                                   WHERE e.patient_id = lr.patient_id AND e.requester_id = %(d)s
                                     AND e.expires_at > NOW()))
                ORDER BY lr.upload_date DESC
            """, {"d": user_uuid})
            rows = cur.fetchall()
    return [LabReportItem(
        id=str(r["id"]), report_name=r["report_name"], report_type=r["report_type"],
        report_id_public=r["report_id_public"], findings=r["findings"],
        normal_range=r["normal_range"], status=r["status"],
        patient_name=r["patient_name"], patient_user_id=r.get("patient_user_id"),
        upload_date=r["upload_date"]
    ) for r in rows]

@app.post("/api/doctor/reports/{report_id}/review")
def review_lab_report(report_id: str, session: dict = Depends(require_role("Doctor"))):
    """Mark a report reviewed, and tell the patient a clinician has read it.

    Scoped to reports this doctor is entitled to: the update previously matched
    on id alone, so any doctor could mark any report in the system reviewed —
    including for patients they had never met.
    """
    doctor_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            report = _doctor_may_read_report(cur, doctor_uuid, report_id)
            if not report:
                raise HTTPException(status_code=404, detail="Report not found")

            cur.execute(
                "UPDATE LabReports SET status = 'Reviewed' WHERE id = %s RETURNING patient_id",
                (report_id,))
            row = cur.fetchone()

            # The moment the patient is actually waiting for: not that a result
            # exists, but that a clinician has looked at it.
            cur.execute(
                """INSERT INTO Notifications (user_id, notification_type, title, body)
                   VALUES (%s, 'REPORT_REVIEWED', %s, %s)""",
                (row["patient_id"], "Your report has been reviewed",
                 f"Dr. {session.get('full_name') or 'Your doctor'} has reviewed your "
                 f"{report.get('report_name') or 'laboratory'} report."))
            log_admin_action(conn, doctor_uuid, session.get("public_user_id"),
                             "DOCTOR_REVIEWED_REPORT", str(row["patient_id"]), None)
            conn.commit()
    return {"status": "success"}

@app.get("/api/doctor/documents")
def get_doctor_documents(session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT m.*, u.full_name as patient_name
                FROM MedicalDocuments m
                JOIN Users u ON m.patient_id = u.id
                WHERE m.doctor_id = %s
                ORDER BY m.created_at DESC
            """, (user_uuid,))
            rows = cur.fetchall()
    return [MedicalDocumentItem(
        id=str(r["id"]), document_name=r["document_name"], document_type=r["document_type"],
        patient_name=r["patient_name"], upload_date=r["created_at"], status=r["status"]
    ) for r in rows]

@app.post("/api/doctor/documents")
def create_medical_document(
    req: CreateDocumentRequest,
    request: Request,
    session: dict = Depends(require_role("Doctor")),
):
    """Author a medical document under the same protection as every other record.

    Discharge summaries, referral letters and medical certificates previously
    stored their body as plaintext and never reached cloud storage, bypassing
    the pipeline entirely. They now follow it: AES-256-GCM encrypts the body,
    ML-KEM-768 protects the key against the patient's public key, ML-DSA-65
    signs the digest, and only ciphertext is written to cloud storage.
    """
    user_uuid = session["user_id"]

    if not req.content:
        raise HTTPException(status_code=400, detail="Document content is required.")

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, user_id, mlkem_public_key FROM Users WHERE id = %s AND role = 'Patient'",
                (req.patient_id,),
            )
            patient = cur.fetchone()
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")
            _require_write_access(cur, session, str(req.patient_id), "medical document")
            if not patient["mlkem_public_key"]:
                raise HTTPException(
                    status_code=409,
                    detail="Patient has no ML-KEM public key; the document cannot be protected.",
                )

            cur.execute("SELECT mldsa_private_key_encrypted FROM Users WHERE id = %s", (user_uuid,))
            doctor = cur.fetchone()

            content_bytes = req.content.encode("utf-8")
            document_hash = sha256_hex(content_bytes)

            try:
                kem_ciphertext, shared_secret = encapsulate_aes_key(patient["mlkem_public_key"])
                aes_key = derive_aes_key(shared_secret)
                encrypted = encrypt_document(content_bytes, aes_key)
                signature = sign_document_hash(document_hash, doctor["mldsa_private_key_encrypted"])
            except PQCUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            # Only ciphertext leaves the process.
            content_cid, s3_key = store_encrypted_document(
                encrypted["ciphertext"].encode("utf-8"), f"{req.document_name}_{req.document_type}"
            )

            cur.execute("""
                INSERT INTO MedicalDocuments (
                    patient_id, doctor_id, document_name, document_type, status,
                    encrypted_content, encrypted_aes_key, encryption_nonce, encryption_tag,
                    document_hash, digital_signature, kem_algorithm, signature_algorithm,
                    ipfs_cid, s3_key
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                req.patient_id, user_uuid, req.document_name, req.document_type, req.status,
                encrypted["ciphertext"], kem_ciphertext, encrypted["nonce"], encrypted["tag"],
                document_hash, signature, ML_KEM_ALG, ML_DSA_ALG,
                content_cid, s3_key,
            ))
            document_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'DOCUMENT_READY', 'New Medical Document Available',
                        'Your doctor has issued a ' || %s || '.')
            """, (req.patient_id, req.document_type))
            conn.commit()

        anchor = anchor_document(
            conn,
            document_type="MedicalDocument", document_id=str(document_id),
            document_hash=document_hash, action="DOCUMENT_ISSUED",
            patient_id=str(req.patient_id), actor_id=user_uuid,
            actor_public_id=session.get("public_user_id"),
        )

        with conn.cursor() as cur:
            cur.execute("UPDATE MedicalDocuments SET blockchain_tx_hash = %s WHERE id = %s",
                        (anchor["tx_hash"], document_id))
            conn.commit()

    return {
        "status": "success",
        "document_id": str(document_id),
        "patient_user_id": patient["user_id"],
        "document_hash": document_hash,
        "kem_algorithm": ML_KEM_ALG,
        "signature_algorithm": ML_DSA_ALG,
        "blockchain_tx_hash": anchor["tx_hash"],
        "anchored_on": anchor["anchored_on"],
        "s3_key": s3_key,
    }



def _decrypt_medical_document(row: dict) -> dict:
    """Release one medical document's body, decrypted and integrity-checked.

    Shared by the doctor who authored it and the patient it is about, so the
    same document can never decrypt differently depending on who asks. The
    digest is re-checked against the value recorded at signing before anything
    is returned.
    """
    # Rows predating encryption kept their plaintext body in `content`.
    if not row.get("encrypted_content"):
        if row.get("content"):
            return {"content": row["content"], "encrypted": False}
        raise HTTPException(status_code=404, detail="No content stored for this document.")

    ciphertext = row["encrypted_content"]
    if not ciphertext and row.get("s3_key"):
        try:
            ciphertext = download_file_from_s3(row["s3_key"]).decode("utf-8")
        except StorageError as exc:
            logger.error("S3 recovery failed for document %s: %s", row.get("id"), exc)

    try:
        shared_secret = decapsulate_aes_key(row["encrypted_aes_key"], row["mlkem_private_key_encrypted"])
        content_bytes = decrypt_document(
            ciphertext, derive_aes_key(shared_secret),
            row["encryption_nonce"], row["encryption_tag"],
        )
    except PQCUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise _IntegrityFailure(status_code=409, detail="Document failed its integrity check.") from exc

    if sha256_hex(content_bytes) != row.get("document_hash"):
        raise _IntegrityFailure(status_code=409, detail="Document digest does not match the recorded hash.")

    return {"content": content_bytes.decode("utf-8"), "encrypted": True}


@app.get("/api/doctor/documents/{document_id}/content")
def get_medical_document_content(document_id: str, session: dict = Depends(require_role("Doctor"))):
    """Decrypt one document the requesting doctor authored.

    Falls back to the S3 copy if the database ciphertext is missing, and
    re-checks the digest against the value recorded at signing before release.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT m.*, u.mlkem_private_key_encrypted,
                       a.mldsa_public_key AS signer_mldsa_public_key
                FROM MedicalDocuments m
                JOIN Users u ON m.patient_id = u.id
                LEFT JOIN Users a ON a.id = m.doctor_id
                WHERE m.id = %s AND m.doctor_id = %s
            """, (document_id, user_uuid))
            r = cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="Document not found")
            # Authorship does not outlive a withdrawal: the document is part of
            # the patient's record, and the patient decides who reads it.
            allowed, basis = _doctor_patient_authorization(cur, user_uuid, str(r["patient_id"]))
            if not allowed:
                _deny(cur, session, resource="medical_document", reason=basis,
                      patient_id=str(r["patient_id"]),
                      detail=f"You no longer have access to this patient's record — {basis}.")

        return _release_verified(conn, session, lambda: _decrypt_medical_document(r), r,
                                 resource=f"MedicalDocument {document_id}",
                                 patient_id=str(r["patient_id"]))

@app.get("/api/doctor/appointments")
def get_doctor_appointments(session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT a.*, u.full_name as patient_name, u.user_id as patient_id_public
                FROM Appointments a
                JOIN Users u ON a.patient_id = u.id
                WHERE a.doctor_id = %s
                ORDER BY a.appointment_date DESC, a.appointment_time DESC
            """, (user_uuid,))
            rows = cur.fetchall()
    return [DoctorAppointmentItem(
        id=str(r["id"]), patient_name=r["patient_name"], patient_id_public=r["patient_id_public"],
        department=r["department"], appointment_date=r["appointment_date"],
        appointment_time=str(r["appointment_time"]) if r["appointment_time"] else None,
        status=r["status"], notes=r["notes"]
    ) for r in rows]

@app.post("/api/doctor/appointments/{appointment_id}/{action}")
def update_appointment_status(appointment_id: str, action: str, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    status_map = {"accept": "Confirmed", "complete": "Completed", "cancel": "Cancelled"}
    if action not in status_map:
        raise HTTPException(status_code=400, detail="Invalid action")
    
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """UPDATE Appointments SET status = %s
                    WHERE id = %s AND doctor_id = %s
                RETURNING patient_id, appointment_date, appointment_time, department""",
                (status_map[action], appointment_id, user_uuid))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Appointment not found")

            # The patient was told when they requested and then never again — so
            # a cancelled appointment was one they turned up for. Every outcome
            # now reaches them.
            when = f"{row['appointment_date']} at {row['appointment_time']}"
            wording = {
                "accept": ("Appointment confirmed", f"Your appointment on {when} is confirmed."),
                "complete": ("Appointment completed", f"Your appointment on {when} has been marked complete."),
                "cancel": ("Appointment cancelled", f"Your appointment on {when} was cancelled. Please book another time."),
            }[action]
            cur.execute(
                """INSERT INTO Notifications (user_id, notification_type, title, body)
                   VALUES (%s, %s, %s, %s)""",
                (row["patient_id"], "APPOINTMENT_" + status_map[action].upper(), wording[0], wording[1]))
            conn.commit()
    return {"status": "success"}

@app.get("/api/doctor/notifications")
def get_doctor_notifications(session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Notifications WHERE user_id = %s ORDER BY created_at DESC", (user_uuid,))
            rows = cur.fetchall()
    return [NotificationItem(
        id=str(r["notification_id"]), notification_type=r["notification_type"],
        title=r["title"], body=r["body"], read_at=r["read_at"], created_at=r["created_at"]
    ) for r in rows]

@app.post("/api/doctor/notifications/{notification_id}/read")
def mark_doctor_notification_read(notification_id: str, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE Notifications SET read_at = CURRENT_TIMESTAMP WHERE notification_id = %s AND user_id = %s AND read_at IS NULL", (notification_id, user_uuid))
            conn.commit()
    return {"status": "success"}

@app.post("/api/doctor/notifications/clear")
def clear_doctor_notifications(session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM Notifications WHERE user_id = %s AND read_at IS NOT NULL", (user_uuid,))
            conn.commit()
    return {"status": "success"}

@app.get("/api/doctor/lab-panels")
def get_doctor_lab_panels(session: dict = Depends(require_role("Doctor"))):
    """Investigations a doctor can order, so the request names a real panel."""
    return list_panels()


@app.post("/api/doctor/requests")
def create_lab_test_request(
    req: CreateLabTestRequest,
    request: Request,
    session: dict = Depends(require_role("Doctor")),
):
    """Raise a laboratory test request against an approved patient."""
    user_uuid = session["user_id"]

    panel = get_panel(req.panel_code) if req.panel_code else None
    if req.panel_code and not panel:
        raise HTTPException(status_code=400, detail=f"Unknown investigation panel '{req.panel_code}'")
    if req.priority not in ("Routine", "Urgent", "Emergency"):
        raise HTTPException(status_code=400, detail="Priority must be Routine, Urgent or Emergency")

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, user_id, full_name FROM Users
                WHERE role = 'Patient' AND status = 'Approved'
                  AND (id::text = %s OR user_id = %s)
            """, (req.patient_id, req.patient_id))
            patient = cur.fetchone()
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found or not an approved patient account")

            # Spec §10: validate the doctor-patient relationship. Ordering a
            # test previously needed nothing, and a lab request counts as a
            # treating relationship — so one order for any patient unlocked
            # that patient's whole chart.
            allowed, basis = _doctor_patient_authorization(cur, user_uuid, str(patient["id"]))
            if not allowed:
                _deny(cur, session, resource="lab_request", reason=basis,
                      patient_id=str(patient["id"]), request=request,
                      detail=("You cannot order investigations for this patient — "
                              f"{basis}. Request access from the patient first."))

            test_name = req.test_name or (panel["name"] if panel else None)
            if not test_name:
                raise HTTPException(status_code=400, detail="A test name or panel must be supplied")

            cur.execute("""
                INSERT INTO LabTestRequests
                    (patient_id, doctor_id, test_name, panel_code, priority, clinical_notes, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'Pending')
                RETURNING id, requested_date
            """, (patient["id"], user_uuid, test_name,
                  panel["code"] if panel else None, req.priority, req.clinical_notes))
            row = cur.fetchone()

            # Notify the laboratory. Without this an Emergency-priority request
            # is seen only if a technician happens to refresh the queue, while
            # every other role in the system is told when work arrives.
            cur.execute("SELECT id FROM Users WHERE role = 'Lab Technician' AND status = 'Approved'")
            technicians = cur.fetchall()
            if technicians:
                urgency = "" if req.priority == "Routine" else f"[{req.priority.upper()}] "
                cur.executemany(
                    """INSERT INTO Notifications (user_id, notification_type, title, body)
                       VALUES (%s, 'LAB_REQUEST', %s, %s)""",
                    [(tech["id"], f"{urgency}New investigation requested",
                      f"{test_name} requested for {patient['full_name']} ({patient['user_id']}).")
                     for tech in technicians])
            aisec.record_security_event(
                cur, actor_id=user_uuid, actor_public_id=session.get("public_user_id"),
                actor_role="Doctor", event_type="LAB_REQUEST_CREATED",
                subject_patient_id=str(patient["id"]), resource="lab_request",
                ip_address=_client_ip(request), metadata={"priority": req.priority})
            conn.commit()

        log_admin_action(
            conn, user_uuid, session.get("public_user_id"),
            "LAB_TEST_REQUESTED", str(patient["id"]), patient["user_id"],
            request.client.host if request and request.client else None,
            {"request_id": str(row["id"]), "test": test_name,
             "panel": panel["code"] if panel else None, "priority": req.priority},
        )

    return {
        "status": "success",
        "request_id": str(row["id"]),
        "patient_user_id": patient["user_id"],
        "test_name": test_name,
        "panel_code": panel["code"] if panel else None,
        "priority": req.priority,
        "requested_date": row["requested_date"],
    }


@app.get("/api/doctor/requests")
def get_doctor_lab_requests(
    status_filter: Optional[str] = None,
    session: dict = Depends(require_role("Doctor")),
):
    """Test requests this doctor raised, with the resulting report once filed."""
    user_uuid = session["user_id"]
    query = """
        SELECT r.*, p.full_name AS patient_name, p.user_id AS patient_user_id,
               lr.id AS report_id, lr.report_id_public AS report_no
        FROM LabTestRequests r
        JOIN Users p ON r.patient_id = p.id
        LEFT JOIN LabReports lr ON lr.lab_request_id = r.id
        WHERE r.doctor_id = %s
    """
    params: list = [user_uuid]
    if status_filter:
        query += " AND r.status = %s"
        params.append(status_filter)
    query += " ORDER BY r.requested_date DESC"

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [LabTestRequestItem(
        id=str(r["id"]), patient_id=str(r["patient_id"]), patient_name=r["patient_name"],
        patient_user_id=r["patient_user_id"], doctor_id=str(user_uuid),
        test_name=r["test_name"], panel_code=r.get("panel_code"),
        priority=r["priority"], status=r["status"], clinical_notes=r["clinical_notes"],
        requested_date=r["requested_date"],
        report_id=str(r["report_id"]) if r.get("report_id") else None,
        report_no=r.get("report_no"),
    ) for r in rows]


# Consent revocation must actually block access, otherwise the control is
# decorative. These two fragments are shared by every doctor-facing read so a
# revocation cannot be honoured in one place and ignored in another.
# A refusal stands until the patient decides otherwise. A doctor re-asking after
# a withdrawal puts the row back to Pending; that used to read as "not refused",
# so a doctor with an old treating relationship regained the chart merely by
# asking. ``prior_refusal`` keeps the block until the patient approves.
_CONSENT_REVOKED = """
    EXISTS (SELECT 1 FROM Consent c
             WHERE c.patient_id = %s AND c.subject_user_id = %s
               AND (c.status IN ('Revoked', 'Rejected')
                    OR (c.status = 'Pending' AND c.prior_refusal)))
"""

_EMERGENCY_ACTIVE = """
    EXISTS (SELECT 1 FROM EmergencyAccess e
             WHERE e.patient_id = %s AND e.requester_id = %s
               AND e.expires_at > NOW())
"""


def _emergency_record(row: dict) -> EmergencyAccessRecord:
    """Shape one EmergencyAccess row. Shared by the doctor and admin views so a
    declaration reads identically to the person who made it and the person
    reviewing it."""
    expires = row.get("expires_at")
    return EmergencyAccessRecord(
        id=str(row["emergency_access_id"]),
        patient_id=str(row["patient_id"]),
        patient_name=row.get("patient_name"),
        patient_user_id=row.get("patient_user_id"),
        requester_id=str(row["requester_id"]),
        requester_name=row.get("requester_name"),
        requester_user_id=row.get("requester_user_id"),
        reason=row["reason"],
        status=row["status"],
        blockchain_tx_hash=row.get("blockchain_tx_hash"),
        created_at=row.get("created_at"),
        expires_at=expires,
        is_active=bool(expires and expires > datetime.now(timezone.utc)),
    )



# ─────────────────────────────────────────────────────────────────────────────
# Access-path security (spec §8, §14, §23, §24, §34)
#
# One sequence for every clinical read, so no endpoint can quietly skip a step:
#
#   RBAC (require_role) → relationship / consent (+ on-chain consent check)
#     → AI risk gate → release with integrity + ML-DSA signature verification
#     → audit log + security event for the AI layer
#
# Refusals are recorded as ACCESS_DENIED events, so repeated probing for
# records is itself a signal; integrity and signature failures open incidents.
# ─────────────────────────────────────────────────────────────────────────────

class _IntegrityFailure(HTTPException):
    """A stored record failed its integrity check (GCM tag or recorded digest)."""


def _client_ip(request: Optional[Request]) -> Optional[str]:
    return request.client.host if request and request.client else None


def _deny(cur, session: dict, *, resource: str, reason: str, patient_id: Optional[str] = None,
          status_code: int = 403, detail: Optional[str] = None,
          request: Optional[Request] = None):
    """Refuse an access, and make the refusal count.

    The refusal is recorded for the AI layer and committed before raising —
    ``get_db`` rolls back on an exception, which would otherwise erase the
    evidence that someone tried.
    """
    secresp.access_denied(
        cur, actor_id=session["user_id"], actor_public_id=session.get("public_user_id"),
        actor_role=session.get("role"), resource=resource, reason=reason,
        patient_id=patient_id, ip_address=_client_ip(request))
    secresp.commit_before_refusal(cur)
    raise HTTPException(status_code=status_code, detail=detail or reason)


def _security_gate(cur, session: dict, *, resource: str, patient_id: Optional[str] = None,
                   emergency: bool = False) -> risk_engine.Decision:
    """AI risk assessment between authorization and release (spec §23).

    Runs only after RBAC and consent have already allowed the read, and can
    only make it stricter: ``monitor`` lets it through with an alert, ``verify``
    demands a recent password re-entry, ``block`` refuses. Which one a level
    gets is configured in ``risk_engine.policy()``.
    """
    actor_id = session["user_id"]
    actor_pub = session.get("public_user_id")
    decision = risk_engine.evaluate(cur, actor_id, session.get("role") or "Unknown",
                                    emergency=emergency)
    if decision.level == "LOW":
        return decision

    alert_id, created = secresp.raise_alert_once(
        cur, severity=decision.level, source=secresp.SOURCE_RISK_GATE, actor_id=actor_id,
        title=f"{decision.level} risk at access — {actor_pub or 'unknown actor'}",
        summary=(f"{decision.narrative} Action under the configured policy: "
                 f"{decision.action.upper()} (resource: {resource}; baseline: "
                 f"{decision.baseline_source}, {decision.baseline_samples} peers)."),
        response={"monitor": "MONITOR", "verify": "VERIFY", "block": "RESTRICT"}.get(
            decision.action, "MONITOR"),
        dedupe_minutes=60)
    if created and decision.level == "HIGH" and not emergency:
        secresp.open_incident(
            cur, event_type="HIGH_RISK_ACCESS", risk_level="HIGH",
            detection_source=decision.baseline_source, actor_id=actor_id,
            affected_resource=resource, alert_id=alert_id,
            explanation=decision.narrative,
            response=f"{decision.action.upper()} under the configured risk policy.")

    if decision.action == "block":
        secresp.access_denied(cur, actor_id=actor_id, actor_public_id=actor_pub,
                              actor_role=session.get("role"), resource=resource,
                              reason=f"blocked by risk policy ({decision.level})",
                              patient_id=patient_id)
        secresp.commit_before_refusal(cur)
        raise HTTPException(status_code=403, detail={
            "code": "RISK_BLOCKED",
            "message": ("Access refused by the security policy. An administrator has "
                        "been alerted."),
            "risk_level": decision.level, "explanation": decision.narrative})

    if decision.action == "verify" and not risk_engine.step_up_valid(cur, actor_id):
        aisec.record_security_event(
            cur, actor_id=actor_id, actor_public_id=actor_pub, actor_role=session.get("role"),
            event_type="STEP_UP_REQUIRED", subject_patient_id=patient_id, resource=resource,
            metadata={"risk_level": decision.level})
        secresp.commit_before_refusal(cur)
        raise HTTPException(status_code=428, detail={
            "code": "STEP_UP_REQUIRED",
            "message": ("Your recent activity was flagged for review. Re-enter your "
                        "password to continue."),
            "risk_level": decision.level, "explanation": decision.narrative})
    return decision


def _record_access(cur, session: dict, *, patient_id: str, resource: str,
                   basis: Optional[str] = None,
                   decision: Optional[risk_engine.Decision] = None) -> None:
    """Feed one completed record read to the AI layer. Metadata only."""
    aisec.record_security_event(
        cur, actor_id=session["user_id"], actor_public_id=session.get("public_user_id"),
        actor_role=session.get("role"), event_type="RECORD_ACCESS",
        subject_patient_id=str(patient_id), resource=resource,
        metadata={"basis": basis, "risk_level": decision.level if decision else None})


def _signature_verdict(document_hash: Optional[str], signature: Optional[str],
                       public_key: Optional[str]) -> Optional[bool]:
    """True/False when the signature can be checked; None when it cannot be.

    Without liboqs every verification returns False, and treating that as
    tampering would raise an incident for every record in the system. "Cannot
    check" is reported as exactly that.
    """
    if not pqc_available():
        return None
    return verify_mldsa_signature(document_hash or "", signature or "", public_key or "")


def _release_verified(conn, session: dict, release, row: dict, *, resource: str,
                      patient_id: Optional[str]):
    """Release a stored record only if it is intact and its signature verifies.

    ``release`` decrypts and checks the digest. A failure of either check is a
    security event, not just an error: the record is withheld and an incident
    opened (spec §14 — "do not silently display as trusted").
    """
    actor = {"actor_id": session.get("user_id"), "actor_public_id": session.get("public_user_id"),
             "actor_role": session.get("role")}
    try:
        payload = release()
    except _IntegrityFailure as exc:
        with conn.cursor(row_factory=dict_row) as cur:
            secresp.integrity_failure(cur, resource=resource, detail=str(exc.detail),
                                      patient_id=patient_id, **actor)
            secresp.commit_before_refusal(cur)
        raise

    if row.get("digital_signature"):
        verdict = _signature_verdict(row.get("document_hash"), row.get("digital_signature"),
                                     row.get("signer_mldsa_public_key"))
        if verdict is False:
            with conn.cursor(row_factory=dict_row) as cur:
                secresp.signature_failure(
                    cur, resource=resource, patient_id=patient_id, **actor,
                    detail="The ML-DSA signature does not verify against the signer's public key.")
                secresp.commit_before_refusal(cur)
            raise HTTPException(
                status_code=409,
                detail=f"{resource} failed signature verification and was not released.")
    return payload


def _doctor_patient_authorization(cur, doctor_uuid: str, patient_uuid: str) -> tuple[bool, str]:
    """Decide whether this doctor may read this patient, and on what basis.

    Spec §8: a read is permitted only when RBAC, relationship and consent all
    agree. Two bases grant it — an existing treating relationship, or explicit
    consent the patient granted through an access request — and a withdrawal or
    rejection overrides both unless break-glass is live.

    Returns ``(allowed, basis)``; the basis is recorded in the audit trail so
    that *why* a record was opened is answerable later, not just that it was.
    """
    cur.execute(
        f"SELECT {_CONSENT_REVOKED} AS blocked, {_EMERGENCY_ACTIVE} AS emergency",
        (patient_uuid, doctor_uuid, patient_uuid, doctor_uuid),
    )
    row = cur.fetchone()
    if row["emergency"]:
        return True, "emergency override"
    if row["blocked"]:
        return False, "patient withdrew or declined access"
    # Smart-contract consent (spec §7), asked of the chain itself for every read
    # — not only consent-based ones, and not gated on a database column saying
    # there is something to check. A withdrawal recorded on-chain that the
    # database no longer shows means the row was edited or deleted outside the
    # application, and a treating relationship must not paper over it.
    onchain = consent_ledger.chain_state(patient_uuid, doctor_uuid)
    if onchain == consent_ledger.REVOKED:
        secresp.consent_ledger_mismatch(
            cur, patient_id=patient_uuid, doctor_id=doctor_uuid,
            detail=("The patient's withdrawal is recorded on the blockchain but the consent "
                    "row no longer shows it. Access refused pending investigation."))
        return False, "consent record does not match the blockchain ledger"

    cur.execute(
        """SELECT EXISTS (
               SELECT 1 FROM Diagnoses WHERE doctor_id = %s AND patient_id = %s
               UNION ALL SELECT 1 FROM Appointments WHERE doctor_id = %s AND patient_id = %s
               UNION ALL SELECT 1 FROM DoctorConsultations WHERE doctor_id = %s AND patient_id = %s
               UNION ALL SELECT 1 FROM LabTestRequests WHERE doctor_id = %s AND patient_id = %s
           ) AS treating,
           EXISTS (
               SELECT 1 FROM Consent WHERE patient_id = %s AND subject_user_id = %s
                 AND subject_role = 'Doctor' AND status = 'Authorized'
           ) AS consented""",
        (doctor_uuid, patient_uuid) * 4 + (patient_uuid, doctor_uuid),
    )
    r = cur.fetchone()
    if r["treating"]:
        return True, "treating relationship"
    if r["consented"]:
        # A contradicting chain was refused above; what is left is whether the
        # chain positively confirms the grant or simply cannot say.
        if onchain == consent_ledger.GRANTED:
            return True, "patient consent (verified on-chain)"
        return True, "patient consent"
    return False, "no treating relationship and no consent"


_CARE_TEAM_SELECT = """
    SELECT a.id, a.patient_id, a.nurse_id, a.assigned_by, a.assigned_by_role, a.reason,
           a.created_at, a.expires_at,
           p.user_id AS patient_user_id, p.full_name AS patient_name,
           n.user_id AS nurse_user_id, n.full_name AS nurse_name,
           b.full_name AS assigned_by_name
      FROM CareTeamAssignments a
      JOIN Users p ON p.id = a.patient_id
      JOIN Users n ON n.id = a.nurse_id
      LEFT JOIN Users b ON b.id = a.assigned_by
     WHERE a.ended_at IS NULL AND (a.expires_at IS NULL OR a.expires_at > NOW())
"""


def _care_team_member(r: dict) -> CareTeamMember:
    return CareTeamMember(
        id=str(r["id"]), patient_id=str(r["patient_id"]), patient_user_id=r.get("patient_user_id"),
        patient_name=r.get("patient_name"), nurse_id=str(r["nurse_id"]),
        nurse_user_id=r.get("nurse_user_id"), nurse_name=r.get("nurse_name"),
        assigned_by_name=r.get("assigned_by_name"), assigned_by_role=r["assigned_by_role"],
        reason=r["reason"], created_at=r["created_at"], expires_at=r.get("expires_at"))


def _nurse_patient_authorization(cur, nurse_uuid: str, patient_uuid: str) -> tuple[bool, str, Optional[dict]]:
    """May this nurse open this patient's chart, and on what basis?

    Nursing access used to be a property of the role: any nurse could search
    every patient and open, annotate or medicate any of them. It is now a
    relationship (spec §4, §34) — an active care-team assignment:

      by an administrator   a ward allocation; stands on its own
      by a doctor           delegated, so it lasts only while that doctor's own
                            access does — a patient withdrawing the doctor also
                            withdraws the nurse that doctor brought in. A
                            doctor's break-glass is personal and is not passed on.

    Returns ``(allowed, basis, assignment)``.
    """
    cur.execute(_CARE_TEAM_SELECT + " AND a.patient_id = %s AND a.nurse_id = %s",
                (patient_uuid, nurse_uuid))
    assignment = cur.fetchone()
    if not assignment:
        return False, "not assigned to this patient's care team", None
    if assignment["assigned_by_role"] == "Administrator":
        return True, "care team (ward allocation)", assignment
    if not assignment["assigned_by"]:
        return False, "the assigning doctor's account no longer exists", assignment
    allowed, basis = _doctor_patient_authorization(cur, str(assignment["assigned_by"]), patient_uuid)
    if allowed and basis != "emergency override":
        return True, "care team (delegated by treating doctor)", assignment
    return False, "the doctor who assigned you no longer has access to this patient", assignment


def _require_nurse_access(cur, session: dict, patient_id: str, resource: str) -> tuple[str, Optional[dict]]:
    """Refuse — and record — a nurse acting outside their care team."""
    allowed, basis, assignment = _nurse_patient_authorization(cur, session["user_id"], patient_id)
    if not allowed:
        _deny(cur, session, resource=resource, reason=basis, patient_id=str(patient_id),
              detail=(f"You cannot open this patient's record — {basis}. A treating doctor "
                      "or an administrator can add you to the patient's care team."))
    return basis, assignment


def _doctor_access_blocked(cur, doctor_uuid: str, patient_uuid: str) -> bool:
    """True when the patient has revoked this doctor and no break-glass is live.

    An active emergency declaration overrides a revocation deliberately: in a
    genuine emergency the record must be reachable. The override is time-boxed
    and permanently recorded, so the cost of using it is that it is seen.
    """
    cur.execute(
        f"SELECT {_CONSENT_REVOKED} AS revoked, {_EMERGENCY_ACTIVE} AS emergency",
        (patient_uuid, doctor_uuid, patient_uuid, doctor_uuid),
    )
    row = cur.fetchone()
    return bool(row["revoked"]) and not bool(row["emergency"])


def _doctor_may_read_report(cur, doctor_uuid: str, report_id: str) -> Optional[dict]:
    """
    Fetch a report only if this doctor is entitled to it.

    Entitlement means the doctor either requested the investigation or has an
    existing clinical relationship with the patient (diagnosis, consultation or
    appointment). Anything else returns nothing, so an unrelated doctor cannot
    read a report by id.

    A clinical relationship is necessary but not sufficient: if the patient has
    revoked consent for this doctor, the report is withheld unless a live
    emergency declaration is in force.
    """
    report, allowed, _ = _doctor_report_access(cur, doctor_uuid, report_id)
    return report if allowed else None


def _doctor_report_access(cur, doctor_uuid: str, report_id: str) -> tuple[Optional[dict], bool, str]:
    """The report, and whether this doctor may read it — by the same test as the chart.

    Reports previously had their own, looser rule (any relationship, consent
    ignored) — two answers to one question. Returns ``(report, allowed, basis)``
    so a refusal can be recorded without revealing whether the report exists.
    """
    cur.execute(_REPORT_SELECT + " WHERE lr.id = %s", (report_id,))
    report = cur.fetchone()
    if not report:
        return None, False, "not found"
    allowed, basis = _doctor_patient_authorization(cur, doctor_uuid, str(report["patient_id"]))
    return report, allowed, basis


@app.post("/api/doctor/emergency-access")
def declare_emergency_access(
    req: EmergencyAccessRequest,
    request: Request,
    session: dict = Depends(require_role("Doctor")),
):
    """Break-glass override of a patient's consent decision (spec §9, §30).

    Not gated on a second party's approval: in an emergency, waiting for one
    defeats the purpose. The controls sit around the override instead, so it is
    restricted, purpose-bound and reviewed rather than a silent bypass:

      identity verification   the declarer re-enters their password
      rate limit              at most EMERGENCY_MAX_PER_DAY declarations a day
      AI risk assessment      scored like any access; HIGH is escalated, or
                              refused if RISK_POLICY_EMERGENCY_HIGH=block
      time box                1–24 hours, then it lapses on its own
      notification            the patient is told immediately
      blockchain              anchored, and recorded through the contract's own
                              emergencyAccess() entry point when a chain is up
      compliance record       an incident is opened for every override
    """
    user_uuid = session["user_id"]
    actor_pub = session.get("public_user_id")
    max_per_day = max(1, int(os.getenv("EMERGENCY_MAX_PER_DAY", "3")))
    expires_at = datetime.now(timezone.utc) + timedelta(hours=req.duration_hours)

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            # Identity verification. A session token alone may be stolen, or
            # left open on a shared ward terminal.
            cur.execute("SELECT password_hash FROM Users WHERE id = %s", (user_uuid,))
            me = cur.fetchone()
            if not me or not verify_password(req.password, me["password_hash"]):
                secresp.failed_login(cur, user_id=user_uuid, public_user_id=actor_pub,
                                     role="Doctor", ip_address=_client_ip(request))
                _deny(cur, session, resource="break_glass", reason="identity verification failed",
                      patient_id=str(req.patient_id), request=request,
                      detail="Password incorrect — emergency access was not granted.")
            # The password was just proven, which also satisfies a step-up.
            risk_engine.record_step_up(cur, user_uuid)

            cur.execute(
                "SELECT id, user_id, full_name FROM Users WHERE id = %s AND role = 'Patient'",
                (req.patient_id,),
            )
            patient = cur.fetchone()
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")

            cur.execute(
                """SELECT COUNT(*) AS n FROM EmergencyAccess
                    WHERE requester_id = %s AND created_at > NOW() - INTERVAL '24 hours'""",
                (user_uuid,))
            recent = cur.fetchone()["n"]
            if recent >= max_per_day:
                secresp.raise_alert(
                    cur, severity="HIGH", source=secresp.SOURCE_EMERGENCY, actor_id=user_uuid,
                    title=f"Emergency access limit reached — {actor_pub or 'unknown actor'}",
                    summary=(f"{actor_pub or 'A doctor'} attempted a further break-glass "
                             f"declaration after {recent} in 24 hours (limit {max_per_day})."),
                    response="ESCALATE", dedupe_minutes=24 * 60)
                _deny(cur, session, resource="break_glass", reason="emergency declaration limit reached",
                      patient_id=str(req.patient_id), status_code=429, request=request,
                      detail=(f"You have declared {recent} emergency accesses in the last 24 hours, "
                              "the configured maximum. An administrator has been alerted."))

            # AI risk assessment, under the emergency policy.
            decision = _security_gate(cur, session, resource="break_glass",
                                      patient_id=str(req.patient_id), emergency=True)

            cur.execute("""
                INSERT INTO EmergencyAccess (requester_id, patient_id, reason, status, expires_at,
                                             risk_level)
                VALUES (%s, %s, %s, 'Emergency', %s, %s)
                RETURNING emergency_access_id
            """, (user_uuid, req.patient_id, req.reason, expires_at, decision.level))
            access_id = cur.fetchone()["emergency_access_id"]

            # The patient is told at once. Break-glass that the patient only
            # discovers later is surveillance, not emergency care.
            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'EMERGENCY_ACCESS', 'Emergency access to your records',
                        'Dr. ' || %s || ' declared emergency access to your records until ' || %s ||
                        '. Stated reason: ' || %s)
            """, (
                req.patient_id, session.get("full_name", "A clinician"),
                expires_at.strftime("%d %b %Y %H:%M UTC"), req.reason,
            ))
            conn.commit()

        event_hash = sha256_hex(
            f"{access_id}|{user_uuid}|{req.patient_id}|{req.reason}".encode("utf-8"))
        anchor = anchor_document(
            conn,
            document_type="EmergencyAccess", document_id=str(access_id),
            document_hash=event_hash, action="EMERGENCY_ACCESS_DECLARED",
            patient_id=str(req.patient_id), actor_id=user_uuid, actor_public_id=actor_pub,
        )
        contract_tx = consent_ledger.emergency(doctor_id=user_uuid, patient_id=str(req.patient_id),
                                               resource_hash=event_hash)

        with conn.cursor(row_factory=dict_row) as cur:
            incident_ref = secresp.emergency_compliance_record(
                cur, actor_id=user_uuid, actor_public_id=actor_pub,
                patient_id=str(req.patient_id), emergency_id=str(access_id),
                risk_level=decision.level, risk_explanation=decision.narrative,
                tx_hash=anchor["tx_hash"])
            cur.execute(
                """UPDATE EmergencyAccess SET blockchain_tx_hash = %s, contract_tx_hash = %s,
                                              incident_ref = %s
                    WHERE emergency_access_id = %s""",
                (anchor["tx_hash"], contract_tx, incident_ref, access_id),
            )
            # Break-glass is rare by design, so its frequency is a strong signal.
            # The reason text is deliberately NOT forwarded: the AI layer scores
            # behaviour, and the clinical justification is none of its business.
            aisec.record_security_event(
                cur, actor_id=user_uuid, actor_public_id=actor_pub,
                actor_role="Doctor", event_type="EMERGENCY_ACCESS",
                subject_patient_id=str(req.patient_id), resource="break_glass",
                ip_address=_client_ip(request), metadata={"risk_level": decision.level})
            conn.commit()

        log_admin_action(
            conn, user_uuid, actor_pub,
            "EMERGENCY_ACCESS_DECLARED", str(req.patient_id), patient["user_id"],
            _client_ip(request),
            {"reason": req.reason, "expires_at": expires_at.isoformat(),
             "tx_hash": anchor["tx_hash"], "contract_tx_hash": contract_tx,
             "risk_level": decision.level, "incident_ref": incident_ref},
        )

    return {
        "status": "success",
        "emergency_access_id": str(access_id),
        "patient_user_id": patient["user_id"],
        "expires_at": expires_at.isoformat(),
        "blockchain_tx_hash": anchor["tx_hash"],
        "anchored_on": anchor["anchored_on"],
        "contract_tx_hash": contract_tx,
        "risk_level": decision.level,
        "incident_ref": incident_ref,
        "message": (
            f"Emergency access granted until {expires_at.strftime('%H:%M UTC')}. "
            f"The patient has been notified and compliance record {incident_ref} was opened."
        ),
    }


@app.get("/api/doctor/emergency-access")
def list_own_emergency_access(session: dict = Depends(require_role("Doctor"))):
    """Break-glass declarations this doctor has made."""
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT e.*, p.full_name AS patient_name, p.user_id AS patient_user_id
                FROM EmergencyAccess e
                JOIN Users p ON p.id = e.patient_id
                WHERE e.requester_id = %s
                ORDER BY e.created_at DESC
            """, (user_uuid,))
            rows = cur.fetchall()
    return [_emergency_record(r) for r in rows]


@app.get("/api/doctor/reports/{report_id}/download")
def download_doctor_lab_report(report_id: str, request: Request, session: dict = Depends(require_role("Doctor"))):
    """Release a report as PDF to a doctor entitled to read it."""
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            report, allowed, basis = _doctor_report_access(cur, user_uuid, report_id)
            if report is None:
                raise HTTPException(status_code=404, detail="Report not found or not authorised")
            if not allowed:
                # Same 404 as "no such report", so a refusal does not confirm the
                # report exists — but the attempt is recorded.
                _deny(cur, session, resource="lab_report", reason=basis,
                      patient_id=str(report["patient_id"]), status_code=404, request=request,
                      detail="Report not found or not authorised")
            decision = _security_gate(cur, session, resource="lab_report",
                                      patient_id=str(report["patient_id"]))

        pdf_bytes = _release_verified(
            conn, session, lambda: _decrypt_report_pdf(report), report,
            resource=f"LabReport {report.get('report_id_public') or report_id}",
            patient_id=str(report["patient_id"]))
        with conn.cursor(row_factory=dict_row) as cur:
            _record_access(cur, session, patient_id=str(report["patient_id"]),
                           resource="lab_report", basis=basis, decision=decision)
            conn.commit()

        anchor_document(
            conn, document_type="LabReport", document_id=str(report["id"]),
            document_hash=report.get("document_hash") or "", action="DOCTOR_ACCESSED_REPORT",
            patient_id=str(report["patient_id"]), actor_id=user_uuid,
            actor_public_id=session.get("public_user_id"),
            report_id_public=report.get("report_id_public"),
        )
        log_admin_action(
            conn, user_uuid, session.get("public_user_id"),
            "DOCTOR_DOWNLOADED_REPORT", str(report["patient_id"]), None,
            request.client.host if request and request.client else None,
            {"report_id": str(report["id"]), "report_no": report.get("report_id_public")},
        )

    filename = f"{report.get('report_id_public') or 'report'}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get("/api/doctor/reports/{report_id}/verify", response_model=ReportVerification)
def verify_doctor_lab_report(report_id: str, session: dict = Depends(require_role("Doctor"))):
    """Verify a report's digest and post-quantum signature."""
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            report, allowed, basis = _doctor_report_access(cur, user_uuid, report_id)
            if report is None:
                raise HTTPException(status_code=404, detail="Report not found or not authorised")
            if not allowed:
                _deny(cur, session, resource="lab_report", reason=basis,
                      patient_id=str(report["patient_id"]), status_code=404,
                      detail="Report not found or not authorised")
        return _verify_and_record(conn, session, report)

# ─── Lab Technician Dashboard Endpoints ────────────────────────────────────

@app.get("/api/lab-tech/profile")
def get_lab_tech_profile(session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
            
            cur.execute("SELECT COUNT(*) as cnt FROM LabReports WHERE lab_tech_id = %s", (user_uuid,))
            reports_cnt = cur.fetchone()["cnt"]
            
    if not user:
        raise HTTPException(status_code=404, detail="Lab Technician not found")
        
    return LabTechProfile(
        id=str(user["id"]), user_id=user["user_id"], full_name=user["full_name"],
        email=user["email"], role=user["role"], gender=user["gender"],
        department="Central Laboratory", reports_generated=reports_cnt,
        status=user["status"], created_at=user["created_at"]
    )

@app.get("/api/lab-tech/dashboard/summary")
def get_lab_tech_dashboard_summary(session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM LabTestRequests WHERE requested_date::date = CURRENT_DATE")
            tests_assigned = cur.fetchone()["cnt"]
            
            cur.execute("SELECT COUNT(*) as cnt FROM LabReports WHERE lab_tech_id = %s AND created_at::date = CURRENT_DATE", (user_uuid,))
            reports_generated = cur.fetchone()["cnt"]
            
            cur.execute("SELECT COUNT(*) as cnt FROM LabTestRequests WHERE status = 'Pending'")
            pending_requests = cur.fetchone()["cnt"]
            
            cur.execute("SELECT COUNT(*) as cnt FROM LabReports WHERE lab_tech_id = %s", (user_uuid,))
            reports_shared = cur.fetchone()["cnt"]
            
            cur.execute("SELECT COUNT(*) as cnt FROM LabReports WHERE status = 'Pending' AND lab_tech_id = %s", (user_uuid,))
            reports_awaiting = cur.fetchone()["cnt"]
            
            cur.execute("SELECT title, body, created_at FROM Notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 5", (user_uuid,))
            activities = cur.fetchall()
            
    return LabTechDashboardSummary(
        tests_assigned_today=tests_assigned, reports_generated_today=reports_generated,
        pending_test_requests=pending_requests, reports_shared=reports_shared,
        reports_awaiting_review=reports_awaiting,
        recent_activities=[{"title": a["title"], "body": a["body"], "created_at": a["created_at"].isoformat() if a["created_at"] else None} for a in activities]
    )

@app.get("/api/lab-tech/requests")
def get_lab_test_requests(status: Optional[str] = None, session: dict = Depends(require_role("Lab Technician"))):
    """Test requests queue. Includes the panel so the correct form can be opened."""
    query = """
        SELECT r.*, p.full_name as patient_name, p.user_id as patient_user_id,
               d.full_name as doctor_name, d.user_id as doctor_user_id,
               lr.id AS report_id, lr.report_id_public AS report_no
        FROM LabTestRequests r
        JOIN Users p ON r.patient_id = p.id
        LEFT JOIN Users d ON r.doctor_id = d.id
        LEFT JOIN LabReports lr ON lr.lab_request_id = r.id
    """
    params: list = []
    if status:
        query += " WHERE r.status = %s"
        params.append(status)
    query += " ORDER BY CASE r.priority WHEN 'Emergency' THEN 0 WHEN 'Urgent' THEN 1 ELSE 2 END, r.requested_date DESC"

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [LabTestRequestItem(
        id=str(r["id"]), patient_id=str(r["patient_id"]), patient_name=r["patient_name"],
        patient_user_id=r["patient_user_id"],
        doctor_id=str(r["doctor_id"]) if r.get("doctor_id") else None,
        doctor_name=r["doctor_name"], doctor_user_id=r.get("doctor_user_id"),
        test_name=r["test_name"], panel_code=r.get("panel_code"),
        priority=r["priority"], status=r["status"],
        clinical_notes=r["clinical_notes"], requested_date=r["requested_date"],
        report_id=str(r["report_id"]) if r.get("report_id") else None,
        report_no=r.get("report_no"),
    ) for r in rows]


@app.get("/api/lab-tech/requests/{request_id}")
def get_lab_test_request_detail(request_id: str, session: dict = Depends(require_role("Lab Technician"))):
    """
    One request with the patient context needed to fill its report.

    Patient demographics are returned from the record so the technician never
    re-types them, which is also what keeps the printed report consistent with
    the patient file.
    """
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT r.*, p.id AS pid, p.user_id AS patient_user_id, p.full_name AS patient_name,
                       p.gender, p.date_of_birth_encrypted, p.blood_group_encrypted,
                       p.mlkem_public_key,
                       d.full_name AS doctor_name, d.user_id AS doctor_user_id, d.specialization,
                       lr.id AS report_id, lr.report_id_public AS report_no
                FROM LabTestRequests r
                JOIN Users p ON r.patient_id = p.id
                LEFT JOIN Users d ON r.doctor_id = d.id
                LEFT JOIN LabReports lr ON lr.lab_request_id = r.id
                WHERE r.id = %s
            """, (request_id,))
            r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Test request not found")

    return {
        "id": str(r["id"]),
        "test_name": r["test_name"],
        "panel_code": r.get("panel_code"),
        "priority": r["priority"],
        "status": r["status"],
        "clinical_notes": r["clinical_notes"],
        "requested_date": r["requested_date"],
        "report_id": str(r["report_id"]) if r.get("report_id") else None,
        "report_no": r.get("report_no"),
        "patient": {
            "id": str(r["pid"]),
            "user_id": r["patient_user_id"],
            "full_name": r["patient_name"],
            "gender": r.get("gender"),
            "date_of_birth": decrypt_data(r["date_of_birth_encrypted"]) if r.get("date_of_birth_encrypted") else None,
            "age_display": _age_display(decrypt_data(r["date_of_birth_encrypted"]) if r.get("date_of_birth_encrypted") else None),
            "blood_group": decrypt_data(r["blood_group_encrypted"]) if r.get("blood_group_encrypted") else None,
            "pqc_ready": bool(r.get("mlkem_public_key")),
        },
        "doctor": {
            "full_name": r.get("doctor_name"),
            "user_id": r.get("doctor_user_id"),
            "specialization": r.get("specialization"),
        } if r.get("doctor_name") else None,
    }


@app.post("/api/lab-tech/requests/{request_id}/status")
def update_lab_test_request_status(request_id: str, payload: dict = Body(...), session: dict = Depends(require_role("Lab Technician"))):
    """Advance a request through the queue: Accepted → In Progress → Completed.

    'Completed' is set by finalising a report, not by hand, so the status can
    never claim a report exists when none was filed.
    """
    new_status = payload.get("status")
    if new_status not in ("Accepted", "In Progress"):
        raise HTTPException(
            status_code=400,
            detail="Status must be 'Accepted' or 'In Progress'. A request is completed by finalising its report.",
        )

    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT status, accepted_by, patient_id FROM LabTestRequests WHERE id = %s",
                        (request_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Test request not found")
            if existing["status"] == "Completed":
                raise HTTPException(status_code=409, detail="This request is already completed.")
            # A request belongs to the technician who accepted it. Another
            # technician advancing it would leave nobody accountable for it.
            if existing["accepted_by"] and str(existing["accepted_by"]) != str(user_uuid):
                _deny(cur, session, resource="lab_request", reason="request held by another technician",
                      patient_id=str(existing["patient_id"]), status_code=409,
                      detail="Another technician has already accepted this request.")

            cur.execute("""
                UPDATE LabTestRequests
                SET status = %s,
                    accepted_by = COALESCE(accepted_by, %s),
                    accepted_at = COALESCE(accepted_at, CURRENT_TIMESTAMP),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (new_status, user_uuid, request_id))
            conn.commit()
    return {"status": "success", "new_status": new_status}


@app.get("/api/lab-tech/patients/search")
def search_patients(q: str, session: dict = Depends(require_role("Lab Technician"))):
    if len(q) < 2:
        return []
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, user_id, full_name, email, gender,
                       blood_group_encrypted, date_of_birth_encrypted
                FROM Users
                WHERE role = 'Patient' AND status = 'Approved'
                  AND (full_name ILIKE %s OR user_id ILIKE %s)
                ORDER BY full_name ASC
                LIMIT 20
            """, (f"%{q}%", f"%{q}%"))
            rows = cur.fetchall()

    # Blood group and age are decrypted here because a technician needs both to
    # interpret results against the correct reference ranges.
    return [{
        "id": str(r["id"]),
        "user_id": r["user_id"],
        "full_name": r["full_name"],
        "email": r["email"],
        "gender": r["gender"],
        "blood_group": decrypt_data(r["blood_group_encrypted"]) if r.get("blood_group_encrypted") else None,
        "age": _age_display(decrypt_data(r["date_of_birth_encrypted"]) if r.get("date_of_birth_encrypted") else None) or None,
    } for r in rows]

@app.get("/api/lab-tech/report-templates")
def get_report_templates(session: dict = Depends(require_role("Lab Technician"))):
    """Catalogue of investigations the technician can report on."""
    return list_panels()


@app.get("/api/lab-tech/report-templates/{panel_code}")
def get_report_template(panel_code: str, session: dict = Depends(require_role("Lab Technician"))):
    """Full form definition for one investigation, used to render its data-entry form."""
    panel = get_panel(panel_code)
    if not panel:
        raise HTTPException(status_code=404, detail="Unknown investigation panel")
    return panel


def _age_display(dob_text: Optional[str]) -> str:
    """Render a date of birth as the 'NN Y' age laboratories print."""
    if not dob_text:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            born = datetime.strptime(dob_text.strip(), fmt).date()
            break
        except ValueError:
            continue
    else:
        return ""
    today = date.today()
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    return f"{years} Y"


def _load_report_subject(cur, req: CreateStructuredLabReportRequest, tech_uuid: str) -> dict:
    """
    Resolve which patient, doctor and request this report belongs to.

    Binding is deliberately strict. When a request_id is supplied the patient
    and referring doctor come from that request and nothing else, so a report
    cannot be filed against the wrong patient. A patient_id is honoured only
    for a direct walk-in report, and must resolve to exactly one approved
    patient — never a "first patient we could find" fallback.
    """
    if req.request_id:
        cur.execute("""
            SELECT r.id AS request_id, r.status, r.test_name, r.panel_code AS requested_panel,
                   r.requested_date, r.doctor_id, r.accepted_by,
                   p.id AS patient_id, p.user_id AS patient_user_id, p.full_name AS patient_name,
                   p.gender, p.date_of_birth_encrypted, p.blood_group_encrypted,
                   p.mlkem_public_key,
                   d.full_name AS doctor_name, d.user_id AS doctor_user_id, d.specialization
            FROM LabTestRequests r
            JOIN Users p ON r.patient_id = p.id
            LEFT JOIN Users d ON r.doctor_id = d.id
            WHERE r.id = %s
        """, (req.request_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Test request not found")
        if row["status"] == "Completed":
            raise HTTPException(status_code=409, detail="A report has already been filed for this request.")

        cur.execute("SELECT id FROM LabReports WHERE lab_request_id = %s", (req.request_id,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="A report has already been filed for this request.")
        return row

    cur.execute("""
        SELECT NULL::uuid AS request_id, NULL AS status, NULL AS test_name,
               NULL AS requested_panel, NULL AS requested_date, NULL::uuid AS doctor_id,
               NULL::uuid AS accepted_by,
               p.id AS patient_id, p.user_id AS patient_user_id, p.full_name AS patient_name,
               p.gender, p.date_of_birth_encrypted, p.blood_group_encrypted,
               p.mlkem_public_key,
               NULL AS doctor_name, NULL AS doctor_user_id, NULL AS specialization
        FROM Users p
        WHERE p.role = 'Patient' AND p.status = 'Approved'
          AND (p.id::text = %s OR p.user_id = %s)
    """, (req.patient_id, req.patient_id))
    rows = cur.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Patient not found or not an approved patient account")
    if len(rows) > 1:
        raise HTTPException(status_code=409, detail="Patient identifier is ambiguous")
    return rows[0]


@app.post("/api/lab-tech/reports/create", response_model=FinalizedReportResponse)
def create_structured_lab_report(
    req: CreateStructuredLabReportRequest,
    request: Request,
    session: dict = Depends(require_role("Lab Technician")),
):
    """
    Finalise a laboratory report.

    Runs the full pipeline: render the hospital-format PDF, hash it, encrypt it
    under a fresh AES-256 key, protect that key with the patient's ML-KEM
    public key, sign the digest with the technician's ML-DSA private key, store
    the ciphertext in cloud storage, anchor the digest for audit, and notify
    the patient and referring doctor. Once written the report is locked.
    """
    tech_uuid = session["user_id"]

    panel = get_panel(req.panel_code)
    if not panel:
        raise HTTPException(status_code=400, detail=f"Unknown investigation panel '{req.panel_code}'")

    if not pqc_available():
        raise HTTPException(
            status_code=503,
            detail="Post-quantum cryptography is unavailable; refusing to issue an unsigned medical report.",
        )

    # Keep only the fields this panel actually defines, then fill in the values
    # a real analyser derives rather than measures.
    if panel.get("layout") == "narrative":
        allowed = {f["key"] for s in panel.get("sections", []) for f in s.get("fields", [])}
        allowed |= {m["key"] for m in panel.get("measurements", [])}
    else:
        allowed = {a["key"] for a in analytes_of(panel)}
    values = {k: v for k, v in (req.values or {}).items() if k in allowed and str(v).strip() != ""}
    if not values:
        raise HTTPException(status_code=400, detail="No results were supplied for this investigation.")
    values = apply_computed(panel["code"], values)

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            subject = _load_report_subject(cur, req, tech_uuid)

            # Spec §11: a report must answer the request it claims to — the
            # investigation that was ordered, filed by the technician who took
            # it. The requested panel was loaded but never compared, so any
            # result could be filed against any order.
            if subject.get("request_id"):
                if subject.get("requested_panel") and subject["requested_panel"] != panel["code"]:
                    raise HTTPException(
                        status_code=409,
                        detail=(f"This request is for {subject['requested_panel']}, not "
                                f"{panel['code']}. File the investigation that was ordered."))
                holder = subject.get("accepted_by")
                if holder and str(holder) != str(tech_uuid):
                    _deny(cur, session, resource="lab_request",
                          reason="report filed against another technician's request",
                          patient_id=str(subject["patient_id"]), status_code=409,
                          detail="Another technician has accepted this request.")
                if not holder:
                    # Filing an unaccepted request claims it, as accepting would.
                    cur.execute(
                        """UPDATE LabTestRequests
                              SET accepted_by = %s, accepted_at = COALESCE(accepted_at, CURRENT_TIMESTAMP)
                            WHERE id = %s AND accepted_by IS NULL""",
                        (tech_uuid, subject["request_id"]))

            cur.execute(
                "SELECT id, user_id, full_name, mldsa_private_key_encrypted FROM Users WHERE id = %s",
                (tech_uuid,),
            )
            technician = cur.fetchone()

            patient_uuid = subject["patient_id"]
            doctor_uuid = subject["doctor_id"]

            if not subject.get("mlkem_public_key"):
                raise HTTPException(
                    status_code=409,
                    detail="Patient has no ML-KEM public key on record; report cannot be secured.",
                )
            if not technician or not technician.get("mldsa_private_key_encrypted"):
                raise HTTPException(
                    status_code=409,
                    detail="Technician has no ML-DSA signing key on record; report cannot be signed.",
                )

            report_no, accession = generate_report_number()
            reported_at = datetime.now(timezone.utc)
            collected_at = req.collected_at or subject.get("requested_date")

            doctor_block = None
            if subject.get("doctor_name"):
                display = f"Dr. {subject['doctor_name']}"
                if subject.get("specialization"):
                    display += f", {subject['specialization']}"
                doctor_block = {"display": display, "user_id": subject.get("doctor_user_id")}

            patient_block = {
                "full_name": subject["patient_name"],
                "user_id": subject["patient_user_id"],
                "gender": subject.get("gender") or "",
                "age_display": _age_display(decrypt_data(subject["date_of_birth_encrypted"])
                                            if subject.get("date_of_birth_encrypted") else None),
                "blood_group": decrypt_data(subject["blood_group_encrypted"])
                               if subject.get("blood_group_encrypted") else None,
            }

            interpretation = interpretation_for(panel["code"], values, patient_block["gender"])

            # 1. Render the hospital-format document.
            pdf_bytes = build_report_pdf(
                panel=panel, values=values,
                patient=patient_block, doctor=doctor_block,
                technician={"full_name": technician["full_name"], "user_id": technician["user_id"]},
                report_no=report_no, accession=accession,
                collected_at=collected_at, reported_at=reported_at,
                remarks=req.remarks, interpretation=interpretation,
                signature_algorithm=ML_DSA_ALG, kem_algorithm=ML_KEM_ALG,
            )

            # 2-4. Hash → AES-256-GCM encrypt → protect the AES key with ML-KEM
            #      → sign the digest with ML-DSA.
            try:
                document_hash = sha256_hex(pdf_bytes)
                kem_ciphertext, shared_secret = encapsulate_aes_key(subject["mlkem_public_key"])
                aes_key = derive_aes_key(shared_secret)
                encrypted = encrypt_document(pdf_bytes, aes_key)
                signature = sign_document_hash(document_hash, technician["mldsa_private_key_encrypted"])
            except PQCUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            # 5. Store only the ciphertext in cloud storage.
            ipfs_cid, s3_key = store_encrypted_document(
                encrypted["ciphertext"].encode("utf-8"), f"{report_no}_{panel['code']}"
            )

            # 6. Persist, permanently linked to request + patient + doctor + technician.
            cur.execute("""
                INSERT INTO LabReports (
                    patient_id, uploaded_by, lab_tech_id, doctor_id, lab_request_id,
                    report_name, report_type, panel_code, report_id_public, accession_number,
                    structured_data, interpretation, remarks,
                    document_hash, encrypted_aes_key, encryption_nonce, encryption_tag,
                    encrypted_document, digital_signature, kem_algorithm, signature_algorithm,
                    ipfs_cid, s3_key, collected_at, finalized_at, is_locked, status
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, TRUE, 'Completed'
                ) RETURNING id
            """, (
                patient_uuid, tech_uuid, tech_uuid, doctor_uuid, subject.get("request_id"),
                panel["name"], panel["db_report_type"], panel["code"], report_no, accession,
                json.dumps(values), interpretation, req.remarks,
                document_hash, kem_ciphertext, encrypted["nonce"], encrypted["tag"],
                encrypted["ciphertext"], signature, ML_KEM_ALG, ML_DSA_ALG,
                ipfs_cid, s3_key, collected_at, reported_at,
            ))
            report_id = cur.fetchone()["id"]

            if subject.get("request_id"):
                cur.execute("""
                    UPDATE LabTestRequests
                    SET status = 'Completed', completed_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (subject["request_id"],))

            # 7. Notify the patient and the requesting doctor. Neither message
            #    carries a result value — only that a report is available.
            notified: list[str] = []
            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'REPORT_READY', %s, %s)
            """, (
                patient_uuid, "New laboratory report available",
                f"Your {panel['short_name']} report ({report_no}) is now available in your medical records.",
            ))
            notified.append(subject["patient_user_id"])

            if doctor_uuid:
                cur.execute("""
                    INSERT INTO Notifications (user_id, notification_type, title, body)
                    VALUES (%s, 'REPORT_READY', %s, %s)
                """, (
                    doctor_uuid, "Requested laboratory report ready",
                    f"The {panel['short_name']} you requested for patient "
                    f"{subject['patient_user_id']} is ready for review (Report {report_no}).",
                ))
                notified.append(subject.get("doctor_user_id"))

            aisec.record_security_event(
                cur, actor_id=tech_uuid, actor_public_id=session.get("public_user_id"),
                actor_role="Lab Technician", event_type="LAB_REPORT_UPLOADED",
                subject_patient_id=str(patient_uuid), resource=f"LabReport {report_no}",
                ip_address=_client_ip(request), metadata={"panel": panel["code"]})
            conn.commit()

        # 8. Anchor the digest for the audit trail (identifiers + hash only).
        anchor = anchor_document(
            conn,
            document_type="LabReport", document_id=str(report_id),
            document_hash=document_hash, action="REPORT_FINALIZED",
            patient_id=str(patient_uuid), actor_id=tech_uuid,
            actor_public_id=session.get("public_user_id"), report_id_public=report_no,
        )

        with conn.cursor() as cur:
            cur.execute("UPDATE LabReports SET blockchain_tx_hash = %s WHERE id = %s",
                        (anchor["tx_hash"], report_id))
            conn.commit()

        log_admin_action(
            conn, tech_uuid, session.get("public_user_id"),
            "LAB_REPORT_FINALIZED", str(patient_uuid), subject["patient_user_id"],
            request.client.host if request and request.client else None,
            {"report_id": str(report_id), "report_no": report_no, "panel": panel["code"],
             "document_hash": document_hash, "tx_hash": anchor["tx_hash"]},
        )

    return FinalizedReportResponse(
        status="success",
        report_id=str(report_id), report_no=report_no, accession=accession,
        panel_code=panel["code"], patient_user_id=subject["patient_user_id"],
        document_hash=document_hash,
        signature_algorithm=ML_DSA_ALG, kem_algorithm=ML_KEM_ALG,
        blockchain_tx_hash=anchor["tx_hash"], anchored_on=anchor["anchored_on"],
        ipfs_cid=ipfs_cid, s3_key=s3_key,
        notified=[n for n in notified if n],
    )


def _decrypt_report_pdf(report: dict) -> bytes:
    """
    Recover the plaintext PDF for an authorised reader.

    The AES key is released only by decapsulating the stored ML-KEM ciphertext
    with the patient's private key, so possession of the ciphertext alone is
    not enough. GCM's tag check then proves the stored bytes were not altered.
    """
    ciphertext = report.get("encrypted_document")

    # The database holds the authoritative copy. If it is missing, fall back to
    # the S3 copy of the same ciphertext — that redundancy is the reason the
    # cloud copy exists. The GCM tag check below still has to pass either way,
    # so a substituted or corrupted object cannot slip through.
    if not ciphertext and report.get("s3_key"):
        try:
            ciphertext = download_file_from_s3(report["s3_key"]).decode("utf-8")
            logger.warning(
                "Report %s recovered from S3; database copy was missing.", report.get("id")
            )
        except StorageError as exc:
            logger.error("S3 recovery failed for report %s: %s", report.get("id"), exc)

    if not ciphertext:
        raise HTTPException(status_code=404, detail="No encrypted document is stored for this report.")
    if not report.get("mlkem_private_key_encrypted"):
        raise HTTPException(status_code=409, detail="Patient decryption key unavailable.")

    try:
        shared_secret = decapsulate_aes_key(
            report["encrypted_aes_key"], report["mlkem_private_key_encrypted"]
        )
        aes_key = derive_aes_key(shared_secret)
        pdf_bytes = decrypt_document(
            ciphertext, aes_key,
            report["encryption_nonce"], report["encryption_tag"],
        )
    except PQCUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        # GCM authentication failed: the stored ciphertext does not match its tag.
        logger.error("Integrity failure decrypting report %s: %s", report.get("id"), exc)
        raise _IntegrityFailure(
            status_code=409,
            detail="Report failed its integrity check and was not released.",
        ) from exc
    except Exception as exc:
        logger.error("Failed to decrypt report %s: %s", report.get("id"), exc)
        raise HTTPException(status_code=500, detail="Unable to decrypt this report.") from exc

    if sha256_hex(pdf_bytes) != report.get("document_hash"):
        raise _IntegrityFailure(
            status_code=409,
            detail="Report digest does not match the recorded hash; release withheld.",
        )
    return pdf_bytes


def _verify_against_chain(report: dict) -> Optional[bool]:
    """Compare the stored digest against the one anchored on-chain.

    This is the check the database cannot fake: even an attacker who rewrites
    ``document_hash`` in Postgres cannot alter the digest already committed to
    the chain, so the two stop agreeing.

    Returns True/False when an on-chain anchor exists and could be read, or
    None when the report was only locally anchored or the chain is unreachable
    (unknown, which must not be reported as "verified").
    """
    from app.chain_client import get_chain_client

    tx_hash = report.get("blockchain_tx_hash")
    anchored_on = report.get("anchored_on")
    if not tx_hash or not anchored_on or anchored_on == "local-simulated":
        return None

    client = get_chain_client()
    if client is None:
        return None

    try:
        if not tx_hash.startswith("0x"):          # rows written by older web3 releases
            tx_hash = "0x" + tx_hash
        receipt = client.web3.eth.get_transaction_receipt(tx_hash)
        # The contract emits AuditLogged(userUUID, actionType, resourceHash, ts);
        # resourceHash is the document digest we anchored.
        events = client.contract.events.AuditLogged().process_receipt(receipt)
        if not events:
            return False
        return any(e["args"]["resourceHash"] == report.get("document_hash") for e in events)
    except Exception as exc:
        logger.error("On-chain verification failed for %s: %s", report.get("id"), exc)
        return None


def _verify_report(report: dict) -> ReportVerification:
    """Check a stored report's digest, ML-DSA signature, and on-chain anchor."""
    hash_matches = False
    detail = "Signature could not be verified."

    try:
        pdf_bytes = _decrypt_report_pdf(report)
        hash_matches = sha256_hex(pdf_bytes) == report.get("document_hash")
    except _IntegrityFailure as exc:
        detail = str(exc.detail)
        report["_integrity_failed"] = True
    except HTTPException as exc:
        detail = str(exc.detail)

    signature_valid = verify_mldsa_signature(
        report.get("document_hash") or "",
        report.get("digital_signature") or "",
        report.get("signer_mldsa_public_key") or "",
    )

    blockchain_verified = _verify_against_chain(report)

    if hash_matches and signature_valid:
        detail = ("Document digest matches and the ML-DSA signature is valid. "
                  "The report is authentic and unaltered.")
        if blockchain_verified is True:
            detail += " The digest also matches the immutable blockchain anchor."
        elif blockchain_verified is False:
            detail = ("INTEGRITY ALERT: the stored digest does not match the digest "
                      "anchored on the blockchain. This report may have been altered.")
    elif hash_matches and not signature_valid:
        detail = "Document is intact but its signature could not be validated."

    return ReportVerification(
        report_id=str(report["id"]), report_no=report.get("report_id_public"),
        document_hash=report.get("document_hash"),
        hash_matches=hash_matches, signature_valid=signature_valid,
        blockchain_verified=blockchain_verified,
        signature_algorithm=report.get("signature_algorithm"),
        kem_algorithm=report.get("kem_algorithm"),
        signed_by=report.get("signer_name"),
        blockchain_tx_hash=report.get("blockchain_tx_hash"),
        anchored_on=report.get("anchored_on"),
        verified_at=datetime.now(timezone.utc), detail=detail,
    )


def _verify_and_record(conn, session: dict, report: dict) -> ReportVerification:
    """Verify a report, and report any failure to Alert & Response (spec §24).

    Verification is the moment tampering is discovered, so a failed check must
    open an incident rather than only render red text to whoever clicked.
    """
    result = _verify_report(report)
    resource = f"LabReport {report.get('report_id_public') or report.get('id')}"
    patient_id = str(report.get("patient_id"))
    actor = {"actor_id": session.get("user_id"), "actor_public_id": session.get("public_user_id"),
             "actor_role": session.get("role")}
    with conn.cursor(row_factory=dict_row) as cur:
        if report.get("_integrity_failed"):
            secresp.integrity_failure(cur, resource=resource, detail=result.detail,
                                      patient_id=patient_id, **actor)
        elif result.blockchain_verified is False:
            secresp.integrity_failure(
                cur, resource=resource, patient_id=patient_id, **actor,
                detail="The stored digest differs from the digest anchored on the blockchain.")
        if pqc_available() and report.get("digital_signature") and not result.signature_valid:
            secresp.signature_failure(
                cur, resource=resource, patient_id=patient_id, **actor,
                detail="The ML-DSA signature does not verify against the signer's public key.")
        aisec.record_security_event(
            cur, event_type="REPORT_VERIFIED", subject_patient_id=patient_id, resource="lab_report",
            metadata={"hash_matches": result.hash_matches, "signature_valid": result.signature_valid,
                      "blockchain_verified": result.blockchain_verified}, **actor)
        conn.commit()
    return result


_REPORT_SELECT = """
    SELECT lr.*, u.mlkem_private_key_encrypted,
           tech.mldsa_public_key AS signer_mldsa_public_key,
           tech.full_name AS signer_name,
           (SELECT anchored_on FROM DocumentAnchors
             WHERE document_id = lr.id ORDER BY created_at DESC LIMIT 1) AS anchored_on
    FROM LabReports lr
    JOIN Users u ON lr.patient_id = u.id
    LEFT JOIN Users tech ON lr.lab_tech_id = tech.id
"""


@app.get("/api/lab-tech/reports")
def get_lab_tech_reports(session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT lr.*, u.full_name as uploaded_by_name,
                       (SELECT anchored_on FROM DocumentAnchors
                         WHERE document_id = lr.id ORDER BY created_at DESC LIMIT 1) AS anchored_on
                FROM LabReports lr
                LEFT JOIN Users u ON lr.patient_id = u.id
                WHERE lr.lab_tech_id = %s OR lr.uploaded_by = %s
                ORDER BY lr.upload_date DESC
            """, (user_uuid, user_uuid))
            rows = cur.fetchall()

    return [LabReportItem(
        id=str(r["id"]), report_name=r["report_name"], report_type=r["report_type"],
        report_id_public=r["report_id_public"], findings=r["findings"],
        normal_range=r["normal_range"], status=r["status"],
        uploaded_by_name=r["uploaded_by_name"],  # Reusing for patient name in tech view
        upload_date=r["upload_date"],
        document_hash=r.get("document_hash"),
        blockchain_tx_hash=r.get("blockchain_tx_hash"),
        anchored_on=r.get("anchored_on"),
        ipfs_cid=r.get("ipfs_cid"),
        s3_key=r.get("s3_key"),
        kem_algorithm=r.get("kem_algorithm"),
        signature_algorithm=r.get("signature_algorithm"),
    ) for r in rows]

@app.get("/api/lab-tech/reports/{report_id}")
def get_lab_tech_report_detail(report_id: str, session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT lr.*, u.full_name as patient_name, u.user_id as patient_user_id
                FROM LabReports lr
                LEFT JOIN Users u ON lr.patient_id = u.id
                WHERE lr.id = %s AND (lr.lab_tech_id = %s OR lr.uploaded_by = %s)
            """, (report_id, user_uuid, user_uuid))
            r = cur.fetchone()
            
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
        
    return {
        "id": str(r["id"]), "report_name": r["report_name"], "report_type": r["report_type"],
        "patient_name": r["patient_name"], "patient_user_id": r["patient_user_id"],
        "findings": r["findings"], "normal_range": r["normal_range"],
        "structured_data": r.get("structured_data"),
        "document_hash": r.get("document_hash"),
        "digital_signature": r.get("digital_signature"),
        "blockchain_tx_hash": r.get("blockchain_tx_hash"),
        "ipfs_cid": r.get("ipfs_cid"),
        "s3_key": r.get("s3_key"),
        "status": r["status"], "upload_date": r["upload_date"]
    }


@app.get("/api/lab-tech/reports/{report_id}/download")
def download_lab_tech_report(report_id: str, request: Request, session: dict = Depends(require_role("Lab Technician"))):
    """Release a report as PDF to the technician who produced it.

    Scoped to their own work, exactly like the list view — a technician can
    re-open what they issued, not the whole laboratory's output.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                _REPORT_SELECT + " WHERE lr.id = %s AND (lr.lab_tech_id = %s OR lr.uploaded_by = %s)",
                (report_id, user_uuid, user_uuid),
            )
            report = cur.fetchone()

        if not report:
            raise HTTPException(status_code=404, detail="Report not found or not authorised")

        pdf_bytes = _release_verified(
            conn, session, lambda: _decrypt_report_pdf(report), report,
            resource=f"LabReport {report.get('report_id_public') or report_id}",
            patient_id=str(report["patient_id"]))

        anchor_document(
            conn, document_type="LabReport", document_id=str(report["id"]),
            document_hash=report.get("document_hash") or "", action="TECHNICIAN_ACCESSED_REPORT",
            patient_id=str(report["patient_id"]), actor_id=user_uuid,
            actor_public_id=session.get("public_user_id"),
            report_id_public=report.get("report_id_public"),
        )

    filename = f"{report.get('report_id_public') or 'report'}.pdf"
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.post("/api/lab-tech/imaging/upload")
def upload_imaging_report(
    req: CreateImagingReportRequest,
    request: Request,
    session: dict = Depends(require_role("Lab Technician")),
):
    """Store an imaging study under the same hybrid protection as lab reports.

    The image is AES-256-GCM encrypted, its key is protected with the patient's
    ML-KEM public key, the digest is signed with the technician's ML-DSA key,
    and only ciphertext is written to cloud storage. The previous version
    uploaded the raw image and — when no image was supplied — 32 random bytes
    standing in for one, which put unencrypted medical content in the bucket.
    """
    user_uuid = session["user_id"]

    if not req.image_data:
        raise HTTPException(status_code=400, detail="image_data is required.")

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, user_id, full_name, mlkem_public_key FROM Users WHERE id = %s AND role = 'Patient'",
                (req.patient_id,),
            )
            patient = cur.fetchone()
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")
            if not patient["mlkem_public_key"]:
                raise HTTPException(
                    status_code=409,
                    detail="Patient has no ML-KEM public key; the study cannot be protected.",
                )

            cur.execute("SELECT mldsa_private_key_encrypted FROM Users WHERE id = %s", (user_uuid,))
            technician = cur.fetchone()

            image_bytes = req.image_data.encode("utf-8")
            document_hash = sha256_hex(image_bytes)

            try:
                kem_ciphertext, shared_secret = encapsulate_aes_key(patient["mlkem_public_key"])
                aes_key = derive_aes_key(shared_secret)
                encrypted = encrypt_document(image_bytes, aes_key)
                signature = sign_document_hash(document_hash, technician["mldsa_private_key_encrypted"])
            except PQCUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            # Only ciphertext leaves the process.
            ipfs_cid, s3_key = store_encrypted_document(
                encrypted["ciphertext"].encode("utf-8"), f"{req.exam_type}_{req.scan_region}"
            )

            cur.execute("""
                INSERT INTO ImagingReports (
                    patient_id, lab_tech_id, scan_region, exam_type, clinical_history,
                    findings, impression, recommendations,
                    encrypted_image, encrypted_aes_key, encryption_nonce, encryption_tag,
                    document_hash, digital_signature, kem_algorithm, signature_algorithm,
                    ipfs_cid, s3_key
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                req.patient_id, user_uuid, req.scan_region, req.exam_type, req.clinical_history,
                req.findings, req.impression, req.recommendations,
                encrypted["ciphertext"], kem_ciphertext, encrypted["nonce"], encrypted["tag"],
                document_hash, signature, ML_KEM_ALG, ML_DSA_ALG,
                ipfs_cid, s3_key,
            ))
            imaging_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'IMAGING_READY', 'New Imaging Report Available',
                        'Your ' || %s || ' (' || %s || ') study is ready to view.')
            """, (req.patient_id, req.exam_type, req.scan_region))
            conn.commit()

        anchor = anchor_document(
            conn,
            document_type="ImagingReport", document_id=str(imaging_id),
            document_hash=document_hash, action="IMAGING_FINALIZED",
            patient_id=str(req.patient_id), actor_id=user_uuid,
            actor_public_id=session.get("public_user_id"),
        )

        with conn.cursor() as cur:
            cur.execute("UPDATE ImagingReports SET blockchain_tx_hash = %s WHERE id = %s",
                        (anchor["tx_hash"], imaging_id))
            conn.commit()

    return {
        "status": "success",
        "imaging_id": str(imaging_id),
        "patient_user_id": patient["user_id"],
        "document_hash": document_hash,
        "kem_algorithm": ML_KEM_ALG,
        "signature_algorithm": ML_DSA_ALG,
        "blockchain_tx_hash": anchor["tx_hash"],
        "anchored_on": anchor["anchored_on"],
        "ipfs_cid": ipfs_cid,
        "s3_key": s3_key,
    }


@app.get("/api/lab-tech/imaging")
def get_imaging_reports(session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT ir.*, u.full_name as patient_name, u.user_id as patient_user_id
                FROM ImagingReports ir
                JOIN Users u ON ir.patient_id = u.id
                WHERE ir.lab_tech_id = %s
                ORDER BY ir.created_at DESC
            """, (user_uuid,))
            rows = cur.fetchall()
            
    return [ImagingReportItem(
        id=str(r["id"]), patient_name=r["patient_name"], patient_user_id=r["patient_user_id"],
        scan_region=r["scan_region"], exam_type=r["exam_type"], clinical_history=r["clinical_history"],
        findings=r["findings"], impression=r["impression"], recommendations=r["recommendations"],
        has_image=bool(r.get("encrypted_image") or r.get("image_data")),
        document_hash=r.get("document_hash"),
        kem_algorithm=r.get("kem_algorithm"),
        signature_algorithm=r.get("signature_algorithm"),
        blockchain_tx_hash=r.get("blockchain_tx_hash"),
        created_at=r["created_at"],
    ) for r in rows]


@app.get("/api/lab-tech/imaging/{imaging_id}/image")
def get_imaging_image(imaging_id: str, session: dict = Depends(require_role("Lab Technician"))):
    """Decrypt and return one imaging study's payload.

    Mirrors the lab-report release path: the AES key is recovered only by
    decapsulating the stored ML-KEM ciphertext with the patient's private key,
    and the GCM tag proves the stored bytes were not altered. The digest is
    re-checked against the value recorded at signing before anything is
    released.
    """
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT ir.*, u.mlkem_private_key_encrypted,
                       t.mldsa_public_key AS signer_mldsa_public_key
                FROM ImagingReports ir
                JOIN Users u ON ir.patient_id = u.id
                LEFT JOIN Users t ON t.id = ir.lab_tech_id
                WHERE ir.id = %s AND ir.lab_tech_id = %s
            """, (imaging_id, user_uuid))
            r = cur.fetchone()
        if not r:
            raise HTTPException(status_code=404, detail="Imaging report not found")
        # One release path for every reader (it used to be a copy of it).
        return _release_verified(conn, session, lambda: _release_imaging_payload(r, imaging_id),
                                 r, resource=f"Imaging {imaging_id}",
                                 patient_id=str(r["patient_id"]))

@app.get("/api/lab-tech/notifications")
def get_lab_tech_notifications(session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Notifications WHERE user_id = %s ORDER BY created_at DESC", (user_uuid,))
            rows = cur.fetchall()
    return [NotificationItem(
        id=str(r["notification_id"]), notification_type=r["notification_type"],
        title=r["title"], body=r["body"], read_at=r["read_at"], created_at=r["created_at"]
    ) for r in rows]

@app.post("/api/lab-tech/notifications/{notification_id}/read")
def mark_lab_tech_notification_read(notification_id: str, session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE Notifications SET read_at = CURRENT_TIMESTAMP WHERE notification_id = %s AND user_id = %s AND read_at IS NULL", (notification_id, user_uuid))
            conn.commit()
    return {"status": "success"}

@app.post("/api/lab-tech/notifications/clear")
def clear_lab_tech_notifications(session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM Notifications WHERE user_id = %s AND read_at IS NOT NULL", (user_uuid,))
            conn.commit()
    return {"status": "success"}


# ─── Nurse Dashboard Endpoints ───────────────────────────────────────────────
#
# Nurses aren't "assigned" to patients the way doctors are (via diagnoses).
# Any approved nurse can search and open any approved patient's chart to record
# vitals, notes, or medication administration; the nurse's own "My Patients"
# list is simply "who I've recorded something for", mirroring how the Lab
# Technician's queue is scoped to their own work rather than a formal roster.

# ─── Clinical record encryption ──────────────────────────────────────────────
#
# Diagnoses and prescriptions are the last record types stored as plaintext
# columns. They are relational rows read by several roles at once — a patient,
# their doctor and a nurse on a medication round — rather than documents
# released to one recipient, so the per-patient ML-KEM wrapping used for
# reports would make them unreadable to the very staff who need them.
#
# They therefore use the same AES-256-CBC column encryption that already
# protects date of birth and blood group. The honest limit of that: it defends
# the database at rest, not a compromised application server, because the app
# holds the key. That is the same property the existing PII columns have.
#
# Only content is encrypted. Dates and foreign keys stay in the clear because
# every ORDER BY and JOIN depends on them — and nothing anywhere sorts,
# filters or searches on the clinical text itself.

DIAGNOSIS_ENCRYPTED_FIELDS = ("title", "description", "symptoms", "doctor_notes", "recommended_tests")
PRESCRIPTION_ENCRYPTED_FIELDS = ("medicine_name", "dosage", "frequency", "duration", "instructions")


def _enc(value: Optional[str]) -> Optional[str]:
    """Encrypt one clinical field, leaving empty values alone."""
    return encrypt_data(value) if value else value


def _dec(value: Optional[str]) -> Optional[str]:
    """Decrypt one clinical field.

    ``decrypt_data`` returns its input unchanged when it is not decryptable,
    so rows written before this change continue to read correctly.
    """
    return decrypt_data(value) if value else value


def _diagnosis_record(row: dict) -> DiagnosisRecord:
    """Shape one Diagnoses row, decrypting its clinical text.

    Shared by every read path so a diagnosis cannot be returned encrypted
    from one endpoint and plain from another.
    """
    return DiagnosisRecord(
        id=str(row["id"]),
        title=_dec(row["title"]) or "",
        description=_dec(row.get("description")),
        symptoms=_dec(row.get("symptoms")),
        doctor_notes=_dec(row.get("doctor_notes")),
        recommended_tests=_dec(row.get("recommended_tests")),
        visit_date=row.get("visit_date"),
        doctor_name=row.get("doctor_name"),
        created_at=row.get("created_at"),
    )


def _prescription_record(row: dict) -> PrescriptionRecord:
    """Shape one Prescriptions row, decrypting its clinical text."""
    return PrescriptionRecord(
        id=str(row["id"]),
        medicine_name=_dec(row["medicine_name"]) or "",
        dosage=_dec(row["dosage"]) or "",
        frequency=_dec(row["frequency"]) or "",
        duration=_dec(row["duration"]) or "",
        instructions=_dec(row.get("instructions")),
        prescribed_date=row.get("prescribed_date"),
        doctor_name=row.get("doctor_name"),
    )


def _vitals_record(row: dict) -> PatientVitalsRecord:
    """Shape one PatientVitals row for the API.

    Shared by the nurse, doctor and patient views so a reading cannot appear
    differently depending on who is looking at it.
    """
    return PatientVitalsRecord(
        id=str(row["id"]),
        temperature_celsius=row["temperature_celsius"],
        blood_pressure_systolic=row["blood_pressure_systolic"],
        blood_pressure_diastolic=row["blood_pressure_diastolic"],
        heart_rate=row["heart_rate"],
        spo2=row["spo2"],
        respiratory_rate=row["respiratory_rate"],
        weight_kg=row["weight_kg"],
        height_cm=row["height_cm"],
        notes=row["notes"],
        recorded_at=row["recorded_at"],
        nurse_name=row.get("nurse_name"),
    )


def _vitals_out_of_range(req: CreateVitalsRequest) -> list[str]:
    """Plain-language flags for readings outside a normal adult range.

    Used only to decide whether the attending doctor gets paged immediately;
    the recorded values themselves are never altered.
    """
    flags = []
    if req.temperature_celsius is not None and (req.temperature_celsius >= 38.0 or req.temperature_celsius <= 35.0):
        flags.append(f"temperature {req.temperature_celsius}°C")
    if req.heart_rate is not None and (req.heart_rate > 100 or req.heart_rate < 50):
        flags.append(f"heart rate {req.heart_rate} bpm")
    if req.spo2 is not None and req.spo2 < 92:
        flags.append(f"SpO2 {req.spo2}%")
    if req.blood_pressure_systolic is not None and (req.blood_pressure_systolic > 140 or req.blood_pressure_systolic < 90):
        flags.append(f"systolic BP {req.blood_pressure_systolic} mmHg")
    if req.blood_pressure_diastolic is not None and (req.blood_pressure_diastolic > 90 or req.blood_pressure_diastolic < 60):
        flags.append(f"diastolic BP {req.blood_pressure_diastolic} mmHg")
    if req.respiratory_rate is not None and (req.respiratory_rate > 24 or req.respiratory_rate < 10):
        flags.append(f"respiratory rate {req.respiratory_rate}/min")
    return flags


@app.get("/api/nurse/profile")
def get_nurse_profile(session: dict = Depends(require_role("Nurse"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s", (user_uuid,))
            user = cur.fetchone()
    if not user:
        raise HTTPException(status_code=404, detail="Nurse not found")
    return NurseProfile(
        id=str(user["id"]), user_id=user["user_id"], full_name=user["full_name"],
        email=user["email"], role=user["role"], gender=user["gender"],
        status=user["status"], created_at=user["created_at"],
    )


@app.get("/api/nurse/dashboard/summary")
def get_nurse_dashboard_summary(session: dict = Depends(require_role("Nurse"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT COUNT(DISTINCT patient_id) as cnt FROM (
                    SELECT patient_id FROM PatientVitals WHERE nurse_id = %s AND recorded_at::date = CURRENT_DATE
                    UNION SELECT patient_id FROM NursingNotes WHERE nurse_id = %s AND created_at::date = CURRENT_DATE
                    UNION SELECT patient_id FROM MedicationAdministration WHERE nurse_id = %s AND administered_at::date = CURRENT_DATE
                ) as attended
            """, (user_uuid, user_uuid, user_uuid))
            patients_attended = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM PatientVitals WHERE nurse_id = %s AND recorded_at::date = CURRENT_DATE", (user_uuid,))
            vitals_today = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM NursingNotes WHERE nurse_id = %s AND created_at::date = CURRENT_DATE", (user_uuid,))
            notes_today = cur.fetchone()["cnt"]

            cur.execute("SELECT COUNT(*) as cnt FROM MedicationAdministration WHERE nurse_id = %s AND administered_at::date = CURRENT_DATE", (user_uuid,))
            meds_today = cur.fetchone()["cnt"]

            cur.execute("SELECT title, body, created_at FROM Notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 5", (user_uuid,))
            activities = cur.fetchall()

    return NurseDashboardSummary(
        patients_attended_today=patients_attended,
        vitals_recorded_today=vitals_today,
        notes_added_today=notes_today,
        medications_administered_today=meds_today,
        recent_activities=[
            PatientActivityItem(title=a["title"], description=a["body"], created_at=a["created_at"])
            for a in activities
        ],
    )


def _nurse_care_team(cur, nurse_uuid: str, query: Optional[str] = None) -> list[NursePatientListItem]:
    """The patients this nurse may currently open — their care team, nothing else."""
    sql = """
        SELECT u.id, u.user_id, u.full_name, u.gender, u.blood_group_encrypted, u.status,
               a.expires_at, a.reason, b.full_name AS assigned_by_name,
               NULLIF(GREATEST(
                   COALESCE((SELECT MAX(recorded_at) FROM PatientVitals WHERE patient_id = u.id AND nurse_id = %s), 'epoch'::timestamptz),
                   COALESCE((SELECT MAX(created_at) FROM NursingNotes WHERE patient_id = u.id AND nurse_id = %s), 'epoch'::timestamptz),
                   COALESCE((SELECT MAX(administered_at) FROM MedicationAdministration WHERE patient_id = u.id AND nurse_id = %s), 'epoch'::timestamptz)
               ), 'epoch'::timestamptz) AS last_recorded_at
          FROM CareTeamAssignments a
          JOIN Users u ON u.id = a.patient_id AND u.role = 'Patient'
          LEFT JOIN Users b ON b.id = a.assigned_by
         WHERE a.nurse_id = %s AND a.ended_at IS NULL
           AND (a.expires_at IS NULL OR a.expires_at > NOW())"""
    params: list = [nurse_uuid] * 4
    if query:
        sql += " AND (u.full_name ILIKE %s OR u.user_id ILIKE %s)"
        params += [f"%{query}%", f"%{query}%"]
    cur.execute(sql + " ORDER BY last_recorded_at DESC NULLS LAST, u.full_name LIMIT 100", params)
    rows = cur.fetchall()
    # A doctor-delegated assignment lapses with the doctor's own access, so the
    # list shows only charts that would actually open.
    return [NursePatientListItem(
        id=str(r["id"]), user_id=r["user_id"], full_name=r["full_name"], gender=r["gender"],
        blood_group=decrypt_data(r["blood_group_encrypted"]) if r.get("blood_group_encrypted") else None,
        last_recorded_at=r["last_recorded_at"], status=r["status"],
        assigned_by_name=r["assigned_by_name"], assignment_expires_at=r["expires_at"],
        assignment_reason=r["reason"],
    ) for r in rows if _nurse_patient_authorization(cur, nurse_uuid, str(r["id"]))[0]]


@app.get("/api/nurse/patients")
def get_nurse_patients(session: dict = Depends(require_role("Nurse"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _nurse_care_team(cur, session["user_id"])


@app.get("/api/nurse/patients/search")
def search_nurse_patients(q: str, session: dict = Depends(require_role("Nurse"))):
    """Search within this nurse's care team. It used to search every patient in
    the hospital and return their e-mail addresses."""
    if len(q) < 2:
        return []
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            return _nurse_care_team(cur, session["user_id"], q.strip()[:80])


@app.get("/api/nurse/patients/{patient_id}", response_model=NursePatientDetail)
def get_nurse_patient_detail(patient_id: str, session: dict = Depends(require_role("Nurse"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s AND role = 'Patient'", (patient_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Patient not found")
            basis, assignment = _require_nurse_access(cur, session, str(patient_id), "patient_chart")
            decision = _security_gate(cur, session, resource="patient_chart",
                                      patient_id=str(patient_id))
            _record_access(cur, session, patient_id=str(patient_id), resource="patient_chart",
                           basis=basis, decision=decision)

            cur.execute("""
                SELECT v.*, n.full_name as nurse_name FROM PatientVitals v
                LEFT JOIN Users n ON v.nurse_id = n.id
                WHERE v.patient_id = %s ORDER BY v.recorded_at DESC LIMIT 10
            """, (patient_id,))
            vitals = cur.fetchall()

            cur.execute("""
                SELECT nn.*, n.full_name as nurse_name FROM NursingNotes nn
                LEFT JOIN Users n ON nn.nurse_id = n.id
                WHERE nn.patient_id = %s ORDER BY nn.created_at DESC LIMIT 10
            """, (patient_id,))
            notes = cur.fetchall()

            cur.execute("""
                SELECT p.*,
                    (SELECT ma.administered_at FROM MedicationAdministration ma WHERE ma.prescription_id = p.id ORDER BY ma.administered_at DESC LIMIT 1) as last_administered_at,
                    (SELECT ma.status FROM MedicationAdministration ma WHERE ma.prescription_id = p.id ORDER BY ma.administered_at DESC LIMIT 1) as last_administered_status
                FROM Prescriptions p
                WHERE p.patient_id = %s
                ORDER BY p.prescribed_date DESC LIMIT 10
            """, (patient_id,))
            prescriptions = cur.fetchall()

    return NursePatientDetail(
        profile=NursePatientListItem(
            id=str(user["id"]), user_id=user["user_id"], full_name=user["full_name"], gender=user["gender"],
            blood_group=decrypt_data(user["blood_group_encrypted"]) if user.get("blood_group_encrypted") else None,
            last_recorded_at=None, status=user["status"],
            assigned_by_name=assignment.get("assigned_by_name") if assignment else None,
            assignment_expires_at=assignment.get("expires_at") if assignment else None,
            assignment_reason=assignment.get("reason") if assignment else None,
        ),
        vitals_history=[_vitals_record(v) for v in vitals],
        nursing_notes=[
            NursingNoteRecord(id=str(n["id"]), note_type=n["note_type"], content=n["content"], created_at=n["created_at"], nurse_name=n["nurse_name"])
            for n in notes
        ],
        active_prescriptions=[
            ActivePrescriptionForNurse(
                id=str(p["id"]), medicine_name=_dec(p["medicine_name"]) or "", dosage=_dec(p["dosage"]) or "",
                frequency=_dec(p["frequency"]) or "", duration=_dec(p["duration"]) or "",
                instructions=_dec(p["instructions"]), prescribed_date=p["prescribed_date"],
                last_administered_at=p["last_administered_at"], last_administered_status=p["last_administered_status"],
            ) for p in prescriptions
        ],
    )


@app.post("/api/nurse/patients/{patient_id}/vitals")
def record_patient_vitals(patient_id: str, req: CreateVitalsRequest, session: dict = Depends(require_role("Nurse"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id FROM Users WHERE id = %s AND role = 'Patient'", (patient_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Patient not found")
            _require_nurse_access(cur, session, str(patient_id), "vitals")

            cur.execute("""
                INSERT INTO PatientVitals
                    (patient_id, nurse_id, temperature_celsius, blood_pressure_systolic, blood_pressure_diastolic,
                     heart_rate, spo2, respiratory_rate, weight_kg, height_cm, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (
                patient_id, user_uuid, req.temperature_celsius, req.blood_pressure_systolic, req.blood_pressure_diastolic,
                req.heart_rate, req.spo2, req.respiratory_rate, req.weight_kg, req.height_cm, req.notes,
            ))
            vitals_id = cur.fetchone()["id"]

            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'VITALS_RECORDED', 'Vitals Recorded', 'A nurse recorded your vitals.')
            """, (patient_id,))

            flags = _vitals_out_of_range(req)
            if flags:
                cur.execute("""
                    SELECT doctor_id FROM (
                        SELECT doctor_id, visit_date as event_date FROM Diagnoses WHERE patient_id = %s AND doctor_id IS NOT NULL
                        UNION ALL
                        SELECT doctor_id, appointment_date as event_date FROM Appointments WHERE patient_id = %s AND doctor_id IS NOT NULL
                    ) as recent ORDER BY event_date DESC LIMIT 1
                """, (patient_id, patient_id))
                doc_row = cur.fetchone()
                if doc_row and doc_row["doctor_id"]:
                    cur.execute("""
                        INSERT INTO Notifications (user_id, notification_type, title, body)
                        VALUES (%s, 'ABNORMAL_VITALS', 'Abnormal Vitals Alert', %s)
                    """, (doc_row["doctor_id"], f"Out-of-range reading(s) for your patient: {', '.join(flags)}."))

            conn.commit()

    return {"status": "success", "id": str(vitals_id), "flags": flags}


@app.post("/api/nurse/patients/{patient_id}/notes")
def add_nursing_note(patient_id: str, req: CreateNursingNoteRequest, session: dict = Depends(require_role("Nurse"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id FROM Users WHERE id = %s AND role = 'Patient'", (patient_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Patient not found")
            _require_nurse_access(cur, session, str(patient_id), "nursing_note")

            cur.execute("""
                INSERT INTO NursingNotes (patient_id, nurse_id, note_type, content)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (patient_id, user_uuid, req.note_type, req.content))
            note_id = cur.fetchone()["id"]
            conn.commit()

    return {"status": "success", "id": str(note_id)}


@app.post("/api/nurse/patients/{patient_id}/medications/{prescription_id}/administer")
def administer_medication(patient_id: str, prescription_id: str, req: CreateMedicationAdministrationRequest, session: dict = Depends(require_role("Nurse"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _require_nurse_access(cur, session, str(patient_id), "medication_administration")
            cur.execute("SELECT id FROM Prescriptions WHERE id = %s AND patient_id = %s", (prescription_id, patient_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Prescription not found for this patient")

            cur.execute("""
                INSERT INTO MedicationAdministration (prescription_id, patient_id, nurse_id, status, remarks)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (prescription_id, patient_id, user_uuid, req.status, req.remarks))
            admin_id = cur.fetchone()["id"]
            conn.commit()

    return {"status": "success", "id": str(admin_id)}


def _assign_care_team(conn, cur, session: dict, patient_id: str, req: CareTeamAssignRequest) -> CareTeamMember:
    """Shared by the doctor and administrator forms."""
    cur.execute(
        """SELECT id, user_id, full_name FROM Users
            WHERE role = 'Nurse' AND status = 'Approved' AND (id::text = %s OR user_id = %s)""",
        (req.nurse_id, req.nurse_id))
    nurse = cur.fetchone()
    if not nurse:
        raise HTTPException(status_code=404, detail="No approved nurse with that ID.")
    cur.execute("SELECT id, user_id, full_name FROM Users WHERE id = %s AND role = 'Patient'",
                (patient_id,))
    patient = cur.fetchone()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    expires_at = (datetime.now(timezone.utc) + timedelta(hours=req.duration_hours)
                  if req.duration_hours else None)
    cur.execute(
        """INSERT INTO CareTeamAssignments (patient_id, nurse_id, assigned_by, assigned_by_role,
                                            reason, expires_at)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON CONFLICT (patient_id, nurse_id) WHERE ended_at IS NULL
           DO UPDATE SET assigned_by = EXCLUDED.assigned_by,
                         assigned_by_role = EXCLUDED.assigned_by_role,
                         reason = EXCLUDED.reason, expires_at = EXCLUDED.expires_at,
                         created_at = CURRENT_TIMESTAMP
           RETURNING id""",
        (patient["id"], nurse["id"], session["user_id"], session["role"], req.reason, expires_at))
    assignment_id = cur.fetchone()["id"]
    until = expires_at.strftime("%d %b %Y %H:%M UTC") if expires_at else "further notice"
    cur.executemany(
        "INSERT INTO Notifications (user_id, notification_type, title, body) VALUES (%s, %s, %s, %s)",
        [(nurse["id"], "CARE_TEAM_ASSIGNED", "Added to a patient's care team",
          f"You can now open {patient['full_name']}'s chart ({patient['user_id']}) until {until}."),
         (patient["id"], "CARE_TEAM_ASSIGNED", "A nurse was added to your care team",
          f"{nurse['full_name']} can now read your chart and record vitals until {until}. "
          f"Reason given: {req.reason}")])
    aisec.record_security_event(
        cur, actor_id=session["user_id"], actor_public_id=session.get("public_user_id"),
        actor_role=session.get("role"), event_type="CARE_TEAM_ASSIGNED",
        subject_patient_id=str(patient["id"]), resource="care_team",
        metadata={"nurse": nurse["user_id"], "hours": req.duration_hours})
    conn.commit()
    log_admin_action(conn, session["user_id"], session.get("public_user_id"), "CARE_TEAM_ASSIGNED",
                     str(patient["id"]), patient["user_id"],
                     details={"nurse": nurse["user_id"], "reason": req.reason,
                              "expires_at": expires_at.isoformat() if expires_at else None})
    cur.execute(_CARE_TEAM_SELECT + " AND a.id = %s", (assignment_id,))
    return _care_team_member(cur.fetchone())


def _end_care_team(conn, cur, session: dict, assignment: dict) -> dict:
    cur.execute("UPDATE CareTeamAssignments SET ended_at = CURRENT_TIMESTAMP, ended_by = %s "
                "WHERE id = %s AND ended_at IS NULL", (session["user_id"], assignment["id"]))
    cur.execute(
        "INSERT INTO Notifications (user_id, notification_type, title, body) VALUES (%s, %s, %s, %s)",
        (assignment["nurse_id"], "CARE_TEAM_ENDED", "Removed from a patient's care team",
         f"Your access to {assignment['patient_name']}'s chart ({assignment['patient_user_id']}) has ended."))
    conn.commit()
    log_admin_action(conn, session["user_id"], session.get("public_user_id"), "CARE_TEAM_ENDED",
                     str(assignment["patient_id"]), assignment["patient_user_id"],
                     details={"nurse": assignment["nurse_user_id"]})
    return {"status": "success", "assignment_id": str(assignment["id"])}


@app.get("/api/doctor/nurses")
def search_nurses(q: str = Query("", max_length=80), session: dict = Depends(require_role("Doctor"))):
    """Approved nurses a doctor can add to a care team. Staff only — no patient data."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT id, user_id, full_name FROM Users
                    WHERE role = 'Nurse' AND status = 'Approved'
                      AND (%s = '' OR full_name ILIKE %s OR user_id ILIKE %s)
                    ORDER BY full_name LIMIT 20""",
                (q.strip(), f"%{q.strip()}%", f"%{q.strip()}%"))
            return [{"id": str(r["id"]), "user_id": r["user_id"], "full_name": r["full_name"]}
                    for r in cur.fetchall()]


@app.get("/api/doctor/patients/{patient_id}/care-team", response_model=list[CareTeamMember])
def get_patient_care_team(patient_id: str, session: dict = Depends(require_role("Doctor"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _require_write_access(cur, session, patient_id, "care team")
            cur.execute(_CARE_TEAM_SELECT + " AND a.patient_id = %s ORDER BY a.created_at DESC",
                        (patient_id,))
            return [_care_team_member(r) for r in cur.fetchall()]


@app.post("/api/doctor/patients/{patient_id}/care-team", response_model=CareTeamMember)
def assign_patient_care_team(patient_id: str, req: CareTeamAssignRequest,
                             session: dict = Depends(require_role("Doctor"))):
    """Delegate chart access to a nurse. Only a doctor who is authorized for the
    patient can do this, and the nurse's access ends with theirs."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _require_write_access(cur, session, patient_id, "care team")
            allowed, basis = _doctor_patient_authorization(cur, session["user_id"], patient_id)
            if basis == "emergency override":
                # Break-glass is personal; it is not a basis for granting others access.
                _deny(cur, session, resource="care_team", reason="emergency access cannot be delegated",
                      patient_id=str(patient_id),
                      detail="Emergency access is personal and cannot be delegated to a nurse.")
            return _assign_care_team(conn, cur, session, patient_id, req)


@app.post("/api/doctor/patients/{patient_id}/care-team/{assignment_id}/end")
def end_patient_care_team(patient_id: str, assignment_id: str,
                          session: dict = Depends(require_role("Doctor"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            _require_write_access(cur, session, patient_id, "care team")
            cur.execute(_CARE_TEAM_SELECT + " AND a.id = %s AND a.patient_id = %s",
                        (assignment_id, patient_id))
            assignment = cur.fetchone()
            if not assignment:
                raise HTTPException(status_code=404, detail="Assignment not found")
            return _end_care_team(conn, cur, session, assignment)


@app.get("/api/admin/care-team", response_model=list[CareTeamMember])
def list_care_teams(q: str = Query("", max_length=80),
                    session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            term = q.strip()
            cur.execute(
                _CARE_TEAM_SELECT + """ AND (%s = '' OR p.full_name ILIKE %s OR p.user_id ILIKE %s
                                              OR n.full_name ILIKE %s OR n.user_id ILIKE %s)
                                     ORDER BY a.created_at DESC LIMIT 200""",
                (term,) + (f"%{term}%",) * 4)
            return [_care_team_member(r) for r in cur.fetchall()]


@app.get("/api/admin/care-team/suggestions")
def care_team_suggestions(days: int = Query(90, ge=1, le=365),
                          session: dict = Depends(require_role("Administrator"))):
    """Nurses' recent patients that have no care-team assignment — for review.

    Before care teams, any nurse could open any chart, so a working nurse may
    have patients they are genuinely caring for and can no longer reach. This
    lists them from the nurse's own recorded work (vitals, notes, medication
    rounds) so an administrator can allocate the ones that should continue.
    It grants nothing by itself: history is evidence, not authorization.
    """
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """WITH activity AS (
                       SELECT nurse_id, patient_id, recorded_at AS at FROM PatientVitals
                       UNION ALL SELECT nurse_id, patient_id, created_at FROM NursingNotes
                       UNION ALL SELECT nurse_id, patient_id, administered_at FROM MedicationAdministration
                   )
                   SELECT a.nurse_id, n.user_id AS nurse_user_id, n.full_name AS nurse_name,
                          a.patient_id, p.user_id AS patient_user_id, p.full_name AS patient_name,
                          MAX(a.at) AS last_activity, COUNT(*) AS entries
                     FROM activity a
                     JOIN Users n ON n.id = a.nurse_id AND n.role = 'Nurse' AND n.status = 'Approved'
                     JOIN Users p ON p.id = a.patient_id AND p.role = 'Patient'
                    WHERE a.at > NOW() - make_interval(days => %s)
                      AND NOT EXISTS (
                          SELECT 1 FROM CareTeamAssignments c
                           WHERE c.nurse_id = a.nurse_id AND c.patient_id = a.patient_id
                             AND c.ended_at IS NULL
                             AND (c.expires_at IS NULL OR c.expires_at > NOW()))
                    GROUP BY a.nurse_id, n.user_id, n.full_name, a.patient_id, p.user_id, p.full_name
                    ORDER BY MAX(a.at) DESC
                    LIMIT 200""", (days,))
            return [{**r, "nurse_id": str(r["nurse_id"]), "patient_id": str(r["patient_id"])}
                    for r in cur.fetchall()]


@app.post("/api/admin/care-team", response_model=CareTeamMember)
def admin_assign_care_team(req: CareTeamAssignRequest,
                           session: dict = Depends(require_role("Administrator"))):
    """Ward allocation: an administrator assigns a nurse to a patient."""
    if not req.patient_id:
        raise HTTPException(status_code=422, detail="patient_id is required.")
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT id FROM Users WHERE role = 'Patient' AND (id::text = %s OR user_id = %s)",
                        (req.patient_id, req.patient_id))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Patient not found")
            return _assign_care_team(conn, cur, session, str(row["id"]), req)


@app.post("/api/admin/care-team/{assignment_id}/end")
def admin_end_care_team(assignment_id: str, session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_CARE_TEAM_SELECT + " AND a.id = %s", (assignment_id,))
            assignment = cur.fetchone()
            if not assignment:
                raise HTTPException(status_code=404, detail="Assignment not found")
            return _end_care_team(conn, cur, session, assignment)


@app.get("/api/patient/care-team", response_model=list[CareTeamMember])
def get_my_care_team(session: dict = Depends(require_role("Patient"))):
    """Which nurses can open my chart, who added them, and until when."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(_CARE_TEAM_SELECT + " AND a.patient_id = %s ORDER BY a.created_at DESC",
                        (session["user_id"],))
            rows = cur.fetchall()
            return [_care_team_member(r) for r in rows
                    if _nurse_patient_authorization(cur, str(r["nurse_id"]), session["user_id"])[0]]


@app.get("/api/nurse/notifications")
def get_nurse_notifications(session: dict = Depends(require_role("Nurse"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Notifications WHERE user_id = %s ORDER BY created_at DESC", (user_uuid,))
            rows = cur.fetchall()
    return [NotificationItem(
        id=str(r["notification_id"]), notification_type=r["notification_type"],
        title=r["title"], body=r["body"], read_at=r["read_at"], created_at=r["created_at"]
    ) for r in rows]


@app.post("/api/nurse/notifications/{notification_id}/read")
def mark_nurse_notification_read(notification_id: str, session: dict = Depends(require_role("Nurse"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE Notifications SET read_at = CURRENT_TIMESTAMP WHERE notification_id = %s AND user_id = %s AND read_at IS NULL", (notification_id, user_uuid))
            conn.commit()
    return {"status": "success"}


@app.post("/api/nurse/notifications/clear")
def clear_nurse_notifications(session: dict = Depends(require_role("Nurse"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM Notifications WHERE user_id = %s AND read_at IS NOT NULL", (user_uuid,))
            conn.commit()
    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

# ─────────────────────────────────────────────────────────────────────────────
# Doctor access requests (spec §6)
#
# Two routes to a patient's record coexist deliberately:
#
#   * A doctor already treating the patient — one who raised the investigation,
#     recorded a diagnosis, or holds an appointment — reads it on that
#     relationship. Making an oncologist file a form before opening the chart of
#     a patient they are actively treating would be obstructive, and clinicians
#     route around obstructive controls.
#   * A doctor with no such relationship has no implicit access at all and must
#     ask. The patient decides, and until they do the answer is no.
#
# Both routes remain subject to revocation, which the patient may exercise at
# any time and which this module treats as final unless break-glass is declared.
# ─────────────────────────────────────────────────────────────────────────────

_ACCESS_REQUEST_SELECT = """
    SELECT c.consent_id, c.patient_id, c.subject_user_id AS doctor_id,
           c.status::text AS status, c.purpose, c.requested_resource,
           c.requested_at, c.decided_at, c.decision_note,
           d.user_id AS doctor_user_id, d.full_name AS doctor_name,
           d.specialization,
           p.user_id AS patient_user_id, p.full_name AS patient_name
      FROM Consent c
      JOIN Users d ON d.id = c.subject_user_id
      JOIN Users p ON p.id = c.patient_id
"""


def _access_request_record(row: dict) -> AccessRequestRecord:
    """Shape one Consent row as an access request, for both sides of it."""
    return AccessRequestRecord(
        request_id=str(row["consent_id"]),
        doctor_id=str(row["doctor_id"]),
        doctor_user_id=row.get("doctor_user_id"),
        doctor_name=row.get("doctor_name"),
        specialization=row.get("specialization"),
        patient_id=str(row["patient_id"]),
        patient_user_id=row.get("patient_user_id"),
        patient_name=row.get("patient_name"),
        requested_resource=row.get("requested_resource"),
        purpose=row.get("purpose"),
        status=row["status"],
        requested_at=row.get("requested_at"),
        decided_at=row.get("decided_at"),
        decision_note=row.get("decision_note"),
    )


@app.post("/api/doctor/access-requests", response_model=AccessRequestRecord)
def create_access_request(
    req: CreateAccessRequest,
    session: dict = Depends(require_role("Doctor")),
):
    """Ask a patient for permission to read their record."""
    doctor_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, user_id, full_name FROM Users WHERE id = %s AND role = 'Patient' AND status = 'Approved'",
                (req.patient_id,),
            )
            patient = cur.fetchone()
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")

            cur.execute(
                """SELECT consent_id, status::text AS status FROM Consent
                    WHERE patient_id = %s AND subject_user_id = %s AND subject_role = 'Doctor'""",
                (req.patient_id, doctor_uuid),
            )
            existing = cur.fetchone()
            if existing and existing["status"] == "Pending":
                raise HTTPException(
                    status_code=409, detail="A request for this patient is already awaiting their decision."
                )
            if existing and existing["status"] == "Authorized":
                raise HTTPException(status_code=409, detail="You already have this patient's consent.")

            # A previously revoked or rejected relationship may be asked about
            # again — circumstances change — but it re-enters as Pending, never
            # straight back to Authorized.
            if existing:
                cur.execute(
                    """UPDATE Consent SET status = 'Pending', purpose = %s, requested_resource = %s,
                              requested_at = CURRENT_TIMESTAMP, decided_at = NULL, decision_note = NULL,
                              prior_refusal = TRUE
                        WHERE consent_id = %s RETURNING consent_id""",
                    (req.purpose, req.requested_resource, existing["consent_id"]),
                )
                request_id = cur.fetchone()["consent_id"]
            else:
                cur.execute(
                    """INSERT INTO Consent (patient_id, subject_user_id, subject_role, status,
                                            purpose, requested_resource, requested_at)
                       VALUES (%s, %s, 'Doctor', 'Pending', %s, %s, CURRENT_TIMESTAMP)
                       RETURNING consent_id""",
                    (req.patient_id, doctor_uuid, req.purpose, req.requested_resource),
                )
                request_id = cur.fetchone()["consent_id"]

            cur.execute(
                """INSERT INTO Notifications (user_id, notification_type, title, body)
                   VALUES (%s, 'ACCESS_REQUEST', %s, %s)""",
                (req.patient_id, "A doctor is requesting access to your records",
                 f"Dr. {session.get('full_name') or 'A clinician'} has asked to read your "
                 f"{req.requested_resource.lower()}. Reason given: {req.purpose}"),
            )
            log_admin_action(
                conn, doctor_uuid, session.get("public_user_id"),
                "ACCESS_REQUESTED", str(req.patient_id), patient["user_id"],
            )
            conn.commit()

            cur.execute(_ACCESS_REQUEST_SELECT + " WHERE c.consent_id = %s", (request_id,))
            return _access_request_record(cur.fetchone())


@app.get("/api/doctor/access-requests", response_model=list[AccessRequestRecord])
def list_doctor_access_requests(session: dict = Depends(require_role("Doctor"))):
    """Every request this doctor has made, and where each one stands."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                _ACCESS_REQUEST_SELECT + """
                 WHERE c.subject_user_id = %s AND c.subject_role = 'Doctor'
                   AND c.requested_at IS NOT NULL
                 ORDER BY c.requested_at DESC""",
                (session["user_id"],),
            )
            return [_access_request_record(r) for r in cur.fetchall()]


@app.get("/api/patient/access-requests", response_model=list[AccessRequestRecord])
def list_patient_access_requests(session: dict = Depends(require_role("Patient"))):
    """Requests awaiting this patient's decision, most recent first."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                _ACCESS_REQUEST_SELECT + """
                 WHERE c.patient_id = %s AND c.requested_at IS NOT NULL
                 ORDER BY (c.status = 'Pending') DESC, c.requested_at DESC""",
                (session["user_id"],),
            )
            return [_access_request_record(r) for r in cur.fetchall()]


def _decide_access_request(request_id: str, session: dict, approve: bool, note: Optional[str]):
    """Record a patient's decision on one request.

    Scoped by patient_id as well as request id, so a patient cannot decide
    another patient's request by substituting an identifier.
    """
    patient_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT c.consent_id, c.subject_user_id AS doctor_id, c.status::text AS status,
                          d.user_id AS doctor_user_id
                     FROM Consent c JOIN Users d ON d.id = c.subject_user_id
                    WHERE c.consent_id = %s AND c.patient_id = %s""",
                (request_id, patient_uuid),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Access request not found")
            if row["status"] != "Pending":
                raise HTTPException(
                    status_code=409,
                    detail=f"This request was already {row['status'].lower()}.",
                )

            status = "Authorized" if approve else "Rejected"

            # On approval, mint the zero-knowledge consent token (§17) — always
            # the post-quantum lattice scheme. Only the commitment is public; the
            # token is encrypted at rest exactly as ML-KEM private keys are, and
            # handed to the doctor once.
            zkp_commitment = zkp_token_enc = None
            if approve:
                consent_token, zkp_commitment = zkp.issue_consent_token()
                zkp_token_enc = encrypt_data(consent_token)

            cur.execute(
                """UPDATE Consent
                      SET status = %s, decided_at = CURRENT_TIMESTAMP, decision_note = %s,
                          granted_at = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE granted_at END,
                          prior_refusal = FALSE,
                          zkp_commitment = COALESCE(%s, zkp_commitment),
                          zkp_token_encrypted = COALESCE(%s, zkp_token_encrypted),
                          zkp_token_collected_at = CASE WHEN %s THEN NULL ELSE zkp_token_collected_at END
                    WHERE consent_id = %s""",
                (status, note, approve, zkp_commitment, zkp_token_enc, approve, request_id),
            )
            cur.execute(
                """INSERT INTO Notifications (user_id, notification_type, title, body)
                   VALUES (%s, %s, %s, %s)""",
                (row["doctor_id"],
                 "ACCESS_GRANTED" if approve else "ACCESS_REJECTED",
                 "Access request approved" if approve else "Access request declined",
                 f"{session.get('full_name') or 'The patient'} "
                 + ("approved your request; their record is now available to you."
                    if approve else "declined your request.")),
            )
            log_admin_action(
                conn, patient_uuid, session.get("public_user_id"),
                "ACCESS_APPROVED" if approve else "ACCESS_REJECTED",
                str(row["doctor_id"]), row["doctor_user_id"],
            )
            aisec.record_security_event(
                cur, actor_id=patient_uuid, actor_public_id=session.get("public_user_id"),
                actor_role="Patient", event_type="CONSENT_EVENT",
                subject_patient_id=str(patient_uuid),
                resource="ACCESS_" + ("APPROVED" if approve else "REJECTED"),
            )
            # A consent decision is an integrity-relevant event: anchoring it
            # means neither party can later dispute what was decided or when.
            anchor = anchor_document(
                conn,
                document_type="ConsentDecision", document_id=str(request_id),
                document_hash=sha256_hex(f"{request_id}:{status}:{row['doctor_id']}".encode()),
                action="ACCESS_" + ("APPROVED" if approve else "REJECTED"),
                patient_id=str(patient_uuid), actor_id=patient_uuid,
                actor_public_id=session.get("public_user_id"),
            )
            # Smart-contract consent (spec §7): the decision itself goes on-chain
            # as consent state, separately from the audit anchor above, so that
            # checkConsent() can later be asked whether the row still agrees.
            ledger = consent_ledger.record(cur, consent_id=str(request_id),
                                           patient_id=str(patient_uuid),
                                           doctor_id=str(row["doctor_id"]), authorized=approve)
            conn.commit()

            cur.execute(_ACCESS_REQUEST_SELECT + " WHERE c.consent_id = %s", (request_id,))
            record = _access_request_record(cur.fetchone())
    return {"status": "success", "request": record,
            "blockchain_tx_hash": (anchor or {}).get("tx_hash"),
            "consent_ledger": ledger}


@app.post("/api/patient/access-requests/{request_id}/approve")
def approve_access_request(
    request_id: str, body: AccessRequestDecision | None = None,
    session: dict = Depends(require_role("Patient")),
):
    return _decide_access_request(request_id, session, True, (body.note if body else None))


@app.post("/api/patient/access-requests/{request_id}/reject")
def reject_access_request(
    request_id: str, body: AccessRequestDecision | None = None,
    session: dict = Depends(require_role("Patient")),
):
    return _decide_access_request(request_id, session, False, (body.note if body else None))


# ─────────────────────────────────────────────────────────────────────────────
# AI security layer (spec §18–25)
#
# Placement matters. This layer runs *after* authentication, RBAC and consent
# have already decided whether an action is permitted (§23). It never grants
# access, and on its own it never revokes it: a statistical model must not be
# the thing standing between a clinician and a patient's record. What it does
# is score behaviour, explain the score, raise an alert, and open an incident
# for a human to judge.
# ─────────────────────────────────────────────────────────────────────────────

from app import ai_security as aisec  # noqa: E402
from app import zkp_service as zkp  # noqa: E402


def _persist_assessment(cur, window, risk, level, contributions, source,
                        hours: int) -> Optional[str]:
    """Store one risk assessment, and raise an alert when it is not LOW.

    Alerts are deduplicated per actor and level for a day: scheduled analysis
    re-scores everyone every half hour, and one open alert is what a reviewer
    needs, not forty-eight. HIGH opens an incident only with a fresh alert.
    """
    import json
    from datetime import timedelta as _td
    end = datetime.now(timezone.utc)
    cur.execute(
        """INSERT INTO RiskAssessments (actor_id, actor_public_id, risk_score, risk_level,
                                        detection_source, features, explanation,
                                        window_start, window_end)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (window.actor_id, window.actor_public_id, risk, level, source,
         json.dumps(window.features), json.dumps(contributions),
         end - _td(hours=hours), end),
    )
    assessment_id = cur.fetchone()["id"]
    if level == "LOW":
        return None

    narrative = aisec.narrate(level, contributions)
    response = aisec.RESPONSE_BY_LEVEL[level]
    alert_id, created = secresp.raise_alert_once(
        cur, severity=level, source=source, actor_id=window.actor_id,
        assessment_id=str(assessment_id),
        title=f"{level} risk behaviour — {window.actor_public_id or 'unknown actor'}",
        summary=narrative, response=response, dedupe_minutes=24 * 60)

    # HIGH risk opens a compliance record (§25). MEDIUM stays an alert: opening
    # an incident for every mild deviation would bury the serious ones.
    if level == "HIGH" and created:
        secresp.open_incident(
            cur, event_type="ANOMALOUS_ACCESS_PATTERN", risk_level=level,
            detection_source=source, actor_id=window.actor_id, alert_id=alert_id,
            affected_resource=f"{int(window.features.get('distinct_patients', 0))} patient records",
            explanation=narrative, response=response, audit_reference=str(assessment_id))
    return str(assessment_id)


def _run_security_analysis(hours: int) -> dict:
    """Score every active actor against their role's baseline.

    The baseline is the federated model for the role when real institutions
    built one, otherwise this hospital's own (see risk_engine.select_baseline).
    Roles with too few actors to define "normal" are reported, not scored.
    """
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            windows = aisec.extract_windows(cur, hours=hours)
            if not windows:
                return {"analysed": 0, "detail": "No activity in this window."}

            by_role: dict[str, list] = {}
            for w in windows:
                by_role.setdefault(w.actor_role or "Unknown", []).append(w)

            local = aisec.fit_role_baselines(windows)
            federated, federated_label = risk_engine.usable_federated_model(cur)
            min_peers = risk_engine.policy()["min_peers"]

            summary = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
            baselines_used: dict[str, str] = {}
            too_small: list[str] = []
            for role, group in by_role.items():
                # Comparing a doctor against nurses would flag ordinary role
                # differences as anomalies, so each role is its own peer group.
                baseline, source, samples = risk_engine.select_baseline(
                    role, local, federated, min_peers)
                if baseline is None:
                    too_small.append(role)
                    continue
                baselines_used[role] = f"{source} ({samples} peers)"
                for w in group:
                    risk, level, contributions = aisec.score(w, baseline)
                    _persist_assessment(cur, w, risk, level, contributions, source, hours)
                    summary[level] += 1
            conn.commit()

    risk_engine.invalidate_baselines()
    return {"analysed": sum(summary.values()), "window_hours": hours,
            "peer_groups": list(by_role.keys()), "risk_breakdown": summary,
            "baselines": baselines_used, "federated_model": federated_label,
            "groups_too_small_to_score": too_small}


@app.post("/api/admin/security/analyze")
def run_security_analysis(hours: int = Query(24, ge=1, le=720),
                          session: dict = Depends(require_role("Administrator"))):
    """Run local anomaly detection over recent activity now (§19).

    It also runs on a schedule; this is the on-demand trigger.
    """
    return _run_security_analysis(hours)


@app.get("/api/admin/security/policy")
def get_security_policy(session: dict = Depends(require_role("Administrator"))):
    """The risk decision policy in force (§23), and where each signal comes from.

    Documented here as well as in code so an administrator can see what a
    MEDIUM or HIGH score actually does without reading the source.
    """
    s_ = federation.settings()
    return {
        "risk_policy": risk_engine.policy(),
        "actions": {
            "allow": "No action; the access proceeds.",
            "monitor": "The access proceeds; an alert is raised for review.",
            "verify": "The access proceeds only after the user re-enters their password.",
            "block": "The access is refused; an alert and an incident are opened.",
        },
        "emergency_max_per_day": max(1, int(os.getenv("EMERGENCY_MAX_PER_DAY", "3"))),
        "scheduled_analysis_minutes": int(os.getenv("SECURITY_ANALYSIS_INTERVAL_MINUTES", "30") or 0),
        "federation_participant": {"configured": federation.is_configured(),
                                   "hub_url": s_["hub_url"], "node_name": s_["node_name"]},
        "consent_ledger": _consent_ledger_state(),
        "configuration_warnings": configuration_warnings(get_settings()),
    }


def _consent_ledger_state() -> str:
    from app.chain_client import get_chain_client
    client = get_chain_client()
    if client is None:
        return "database only (chain unreachable)"
    if not getattr(client, "supports_consent_status", True):
        return "contract outdated — redeploy PHR.sol; consent is not being verified on-chain"
    return "on-chain"


@app.get("/api/admin/security/risk-assessments")
def list_risk_assessments(level: Optional[str] = Query(None, pattern="^(LOW|MEDIUM|HIGH)$"),
                          page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100),
                          session: dict = Depends(require_role("Administrator"))):
    """Scored actors with their Explainable AI attributions (§22)."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            where = "WHERE r.risk_level = %s" if level else ""
            params: tuple = (level,) if level else ()
            cur.execute(f"SELECT COUNT(*) AS n FROM RiskAssessments r {where}", params)
            total = cur.fetchone()["n"]
            cur.execute(
                f"""SELECT r.*, u.full_name, u.role::text AS role
                      FROM RiskAssessments r LEFT JOIN Users u ON u.id = r.actor_id
                      {where}
                     ORDER BY r.risk_score DESC, r.created_at DESC
                     LIMIT %s OFFSET %s""",
                params + (per_page, (page - 1) * per_page),
            )
            rows = []
            for r in cur.fetchall():
                rows.append({
                    "id": str(r["id"]), "actor_name": r["full_name"],
                    "actor_public_id": r["actor_public_id"], "actor_role": r["role"],
                    "risk_score": float(r["risk_score"]), "risk_level": r["risk_level"],
                    "detection_source": r["detection_source"],
                    "features": r["features"], "explanation": r["explanation"],
                    "narrative": aisec.narrate(r["risk_level"], r["explanation"] or []),
                    "created_at": r["created_at"],
                })
    return {"total": total, "page": page, "per_page": per_page, "assessments": rows}


@app.get("/api/admin/security/alerts")
def list_security_alerts(page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100),
                         session: dict = Depends(require_role("Administrator"))):
    """Alert & response queue (§24)."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT COUNT(*) AS n FROM SecurityAlerts")
            total = cur.fetchone()["n"]
            cur.execute(
                """SELECT a.*, u.full_name, u.user_id AS actor_public_id
                     FROM SecurityAlerts a LEFT JOIN Users u ON u.id = a.actor_id
                    ORDER BY (a.acknowledged_at IS NULL) DESC, a.created_at DESC
                    LIMIT %s OFFSET %s""", (per_page, (page - 1) * per_page))
            alerts = [{
                "id": str(r["id"]), "severity": r["severity"], "title": r["title"],
                "summary": r["summary"], "response": r["response"],
                "source": r.get("source") or "LOCAL_ANOMALY",
                "actor_name": r["full_name"], "actor_public_id": r["actor_public_id"],
                "acknowledged": r["acknowledged_at"] is not None,
                "created_at": r["created_at"],
            } for r in cur.fetchall()]
    return {"total": total, "page": page, "per_page": per_page, "alerts": alerts}


@app.post("/api/admin/security/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: str, session: dict = Depends(require_role("Administrator"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """UPDATE SecurityAlerts SET acknowledged_at = CURRENT_TIMESTAMP,
                          acknowledged_by = %s
                    WHERE id = %s AND acknowledged_at IS NULL RETURNING id""",
                (session["user_id"], alert_id))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Alert not found or already acknowledged")
            log_admin_action(conn, session["user_id"], session.get("public_user_id"),
                             "SECURITY_ALERT_ACKNOWLEDGED")
            conn.commit()
    return {"status": "success"}


@app.get("/api/admin/security/incidents")
def list_security_incidents(session: dict = Depends(require_role("Administrator"))):
    """Incident and compliance records (§25)."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT i.*, u.full_name, u.user_id AS actor_public_id,
                          r.user_id AS resolved_by_public_id
                     FROM SecurityIncidents i
                     LEFT JOIN Users u ON u.id = i.actor_id
                     LEFT JOIN Users r ON r.id = i.resolved_by
                    ORDER BY CASE i.status WHEN 'Open' THEN 0 WHEN 'Investigating' THEN 1 ELSE 2 END,
                             i.created_at DESC
                    LIMIT 100""")
            incidents = [{
                "id": str(r["id"]),
                "incident_ref": r["incident_ref"], "event_type": r["event_type"],
                "affected_resource": r["affected_resource"], "risk_level": r["risk_level"],
                "detection_source": r["detection_source"], "explanation": r["explanation"],
                "response": r["response"], "status": r["status"],
                "resolution": r.get("resolution"),
                "resolved_by": r.get("resolved_by_public_id"),
                "actor_name": r["full_name"], "actor_public_id": r["actor_public_id"],
                "audit_reference": r["audit_reference"],
                "blockchain_tx_hash": r.get("blockchain_tx_hash"),
                "created_at": r["created_at"], "updated_at": r.get("updated_at"),
                "closed_at": r.get("closed_at"),
            } for r in cur.fetchall()]
    return {"total": len(incidents), "incidents": incidents}


@app.post("/api/admin/security/incidents/{incident_id}")
def update_security_incident(incident_id: str, req: IncidentUpdateRequest,
                             session: dict = Depends(require_role("Administrator"))):
    """Work an incident: Open → Investigating → Closed (with a resolution).

    A closed incident is never reopened or deleted here; a recurrence opens a
    new record, so the compliance history only ever grows.
    """
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT incident_ref, status FROM SecurityIncidents WHERE id = %s",
                        (incident_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Incident not found")
            if row["status"] == "Closed":
                raise HTTPException(status_code=409, detail="This incident is already closed.")
            cur.execute(
                """UPDATE SecurityIncidents
                      SET status = %s,
                          resolution = COALESCE(%s, resolution),
                          resolved_by = CASE WHEN %s = 'Closed' THEN %s ELSE resolved_by END,
                          closed_at = CASE WHEN %s = 'Closed' THEN CURRENT_TIMESTAMP ELSE closed_at END,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s""",
                (req.status, (req.resolution or "").strip() or None, req.status,
                 session["user_id"], req.status, incident_id))
            log_admin_action(conn, session["user_id"], session.get("public_user_id"),
                             f"SECURITY_INCIDENT_{req.status.upper()}",
                             details={"incident_ref": row["incident_ref"]})
            conn.commit()
    return {"status": "success", "incident_ref": row["incident_ref"], "new_status": req.status}


# ─── Federated learning / federated IDS (spec §20–21) ────────────────────────
#
# Honest scope. This deployment is ONE hospital, so there are no peer
# institutions to federate with. What is real here is the *mechanism*: local
# baselines are fitted from this hospital's own activity, and FedAvg aggregates
# parameters weighted by sample count exactly as it would across real nodes.
# The peer nodes are simulated, every stored row is flagged is_simulated, and
# the API says so in its own response. Claiming a live multi-hospital
# federation would be a lie the architecture cannot currently back.
#
# What federation buys is stated precisely: only medians and scales cross the
# boundary. No record, event or identifier leaves the institution.

SIMULATED_PEERS = [
    ("St. Mary's Regional", 1.15, 0.9),
    ("Northside Teaching Hospital", 0.85, 1.25),
    ("Coastal Community Clinic", 1.35, 0.75),
]


@app.post("/api/admin/security/federated/round")
def run_federated_round(session: dict = Depends(require_role("Administrator"))):
    """Fit this hospital's local model, then aggregate a federated round."""
    import json
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            windows = aisec.extract_windows(cur, hours=720)
            if not windows:
                raise HTTPException(status_code=400, detail="No activity to learn from yet.")

            # Per-role local model: detection compares each actor with their own
            # role, so the shared model must be per role too (version 2 params).
            local_baselines = aisec.fit_role_baselines(windows)
            local_params = aisec.role_parameters(local_baselines)
            local_samples = len(windows)
            cur.execute("SELECT COALESCE(MAX(round_number), 0) + 1 AS n FROM FederatedRounds")
            rnd = cur.fetchone()["n"]

            nodes: list[tuple[str, int, dict]] = []

            # This node is real: parameters fitted from this hospital's activity.
            cur.execute(
                """INSERT INTO FederatedRounds (round_number, node_name, is_simulated,
                                                sample_count, local_parameters)
                   VALUES (%s,%s,FALSE,%s,%s)""",
                (rnd, "This hospital (local)", local_samples, json.dumps(local_params)))
            nodes.append(("This hospital (local)", local_samples, local_params))

            # Real peer submissions for this round take precedence. Simulated
            # peers exist to demonstrate the aggregation when nobody has
            # federated yet; the moment a real institution submits, padding the
            # round with invented nodes would misrepresent the result.
            cur.execute(
                """SELECT node_name, sample_count, local_parameters
                     FROM FederatedRounds
                    WHERE round_number = %s AND is_simulated = FALSE
                      AND node_name <> 'This hospital (local)'""",
                (rnd,))
            real_peers = cur.fetchall()
            for peer in real_peers:
                nodes.append((peer["node_name"], peer["sample_count"], peer["local_parameters"]))

            # Also pick up submissions filed against the previous round, since a
            # peer cannot know the round number this node is about to open.
            if not real_peers:
                cur.execute(
                    """SELECT DISTINCT ON (node_name) node_name, sample_count, local_parameters
                         FROM FederatedRounds
                        WHERE is_simulated = FALSE AND node_name <> 'This hospital (local)'
                          AND created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
                        ORDER BY node_name, round_number DESC""")
                recent = cur.fetchall()
                for peer in recent:
                    nodes.append((peer["node_name"], peer["sample_count"], peer["local_parameters"]))
                    cur.execute(
                        """INSERT INTO FederatedRounds (round_number, node_name, is_simulated,
                                                        sample_count, local_parameters)
                           VALUES (%s, %s, FALSE, %s, %s)
                           ON CONFLICT (round_number, node_name) DO NOTHING""",
                        (rnd, peer["node_name"], peer["sample_count"],
                         psycopg.types.json.Json(peer["local_parameters"])))
                real_peers = recent

            simulated_used = 0 if real_peers else len(SIMULATED_PEERS)
            for name, m_scale, s_scale in (SIMULATED_PEERS if not real_peers else []):
                roles = {
                    role: {
                        "medians": {k: round(v * m_scale, 4) for k, v in b.medians.items()},
                        "scales": {k: round(v * s_scale, 4) for k, v in b.scales.items()},
                        "sample_count": max(1, int(b.sample_count * m_scale)),
                    } for role, b in local_baselines.items()
                }
                params = {"version": aisec.PARAMETERS_VERSION, "roles": roles}
                samples = max(1, int(local_samples * m_scale))
                cur.execute(
                    """INSERT INTO FederatedRounds (round_number, node_name, is_simulated,
                                                    sample_count, local_parameters)
                       VALUES (%s,%s,TRUE,%s,%s)""",
                    (rnd, name, samples, json.dumps(params)))
                nodes.append((name, samples, params))

            global_params = aisec.federated_average_roles(nodes)
            real_nodes = 1 + len(real_peers)
            cur.execute(
                """INSERT INTO FederatedGlobalModel (round_number, parameters,
                                                     contributing_nodes, total_samples,
                                                     real_nodes, simulated_nodes)
                   VALUES (%s,%s,%s,%s,%s,%s)""",
                (rnd, json.dumps(global_params), global_params["contributing_nodes"],
                 global_params["total_samples"], real_nodes, simulated_used))
            log_admin_action(conn, session["user_id"], session.get("public_user_id"),
                             "FEDERATED_ROUND_COMPLETED")
            conn.commit()

    # A model real institutions built replaces the local baseline in detection;
    # drop the cached one so the next access is scored against it.
    risk_engine.invalidate_baselines()
    real_peer_count = len(real_peers)
    if real_peer_count:
        disclosure = (
            f"{real_peer_count + 1} real nodes: this hospital plus "
            f"{real_peer_count} peer institution(s) that submitted signed parameters. "
            "No simulated nodes were included. Only medians and scales are "
            "aggregated — no record, event or identifier crosses the boundary."
        )
    else:
        disclosure = (
            f"One real node (this hospital) and {simulated_used} simulated peers, "
            "because no peer institution has submitted yet. The aggregation is genuine "
            "FedAvg; the peers are not real institutions. Register a peer and have it "
            "POST to /api/federated/submit to federate for real."
        )

    return {
        "round": rnd,
        "aggregation": "FedAvg (weighted by sample count)",
        "contributing_nodes": global_params["contributing_nodes"],
        "total_samples": global_params["total_samples"],
        "local_node_is_real": True,
        "real_peer_nodes": real_peer_count,
        "peer_nodes_simulated": simulated_used,
        "used_for_detection": real_peer_count > 0,
        "disclosure": disclosure + (
            " This model now replaces the local baseline in detection for the roles it describes."
            if real_peer_count else
            " A model that includes simulated peers is never used to score real people."),
        "global_parameters": global_params,
    }


@app.get("/api/admin/security/federated/status")
def federated_status(session: dict = Depends(require_role("Administrator"))):
    """Federated IDS status: rounds, nodes, the current global model, and
    which model detection is actually using."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""SELECT * FROM FederatedGlobalModel
                            ORDER BY round_number DESC LIMIT 1""")
            latest = cur.fetchone()
            cur.execute("""SELECT node_name, is_simulated, sample_count, round_number
                             FROM FederatedRounds
                            WHERE round_number = COALESCE(
                                (SELECT MAX(round_number) FROM FederatedRounds), 0)
                            ORDER BY is_simulated, node_name""")
            nodes = cur.fetchall()
            cur.execute("SELECT COUNT(DISTINCT round_number) AS n FROM FederatedRounds")
            rounds = cur.fetchone()["n"]
            cur.execute("""SELECT hub_url, hub_round, real_nodes, pulled_at
                             FROM FederatedHubModels ORDER BY pulled_at DESC LIMIT 1""")
            hub_model = cur.fetchone()
            in_use, in_use_label = risk_engine.usable_federated_model(cur)

    real_nodes = (latest or {}).get("real_nodes") or 0
    simulated = (latest or {}).get("simulated_nodes") or 0
    if not rounds and not hub_model:
        state, disclosure = "NOT_YET_RUN", "No federated round has run yet."
    elif real_nodes >= 2 or hub_model:
        state = "LIVE_FEDERATION"
        disclosure = (f"The latest model was built by {real_nodes} real institution(s)"
                      + (f" and {simulated} simulated node(s)" if simulated else "")
                      + "." if latest else "A global model was pulled from a federation hub.")
    else:
        state = "SIMULATED_PEERS"
        disclosure = ("Federated aggregation runs for real, but no peer institution has "
                      "submitted yet, so the other nodes in the latest round are simulated. "
                      "That model is not used to score anyone.")

    s_ = federation.settings()
    return {
        "rounds_completed": rounds,
        "latest_round": latest["round_number"] if latest else None,
        "aggregation": "FedAvg, per role",
        "global_model": latest["parameters"] if latest else None,
        "real_nodes": real_nodes,
        "simulated_nodes": simulated,
        "nodes": [{"name": n["node_name"], "simulated": n["is_simulated"],
                   "samples": n["sample_count"]} for n in nodes],
        "status": state,
        "detection_baseline": in_use_label or "local (no real federated model yet)",
        "participant": {
            "configured": federation.is_configured(),
            "hub_url": s_["hub_url"], "node_name": s_["node_name"],
            "last_pulled": ({"hub_round": hub_model["hub_round"],
                             "real_nodes": hub_model["real_nodes"],
                             "pulled_at": hub_model["pulled_at"]} if hub_model else None),
        },
        "disclosure": disclosure,
    }


# ─── This hospital as a participant in someone else's federation ────────────

@app.post("/api/admin/federated/hub/submit")
def submit_to_federation_hub(session: dict = Depends(require_role("Administrator"))):
    """Fit this hospital's per-role model and submit it, signed, to the hub."""
    if not federation.is_configured():
        raise HTTPException(status_code=409, detail=(
            "This hospital is not configured as a federation participant. Set "
            "FEDERATION_HUB_URL, FEDERATION_NODE_NAME and FEDERATION_SHARED_SECRET."))
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            try:
                result = federation.submit_local_update(cur)
            except federation.FederationError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            log_admin_action(conn, session["user_id"], session.get("public_user_id"),
                             "FEDERATED_UPDATE_SUBMITTED",
                             details={"round": result.get("round_number"),
                                      "roles": result.get("roles")})
            conn.commit()
    return {**result, "note": "Only per-role medians and scales were sent. No records, "
                              "events or identifiers left this hospital."}


@app.post("/api/admin/federated/hub/pull")
def pull_from_federation_hub(session: dict = Depends(require_role("Administrator"))):
    """Fetch the hub's global model and start scoring with it."""
    if not federation.is_configured():
        raise HTTPException(status_code=409, detail=(
            "This hospital is not configured as a federation participant."))
    try:
        model = federation.pull_global_model()
    except federation.FederationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            federation.store_pulled_model(cur, model)
            log_admin_action(conn, session["user_id"], session.get("public_user_id"),
                             "FEDERATED_MODEL_PULLED",
                             details={"hub_round": model.get("round_number")})
            conn.commit()
    risk_engine.invalidate_baselines()
    roles = sorted(aisec.as_role_parameters(model["parameters"]))
    return {"status": "success", "hub_round": model.get("round_number"),
            "contributing_nodes": model.get("contributing_nodes"),
            "real_nodes": model.get("real_nodes"), "roles": roles,
            "note": "Detection now uses this global model for the roles it describes."}


# ─────────────────────────────────────────────────────────────────────────────
# Imaging delivery (closes a dead end)
#
# Studies were encrypted, signed and anchored correctly, and the patient was
# even notified that one was ready — but only the uploading technician could
# open it. A patient was told to view something they could not reach, and the
# doctor who needed to read the scan had no access at all. The protection was
# real; the delivery was missing.
# ─────────────────────────────────────────────────────────────────────────────

_IMAGING_SELECT = """
    SELECT ir.*, p.full_name AS patient_name, p.user_id AS patient_user_id,
           t.full_name AS technician_name
      FROM ImagingReports ir
      JOIN Users p ON p.id = ir.patient_id
      LEFT JOIN Users t ON t.id = ir.lab_tech_id
"""


def _imaging_summary(r: dict) -> dict:
    """Shape one imaging row for a list. Never carries the image payload.

    Decrypting every study to render a list would be both wasteful and needless
    exposure — images are released one at a time, on request.
    """
    return {
        "id": str(r["id"]),
        "patient_name": r.get("patient_name"),
        "patient_user_id": r.get("patient_user_id"),
        "technician_name": r.get("technician_name"),
        "scan_region": r.get("scan_region"),
        "exam_type": r.get("exam_type"),
        "clinical_history": r.get("clinical_history"),
        "findings": r.get("findings"),
        "impression": r.get("impression"),
        "recommendations": r.get("recommendations"),
        "has_image": bool(r.get("encrypted_image") or r.get("image_data")),
        "document_hash": r.get("document_hash"),
        "kem_algorithm": r.get("kem_algorithm"),
        "signature_algorithm": r.get("signature_algorithm"),
        "blockchain_tx_hash": r.get("blockchain_tx_hash"),
        "created_at": r.get("created_at"),
    }


def _release_imaging_payload(r: dict, imaging_id: str) -> dict:
    """Decrypt one study after verifying it. Shared by every reader.

    One implementation for patient, doctor and technician so a study cannot be
    released to one role under weaker checks than another.
    """
    if not r.get("encrypted_image"):
        if r.get("image_data"):
            return {"image_data": r["image_data"], "encrypted": False}
        raise HTTPException(status_code=404, detail="No image stored for this study.")

    ciphertext = r["encrypted_image"]
    if not ciphertext and r.get("s3_key"):
        try:
            ciphertext = download_file_from_s3(r["s3_key"]).decode("utf-8")
        except StorageError as exc:
            logger.error("S3 recovery failed for imaging %s: %s", imaging_id, exc)
    # Third copy. Now that content is genuinely pinned, IPFS is a real recovery
    # path rather than a fingerprint — worth trying before giving up.
    if not ciphertext and r.get("ipfs_cid") and is_ipfs_configured():
        try:
            ciphertext = fetch_from_ipfs(r["ipfs_cid"]).decode("utf-8")
            logger.info("Recovered imaging %s from IPFS", imaging_id)
        except IPFSError as exc:
            logger.error("IPFS recovery failed for imaging %s: %s", imaging_id, exc)

    try:
        shared_secret = decapsulate_aes_key(r["encrypted_aes_key"], r["mlkem_private_key_encrypted"])
        image_bytes = decrypt_document(
            ciphertext, derive_aes_key(shared_secret),
            r["encryption_nonce"], r["encryption_tag"],
        )
    except PQCUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise _IntegrityFailure(status_code=409, detail="Image failed its integrity check.") from exc

    if sha256_hex(image_bytes) != r.get("document_hash"):
        raise _IntegrityFailure(status_code=409, detail="Image digest does not match the recorded hash.")

    return {"image_data": image_bytes.decode("utf-8"), "encrypted": True}


@app.get("/api/patient/imaging")
def get_patient_imaging(session: dict = Depends(require_role("Patient"))):
    """A patient's own imaging studies."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                _IMAGING_SELECT + " WHERE ir.patient_id = %s ORDER BY ir.created_at DESC",
                (session["user_id"],))
            return [_imaging_summary(r) for r in cur.fetchall()]


@app.get("/api/patient/imaging/{imaging_id}/image")
def get_patient_imaging_image(imaging_id: str, session: dict = Depends(require_role("Patient"))):
    """Release one of the patient's own studies, scoped by patient_id."""
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT ir.*, u.mlkem_private_key_encrypted,
                          t.mldsa_public_key AS signer_mldsa_public_key
                     FROM ImagingReports ir JOIN Users u ON u.id = ir.patient_id
                     LEFT JOIN Users t ON t.id = ir.lab_tech_id
                    WHERE ir.id = %s AND ir.patient_id = %s""",
                (imaging_id, user_uuid))
            r = cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="Imaging report not found")
            payload = _release_verified(conn, session,
                                        lambda: _release_imaging_payload(r, imaging_id), r,
                                        resource=f"Imaging {imaging_id}",
                                        patient_id=str(user_uuid))
            log_admin_action(conn, user_uuid, session.get("public_user_id"),
                             "PATIENT_VIEWED_IMAGING", str(user_uuid), session.get("public_user_id"))
            aisec.record_security_event(
                cur, actor_id=user_uuid, actor_public_id=session.get("public_user_id"),
                actor_role="Patient", event_type="RECORD_ACCESS",
                subject_patient_id=str(user_uuid), resource="imaging")
            conn.commit()
    return payload


@app.get("/api/doctor/imaging")
def get_doctor_imaging(patient_id: Optional[str] = None,
                       session: dict = Depends(require_role("Doctor"))):
    """Imaging for patients this doctor is entitled to read.

    Entitlement is the same test the chart uses, so a doctor cannot reach a scan
    for a patient whose record they could not open.
    """
    doctor_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if patient_id:
                allowed, basis = _doctor_patient_authorization(cur, doctor_uuid, patient_id)
                if not allowed:
                    _deny(cur, session, resource="imaging", reason=basis, patient_id=str(patient_id),
                          detail=f"You do not have access to this patient's imaging — {basis}.")
                cur.execute(
                    _IMAGING_SELECT + " WHERE ir.patient_id = %s ORDER BY ir.created_at DESC",
                    (patient_id,))
                return [_imaging_summary(r) for r in cur.fetchall()]

            # No patient named: every study for a patient this doctor treats,
            # minus anyone who has withdrawn or been refused.
            cur.execute(
                _IMAGING_SELECT + """
                 WHERE EXISTS (
                     SELECT 1 FROM Diagnoses d WHERE d.doctor_id = %s AND d.patient_id = ir.patient_id
                     UNION ALL SELECT 1 FROM Appointments a WHERE a.doctor_id = %s AND a.patient_id = ir.patient_id
                     UNION ALL SELECT 1 FROM LabTestRequests l WHERE l.doctor_id = %s AND l.patient_id = ir.patient_id
                     UNION ALL SELECT 1 FROM DoctorConsultations c WHERE c.doctor_id = %s AND c.patient_id = ir.patient_id
                     UNION ALL SELECT 1 FROM Consent k WHERE k.subject_user_id = %s AND k.patient_id = ir.patient_id
                                                        AND k.status = 'Authorized'
                 )
                 AND NOT EXISTS (
                     SELECT 1 FROM Consent c2 WHERE c2.patient_id = ir.patient_id
                       AND c2.subject_user_id = %s AND c2.status IN ('Revoked', 'Rejected')
                 )
                 ORDER BY ir.created_at DESC""",
                (doctor_uuid,) * 6)
            return [_imaging_summary(r) for r in cur.fetchall()]


@app.get("/api/doctor/imaging/{imaging_id}/image")
def get_doctor_imaging_image(imaging_id: str, session: dict = Depends(require_role("Doctor"))):
    """Release one study to an entitled doctor."""
    doctor_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT ir.*, u.mlkem_private_key_encrypted,
                          t.mldsa_public_key AS signer_mldsa_public_key
                     FROM ImagingReports ir JOIN Users u ON u.id = ir.patient_id
                     LEFT JOIN Users t ON t.id = ir.lab_tech_id
                    WHERE ir.id = %s""", (imaging_id,))
            r = cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="Imaging report not found")

            allowed, basis = _doctor_patient_authorization(cur, doctor_uuid, str(r["patient_id"]))
            if not allowed:
                _deny(cur, session, resource="imaging", reason=basis,
                      patient_id=str(r["patient_id"]),
                      detail=f"You do not have access to this patient's imaging — {basis}.")
            decision = _security_gate(cur, session, resource="imaging",
                                      patient_id=str(r["patient_id"]))

            payload = _release_verified(conn, session,
                                        lambda: _release_imaging_payload(r, imaging_id), r,
                                        resource=f"Imaging {imaging_id}",
                                        patient_id=str(r["patient_id"]))
            log_admin_action(conn, doctor_uuid, session.get("public_user_id"),
                             "DOCTOR_VIEWED_IMAGING", str(r["patient_id"]), None,
                             details={"basis": basis, "risk_level": decision.level})
            _record_access(cur, session, patient_id=str(r["patient_id"]), resource="imaging",
                           basis=basis, decision=decision)
            conn.commit()
    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Medication adherence (closes a dead end)
#
# Nurses recorded every round — Administered, Refused, Held, Missed — and no
# endpoint ever returned it. A prescriber could not see whether their
# prescription was being taken, and a patient refusing medication was recorded
# without ever surfacing. Refusals and missed doses are exactly what a
# prescriber needs to know.
# ─────────────────────────────────────────────────────────────────────────────

_ADHERENCE_SELECT = """
    SELECT ma.id, ma.status, ma.remarks, ma.administered_at,
           ma.prescription_id,
           n.full_name AS nurse_name,
           p.medicine_name, p.dosage, p.frequency,
           d.full_name AS prescriber_name
      FROM MedicationAdministration ma
      LEFT JOIN Users n ON n.id = ma.nurse_id
      LEFT JOIN Prescriptions p ON p.id = ma.prescription_id
      LEFT JOIN Users d ON d.id = p.doctor_id
"""


def _adherence_record(r: dict) -> dict:
    """Shape one administration row, decrypting the medicine it refers to."""
    return {
        "id": str(r["id"]),
        "prescription_id": str(r["prescription_id"]) if r.get("prescription_id") else None,
        "medicine_name": _dec(r.get("medicine_name")),
        "dosage": _dec(r.get("dosage")),
        "frequency": _dec(r.get("frequency")),
        "status": r.get("status"),
        "remarks": r.get("remarks"),
        "nurse_name": r.get("nurse_name"),
        "prescriber_name": r.get("prescriber_name"),
        "administered_at": r.get("administered_at"),
    }


def _adherence_summary(rows: list[dict]) -> dict:
    """Counts plus the figure that actually matters.

    Percentages alone hide the clinically important part: a 90% adherence rate
    reads as fine while concealing that every missing dose was an active
    refusal. Refusals and misses are therefore surfaced in their own right.
    """
    total = len(rows)
    counts = {s: 0 for s in ("Administered", "Refused", "Held", "Missed")}
    for r in rows:
        if r["status"] in counts:
            counts[r["status"]] += 1
    taken = counts["Administered"]
    return {
        "total_rounds": total,
        "administered": taken,
        "refused": counts["Refused"],
        "held": counts["Held"],
        "missed": counts["Missed"],
        "adherence_percent": round(taken / total * 100, 1) if total else None,
        "needs_attention": counts["Refused"] + counts["Missed"] > 0,
    }


@app.get("/api/doctor/patients/{patient_id}/adherence")
def get_patient_adherence(patient_id: str, session: dict = Depends(require_role("Doctor"))):
    """Whether this patient is actually taking what was prescribed."""
    doctor_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            allowed, basis = _doctor_patient_authorization(cur, doctor_uuid, patient_id)
            if not allowed:
                _deny(cur, session, resource="adherence", reason=basis, patient_id=str(patient_id),
                      detail=f"You do not have access to this patient's record — {basis}.")
            decision = _security_gate(cur, session, resource="adherence",
                                      patient_id=str(patient_id))
            _record_access(cur, session, patient_id=str(patient_id), resource="adherence",
                           basis=basis, decision=decision)
            cur.execute(
                _ADHERENCE_SELECT + " WHERE ma.patient_id = %s ORDER BY ma.administered_at DESC LIMIT 200",
                (patient_id,))
            rows = [_adherence_record(r) for r in cur.fetchall()]
    return {"summary": _adherence_summary(rows), "rounds": rows}


@app.get("/api/patient/adherence")
def get_own_adherence(session: dict = Depends(require_role("Patient"))):
    """A patient's own medication history — what was given, and what was not."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                _ADHERENCE_SELECT + " WHERE ma.patient_id = %s ORDER BY ma.administered_at DESC LIMIT 200",
                (session["user_id"],))
            rows = [_adherence_record(r) for r in cur.fetchall()]
    return {"summary": _adherence_summary(rows), "rounds": rows}


# ─────────────────────────────────────────────────────────────────────────────
# Zero-knowledge consent proofs (spec §17)
#
# A doctor proves they hold the consent token the patient's approval issued,
# without transmitting it. New consents use the lattice proof in
# app/zkp_lattice.py (Module-LWE/SIS, ML-DSA-65 parameters — post-quantum).
# Consents approved before that switch carry Schnorr commitments; those still
# verify, and every response says plainly that they are not post-quantum.
#
# This runs *alongside* the ordinary consent check rather than instead of it.
# A proof failing does not open a record, and a proof succeeding does not open
# one either: authorization is still decided by relationship and consent state.
# What the proof adds is evidence that the party presenting it is the one the
# patient actually approved.
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/doctor/consent-token/{patient_id}")
def collect_consent_token(patient_id: str, session: dict = Depends(require_role("Doctor"))):
    """Collect the consent token for an approved relationship.

    Delivered once. After collection the server keeps only the commitment, so a
    later database compromise cannot recover the token.
    """
    doctor_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT consent_id, status::text AS status, zkp_commitment,
                          zkp_token_encrypted, zkp_token_collected_at
                     FROM Consent
                    WHERE patient_id = %s AND subject_user_id = %s AND subject_role = 'Doctor'""",
                (patient_id, doctor_uuid))
            row = cur.fetchone()
            if not row or row["status"] != "Authorized":
                raise HTTPException(status_code=404, detail="No approved consent for this patient.")
            if not row["zkp_token_encrypted"]:
                # Two very different situations. Telling a doctor their consent
                # predates the feature when in fact they already collected the
                # token would send them to the patient for no reason.
                if row["zkp_token_collected_at"]:
                    raise HTTPException(
                        status_code=409,
                        detail="You already collected this token on "
                               f"{row['zkp_token_collected_at']:%d %b %Y at %H:%M}. It is "
                               "delivered once and the server no longer holds it. Ask the "
                               "patient to withdraw and re-approve to have a new one issued.")
                raise HTTPException(
                    status_code=409,
                    detail="This consent predates zero-knowledge tokens. Ask the patient to "
                           "withdraw and re-approve to have one issued.")

            token = decrypt_data(row["zkp_token_encrypted"])
            cur.execute(
                """UPDATE Consent SET zkp_token_encrypted = NULL,
                          zkp_token_collected_at = CURRENT_TIMESTAMP
                    WHERE consent_id = %s""", (row["consent_id"],))
            log_admin_action(conn, doctor_uuid, session.get("public_user_id"),
                             "ZKP_TOKEN_COLLECTED", str(patient_id), None)
            conn.commit()

    return {
        "consent_token": token,
        "commitment": row["zkp_commitment"],
        "scheme": zkp.scheme_of(row["zkp_commitment"]),
        "post_quantum_secure": zkp.is_post_quantum(row["zkp_commitment"]),
        "delivered_once": True,
        "notice": "Store this securely. The server has now discarded it and keeps only "
                  "the public commitment. Proofs are made on your side — in the browser "
                  "on the patient's page, or with backend/demo/zkp_prove.py — so the token "
                  "never has to be sent again.",
    }


@app.post("/api/doctor/zkp/challenge")
def request_zkp_challenge(patient_id: str = Query(...),
                          session: dict = Depends(require_role("Doctor"))):
    """Get a single-use nonce to bind one proof to one verification."""
    doctor_uuid = session["user_id"]
    challenge = zkp.make_challenge()
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT zkp_commitment FROM Consent
                    WHERE patient_id = %s AND subject_user_id = %s
                      AND status = 'Authorized' AND zkp_commitment IS NOT NULL""",
                (patient_id, doctor_uuid))
            consent = cur.fetchone()
            if not consent:
                raise HTTPException(status_code=404, detail="No approved consent for this patient.")
            cur.execute(
                """INSERT INTO ZkpChallenges (challenge, subject_user_id, patient_id)
                   VALUES (%s, %s, %s)""", (challenge, doctor_uuid, patient_id))
            conn.commit()
    # The scheme tells the prover which kind of proof this consent expects.
    return {"challenge": challenge, "expires_in_seconds": 300,
            "context": f"consent:{patient_id}",
            "scheme": zkp.scheme_of(consent["zkp_commitment"])}


@app.post("/api/doctor/zkp/verify")
def verify_zkp_proof(body: ZkpProofRequest, session: dict = Depends(require_role("Doctor"))):
    """Verify a proof of knowledge of the consent token."""
    doctor_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT id, patient_id, consumed_at, expires_at
                     FROM ZkpChallenges
                    WHERE challenge = %s AND subject_user_id = %s""",
                (body.challenge, doctor_uuid))
            ch = cur.fetchone()
            if not ch:
                raise HTTPException(status_code=404, detail="Unknown challenge.")
            if ch["consumed_at"]:
                raise HTTPException(status_code=409, detail="That challenge was already used.")
            if ch["expires_at"] < datetime.now(timezone.utc):
                raise HTTPException(status_code=410, detail="That challenge has expired.")

            cur.execute(
                """SELECT zkp_commitment FROM Consent
                    WHERE patient_id = %s AND subject_user_id = %s AND status = 'Authorized'""",
                (ch["patient_id"], doctor_uuid))
            consent = cur.fetchone()
            if not consent or not consent["zkp_commitment"]:
                raise HTTPException(status_code=404, detail="No commitment recorded for this consent.")

            commitment = consent["zkp_commitment"]
            ok = zkp.verify(
                commitment,
                body.as_proof(),
                body.challenge,
                f"consent:{ch['patient_id']}",
            )

            # Consumed either way. A challenge that survives a failed attempt
            # lets an attacker grind against one nonce.
            cur.execute(
                "UPDATE ZkpChallenges SET consumed_at = CURRENT_TIMESTAMP, verified = %s WHERE id = %s",
                (ok, ch["id"]))
            log_admin_action(conn, doctor_uuid, session.get("public_user_id"),
                             "ZKP_PROOF_VERIFIED" if ok else "ZKP_PROOF_FAILED",
                             str(ch["patient_id"]), None)
            aisec.record_security_event(
                cur, actor_id=doctor_uuid, actor_public_id=session.get("public_user_id"),
                actor_role="Doctor",
                event_type="ZKP_PROOF" if ok else "ZKP_PROOF_FAILED",
                subject_patient_id=str(ch["patient_id"]), resource="consent_proof")
            conn.commit()

    post_quantum = zkp.is_post_quantum(commitment)
    return {
        "verified": ok,
        "scheme": zkp.scheme_of(commitment),
        "proves": "knowledge of the consent token issued when this patient approved access",
        "reveals": "nothing about the token itself",
        "post_quantum_secure": post_quantum,
        "caveat": (
            "Lattice proof (Fiat–Shamir with aborts, ML-DSA-65 parameters): rests on "
            "Module-LWE and Module-SIS, the same assumptions as ML-DSA. Not itself a "
            "NIST-standardised scheme."
            if post_quantum else
            "This consent predates the post-quantum proof and still uses Schnorr, which "
            "rests on discrete logarithm — broken by Shor's algorithm. Ask the patient to "
            "withdraw and re-approve to have a post-quantum token issued."
        ),
    }


@app.get("/api/admin/ipfs/status")
def get_ipfs_status(session: dict = Depends(require_role("Administrator"))):
    """Live IPFS node health, and an honest count of what is actually published.

    Reports 'not configured' separately from 'configured but unreachable' —
    those need different actions from whoever is on call. When replication is
    configured it adds, per target, how many documents are confirmed pinned,
    still queued, or failed; without it, it says plainly that pinning on one
    node is not replication.
    """
    status = ipfs_status()
    configured = ipfs_replication.targets()
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT COUNT(*) AS total,
                          COUNT(ipfs_cid) AS with_cid
                     FROM LabReports""")
            reports = cur.fetchone()
            replicas, documents = [], set()
            if configured or ipfs_replication.config_errors():
                cur.execute("SELECT cid, target, status FROM IpfsReplicas")
                replicas = cur.fetchall()
                documents = _document_cids(cur)
    status["reports_total"] = reports["total"]
    status["reports_with_cid"] = reports["with_cid"]

    status["replication"] = None
    if configured or ipfs_replication.config_errors():
        pinned = ipfs_replication.primary_pins() if status["connected"] else None
        status["replication"] = ipfs_replication.summarise(
            replicas, configured, documents & pinned if pinned is not None else None)
    return status


def _document_cids(cur) -> set[str]:
    """Every CID a stored document points at, across all three document tables."""
    cur.execute(
        """SELECT ipfs_cid FROM LabReports WHERE ipfs_cid IS NOT NULL
           UNION SELECT ipfs_cid FROM ImagingReports WHERE ipfs_cid IS NOT NULL
           UNION SELECT ipfs_cid FROM MedicalDocuments WHERE ipfs_cid IS NOT NULL""")
    return {r["ipfs_cid"] for r in cur.fetchall()}


@app.post("/api/admin/ipfs/replication/sync")
def sync_ipfs_replication(session: dict = Depends(require_role("Administrator"))):
    """Bring every published document up to full replication.

    New documents replicate on their own as they are filed. This covers the
    rest: documents published before replication was configured, targets added
    since, and requests that failed. It also polls pinning services for requests
    still queued, since a service only reports progress when asked.

    Replication itself runs in the background; this returns what was started.
    """
    configured = ipfs_replication.targets()
    if not configured:
        raise HTTPException(
            status_code=409,
            detail="No replication targets are configured. Set IPFS_REPLICA_NODES or "
                   "IPFS_PINNING_SERVICES." + (" " + " ".join(ipfs_replication.config_errors())
                                              if ipfs_replication.config_errors() else ""))
    pinned = ipfs_replication.primary_pins()
    if pinned is None:
        raise HTTPException(
            status_code=503,
            detail="The primary IPFS node cannot be reached, so there is nothing to replicate from.")

    by_name = {t.name: t for t in configured}
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT cid, target, status, request_id FROM IpfsReplicas")
            rows = cur.fetchall()
            documents = _document_cids(cur)

        # 1. Poll services about requests still in flight.
        refreshed = []
        for row in rows:
            target = by_name.get(row["target"])
            if (target and target.kind == "service" and row["request_id"]
                    and row["status"] in ("queued", "pinning")):
                update = ipfs_replication.refresh(target, row["request_id"])
                if update["status"]:
                    row["status"] = update["status"]
                    refreshed.append({"cid": row["cid"], "target": target.name, "kind": "service",
                                      "status": update["status"], "request_id": row["request_id"],
                                      "error": None})
        if refreshed:
            ipfs_replication.record(conn, refreshed)

        # 2. Ask for whatever copies are missing. A failed replica is retried; a
        #    queued or pinned one is left alone.
        live = {(r["cid"], r["target"]) for r in rows if r["status"] in ipfs_replication.LIVE}
        publishable = documents & pinned
        scheduled = 0
        for cid in sorted(publishable):
            missing = {name for name in by_name if (cid, name) not in live}
            if missing:
                ipfs_replication.schedule(cid, f"quantumcare-{cid}", only=missing)
                scheduled += 1

        log_admin_action(conn, session["user_id"], session.get("public_user_id"),
                         "IPFS_REPLICATION_SYNC")
        conn.commit()

    return {
        "documents_published": len(publishable),
        # CIDs recorded while no node was running were computed, never published;
        # they cannot be replicated until the document is re-published.
        "documents_not_on_node": len(documents - pinned),
        "requests_refreshed": len(refreshed),
        "documents_scheduled": scheduled,
        "note": "Replication runs in the background. Refresh the status to see confirmed copies.",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Real federation peers (spec §20–21)
#
# The simulated peers demonstrate the aggregation; these endpoints make it
# deployable. A second QuantumCare instance registers as a peer, fits its own
# baseline locally, and submits only the parameters — medians and scales. No
# record, event or identifier crosses the boundary, which is the entire reason
# to federate rather than pool.
#
# Submissions are HMAC-signed with a per-peer shared secret. Without that, any
# party who can reach this endpoint could drag the global baseline wherever
# they liked and silently blind every participant's detector.
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/api/admin/federated/peers")
def register_federated_peer(req: RegisterPeerRequest,
                            session: dict = Depends(require_role("Administrator"))):
    """Register a peer institution and mint its shared secret.

    The secret is shown once and stored encrypted, in the same shape as
    ML-KEM private keys and ZKP consent tokens.
    """
    secret = secrets.token_hex(32)
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT 1 FROM FederatedPeers WHERE node_name = %s", (req.node_name,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="A peer with that name is already registered.")
            cur.execute(
                """INSERT INTO FederatedPeers (node_name, shared_secret_encrypted, contact_url)
                   VALUES (%s, %s, %s) RETURNING id""",
                (req.node_name, encrypt_data(secret), req.contact_url))
            peer_id = cur.fetchone()["id"]
            log_admin_action(conn, session["user_id"], session.get("public_user_id"),
                             "FEDERATED_PEER_REGISTERED")
            conn.commit()
    return {
        "peer_id": str(peer_id),
        "node_name": req.node_name,
        "shared_secret": secret,
        "delivered_once": True,
        "notice": "Give this to the peer institution over a secure channel. It is stored "
                  "encrypted here and will not be shown again.",
    }


@app.get("/api/admin/federated/peers")
def list_federated_peers(session: dict = Depends(require_role("Administrator"))):
    """Registered peers, and whether any have actually submitted."""
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT id, node_name, contact_url, is_active, submissions,
                          last_submission_at, created_at
                     FROM FederatedPeers ORDER BY node_name""")
            peers = [{**r, "id": str(r["id"])} for r in cur.fetchall()]
    return {
        "peers": peers,
        "total": len(peers),
        "active_contributors": sum(1 for p in peers if p["submissions"] > 0),
        "note": "Peers listed here are real remote institutions. The simulated nodes that "
                "appear in a federated round are separate and always flagged as simulated.",
    }


@app.post("/api/admin/federated/peers/{peer_id}/{action}")
def set_federated_peer_active(peer_id: str, action: str,
                              session: dict = Depends(require_role("Administrator"))):
    """Suspend or reinstate a peer.

    A suspended peer's submissions are refused with 403, which is how a
    compromised or departed institution is cut off without losing its history.
    Its parameters already in past rounds stay, as the record of what was used.
    """
    states = {"deactivate": False, "activate": True}
    if action not in states:
        raise HTTPException(status_code=400, detail="Action must be 'activate' or 'deactivate'.")
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "UPDATE FederatedPeers SET is_active = %s WHERE id = %s RETURNING node_name",
                (states[action], peer_id))
            peer = cur.fetchone()
            if not peer:
                raise HTTPException(status_code=404, detail="Peer not found.")
            log_admin_action(conn, session["user_id"], session.get("public_user_id"),
                             "FEDERATED_PEER_ACTIVATED" if states[action] else "FEDERATED_PEER_DEACTIVATED",
                             details={"node_name": peer["node_name"]})
            conn.commit()
    return {"node_name": peer["node_name"], "is_active": states[action]}


@app.get("/api/federated/global-model")
def serve_global_model(request: Request):
    """Distribute the global model to a registered peer (spec §21).

    The "updated local models" step: without it peers could contribute but
    never benefit. Authenticated like a submission — an HMAC with the peer's
    shared secret over its name and a timestamp, refused if stale — and only a
    model built entirely by real institutions is ever handed out.
    """
    node = request.headers.get("X-Federation-Node", "")
    ts = request.headers.get("X-Federation-Timestamp", "")
    sig = request.headers.get("X-Federation-Signature", "")
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT shared_secret_encrypted, is_active FROM FederatedPeers WHERE node_name = %s",
                (node,))
            peer = cur.fetchone()
            if not peer or not peer["is_active"]:
                raise HTTPException(status_code=403, detail="Unknown or inactive peer.")
            if not federation.verify_request_signature(
                    node, ts, "global-model", decrypt_data(peer["shared_secret_encrypted"]), sig):
                aisec.record_security_event(
                    cur, actor_id=None, actor_role=None, event_type="FEDERATED_REQUEST_REJECTED",
                    resource=node[:120], ip_address=_client_ip(request))
                conn.commit()
                raise HTTPException(status_code=401, detail="Signature verification failed.")
            cur.execute(
                """SELECT round_number, parameters, contributing_nodes, total_samples, real_nodes
                     FROM FederatedGlobalModel
                    WHERE simulated_nodes = 0 AND real_nodes >= 2
                    ORDER BY round_number DESC LIMIT 1""")
            model = cur.fetchone()
    if not model:
        raise HTTPException(
            status_code=404,
            detail="No global model built by real institutions yet. Submit and wait for a round.")
    return {"round_number": model["round_number"], "parameters": model["parameters"],
            "contributing_nodes": model["contributing_nodes"],
            "total_samples": model["total_samples"], "real_nodes": model["real_nodes"],
            "aggregation": "FedAvg, per role"}


@app.post("/api/federated/submit")
def receive_peer_parameters(req: PeerSubmissionRequest, request: Request = None):
    """Accept a peer institution's model parameters.

    Deliberately not behind ``require_role``: the caller is another
    institution's server, not a user of this one. Authentication is the HMAC
    over the submission, checked against that peer's shared secret.
    """
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, shared_secret_encrypted, is_active FROM FederatedPeers WHERE node_name = %s",
                (req.node_name,))
            peer = cur.fetchone()
            if not peer or not peer["is_active"]:
                raise HTTPException(status_code=403, detail="Unknown or inactive peer.")

            secret = decrypt_data(peer["shared_secret_encrypted"])
            if not aisec.verify_parameters_signature(
                    req.node_name, req.round_number, req.sample_count,
                    req.parameters, secret, req.signature):
                logger.warning("Rejected federated submission from %s: bad signature", req.node_name)
                aisec.record_security_event(
                    cur, actor_id=None, actor_role=None,
                    event_type="FEDERATED_SUBMISSION_REJECTED",
                    resource=req.node_name,
                    ip_address=request.client.host if request and request.client else None)
                conn.commit()
                raise HTTPException(status_code=401, detail="Signature verification failed.")

            if not aisec.sane_parameters(req.parameters):
                raise HTTPException(
                    status_code=400,
                    detail="Parameters are outside plausible bounds and were not accepted.")

            cur.execute(
                """INSERT INTO FederatedRounds (round_number, node_name, is_simulated,
                                                sample_count, local_parameters)
                   VALUES (%s, %s, FALSE, %s, %s)
                   ON CONFLICT (round_number, node_name) DO UPDATE
                     SET sample_count = EXCLUDED.sample_count,
                         local_parameters = EXCLUDED.local_parameters,
                         created_at = CURRENT_TIMESTAMP""",
                (req.round_number, req.node_name, req.sample_count,
                 psycopg.types.json.Json(req.parameters)))
            cur.execute(
                """UPDATE FederatedPeers
                      SET submissions = submissions + 1,
                          last_submission_at = CURRENT_TIMESTAMP
                    WHERE id = %s""", (peer["id"],))
            conn.commit()

    return {"accepted": True, "round": req.round_number, "node": req.node_name,
            "note": "Parameters only. No records were transmitted or expected."}
