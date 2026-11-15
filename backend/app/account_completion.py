"""Rotating browser sessions, verified email and dual-control MFA recovery."""

import secrets
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID
from urllib.parse import quote, urlparse
from email.message import EmailMessage
import smtplib

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from psycopg.rows import dict_row
from app import account_security as account
from app.config import get_settings
from app.database import get_db
from app.security import (
    get_current_session,
    require_role,
    create_session_token,
    SESSION_COOKIE_NAME,
    hash_password,
)

router = APIRouter(prefix="/api/auth", tags=["Account completion"])
REFRESH_COOKIE = "quantumcare_refresh"


def send_link(address, token, path, subject):
    cfg = get_settings()
    origin = cfg.PUBLIC_APP_URL.rstrip("/")
    parsed = urlparse(origin)
    if (
        not cfg.SMTP_HOST
        or not cfg.SMTP_USER
        or not cfg.SMTP_PASSWORD
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or (
            parsed.scheme != "https"
            and parsed.hostname not in ("localhost", "127.0.0.1")
        )
    ):
        raise RuntimeError("Secure mail delivery is not configured")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg.SMTP_USER, address, subject
    msg.set_content(
        f"{subject}\n\nOpen this single-use link:\n{origin}/{path}#token={quote(token)}\n\nIf you did not request this, contact your administrator."
    )
    with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT, timeout=15) as server:
        if cfg.SMTP_STARTTLS:
            server.starttls()
        server.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD)
        server.send_message(msg)


def cookie(response, name, value, seconds):
    cfg = get_settings()
    same = (
        cfg.SESSION_COOKIE_SAMESITE
        if cfg.SESSION_COOKIE_SAMESITE in ("lax", "strict", "none")
        else "lax"
    )
    response.set_cookie(
        name,
        value,
        httponly=True,
        secure=cfg.SESSION_COOKIE_SECURE or same == "none",
        samesite=same,
        path="/",
        max_age=max(0, int(seconds)),
    )


def issue_refresh(cur, user_id, jti, response, expires=None):
    expires = expires or datetime.now(timezone.utc) + timedelta(
        days=get_settings().refresh_token_days
    )
    raw = secrets.token_urlsafe(32)
    cur.execute(
        "INSERT INTO RefreshTokens (token_hash,user_id,session_jti,expires_at) VALUES (%s,%s,%s,%s)",
        (account.token_digest(raw), user_id, jti, expires),
    )
    cookie(
        response,
        REFRESH_COOKIE,
        raw,
        (expires - datetime.now(timezone.utc)).total_seconds(),
    )


@router.post("/refresh")
def refresh(request: Request, response: Response):
    if request.headers.get("X-Requested-With") != "QuantumCare":
        raise HTTPException(403, "Cross-site refresh refused.")
    account.ip_throttle(request, "refresh")
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(401, "Sign in again.")
    digest = account.token_digest(raw)
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT user_id FROM RefreshTokens WHERE token_hash=%s", (digest,))
        candidate = cur.fetchone()
        if not candidate:
            raise HTTPException(401, "Sign in again.")
        # Every credential change and refresh locks the user first.
        cur.execute(
            "SELECT * FROM Users WHERE id=%s FOR UPDATE", (candidate["user_id"],)
        )
        user = cur.fetchone()
        cur.execute(
            "SELECT * FROM RefreshTokens WHERE token_hash=%s FOR UPDATE", (digest,)
        )
        row = cur.fetchone()
        if row["consumed_at"]:
            cur.execute(
                "UPDATE Sessions SET is_active=FALSE WHERE jti=%s",
                (row["session_jti"],),
            )
            account.audit(cur, user["id"], "REFRESH_REPLAY_BLOCKED")
            conn.commit()
            raise HTTPException(
                401, "Session revoked after refresh-token reuse. Sign in again."
            )
        cur.execute(
            "SELECT is_active FROM Sessions WHERE jti=%s AND user_id=%s",
            (row["session_jti"], user["id"]),
        )
        session = cur.fetchone()
        if (
            user["status"] != "Approved"
            or row["expires_at"] <= datetime.now(timezone.utc)
            or not session
            or not session["is_active"]
        ):
            raise HTTPException(401, "Sign in again.")
        payload = {
            k: str(user["id"]) if k == "user_id" else user[k]
            for k in ("user_id", "role", "email", "full_name")
        }
        payload.update(public_user_id=user["user_id"], jti=row["session_jti"])
        token, expires = create_session_token(payload)
        cur.execute(
            "UPDATE RefreshTokens SET consumed_at=NOW() WHERE token_hash=%s", (digest,)
        )
        cur.execute(
            "UPDATE Sessions SET token_hash=%s,expires_at=%s WHERE jti=%s",
            (account.token_digest(token), expires, row["session_jti"]),
        )
        issue_refresh(cur, user["id"], row["session_jti"], response, row["expires_at"])
        conn.commit()
    cookie(
        response, SESSION_COOKIE_NAME, token, get_settings().access_token_minutes * 60
    )
    response.headers["Cache-Control"] = "no-store"
    return {"message": "Session refreshed."}


