import hashlib
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
    PatientDocumentItem,
    NurseProfile, NurseDashboardSummary, NursePatientListItem,
    PatientVitalsRecord, CreateVitalsRequest, NursingNoteRecord, CreateNursingNoteRequest,
    ActivePrescriptionForNurse, MedicationAdministrationRecord, CreateMedicationAdministrationRequest,
    NursePatientDetail,
)
from app.config import get_settings
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
)

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
    init_db()

@app.get("/api/health")
def health_check():
    return {"status": "ok"}

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
            latest_diagnosis=latest_diag["title"] if latest_diag else None,
            current_treatment=f"{latest_rx['medicine_name']} ({latest_rx['dosage']})" if latest_rx else None,
            latest_prescription=latest_rx["medicine_name"] if latest_rx else None,
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
    return [DiagnosisRecord(
        id=str(r["id"]), title=r["title"], description=r["description"],
        symptoms=r["symptoms"], doctor_notes=r["doctor_notes"],
        recommended_tests=r["recommended_tests"],
        visit_date=r["visit_date"], doctor_name=r["doctor_name"],
        created_at=r["created_at"]
    ) for r in rows]


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
    return DiagnosisRecord(
        id=str(r["id"]), title=r["title"], description=r["description"],
        symptoms=r["symptoms"], doctor_notes=r["doctor_notes"],
        recommended_tests=r["recommended_tests"],
        visit_date=r["visit_date"], doctor_name=r["doctor_name"],
        created_at=r["created_at"]
    )


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

        pdf_bytes = _decrypt_report_pdf(report)

        if not verify_mldsa_signature(report.get("document_hash") or "",
                                      report.get("digital_signature") or "",
                                      report.get("signer_mldsa_public_key") or ""):
            logger.warning("Releasing report %s with an unverified ML-DSA signature", report_id)

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
    return _verify_report(report)


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
    return [PrescriptionRecord(
        id=str(r["id"]), medicine_name=r["medicine_name"], dosage=r["dosage"],
        frequency=r["frequency"], duration=r["duration"], instructions=r["instructions"],
        prescribed_date=r["prescribed_date"], doctor_name=r["doctor_name"]
    ) for r in rows]


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
                SELECT m.*, u.mlkem_private_key_encrypted
                FROM MedicalDocuments m
                JOIN Users u ON m.patient_id = u.id
                WHERE m.id = %s AND m.patient_id = %s
            """, (document_id, user_uuid))
            r = cur.fetchone()

        if not r:
            raise HTTPException(status_code=404, detail="Document not found")

        released = _decrypt_medical_document(r)

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
            """, (user_uuid, doctor_id, json.dumps({"reason": body.reason} if body.reason else {})))

            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'CONSENT_REVOKED', 'Record access withdrawn',
                        'A patient has withdrawn your access to their records. Emergency access remains available and is audited.')
            """, (doctor_id,))
            conn.commit()

        log_admin_action(
            conn, user_uuid, session.get("public_user_id"),
            "CONSENT_REVOKED", doctor_id, None,
            request.client.host if request and request.client else None,
            {"doctor": doctor["full_name"], "reason": body.reason},
        )

    return {"status": "success", "message": f"Dr. {doctor['full_name']} can no longer access your records."}


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
                DO UPDATE SET status = 'Authorized', granted_at = NOW(), revoked_at = NULL
            """, (user_uuid, doctor_id))

            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'CONSENT_GRANTED', 'Record access restored',
                        'A patient has restored your access to their records.')
            """, (doctor_id,))
            conn.commit()

        log_admin_action(
            conn, user_uuid, session.get("public_user_id"),
            "CONSENT_GRANTED", doctor_id, None,
            request.client.host if request and request.client else None,
            {"doctor": doctor["full_name"]},
        )

    return {"status": "success", "message": f"Dr. {doctor['full_name']}'s access has been restored."}


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

            # Check if assigned to this doctor
            cur.execute("""
                SELECT 1 FROM (
                    SELECT patient_id FROM Diagnoses WHERE doctor_id = %s AND patient_id = %s
                    UNION SELECT patient_id FROM Appointments WHERE doctor_id = %s AND patient_id = %s
                    UNION SELECT patient_id FROM DoctorConsultations WHERE doctor_id = %s AND patient_id = %s
                ) as assigned
            """, (user_uuid, patient_id, user_uuid, patient_id, user_uuid, patient_id))
            if not cur.fetchone():
                # Allow access anyway for emergency / new patients, or enforce it. 
                # For this demo, let's allow it as they might want to see any patient they search for.
                pass

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
        "diagnoses": [
            DiagnosisRecord(
                id=str(r["id"]), title=r["title"], description=r["description"],
                symptoms=r["symptoms"], doctor_notes=r["doctor_notes"],
                recommended_tests=r["recommended_tests"], visit_date=r["visit_date"],
                created_at=r["created_at"]
            ) for r in diagnoses
        ],
        "prescriptions": [
            PrescriptionRecord(
                id=str(r["id"]), medicine_name=r["medicine_name"], dosage=r["dosage"],
                frequency=r["frequency"], duration=r["duration"], instructions=r["instructions"],
                prescribed_date=r["prescribed_date"]
            ) for r in prescriptions
        ],
        "vitals": [_vitals_record(v) for v in vitals],
        "nursing_notes": [
            NursingNoteRecord(
                id=str(n["id"]), note_type=n["note_type"], content=n["content"],
                created_at=n["created_at"], nurse_name=n["nurse_name"],
            ) for n in nursing_notes
        ],
    }

@app.post("/api/doctor/patients/{patient_id}/diagnosis")
def create_diagnosis(patient_id: str, req: CreateDiagnosisRequest, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO Diagnoses (patient_id, doctor_id, title, description, symptoms, doctor_notes, recommended_tests, visit_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (patient_id, user_uuid, req.title, req.description, req.symptoms, req.doctor_notes, req.recommended_tests, req.visit_date))
            conn.commit()
    return {"status": "success"}

@app.post("/api/doctor/patients/{patient_id}/prescription")
def create_prescription(patient_id: str, req: CreatePrescriptionRequest, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO Prescriptions (patient_id, doctor_id, medicine_name, dosage, frequency, duration, instructions, prescribed_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (patient_id, user_uuid, req.medicine_name, req.dosage, req.frequency, req.duration, req.instructions, req.prescribed_date))
            conn.commit()
    return {"status": "success"}

@app.post("/api/doctor/patients/{patient_id}/consultation")
def create_consultation(patient_id: str, req: CreateConsultationRequest, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
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
            cur.execute("""
                SELECT lr.*, u.full_name as patient_name, u.user_id as patient_user_id
                FROM LabReports lr
                JOIN Users u ON lr.patient_id = u.id
                WHERE lr.doctor_id = %s
                   OR EXISTS (SELECT 1 FROM Diagnoses d
                               WHERE d.patient_id = lr.patient_id AND d.doctor_id = %s)
                   OR EXISTS (SELECT 1 FROM DoctorConsultations c
                               WHERE c.patient_id = lr.patient_id AND c.doctor_id = %s)
                   OR EXISTS (SELECT 1 FROM Appointments a
                               WHERE a.patient_id = lr.patient_id AND a.doctor_id = %s)
                ORDER BY lr.upload_date DESC
            """, (user_uuid, user_uuid, user_uuid, user_uuid))
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
    # Only marks as reviewed, no content changes
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE LabReports SET status = 'Reviewed' WHERE id = %s", (report_id,))
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
        raise HTTPException(status_code=409, detail="Document failed its integrity check.") from exc

    if sha256_hex(content_bytes) != row.get("document_hash"):
        raise HTTPException(status_code=409, detail="Document digest does not match the recorded hash.")

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
                SELECT m.*, u.mlkem_private_key_encrypted
                FROM MedicalDocuments m
                JOIN Users u ON m.patient_id = u.id
                WHERE m.id = %s AND m.doctor_id = %s
            """, (document_id, user_uuid))
            r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Document not found")
    return _decrypt_medical_document(r)

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
        with conn.cursor() as cur:
            cur.execute("UPDATE Appointments SET status = %s WHERE id = %s AND doctor_id = %s", (status_map[action], appointment_id, user_uuid))
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
_CONSENT_REVOKED = """
    EXISTS (SELECT 1 FROM Consent c
             WHERE c.patient_id = %s AND c.subject_user_id = %s
               AND c.status = 'Revoked')
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
    cur.execute(_REPORT_SELECT + """
        WHERE lr.id = %s
          AND (
            lr.doctor_id = %s
            OR EXISTS (SELECT 1 FROM Diagnoses d
                        WHERE d.patient_id = lr.patient_id AND d.doctor_id = %s)
            OR EXISTS (SELECT 1 FROM DoctorConsultations c
                        WHERE c.patient_id = lr.patient_id AND c.doctor_id = %s)
            OR EXISTS (SELECT 1 FROM Appointments a
                        WHERE a.patient_id = lr.patient_id AND a.doctor_id = %s)
          )
    """, (report_id, doctor_uuid, doctor_uuid, doctor_uuid, doctor_uuid))
    report = cur.fetchone()
    if not report:
        return None
    if _doctor_access_blocked(cur, doctor_uuid, str(report["patient_id"])):
        return None
    return report


@app.post("/api/doctor/emergency-access")
def declare_emergency_access(
    req: EmergencyAccessRequest,
    request: Request,
    session: dict = Depends(require_role("Doctor")),
):
    """Break-glass override of a patient's consent revocation.

    Deliberately not gated on approval: in an emergency, waiting for a second
    party defeats the purpose. The control is accountability rather than
    prevention — the declaration is time-boxed, notified to the patient
    immediately, written to the admin audit log, and anchored on-chain so it
    cannot later be quietly removed.
    """
    user_uuid = session["user_id"]
    expires_at = datetime.now(timezone.utc) + timedelta(hours=req.duration_hours)

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, user_id, full_name FROM Users WHERE id = %s AND role = 'Patient'",
                (req.patient_id,),
            )
            patient = cur.fetchone()
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")

            cur.execute("""
                INSERT INTO EmergencyAccess (requester_id, patient_id, reason, status, expires_at)
                VALUES (%s, %s, %s, 'Emergency', %s)
                RETURNING emergency_access_id
            """, (user_uuid, req.patient_id, req.reason, expires_at))
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

        anchor = anchor_document(
            conn,
            document_type="EmergencyAccess", document_id=str(access_id),
            document_hash=sha256_hex(
                f"{access_id}|{user_uuid}|{req.patient_id}|{req.reason}".encode("utf-8")
            ),
            action="EMERGENCY_ACCESS_DECLARED",
            patient_id=str(req.patient_id), actor_id=user_uuid,
            actor_public_id=session.get("public_user_id"),
        )

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE EmergencyAccess SET blockchain_tx_hash = %s WHERE emergency_access_id = %s",
                (anchor["tx_hash"], access_id),
            )
            conn.commit()

        log_admin_action(
            conn, user_uuid, session.get("public_user_id"),
            "EMERGENCY_ACCESS_DECLARED", str(req.patient_id), patient["user_id"],
            request.client.host if request and request.client else None,
            {"reason": req.reason, "expires_at": expires_at.isoformat(), "tx_hash": anchor["tx_hash"]},
        )

    return {
        "status": "success",
        "emergency_access_id": str(access_id),
        "patient_user_id": patient["user_id"],
        "expires_at": expires_at.isoformat(),
        "blockchain_tx_hash": anchor["tx_hash"],
        "anchored_on": anchor["anchored_on"],
        "message": (
            f"Emergency access granted until {expires_at.strftime('%H:%M UTC')}. "
            "The patient has been notified and this is permanently recorded."
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
            report = _doctor_may_read_report(cur, user_uuid, report_id)

        if not report:
            raise HTTPException(status_code=404, detail="Report not found or not authorised")

        pdf_bytes = _decrypt_report_pdf(report)

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
            report = _doctor_may_read_report(cur, user_uuid, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found or not authorised")
    return _verify_report(report)

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
            cur.execute("SELECT status FROM LabTestRequests WHERE id = %s", (request_id,))
            existing = cur.fetchone()
            if not existing:
                raise HTTPException(status_code=404, detail="Test request not found")
            if existing["status"] == "Completed":
                raise HTTPException(status_code=409, detail="This request is already completed.")

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
                   r.requested_date, r.doctor_id,
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
        raise HTTPException(
            status_code=409,
            detail="Report failed its integrity check and was not released.",
        ) from exc
    except Exception as exc:
        logger.error("Failed to decrypt report %s: %s", report.get("id"), exc)
        raise HTTPException(status_code=500, detail="Unable to decrypt this report.") from exc

    if sha256_hex(pdf_bytes) != report.get("document_hash"):
        raise HTTPException(
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

        pdf_bytes = _decrypt_report_pdf(report)

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
                SELECT ir.*, u.mlkem_private_key_encrypted
                FROM ImagingReports ir
                JOIN Users u ON ir.patient_id = u.id
                WHERE ir.id = %s AND ir.lab_tech_id = %s
            """, (imaging_id, user_uuid))
            r = cur.fetchone()

    if not r:
        raise HTTPException(status_code=404, detail="Imaging report not found")

    # Rows predating encryption kept their plaintext payload in image_data.
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

    try:
        shared_secret = decapsulate_aes_key(r["encrypted_aes_key"], r["mlkem_private_key_encrypted"])
        image_bytes = decrypt_document(
            ciphertext, derive_aes_key(shared_secret),
            r["encryption_nonce"], r["encryption_tag"],
        )
    except PQCUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail="Image failed its integrity check.") from exc

    if sha256_hex(image_bytes) != r.get("document_hash"):
        raise HTTPException(status_code=409, detail="Image digest does not match the recorded hash.")

    return {"image_data": image_bytes.decode("utf-8"), "encrypted": True}

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


