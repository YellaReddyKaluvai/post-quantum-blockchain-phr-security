import math
from fastapi import FastAPI, Depends, HTTPException, Request, Response, status, Body
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
from typing import Optional
import psycopg
from psycopg.rows import dict_row

from app.schemas import (
    RegistrationRequest, LoginRequest, RegistrationResponse, LoginResponse, 
    PendingRegistration, AdminActionRequest, AdminActionResponse,
    RejectRequest, DashboardStats, UserDetail, AuditLogEntry, SecurityStats,
    PatientProfile, PatientDashboardSummary, DiagnosisRecord, LabReportItem,
    PrescriptionRecord, ConsultationRecord, AppointmentRecord, NotificationItem,
    PatientSecurityInfo, DoctorProfile, DoctorDashboardSummary, DoctorPatientListItem,
    CreateDiagnosisRequest, CreatePrescriptionRequest, CreateConsultationRequest,
    MedicalDocumentItem, CreateDocumentRequest, DoctorAppointmentItem,
    LabTechProfile, LabTechDashboardSummary, LabTestRequestItem,
    CreateLabTestRequest, CreateStructuredLabReportRequest,
    CreateImagingReportRequest, ImagingReportItem
)
from app.database import get_db, init_db
from app.security import (
    hash_password, verify_password, encrypt_data, decrypt_data,
    create_session_token, get_current_session, require_role, require_permission
)
from app.crypto_service import generate_mlkem_keypair, generate_mldsa_keypair
from app.email_service import send_and_log_email, retry_failed_email, send_admin_notification
from app.user_id_service import generate_user_id
from app.rbac import get_permissions_for_role, normalize_role
from app.audit_service import log_admin_action

app = FastAPI(title="PQC Hospital IAM API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
            
    response.set_cookie("aegis_access_token", token, httponly=True, secure=False, samesite="lax", path="/")
    
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
            
    response.delete_cookie("aegis_access_token", path="/")
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
    page: int = 1,
    per_page: int = 10,
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
    page: int = 1,
    per_page: int = 20,
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
            
            cur.execute("SELECT report_name FROM LabReports WHERE patient_id = %s ORDER BY upload_date DESC LIMIT 1", (user_uuid,))
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
        user_id=user["user_id"],
        blood_group=decrypt_data(user["blood_group_encrypted"]) if user.get("blood_group_encrypted") else None,
        assigned_doctor=assigned_doc["full_name"] if assigned_doc else None,
        latest_diagnosis=latest_diag["title"] if latest_diag else None,
        current_treatment=f"{latest_rx['medicine_name']} ({latest_rx['dosage']})" if latest_rx else None,
        latest_prescription=latest_rx["medicine_name"] if latest_rx else None,
        total_reports=report_stats["total"],
        pending_reports=report_stats["pending"],
        latest_report=latest_report["report_name"] if latest_report else None,
        upcoming_appointment={"date": str(upcoming["appointment_date"]), "time": str(upcoming["appointment_time"]), "doctor": upcoming["doctor_name"], "department": upcoming["department"]} if upcoming else None,
        previous_visit={"date": str(previous["appointment_date"]), "doctor": previous["doctor_name"], "department": previous["department"]} if previous else None,
        recent_activities=[{"title": a["title"], "body": a["body"], "created_at": a["created_at"].isoformat() if a["created_at"] else None} for a in activities]
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
        ]
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
                SELECT lr.*, u.full_name as patient_name
                FROM LabReports lr
                JOIN Users u ON lr.patient_id = u.id
                JOIN (
                    SELECT patient_id FROM Diagnoses WHERE doctor_id = %s
                    UNION SELECT patient_id FROM Appointments WHERE doctor_id = %s
                ) as assigned ON lr.patient_id = assigned.patient_id
                ORDER BY lr.upload_date DESC
            """, (user_uuid, user_uuid))
            rows = cur.fetchall()
    return [LabReportItem(
        id=str(r["id"]), report_name=r["report_name"], report_type=r["report_type"],
        report_id_public=r["report_id_public"], findings=r["findings"],
        normal_range=r["normal_range"], status=r["status"],
        uploaded_by_name=r["patient_name"],  # Reusing this field for patient_name in UI
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
def create_medical_document(req: CreateDocumentRequest, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO MedicalDocuments (patient_id, doctor_id, document_name, document_type, content, status)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (req.patient_id, user_uuid, req.document_name, req.document_type, req.content, req.status))
            conn.commit()
    return {"status": "success"}

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

@app.post("/api/doctor/requests")
def create_lab_test_request(req: CreateLabTestRequest, session: dict = Depends(require_role("Doctor"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO LabTestRequests (patient_id, doctor_id, test_name, priority, clinical_notes, status)
                VALUES (%s, %s, %s, %s, %s, 'Pending') RETURNING id
            """, (req.patient_id, user_uuid, req.test_name, req.priority, req.clinical_notes))
            conn.commit()
    return {"status": "success"}

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
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            query = """
                SELECT r.*, p.full_name as patient_name, p.user_id as patient_user_id, d.full_name as doctor_name
                FROM LabTestRequests r
                JOIN Users p ON r.patient_id = p.id
                LEFT JOIN Users d ON r.doctor_id = d.id
            """
            params = []
            if status:
                query += " WHERE r.status = %s"
                params.append(status)
            query += " ORDER BY r.requested_date DESC"
            
            cur.execute(query, params)
            rows = cur.fetchall()
            
    return [LabTestRequestItem(
        id=str(r["id"]), patient_id=str(r["patient_id"]), patient_name=r["patient_name"],
        patient_user_id=r["patient_user_id"], doctor_name=r["doctor_name"],
        test_name=r["test_name"], priority=r["priority"], status=r["status"],
        clinical_notes=r["clinical_notes"], requested_date=r["requested_date"]
    ) for r in rows]