def request_email_verification(email):
    raw = secrets.token_urlsafe(32)
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id,email FROM Users WHERE lower(email)=lower(%s) AND email_verified_at IS NULL AND status::text IN ('Pending','Approved') FOR UPDATE",
            (email,),
        )
        user = cur.fetchone()
        if not user:
            return
        cur.execute(
            "DELETE FROM EmailVerificationTokens WHERE user_id=%s", (user["id"],)
        )
        cur.execute(
            "INSERT INTO EmailVerificationTokens VALUES (%s,%s,NOW()+INTERVAL '1 hour')",
            (account.token_digest(raw), user["id"]),
        )
        conn.commit()
    try:
        send_link(
            user["email"],
            raw,
            "verify-email",
            "Verify your QuantumCare email (expires in one hour)",
        )
    except Exception:
        logging.getLogger(__name__).warning("Verification email delivery failed")
        with get_db() as conn:
            conn.execute(
                "DELETE FROM EmailVerificationTokens WHERE token_hash=%s",
                (account.token_digest(raw),),
            )
            conn.commit()


@router.post("/email/request")
def email_request(body: account.RecoveryRequest, request: Request):
    account.ip_throttle(request, "verify-email")
    account.throttle("verify-email", str(body.email), 3)
    request_email_verification(str(body.email))
    return {"message": "If the account needs verification, a link will be sent."}


class TokenBody(BaseModel):
    token: str = Field(min_length=32, max_length=128)


@router.post("/email/verify")
def email_verify(body: TokenBody, request: Request):
    account.ip_throttle(request, "verify-token")
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT user_id FROM EmailVerificationTokens WHERE token_hash=%s AND expires_at>NOW()",
            (account.token_digest(body.token),),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(400, "Verification link invalid or expired.")
        cur.execute("SELECT id FROM Users WHERE id=%s FOR UPDATE", (row["user_id"],))
        cur.execute(
            "DELETE FROM EmailVerificationTokens WHERE token_hash=%s AND expires_at>NOW() RETURNING user_id",
            (account.token_digest(body.token),),
        )
        if not cur.fetchone():
            raise HTTPException(400, "Verification link invalid or expired.")
        cur.execute(
            "UPDATE Users SET email_verified_at=NOW() WHERE id=%s", (row["user_id"],)
        )
        account.audit(cur, row["user_id"], "EMAIL_VERIFIED")
        conn.commit()
    return {
        "message": "Email verified. Administrator approval is still required before sign-in."
    }


@router.post("/mfa/recovery-codes")
def regenerate_codes(body: account.Credentials, session=Depends(get_current_session)):
    account.throttle("account-security", session["user_id"])
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        user = account.authenticated_user(cur, session, body)
        if not user["mfa_secret_encrypted"]:
            raise HTTPException(409, "Enable MFA first.")
        codes = [secrets.token_hex(10) for _ in range(10)]
        cur.execute("DELETE FROM MfaRecoveryCodes WHERE user_id=%s", (user["id"],))
        for code in codes:
            cur.execute(
                "INSERT INTO MfaRecoveryCodes VALUES (%s,%s)",
                (user["id"], account.token_digest(code)),
            )
        account.audit(cur, user["id"], "MFA_CODES_REGENERATED")
        conn.commit()
    return {
        "recovery_codes": codes,
        "message": "Previous recovery codes have been invalidated. Save these new codes.",
    }


class RecoveryCase(account.Credentials):
    user_id: UUID
    evidence_reference: str = Field(min_length=10, max_length=300)


def verified_admin(cur, session, body):
    admin = account.authenticated_user(cur, session, body)
    if not admin["mfa_secret_encrypted"]:
        raise HTTPException(
            403, "Administrators must enroll MFA before approving identity recovery."
        )
    return admin


@router.post("/admin/mfa-recovery")
def create_case(body: RecoveryCase, session=Depends(require_role("Administrator"))):
    account.throttle("account-security", session["user_id"])
    if str(body.user_id) == session["user_id"]:
        raise HTTPException(403, "You cannot recover your own account.")
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        verified_admin(cur, session, body)
        cur.execute(
            "SELECT id FROM Users WHERE id=%s AND status='Approved' AND mfa_secret_encrypted IS NOT NULL",
            (body.user_id,),
        )
        if not cur.fetchone():
            raise HTTPException(404, "Eligible MFA account not found.")
        cur.execute(
            "INSERT INTO MfaRecoveryRequests (user_id,requested_by,evidence_reference) VALUES (%s,%s,%s) RETURNING id",
            (body.user_id, session["user_id"], body.evidence_reference),
        )
        result = cur.fetchone()
        account.audit(cur, body.user_id, "MFA_RECOVERY_REQUESTED")
        conn.commit()
    return {
        "id": str(result["id"]),
        "message": "A different MFA-enabled administrator must independently verify identity and approve within 24 hours.",
    }


