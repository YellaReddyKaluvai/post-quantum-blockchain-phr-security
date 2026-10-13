"""Federated learning between three running hospitals (spec §20–21).

    Hospital A  this process (the app under FastAPI's TestClient), its own database
    Hospital B  the hub — a separate backend server with its own database
    Hospital C  another participant — a third server with its own database

Nothing passes between them but the signed model parameters the protocol
sends. The run follows the spec's picture exactly:

    A, C: local security data (investigated incidents) → local training
          → model update (clipped, signed) ──────────────► B
    B:    federated aggregation (per-role FedAvg + robust FedAvg of the classifier)
    A, C: ◄── global security model, evaluated locally before adoption
    …a second round, each hospital training from the global weights.

A and C join through the admin API (participation stored in their databases),
not environment variables. Then the hub's defences, against the real servers:
a captured submission replayed, a submission to a round not yet open, a peer
secret rotated, and a suspended peer left out of the next round. CI starts B and C as containers
(.github/workflows/deploy.yml). Opt-in, like the end-to-end flow:

    RUN_E2E=1 FED_HUB_URL=… FED_HUB_DATABASE_URL=… FED_C_URL=… FED_C_DATABASE_URL=…
"""

import json
import os
import random
import time
import urllib.error
import urllib.request
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1" or not os.getenv("FED_HUB_URL") or not os.getenv("FED_C_URL"),
    reason="live federation needs RUN_E2E=1 and running hospitals B and C (FED_HUB_URL, FED_C_URL)")

PASSWORD = "Str0ng-Fed-pass!"