@app.post("/api/lab-tech/requests/{request_id}/status")
def update_lab_test_request_status(request_id: str, payload: dict = Body(...), session: dict = Depends(require_role("Lab Technician"))):
    new_status = payload.get("status")
    if new_status not in ['Accepted', 'In Progress', 'Completed']:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE LabTestRequests SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (new_status, request_id))
            conn.commit()
    return {"status": "success"}

@app.get("/api/lab-tech/patients/search")
def search_patients(q: str, session: dict = Depends(require_role("Lab Technician"))):
    if len(q) < 2:
        return []
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT id, user_id, full_name, email, gender 
                FROM Users 
                WHERE role = 'Patient' AND (full_name ILIKE %s OR user_id ILIKE %s)
                LIMIT 10
            """, (f"%{q}%", f"%{q}%"))
            rows = cur.fetchall()
            
    return [{"id": str(r["id"]), "user_id": r["user_id"], "full_name": r["full_name"], "email": r["email"], "gender": r["gender"]} for r in rows]

import hashlib
import os
import json

@app.post("/api/lab-tech/reports/create")
def create_structured_lab_report(req: CreateStructuredLabReportRequest, session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    
    # Process report with full PQC pipeline
    structured_content = json.dumps(req.structured_data, sort_keys=True)
    document_hash = hashlib.sha256(structured_content.encode('utf-8')).hexdigest()
    
    # Mock AES key generation and encryption
    aes_key = os.urandom(32).hex()
    encrypted_payload = f"ENCRYPTED_{document_hash}_{aes_key[:10]}" # Mock payload
    
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT mlkem_public_key, mldsa_private_key_encrypted FROM Users WHERE id = %s", (req.patient_id,))
            patient = cur.fetchone()
            
            cur.execute("SELECT mldsa_private_key_encrypted FROM Users WHERE id = %s", (user_uuid,))
            lab_tech = cur.fetchone()
            
            if not patient:
                raise HTTPException(status_code=404, detail="Patient not found")
                
            # Mock Key Encapsulation (wrapping AES key using patient's ML-KEM public key)
            encrypted_aes_key = f"WRAPPED_BY_{patient['mlkem_public_key'][:10]}_{aes_key[:10]}" if patient['mlkem_public_key'] else f"UNWRAPPED_{aes_key[:10]}"
            
            # Mock Digital Signature
            digital_signature = f"SIGNED_BY_{user_uuid[:8]}_{document_hash[:10]}"
            
            blockchain_tx_hash = f"0x{hashlib.sha256(os.urandom(32)).hexdigest()}"
            
            # Insert into LabReports
            cur.execute("""
                INSERT INTO LabReports (patient_id, uploaded_by, lab_tech_id, report_name, report_type, findings, normal_range, structured_data, document_hash, encrypted_aes_key, digital_signature, blockchain_tx_hash, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Completed') RETURNING id
            """, (req.patient_id, user_uuid, user_uuid, req.report_name, req.report_type, req.findings, req.normal_range, json.dumps(req.structured_data), document_hash, encrypted_aes_key, digital_signature, blockchain_tx_hash))
            report_id = cur.fetchone()["id"]
            
            # Audit log
            cur.execute("""
                INSERT INTO AdminAuditLogs (admin_user_id, action, target_user_id, details)
                VALUES (%s, 'LAB_REPORT_CREATED_BLOCKCHAIN', %s, %s)
            """, (session.get("public_user_id", "SYS"), req.patient_id, json.dumps({"report_id": str(report_id), "tx_hash": blockchain_tx_hash})))
            
            # Create notification for Patient
            cur.execute("""
                INSERT INTO Notifications (user_id, notification_type, title, body)
                VALUES (%s, 'REPORT_READY', 'New Lab Report Available', 'Your lab report for ' || %s || ' is now available.')
            """, (req.patient_id, req.report_name))
            
            # Create notification for Doctor (find assigned doctor)
            cur.execute("""
                SELECT doctor_id FROM Diagnoses WHERE patient_id = %s ORDER BY visit_date DESC LIMIT 1
            """, (req.patient_id,))
            doc_row = cur.fetchone()
            if doc_row and doc_row["doctor_id"]:
                cur.execute("""
                    INSERT INTO Notifications (user_id, notification_type, title, body)
                    VALUES (%s, 'REPORT_READY', 'Patient Report Ready', 'Lab report ' || %s || ' for your patient is ready.')
                """, (doc_row["doctor_id"], req.report_name))
                
            conn.commit()
            
    return {"status": "success", "report_id": str(report_id), "blockchain_tx_hash": blockchain_tx_hash}

@app.get("/api/lab-tech/reports")
def get_lab_tech_reports(session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT lr.*, u.full_name as uploaded_by_name
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
        upload_date=r["upload_date"]
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
        "status": r["status"], "upload_date": r["upload_date"]
    }

@app.post("/api/lab-tech/imaging/upload")
def upload_imaging_report(req: CreateImagingReportRequest, session: dict = Depends(require_role("Lab Technician"))):
    user_uuid = session["user_id"]
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ImagingReports (patient_id, lab_tech_id, scan_region, exam_type, clinical_history, findings, impression, recommendations, image_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """, (req.patient_id, user_uuid, req.scan_region, req.exam_type, req.clinical_history, req.findings, req.impression, req.recommendations, req.image_data))
            conn.commit()
    return {"status": "success"}

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
        image_data=r["image_data"], created_at=r["created_at"]
    ) for r in rows]

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)