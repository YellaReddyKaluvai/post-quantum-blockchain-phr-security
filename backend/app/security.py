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

from app.config import get_settings
from app.rbac import get_permissions_for_role

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

def get_encryption_key() -> bytes:
    settings = get_settings()
    key = settings.ENCRYPTION_KEY.encode('utf-8')
    # ensure it's 32 bytes for AES-256
    if len(key) < 32:
        key = key.ljust(32, b'0')
    elif len(key) > 32:
        key = key[:32]
    return key

def encrypt_data(data: str) -> str:
    if not data:
        return data
    key = get_encryption_key()
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

def create_session_token(payload: dict[str, Any], minutes: int | None = None) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes or settings.access_token_minutes)
    token_payload = {
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

def get_current_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    token = _extract_token(request, credentials)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    payload = verify_session_token(token)
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
        if permission not in session.get("permissions", []):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden: insufficient permission.")
        return session

    return _dependency
