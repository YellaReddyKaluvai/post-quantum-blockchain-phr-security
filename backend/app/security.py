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

class ColumnIntegrityError(ValueError):
    """An encrypted column could not be authenticated/decrypted."""


def encrypt_data(data: str, key_text: str | None = None) -> str:
    if not data:
        return data
    cipher = AES.new(get_encryption_key(key_text), AES.MODE_GCM, nonce=secrets.token_bytes(12))
    cipher.update(b"QuantumCare:column:v2")
    ciphertext, tag = cipher.encrypt_and_digest(data.encode("utf-8"))
    return "gcm2:" + ":".join(base64.b64encode(x).decode("ascii") for x in (cipher.nonce, ciphertext, tag))


def looks_encrypted(data: str | None) -> bool:
    if not data:
        return False
    if data.startswith("gcm2:"):
        return True  # malformed versioned ciphertext must fail, never become plaintext
    if data.count(":") != 1:
        return False
    try:
        iv, ct = (base64.b64decode(x, validate=True) for x in data.split(":"))
        return len(iv) == 16 and bool(ct) and len(ct) % 16 == 0
    except Exception:
        return False


def decrypt_data_strict(data: str, key_text: str | None = None) -> str:
    """Read authenticated v2 or legacy CBC; new writes always use v2.

    CBC compatibility is only for migration. It cannot authenticate old rows.
    """
    if not looks_encrypted(data):
        raise ColumnIntegrityError("Not a recognized encrypted column")
    try:
        key = get_encryption_key(key_text)
        if data.startswith("gcm2:"):
            _, nonce, ct, tag = data.split(":")
            cipher = AES.new(key, AES.MODE_GCM, nonce=base64.b64decode(nonce, validate=True))
            cipher.update(b"QuantumCare:column:v2")
            return cipher.decrypt_and_verify(base64.b64decode(ct, validate=True),
                                             base64.b64decode(tag, validate=True)).decode("utf-8")
        iv, ct = (base64.b64decode(x, validate=True) for x in data.split(":"))
        return unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), AES.block_size).decode("utf-8")
    except Exception as exc:
        raise ColumnIntegrityError("Encrypted column failed integrity/decryption checks") from exc


def decrypt_data(data: str) -> str:
    # Old clinical rows may be plaintext; recognized ciphertext never falls back.
    if not data:
        return data
    if os.getenv("REQUIRE_AUTHENTICATED_COLUMNS", "false").lower() == "true" and not data.startswith("gcm2:"):
        raise ColumnIntegrityError("Legacy/plaintext column refused; complete the GCM migration")
    if not looks_encrypted(data):
        return data
    return decrypt_data_strict(data)


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
