"""Federated learning between two running hospitals (spec §20–21).

Hospital A is this process (the app under FastAPI's TestClient, on its own
database). Hospital B — the hub — is a separate backend server with a separate
database, reached over real HTTP. Nothing is shared between them but the
signed parameters the protocol sends:

    B's admin registers A as a peer          → shared secret, shown once
    A fits its per-role model and submits it → HMAC-signed, verified by B
    B's admin runs a federated round         → FedAvg over B's model and A's
    A pulls the global model                 → signed request; stored and used

CI starts the hub as a second container (see .github/workflows/deploy.yml).
Opt-in, like the end-to-end flow:

    RUN_E2E=1 FED_HUB_URL=http://127.0.0.1:8001 FED_HUB_DATABASE_URL=postgresql://…
"""

import json
import os
import urllib.request
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1" or not os.getenv("FED_HUB_URL"),
    reason="live federation needs RUN_E2E=1, FED_HUB_URL and FED_HUB_DATABASE_URL")

PASSWORD = "Str0ng-Fed-pass!"


def _hub(method, path, token=None, body=None):
    """One HTTP call to hospital B — a different server, not this process."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        os.environ["FED_HUB_URL"].rstrip("/") + path, method=method, headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def _seed_admin(database_url, user_id):
    """An approved administrator, written straight into one hospital's database."""
    import psycopg
    from app.security import encrypt_data, hash_password
    with psycopg.connect(database_url, autocommit=True) as db:
        db.execute(
            """INSERT INTO Users (user_id, full_name, email, password_hash, role, gender,
                                  date_of_birth_encrypted, status)
               VALUES (%s, 'Federation Admin', %s, %s, 'Administrator', 'Other', %s, 'Approved')""",
            (user_id, f"{user_id.lower()}@fed.example.com", hash_password(PASSWORD),
             encrypt_data("1980-01-01")))


@pytest.fixture(scope="module")
def hospitals():
    os.environ["SECURITY_ANALYSIS_INTERVAL_MINUTES"] = "0"
    from fastapi.testclient import TestClient
    from app.main import app

    tag = uuid.uuid4().hex[:6]
    with TestClient(app) as a:                      # startup creates A's schema
        status, _ = _hub("GET", "/api/health")
        assert status == 200, "hospital B (the hub) is not running"

        hub_admin = f"ADM-HUB-{tag}"
        _seed_admin(os.environ["FED_HUB_DATABASE_URL"], hub_admin)
        status, body = _hub("POST", "/api/login", body={"user_id": hub_admin, "password": PASSWORD})
        assert status == 200, body
        hub_token = body["access_token"]           # the login is also B's own activity

        a_admin = f"ADM-A-{tag}"
        _seed_admin(os.environ["DATABASE_URL"], a_admin)
        r = a.post("/api/login", json={"user_id": a_admin, "password": PASSWORD})
        assert r.status_code == 200, r.text
        a_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        yield {"a": a, "a_headers": a_headers, "hub_token": hub_token,
               "node": f"hospital-a-{tag}"}


def test_two_hospitals_federate_and_share_only_parameters(hospitals, monkeypatch):
    a, a_headers, hub_token, node = (hospitals["a"], hospitals["a_headers"],
                                     hospitals["hub_token"], hospitals["node"])

    # Before registration the hub refuses A outright.
    monkeypatch.setenv("FEDERATION_HUB_URL", os.environ["FED_HUB_URL"])
    monkeypatch.setenv("FEDERATION_NODE_NAME", node)
    monkeypatch.setenv("FEDERATION_SHARED_SECRET", "0" * 64)
    assert a.post("/api/admin/federated/hub/submit", headers=a_headers).status_code == 502

    # B's administrator registers A; the secret is handed over once.
    status, peer = _hub("POST", "/api/admin/federated/peers", hub_token,
                        {"node_name": node, "contact_url": "https://hospital-a.example.org"})
    assert status == 200, peer
    secret = peer["shared_secret"]

    # A wrong secret is refused by B's signature check…
    r = a.post("/api/admin/federated/hub/submit", headers=a_headers)
    assert r.status_code == 502 and "401" in r.text

    # …the right one is accepted.
    monkeypatch.setenv("FEDERATION_SHARED_SECRET", secret)
    r = a.post("/api/admin/federated/hub/submit", headers=a_headers)
    assert r.status_code == 200, r.text
    submitted = r.json()
    assert submitted["accepted"] is True and submitted["roles"]

    # Nothing to pull until B has aggregated a round with a real peer in it.
    assert a.post("/api/admin/federated/hub/pull", headers=a_headers).status_code == 502

    # B runs FedAvg over its own model and A's submission.
    status, round_ = _hub("POST", "/api/admin/security/federated/round", hub_token)
    assert status == 200, round_
    status, fed = _hub("GET", "/api/admin/security/federated/status", hub_token)
    assert status == 200 and fed["real_nodes"] >= 2 and fed["simulated_nodes"] == 0, fed

    # A pulls the global model both hospitals built, and stores it for scoring.
    r = a.post("/api/admin/federated/hub/pull", headers=a_headers)
    assert r.status_code == 200, r.text
    pulled = r.json()
    assert pulled["real_nodes"] >= 2 and pulled["contributing_nodes"] >= 2

    import psycopg
    from psycopg.rows import dict_row
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as db:
        row = db.execute("SELECT hub_url, real_nodes, parameters FROM FederatedHubModels "
                         "ORDER BY pulled_at DESC LIMIT 1").fetchone()
    assert row["hub_url"] == os.environ["FED_HUB_URL"].rstrip("/") and row["real_nodes"] >= 2
    # Parameters only: per-role medians and scales, no identifiers or events.
    text = json.dumps(row["parameters"])
    assert "medians" in text and node not in text and "@" not in text
