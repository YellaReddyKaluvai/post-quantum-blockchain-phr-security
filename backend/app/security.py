from datetime import datetime, timedelta, timezone
from typing import Any
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import base64
import os
import secrets

from app.config import get_settings
from app.rbac import get_permissions_for_role, has_permission

bearer_scheme = HTTPBearer(auto_error=False)
ph = PasswordHasher()

# Name of the HTTP-only cookie carrying the QuantumCare session token.
SESSION_COOKIE_NAME = "quantumcare_token"

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, password)
    except VerifyMismatchError:
        return False

def get_encryption_key(key_text: str | None = None) -> bytes:
    """The AES-256 key: ``key_text`` if given (key rotation), else ENCRYPTION_KEY."""
    key = (key_text if key_text is not None else get_settings().ENCRYPTION_KEY).encode('utf-8')
    # ensure it's 32 bytes for AES-256
    if len(key) < 32:
        key = key.ljust(32, b'0')
    elif len(key) > 32:
        key = key[:32]
    return key

def encrypt_data(data: str, key_text: str | None = None) -> str:
    if not data:
        return data
    key = get_encryption_key(key_text)
    cipher = AES.new(key, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(data.encode('utf-8'), AES.block_size))
    iv = base64.b64encode(cipher.iv).decode('utf-8')
    ct = base64.b64encode(ct_bytes).decode('utf-8')
    return f"{iv}:{ct}"

def decrypt_data(data: str) -> str:
    if not data or ':' not in data:
        return data
    try:
        key = get_encryption_key()
        iv, ct = data.split(':', 1)
        iv = base64.b64decode(iv)
        ct = base64.b64decode(ct)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        pt_bytes = unpad(cipher.decrypt(ct), AES.block_size)
        return pt_bytes.decode('utf-8')
    except Exception:
        return data

def looks_encrypted(data: str | None) -> bool:
    """True when ``data`` has the shape encrypt_data produces: base64(16-byte IV):base64(blocks)."""
    if not data or data.count(':') != 1:
        return False
    iv, ct = data.split(':', 1)
    try:
        iv_bytes = base64.b64decode(iv, validate=True)
        ct_bytes = base64.b64decode(ct, validate=True)
    except Exception:
        return False
    return len(iv_bytes) == 16 and len(ct_bytes) > 0 and len(ct_bytes) % 16 == 0


def decrypt_data_strict(data: str, key_text: str) -> str:
    """Decrypt with exactly this key, raising ValueError on any failure.

    ``decrypt_data`` returns its input when it cannot decrypt, which keeps old
    plaintext rows readable but cannot tell "not encrypted" from "encrypted
    under another key". Key rotation must tell them apart, so it uses this.
    """
    if not looks_encrypted(data):
        raise ValueError("not an encrypt_data value")
    iv, ct = data.split(':', 1)
    cipher = AES.new(get_encryption_key(key_text), AES.MODE_CBC, base64.b64decode(iv))
    try:
        return unpad(cipher.decrypt(base64.b64decode(ct)), AES.block_size).decode('utf-8')
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("does not decrypt under this key") from exc


def create_session_token(payload: dict[str, Any], minutes: int | None = None) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes or settings.access_token_minutes)
    token_payload = {
        "jti": secrets.token_hex(16),        # names this session, so it can be revoked
        **payload,
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
        "iss": "pqc-hospital-backend",
    }
    token = jwt.encode(token_payload, settings.SECRET_KEY, algorithm=settings.jwt_algorithm)
    return token, expires_at

def verify_session_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.jwt_algorithm])
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token.") from exc

def _extract_token(request: Request, credentials: HTTPAuthorizationCredentials | None) -> str | None:
    if credentials is not None:
        return credentials.credentials
    return request.cookies.get(SESSION_COOKIE_NAME)


# A browser attaches the session cookie to any request to this API, including
# one a hostile page triggers (a form post, an <img>). A state-changing request
# authenticated by the cookie alone must therefore carry this header, which a
# page on another origin cannot add without a CORS preflight that CORS_ORIGINS
# refuses. A Bearer token is never sent automatically, so it needs no such guard.
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "QuantumCare"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def session_state(user_id: str, jti: str | None) -> tuple[bool, str | None]:
    """Is this session still good? (revoked, user status) from the database.

    The seam tests replace. A token for a session that was logged out, or for
    a user since disabled, must stop working at once rather than at expiry.
    """
    from app.database import get_db
    with get_db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT u.status::text,
                      EXISTS (SELECT 1 FROM Sessions s
                               WHERE s.jti = %s AND NOT s.is_active) AS revoked
                 FROM Users u WHERE u.id = %s""", (jti, user_id))
        row = cur.fetchone()
    if not row:
        return True, None
    return bool(row[1]), row[0]


def get_current_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    token = _extract_token(request, credentials)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    if credentials is None and request.method not in SAFE_METHODS \
            and request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Cross-site request refused (missing X-Requested-With header).")
    payload = verify_session_token(token)
    revoked, user_status = session_state(payload.get("user_id"), payload.get("jti"))
    if revoked or user_status != "Approved":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="This session has ended. Please sign in again.")
    permissions = payload.get("permissions") or []
    if not permissions:
        permissions = list(get_permissions_for_role(payload["role"]))
    payload["permissions"] = permissions
    return payload

def require_role(*allowed_roles: str):
    normalized_roles = {role.strip().title() for role in allowed_roles}

    def _dependency(session: dict[str, Any] = Depends(get_current_session)) -> dict[str, Any]:
        if session.get("role", "").strip().title() not in normalized_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: role not allowed.")
        return session

    return _dependency

def require_permission(permission: str):
    def _dependency(session: dict[str, Any] = Depends(get_current_session)) -> dict[str, Any]:
        # Checked against the role fresh via rbac, not the token's own
        # "permissions" claim: a session token must never be the thing that
        # decides what it is allowed to do, only who it belongs to.
        if not has_permission(session.get("role", ""), permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: insufficient permission.")
        return session

    return _dependency
