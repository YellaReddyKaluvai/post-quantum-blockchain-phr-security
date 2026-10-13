"""Browser sessions: a cookie page scripts cannot read, a CSRF guard on it, and
revocation that takes effect at once (logout, a disabled account).

Runs without a database: ``security.session_state`` is the seam replaced here.
The same behaviour against a real database is in test_e2e_flow.py.
"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app import security


class _Request:
    def __init__(self, method="GET", cookie=None, headers=None):
        self.method = method
        self.cookies = {security.SESSION_COOKIE_NAME: cookie} if cookie else {}
        self.headers = headers or {}


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(security, "session_state", lambda user_id, jti: (False, "Approved"))
    tok, _ = security.create_session_token({"user_id": "u-1", "role": "Doctor"})
    return tok


def test_every_session_token_is_named_so_it_can_be_revoked(token):
    jti = security.verify_session_token(token)["jti"]
    other, _ = security.create_session_token({"user_id": "u-1", "role": "Doctor"})
    assert len(jti) == 32 and jti != security.verify_session_token(other)["jti"]


def test_a_cookie_session_reads_without_the_header(token):
    assert security.get_current_session(_Request("GET", cookie=token), None)["user_id"] == "u-1"


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_a_cookie_session_cannot_change_anything_without_the_header(token, method):
    with pytest.raises(HTTPException) as exc:
        security.get_current_session(_Request(method, cookie=token), None)
    assert exc.value.status_code == 403
    ok = security.get_current_session(
        _Request(method, cookie=token, headers={"X-Requested-With": "QuantumCare"}), None)
    assert ok["user_id"] == "u-1"


def test_a_bearer_token_needs_no_csrf_header(token):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert security.get_current_session(_Request("POST"), creds)["user_id"] == "u-1"


@pytest.mark.parametrize("state", [(True, "Approved"), (False, "Disabled"), (True, None)])
def test_a_revoked_session_or_disabled_user_is_refused_at_once(token, monkeypatch, state):
    monkeypatch.setattr(security, "session_state", lambda user_id, jti: state)
    with pytest.raises(HTTPException) as exc:
        security.get_current_session(_Request("GET", cookie=token), None)
    assert exc.value.status_code == 401


def test_the_login_cookie_is_httponly_and_cors_is_not_a_wildcard():
    import inspect
    from app import main
    login_src = inspect.getsource(main.login)
    assert "httponly=True" in login_src and "max_age=" in login_src
    assert "UPDATE Sessions SET is_active = FALSE WHERE jti" in inspect.getsource(main.logout)
    cors = next(m for m in main.app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert "*" not in cors.kwargs["allow_origins"] and cors.kwargs["allow_credentials"]