def _http(base, method, path, token=None, body=None):
    """One HTTP call to another hospital — a different server, not this process."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base.rstrip("/") + path, method=method, headers=headers,
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


def _db(url):
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(url, autocommit=True, row_factory=dict_row)


def _seed_admin(database_url, user_id):
    from app.security import encrypt_data, hash_password
    with _db(database_url) as db:
        db.execute(
            """INSERT INTO Users (user_id, full_name, email, password_hash, role, gender,
                                  date_of_birth_encrypted, status)
               VALUES (%s, 'Federation Admin', %s, %s, 'Administrator', 'Other', %s, 'Approved')""",
            (user_id, f"{user_id.lower()}@fed.example.com", hash_password(PASSWORD),
             encrypt_data("1980-01-01")))


def _behaviour(rng, threat):
    if threat:
        return {"records_accessed": rng.randint(60, 300), "distinct_patients": rng.randint(40, 150),
                "off_hours_ratio": rng.uniform(0.4, 0.9), "failed_logins": rng.randint(0, 6),
                "emergency_declarations": rng.randint(0, 2), "peak_burst": rng.randint(20, 80),
                "access_denied": rng.randint(3, 12)}
    return {"records_accessed": rng.randint(3, 25), "distinct_patients": rng.randint(1, 10),
            "off_hours_ratio": rng.uniform(0.0, 0.25), "failed_logins": rng.randint(0, 1),
            "emergency_declarations": 0, "peak_burst": rng.randint(1, 8),
            "access_denied": rng.randint(0, 1)}


def _seed_investigated_incidents(database_url, seed, threats, benign):
    """Each hospital's own investigators' verdicts — local data that never leaves it."""
    rng = random.Random(seed)
    with _db(database_url) as db:
        for label, count in ((1, threats), (0, benign)):
            for _ in range(count):
                db.execute("""INSERT INTO SecurityLabels (actor_role, features, label, source, source_ref)
                              VALUES ('Doctor', %s, %s, 'INCIDENT', %s)""",
                           (json.dumps(_behaviour(rng, bool(label))), label, str(uuid.uuid4())))


def _login(base, user_id):
    status, body = _http(base, "POST", "/api/login", body={"user_id": user_id, "password": PASSWORD})
    assert status == 200, body
    return body["access_token"]


@pytest.fixture(scope="module")
def hospitals():
    os.environ["SECURITY_ANALYSIS_INTERVAL_MINUTES"] = "0"
    for name in ("FEDERATION_HUB_URL", "FEDERATION_NODE_NAME", "FEDERATION_SHARED_SECRET"):
        os.environ.pop(name, None)                 # A joins through the admin API
    from fastapi.testclient import TestClient
    from app.main import app

    hub, c_url = os.environ["FED_HUB_URL"], os.environ["FED_C_URL"]
    tag = uuid.uuid4().hex[:6]
    with TestClient(app) as a:
        for base in (hub, c_url):
            assert _http(base, "GET", "/api/health")[0] == 200, f"{base} is not running"
        _seed_admin(os.environ["FED_HUB_DATABASE_URL"], f"ADM-B-{tag}")
        _seed_admin(os.environ["FED_C_DATABASE_URL"], f"ADM-C-{tag}")
        _seed_admin(os.environ["DATABASE_URL"], f"ADM-A-{tag}")
        _seed_investigated_incidents(os.environ["DATABASE_URL"], seed=1, threats=4, benign=10)
        _seed_investigated_incidents(os.environ["FED_C_DATABASE_URL"], seed=2, threats=5, benign=8)
        r = a.post("/api/login", json={"user_id": f"ADM-A-{tag}", "password": PASSWORD})
        assert r.status_code == 200, r.text
        yield {"a": a, "a_auth": {"Authorization": f"Bearer {r.json()['access_token']}"},
               "hub": hub, "hub_token": _login(hub, f"ADM-B-{tag}"),
               "c": c_url, "c_token": _login(c_url, f"ADM-C-{tag}"), "tag": tag}


def test_three_hospitals_train_a_shared_threat_model(hospitals, monkeypatch):
    from app import federation
    a, A, hub, B, c, C, tag = (hospitals["a"], hospitals["a_auth"], hospitals["hub"],
                               hospitals["hub_token"], hospitals["c"], hospitals["c_token"],
                               hospitals["tag"])
    node_a, node_c = f"hospital-a-{tag}", f"hospital-c-{tag}"

    # Keep a copy of what A sends, to replay it later as an eavesdropper could.
    sent, real_http = [], federation._http

    def recording(method, url, *, body=None, headers=None, timeout=30):
        if url.endswith("/api/federated/submit") and body:
            sent.append(json.loads(body))
        return real_http(method, url, body=body, headers=headers, timeout=timeout)

    monkeypatch.setattr(federation, "_http", recording)

    # Not a participant yet; then a participant the hub has never heard of.
    assert a.post("/api/admin/federated/hub/submit", headers=A).status_code == 409
    join = {"hub_url": hub, "node_name": node_a, "shared_secret": "0" * 64}
    assert a.put("/api/admin/federated/participation", headers=A, json=join).status_code == 200
    assert a.post("/api/admin/federated/hub/submit", headers=A).status_code == 502

    # B registers A and C; each joins with the secret it was issued, through its admin API.
    secrets_ = {}
    for node in (node_a, node_c):
        status, peer = _http(hub, "POST", "/api/admin/federated/peers", B,
                             {"node_name": node, "contact_url": f"https://{node}.example.org"})
        assert status == 200, peer
        secrets_[node] = peer["shared_secret"]
    r = a.put("/api/admin/federated/participation", headers=A,
              json={"hub_url": hub, "node_name": node_a, "shared_secret": secrets_[node_a]})
    assert r.status_code == 200, r.text
    status, body = _http(c, "PUT", "/api/admin/federated/participation", C,
                         {"hub_url": hub, "node_name": node_c, "shared_secret": secrets_[node_c]})
    assert status == 200, body
    participation = a.get("/api/admin/federated/participation", headers=A).json()
    assert participation["configured"] and participation["source"] == "database"
    assert "shared_secret" not in participation                      # never echoed back

    for round_no in (1, 2):
        # Local training at A and C (C over HTTP), from the global weights after round 1.
        r = a.post("/api/admin/federated/hub/submit", headers=A)
        assert r.status_code == 200, r.text
        training = r.json()["classifier"]
        assert training["trained"] and training["labels"] >= 14
        assert training["started_from"] == ("zero" if round_no == 1 else "global model")
        status, body = _http(c, "POST", "/api/admin/federated/hub/submit", C)
        assert status == 200 and body["classifier"]["trained"], body

        # Aggregation at B.
        status, result = _http(hub, "POST", "/api/admin/security/federated/round", B)
        assert status == 200, result
        assert result["real_peer_nodes"] == 2 and result["peer_nodes_simulated"] == 0
        assert set(result["classifier"]["classifier_nodes"]) >= {node_a, node_c}
        assert result["classifier"]["rounds"] == round_no
        assert result["evaluation"] is not None              # B judged it on its own data
        assert sent[-1]["round_number"] == result["round"]   # filed against the open round

        # Distribution: A and C pull; A evaluates it on its own incidents and adopts it.
        r = a.post("/api/admin/federated/hub/pull", headers=A)
        assert r.status_code == 200, r.text
        pulled = r.json()
        assert pulled["real_nodes"] == 3 and pulled["has_classifier"]
        assert pulled["adopted"], pulled["evaluation"]
        assert pulled["evaluation"]["classifier"]["global"]["accuracy"] >= 0.8
        status, body = _http(c, "POST", "/api/admin/federated/hub/pull", C)
        assert status == 200 and body["adopted"], body

    # A's detection now uses the federated classifier built by both participants.
    clf = a.get("/api/admin/federated/classifier", headers=A).json()
    assert clf["in_use"]["label"].startswith("federated classifier")
    assert clf["in_use"]["nodes"] >= 2 and clf["in_use"]["rounds"] == 2
    models = a.get("/api/admin/federated/models", headers=A).json()
    assert len(models) >= 2 and models[0]["active"] and not models[1]["active"]

    # Rollback: local models only, then back to the older global model.
    assert a.post("/api/admin/federated/models/deactivate", headers=A).status_code == 200
    assert a.get("/api/admin/federated/classifier", headers=A).json()["in_use"]["label"] \
        .startswith("local classifier")
    assert a.post(f"/api/admin/federated/models/{models[1]['id']}/activate", headers=A).status_code == 200
    assert a.get("/api/admin/federated/models", headers=A).json()[1]["active"]

    # What crossed the boundary: parameters only. B holds no labels, and nothing
    # A stored from the hub names a person or a node.
    with _db(os.environ["FED_HUB_DATABASE_URL"]) as db:
        assert db.execute("SELECT COUNT(*) AS n FROM SecurityLabels").fetchone()["n"] == 0
        submitted = db.execute("SELECT local_parameters FROM FederatedRounds WHERE node_name = %s "
                               "ORDER BY round_number DESC LIMIT 1", (node_a,)).fetchone()
    assert set(submitted["local_parameters"]) == {"version", "roles", "classifier"}
    with _db(os.environ["DATABASE_URL"]) as db:
        stored = db.execute("SELECT parameters FROM FederatedHubModels ORDER BY pulled_at DESC "
                            "LIMIT 1").fetchone()["parameters"]
    text = json.dumps(stored)
    assert "medians" in text and node_a not in text and node_c not in text and "@" not in text

    _hub_defences(hospitals, sent, secrets_, node_a, node_c)


def _hub_defences(hospitals, sent, secrets_, node_a, node_c):
    """The hub's refusals, exercised against the running hub B."""
    from app import ai_security as aisec
    a, A, hub, B, c, C = (hospitals["a"], hospitals["a_auth"], hospitals["hub"],
                          hospitals["hub_token"], hospitals["c"], hospitals["c_token"])

    # A captured submission, replayed verbatim: refused, and recorded as an event.
    status, body = _http(hub, "POST", "/api/federated/submit", body=sent[-1])
    assert status == 409, body

    # Correctly signed with A's secret, but for a round that has not opened.
    forged = dict(sent[-1], round_number=999, timestamp=int(time.time()) + 2)
    forged["signature"] = aisec.parameters_signature(
        node_a, 999, forged["sample_count"], forged["parameters"], secrets_[node_a],
        forged["timestamp"])
    status, body = _http(hub, "POST", "/api/federated/submit", body=forged)
    assert status == 400 and "not open" in body["detail"], body

    status, listed = _http(hub, "GET", "/api/admin/federated/peers", B)
    peer_id = {p["node_name"]: p["id"] for p in listed["peers"]}

    # Rotating C's secret cuts the old one off at once; the new one works.
    status, rotated = _http(hub, "POST", f"/api/admin/federated/peers/{peer_id[node_c]}/rotate-secret", B)
    assert status == 200 and rotated["shared_secret"] != secrets_[node_c]
    status, body = _http(c, "POST", "/api/admin/federated/hub/pull", C)
    assert status == 502 and "401" in body["detail"], body
    status, _ = _http(c, "PUT", "/api/admin/federated/participation", C,
                      {"hub_url": hub, "node_name": node_c, "shared_secret": rotated["shared_secret"]})
    assert status == 200
    status, body = _http(c, "POST", "/api/admin/federated/hub/pull", C)
    assert status == 200, body

    # A suspended peer can neither submit nor shape the next round with what it sent before.
    status, _ = _http(hub, "POST", f"/api/admin/federated/peers/{peer_id[node_a]}/deactivate", B)
    assert status == 200
    assert a.post("/api/admin/federated/hub/submit", headers=A).status_code == 502
    status, result = _http(hub, "POST", "/api/admin/security/federated/round", B)
    assert status == 200, result
    assert result["real_peer_nodes"] == 1
    assert node_a not in result["classifier"]["classifier_nodes"]
    status, _ = _http(hub, "POST", f"/api/admin/federated/peers/{peer_id[node_a]}/activate", B)
    assert status == 200

    status, fed = _http(hub, "GET", "/api/admin/security/federated/status", B)
    assert status == 200 and isinstance(fed["latest_round_adopted"], bool), fed