@app.get("/api/nurse/patients")
def get_nurse_patients(session: dict = Depends(require_role("Nurse"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT u.*,
                    GREATEST(
                        COALESCE((SELECT MAX(recorded_at) FROM PatientVitals WHERE patient_id = u.id AND nurse_id = %s), 'epoch'::timestamptz),
                        COALESCE((SELECT MAX(created_at) FROM NursingNotes WHERE patient_id = u.id AND nurse_id = %s), 'epoch'::timestamptz),
                        COALESCE((SELECT MAX(administered_at) FROM MedicationAdministration WHERE patient_id = u.id AND nurse_id = %s), 'epoch'::timestamptz)
                    ) as last_recorded_at
                FROM Users u
                JOIN (
                    SELECT patient_id FROM PatientVitals WHERE nurse_id = %s
                    UNION SELECT patient_id FROM NursingNotes WHERE nurse_id = %s
                    UNION SELECT patient_id FROM MedicationAdministration WHERE nurse_id = %s
                ) as attended ON u.id = attended.patient_id
                WHERE u.role = 'Patient'
                ORDER BY last_recorded_at DESC
            """, (user_uuid, user_uuid, user_uuid, user_uuid, user_uuid, user_uuid))
            rows = cur.fetchall()

    return [NursePatientListItem(
        id=str(r["id"]), user_id=r["user_id"], full_name=r["full_name"], gender=r["gender"],
        blood_group=decrypt_data(r["blood_group_encrypted"]) if r.get("blood_group_encrypted") else None,
        last_recorded_at=r["last_recorded_at"], status=r["status"],
    ) for r in rows]


@app.get("/api/nurse/patients/search")
def search_nurse_patients(q: str, session: dict = Depends(require_role("Nurse"))):
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


@app.get("/api/nurse/patients/{patient_id}", response_model=NursePatientDetail)
def get_nurse_patient_detail(patient_id: str, session: dict = Depends(require_role("Nurse"))):
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM Users WHERE id = %s AND role = 'Patient'", (patient_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="Patient not found")

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
        ),
        vitals_history=[_vitals_record(v) for v in vitals],
        nursing_notes=[
            NursingNoteRecord(id=str(n["id"]), note_type=n["note_type"], content=n["content"], created_at=n["created_at"], nurse_name=n["nurse_name"])
            for n in notes
        ],
        active_prescriptions=[
            ActivePrescriptionForNurse(
                id=str(p["id"]), medicine_name=p["medicine_name"], dosage=p["dosage"], frequency=p["frequency"],
                duration=p["duration"], instructions=p["instructions"], prescribed_date=p["prescribed_date"],
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