@router.get("/admin/mfa-recovery")
def list_cases(session=Depends(require_role("Administrator"))):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id,user_id,requested_by,approved_by,evidence_reference,created_at,expires_at,consumed_at FROM MfaRecoveryRequests ORDER BY created_at DESC LIMIT 100"
        )
        return cur.fetchall()


@router.post("/admin/mfa-recovery/{case_id}/approve")
def approve_case(
    case_id: UUID,
    body: account.Credentials,
    session=Depends(require_role("Administrator")),
):
    account.throttle("account-security", session["user_id"])
    raw = secrets.token_urlsafe(32)
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        verified_admin(cur, session, body)
        cur.execute(
            "SELECT * FROM MfaRecoveryRequests WHERE id=%s FOR UPDATE", (case_id,)
        )
        row = cur.fetchone()
        if (
            not row
            or row["approved_by"]
            or row["expires_at"] <= datetime.now(timezone.utc)
        ):
            raise HTTPException(409, "Case unavailable or already approved.")
        if session["user_id"] in (str(row["requested_by"]), str(row["user_id"])):
            raise HTTPException(
                403,
                "Approval requires a different administrator, not the account owner.",
            )
        cur.execute(
            "SELECT email FROM Users WHERE id=%s AND status='Approved'",
            (row["user_id"],),
        )
        user = cur.fetchone()
        if not user:
            raise HTTPException(409, "Account unavailable.")
        # Mail failure rolls back approval: administrator can retry; no raw token returned.
        try:
            send_link(
                user["email"],
                raw,
                "recover-mfa",
                "Complete approved MFA recovery (expires in 15 minutes)",
            )
        except Exception as exc:
            raise HTTPException(
                503, "Recovery email could not be delivered; approval was not saved."
            ) from exc
        cur.execute(
            "UPDATE MfaRecoveryRequests SET approved_by=%s,token_hash=%s,token_expires_at=NOW()+INTERVAL '15 minutes' WHERE id=%s",
            (session["user_id"], account.token_digest(raw), case_id),
        )
        account.audit(cur, row["user_id"], "MFA_RECOVERY_APPROVED")
        conn.commit()
    return {
        "message": "Recovery link sent to the registered address. No factors have been removed yet."
    }


class FinishRecovery(TokenBody):
    new_password: str = Field(min_length=12, max_length=1024)


@router.post("/mfa/recover")
def finish_recovery(body: FinishRecovery, request: Request):
    account.ip_throttle(request, "mfa-recover")
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT user_id FROM MfaRecoveryRequests WHERE token_hash=%s",
            (account.token_digest(body.token),),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(400, "Recovery link invalid or expired.")
        cur.execute(
            "SELECT id FROM Users WHERE id=%s AND status='Approved' FOR UPDATE",
            (row["user_id"],),
        )
        if not cur.fetchone():
            raise HTTPException(400, "Account unavailable.")
        cur.execute(
            "UPDATE MfaRecoveryRequests SET consumed_at=NOW() WHERE token_hash=%s AND consumed_at IS NULL AND approved_by IS NOT NULL AND token_expires_at>NOW() RETURNING user_id",
            (account.token_digest(body.token),),
        )
        if not cur.fetchone():
            raise HTTPException(400, "Recovery link invalid or expired.")
        cur.execute(
            "UPDATE Users SET password_hash=%s,mfa_secret_encrypted=NULL,mfa_pending_encrypted=NULL,mfa_pending_until=NULL,mfa_last_counter=NULL WHERE id=%s",
            (hash_password(body.new_password), row["user_id"]),
        )
        cur.execute("DELETE FROM MfaRecoveryCodes WHERE user_id=%s", (row["user_id"],))
        cur.execute(
            "DELETE FROM PasswordResetTokens WHERE user_id=%s", (row["user_id"],)
        )
        cur.execute(
            "UPDATE Sessions SET is_active=FALSE WHERE user_id=%s", (row["user_id"],)
        )
        cur.execute(
            "UPDATE MfaRecoveryRequests SET consumed_at=NOW() WHERE user_id=%s AND consumed_at IS NULL",
            (row["user_id"],),
        )
        account.audit(cur, row["user_id"], "MFA_RECOVERY_COMPLETED")
        cur.execute(
            "INSERT INTO Notifications (user_id,notification_type,title,body) VALUES (%s,'SECURITY','MFA recovery completed','All sessions were revoked. Sign in and enroll a new authenticator immediately.')",
            (row["user_id"],),
        )
        conn.commit()
    return {
        "message": "Password reset and lost factors removed. Sign in and enroll a new authenticator immediately."
    }
