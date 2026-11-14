"""Account recovery, RFC 6238 MFA and shared, atomic authentication throttles."""
import base64
import hashlib
import hmac
import secrets
import smtplib
import struct
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, EmailStr
from psycopg.rows import dict_row

from app.config import get_settings
from app.database import get_db
from app.security import encrypt_data, decrypt_data, hash_password, verify_password, get_current_session

router = APIRouter(prefix="/api/auth", tags=["Account security"])


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def throttle(scope: str, identity: str, limit: int = 10, seconds: int = 900) -> None:
    """Count attempts before expensive work. The upsert serializes concurrent workers.

    Fixed windows start with the first attempt, not at wall-clock boundaries.
    Raw email addresses/IPs are not stored in this table.
    """
    key = token_digest(scope + ":" + identity.strip().lower())
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""INSERT INTO AuthRateLimits (bucket, attempts, expires_at)
            VALUES (%s, 1, NOW() + make_interval(secs => %s))
            ON CONFLICT (bucket) DO UPDATE SET
              attempts = CASE WHEN AuthRateLimits.expires_at <= NOW() THEN 1 ELSE AuthRateLimits.attempts + 1 END,
              expires_at = CASE WHEN AuthRateLimits.expires_at <= NOW()
                THEN NOW() + make_interval(secs => %s) ELSE AuthRateLimits.expires_at END
            RETURNING attempts, GREATEST(1, EXTRACT(EPOCH FROM expires_at - NOW())::int) AS retry""",
                    (key, seconds, seconds))
        row = cur.fetchone()
        cur.execute("DELETE FROM AuthRateLimits WHERE expires_at < NOW() - INTERVAL '1 day'")
        conn.commit()
    if row["attempts"] > limit:
        raise HTTPException(429, "Too many attempts. Please try again later.", headers={"Retry-After": str(row["retry"])})


def ip_throttle(request: Request, scope: str) -> None:
    # Do not trust a caller-supplied X-Forwarded-For header. Configure trusted
    # proxy addresses in uvicorn when deployed behind a reverse proxy.
    throttle(scope + ":ip", request.client.host if request.client else "unknown", 100)


def totp(secret: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff
    return str(value % (10 ** digits)).zfill(digits)


def match_totp(secret: str, code: str, last_counter: int = -1, now: float | None = None) -> int | None:
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    counter = int(time.time() if now is None else now) // 30
    for step in (counter, counter - 1, counter + 1):
        if step > last_counter and step >= 0 and hmac.compare_digest(totp(secret, step), code):
            return step
    return None


def verify_mfa(cur, user: dict, code: str | None) -> bool:
    """Caller must hold Users row FOR UPDATE; consume OTP/recovery atomically."""
    if not user.get("mfa_secret_encrypted"):
        return True
    code = (code or "").strip()
    counter = match_totp(decrypt_data(user["mfa_secret_encrypted"]), code,
                         user.get("mfa_last_counter") if user.get("mfa_last_counter") is not None else -1)
    if counter is not None:
        cur.execute("UPDATE Users SET mfa_last_counter = %s WHERE id = %s", (counter, user["id"]))
        return True
    digest = token_digest(code)
    cur.execute("DELETE FROM MfaRecoveryCodes WHERE user_id = %s AND code_hash = %s RETURNING code_hash",
                (user["id"], digest))
    return cur.fetchone() is not None


class Credentials(BaseModel):
    password: str = Field(min_length=1, max_length=1024)
    otp: str | None = Field(default=None, max_length=100)


class PasswordChange(Credentials):
    new_password: str = Field(min_length=12, max_length=1024)


class RecoveryRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str = Field(min_length=32, max_length=128)
    new_password: str = Field(min_length=12, max_length=1024)
    otp: str | None = Field(default=None, max_length=100)


class MfaConfirmation(BaseModel):
    code: str = Field(min_length=6, max_length=6)


def authenticated_user(cur, session, credentials):
    cur.execute("SELECT * FROM Users WHERE id = %s FOR UPDATE", (session["user_id"],))
    user = cur.fetchone()
    if not user or not verify_password(credentials.password, user["password_hash"]) or not verify_mfa(cur, user, credentials.otp):
        raise HTTPException(403, "Password or authentication code incorrect.")
    return user


def audit(cur, user_id, action):
    cur.execute("INSERT INTO AuthLogs (user_id, action) VALUES (%s, %s)", (user_id, action))


@router.get("/security")
def status(session=Depends(get_current_session)):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT mfa_secret_encrypted IS NOT NULL AS enabled FROM Users WHERE id = %s", (session["user_id"],))
        row = cur.fetchone()
        cur.execute("SELECT COUNT(*) AS n FROM MfaRecoveryCodes WHERE user_id = %s", (session["user_id"],))
        return {"mfa_enabled": row["enabled"], "recovery_codes_remaining": cur.fetchone()["n"]}


@router.post("/password/change")
def change_password(body: PasswordChange, session=Depends(get_current_session)):
    throttle("account-security", session["user_id"])
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        user = authenticated_user(cur, session, body)
        cur.execute("UPDATE Users SET password_hash = %s WHERE id = %s", (hash_password(body.new_password), user["id"]))
        cur.execute("UPDATE Sessions SET is_active = FALSE WHERE user_id = %s", (user["id"],))
        cur.execute("DELETE FROM PasswordResetTokens WHERE user_id = %s", (user["id"],))
        audit(cur, user["id"], "PASSWORD_CHANGED")
        conn.commit()
    return {"message": "Password changed. Sign in again on all devices."}


def send_reset_email(address: str, token: str):
    settings = get_settings()
    origin = settings.PUBLIC_APP_URL.rstrip("/")
    parsed = urlparse(origin)
    if not settings.SMTP_HOST or not settings.SMTP_USER or not settings.SMTP_PASSWORD or not parsed.netloc:
        raise RuntimeError("Recovery email is not configured")
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise RuntimeError("Recovery URL must use HTTPS")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.SMTP_USER, address, "Reset your QuantumCare password"
    # Fragment is not sent to the web server or in referrer URLs.
    msg.set_content("Use this single-use link within 15 minutes:\n" + origin + "/reset-password#token=" + quote(token)
                    + "\n\nIf you did not request this, ignore this email. MFA remains enabled.")
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if settings.SMTP_STARTTLS:
            server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


@router.post("/password/forgot")
def forgot_password(body: RecoveryRequest, request: Request):
    ip_throttle(request, "recovery")
    throttle("recovery", str(body.email), 3)
    token = secrets.token_urlsafe(32)
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, email FROM Users WHERE lower(email) = lower(%s) AND status = 'Approved' FOR UPDATE", (str(body.email),))
        user = cur.fetchone()
        if user:
            cur.execute("DELETE FROM PasswordResetTokens WHERE user_id = %s", (user["id"],))
            cur.execute("INSERT INTO PasswordResetTokens (token_hash, user_id, expires_at) VALUES (%s, %s, NOW() + INTERVAL '15 minutes')",
                        (token_digest(token), user["id"]))
            conn.commit()
    if user:
        try:
            send_reset_email(user["email"], token)
        except Exception:
            # Never log the link, raw token or email body; never claim delivery.
            import logging
            logging.getLogger(__name__).warning("Password reset delivery failed")
            with get_db() as conn:
                conn.execute("DELETE FROM PasswordResetTokens WHERE token_hash = %s", (token_digest(token),))
                conn.commit()
    return {"message": "If an eligible account exists, a reset link will be sent. If it does not arrive, contact your administrator."}


@router.post("/password/reset")
def reset_password(body: PasswordReset, request: Request):
    ip_throttle(request, "reset")
    throttle("reset", token_digest(body.token), 10)
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        # Lock user first consistently with change/forgot to avoid lock inversions.
        cur.execute("SELECT user_id FROM PasswordResetTokens WHERE token_hash = %s AND expires_at > NOW()", (token_digest(body.token),))
        candidate = cur.fetchone()
        if not candidate:
            raise HTTPException(400, "Reset link is invalid or expired.")
        cur.execute("SELECT * FROM Users WHERE id = %s AND status = 'Approved' FOR UPDATE", (candidate["user_id"],))
        user = cur.fetchone()
        cur.execute("DELETE FROM PasswordResetTokens WHERE token_hash = %s AND expires_at > NOW() RETURNING user_id", (token_digest(body.token),))
        if not cur.fetchone() or not user:
            raise HTTPException(400, "Reset link is invalid or expired.")
        if not verify_mfa(cur, user, body.otp):
            raise HTTPException(403, "Enter an authenticator or recovery code.")
        cur.execute("UPDATE Users SET password_hash = %s WHERE id = %s", (hash_password(body.new_password), user["id"]))
        cur.execute("UPDATE Sessions SET is_active = FALSE WHERE user_id = %s", (user["id"],))
        cur.execute("DELETE FROM PasswordResetTokens WHERE user_id = %s", (user["id"],))
        audit(cur, user["id"], "PASSWORD_RESET")
        conn.commit()
    return {"message": "Password reset. Sign in with your new password."}


@router.post("/mfa/setup")
def setup_mfa(body: Credentials, session=Depends(get_current_session)):
    throttle("account-security", session["user_id"])
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii")
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        user = authenticated_user(cur, session, body)
        if user.get("mfa_secret_encrypted"):
            raise HTTPException(409, "MFA is already enabled.")
        cur.execute("UPDATE Users SET mfa_pending_encrypted = %s, mfa_pending_until = NOW() + INTERVAL '10 minutes' WHERE id = %s",
                    (encrypt_data(secret), user["id"]))
        conn.commit()
    uri = ("otpauth://totp/" + quote("QuantumCare:" + session.get("public_user_id", session["user_id"]))
            + "?secret=" + secret + "&issuer=QuantumCare&algorithm=SHA1&digits=6&period=30")
    import io
    import qrcode
    output = io.BytesIO()
    qrcode.make(uri).save(output, format="PNG")
    return {"secret": secret, "uri": uri, "qr_data_url": "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()}


@router.post("/mfa/confirm")
def confirm_mfa(body: MfaConfirmation, session=Depends(get_current_session)):
    throttle("account-security", session["user_id"])
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM Users WHERE id = %s FOR UPDATE", (session["user_id"],))
        user = cur.fetchone()
        if user["mfa_secret_encrypted"] or not user["mfa_pending_encrypted"] or user["mfa_pending_until"] < datetime.now(timezone.utc):
            raise HTTPException(409, "Start a new MFA setup.")
        counter = match_totp(decrypt_data(user["mfa_pending_encrypted"]), body.code)
        if counter is None:
            raise HTTPException(400, "Authentication code incorrect.")
        cur.execute("""UPDATE Users SET mfa_secret_encrypted = mfa_pending_encrypted,
            mfa_pending_encrypted = NULL, mfa_pending_until = NULL, mfa_last_counter = %s WHERE id = %s""", (counter, user["id"]))
        codes = [secrets.token_hex(10) for _ in range(10)]
        cur.execute("DELETE FROM MfaRecoveryCodes WHERE user_id = %s", (user["id"],))
        for code in codes:
            cur.execute("INSERT INTO MfaRecoveryCodes (user_id, code_hash) VALUES (%s, %s)", (user["id"], token_digest(code)))
        cur.execute("UPDATE Sessions SET is_active = FALSE WHERE user_id = %s AND jti <> %s", (user["id"], session["jti"]))
        audit(cur, user["id"], "MFA_ENABLED")
        conn.commit()
    return {"recovery_codes": codes, "message": "Save these codes securely. Each can be used once."}


@router.post("/mfa/disable")
def disable_mfa(body: Credentials, session=Depends(get_current_session)):
    throttle("account-security", session["user_id"])
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        user = authenticated_user(cur, session, body)
        cur.execute("UPDATE Users SET mfa_secret_encrypted = NULL, mfa_pending_encrypted = NULL, mfa_pending_until = NULL, mfa_last_counter = NULL WHERE id = %s", (user["id"],))
        cur.execute("DELETE FROM MfaRecoveryCodes WHERE user_id = %s", (user["id"],))
        cur.execute("UPDATE Sessions SET is_active = FALSE WHERE user_id = %s AND jti <> %s", (user["id"], session["jti"]))
        audit(cur, user["id"], "MFA_DISABLED")
        conn.commit()
    return {"message": "MFA disabled."}
