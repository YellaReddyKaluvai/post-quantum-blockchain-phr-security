"""The hub side of federated learning (spec §20–21): what it accepts, and what
it hands out.

A participant's half is tested in test_security_architecture.py; the three-
hospital run against real servers is test_federation_live.py. Here the hub's
endpoints run against a scripted cursor, so each refusal can be shown on its
own: a replayed or stale submission, a submission to a round that has not
opened, per-role counts that do not add up, an unsigned request for the model.
"""

import contextlib
import time

import pytest
from fastapi import HTTPException

from app import ai_security as aisec
from app import federation
from app import main
from app.schemas import PeerSubmissionRequest

SECRET = "s3cret"
NODE = "hospital-b"


def _flat(median=4.0, scale=2.0, samples=10):
    return {"medians": {k: median for k in aisec.FEATURE_WEIGHTS},
            "scales": {k: scale for k in aisec.FEATURE_WEIGHTS},
            "sample_count": samples}


class _Cursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.executed = []
        self.connection = self          # record_security_event opens a savepoint here

    def transaction(self):
        return contextlib.nullcontext()

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        return (self.rows.pop(0) if self.rows else None) or []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def statements(self, fragment):
        return [(sql, p) for sql, p in self.executed if fragment in sql]


class _Conn:
    def __init__(self, cur):
        self.cur, self.commits = cur, 0

    def cursor(self, **_):
        return self.cur

    def commit(self):
        self.commits += 1


@pytest.fixture
def hub(monkeypatch):
    """Point the hub's endpoints at a scripted cursor; secrets are stored as-is."""
    state = {}

    def install(rows):
        cur = _Cursor(rows)
        state["cur"], state["conn"] = cur, _Conn(cur)
        return cur

    @contextlib.contextmanager
    def fake_db():
        yield state["conn"]

    monkeypatch.setattr(main, "get_db", fake_db)
    monkeypatch.setattr(main, "decrypt_data", lambda v: v)
    return install


def _peer(last_ts=None, active=True):
    return {"id": "p-1", "shared_secret_encrypted": SECRET, "is_active": active,
            "last_submission_ts": last_ts}


def _submission(round_number=3, ts=None, parameters=None, samples=10, secret=SECRET):
    params = parameters or {"version": 2, "roles": {"Doctor": _flat(samples=samples)}}
    ts = int(time.time()) if ts is None else ts
    sig = aisec.parameters_signature(NODE, round_number, samples, params, secret, ts)
    return PeerSubmissionRequest(node_name=NODE, round_number=round_number, sample_count=samples,
                                 parameters=params, timestamp=ts, signature=sig)


def _refused(fn, *args):
    with pytest.raises(HTTPException) as exc:
        fn(*args)
    return exc.value.status_code, exc.value.detail


# ═══ /api/federated/submit ═══════════════════════════════════════════════════

def test_a_fresh_signed_submission_is_filed_and_its_timestamp_kept(hub):
    req = _submission(round_number=3)
    cur = hub([_peer(last_ts=req.timestamp - 600), {"n": 3}])
    assert main.receive_peer_parameters(req)["accepted"]
    assert cur.statements("INSERT INTO FederatedRounds")
    (_, params), = cur.statements("UPDATE FederatedPeers")
    assert params == (req.timestamp, "p-1")          # the newest accepted timestamp


def test_the_same_submission_replayed_is_refused(hub):
    req = _submission()
    cur = hub([_peer(last_ts=req.timestamp)])          # the hub already took this one
    status, _ = _refused(main.receive_peer_parameters, req)
    assert status == 409
    assert not cur.statements("INSERT INTO FederatedRounds")
    (_, event), = cur.statements("INSERT INTO SecurityEvents")
    assert "FEDERATED_SUBMISSION_REPLAYED" in event


def test_a_stale_submission_is_refused_even_if_never_seen(hub):
    hub([_peer()])
    status, _ = _refused(main.receive_peer_parameters,
                         _submission(ts=int(time.time()) - 3600))
    assert status == 409


def test_a_resigned_timestamp_does_not_verify(hub):
    req = _submission()
    forged = req.model_copy(update={"timestamp": req.timestamp + 5})
    hub([_peer()])
    assert _refused(main.receive_peer_parameters, forged)[0] == 401


def test_a_submission_to_a_round_not_yet_open_is_refused(hub):
    cur = hub([_peer(), {"n": 3}])
    status, detail = _refused(main.receive_peer_parameters, _submission(round_number=999))
    assert status == 400 and "open round is 3" in detail
    assert not cur.statements("INSERT INTO FederatedRounds")


def test_per_role_counts_that_exceed_the_total_are_refused(hub):
    params = {"version": 2, "roles": {"Doctor": _flat(samples=8), "Nurse": _flat(samples=8)}}
    hub([_peer()])
    status, _ = _refused(main.receive_peer_parameters, _submission(parameters=params, samples=10))
    assert status == 400


def test_a_suspended_peer_is_refused(hub):
    hub([_peer(active=False)])
    assert _refused(main.receive_peer_parameters, _submission())[0] == 403


# ═══ /api/federated/global-model ═════════════════════════════════════════════

class _Request:
    def __init__(self, headers):
        self.headers = headers
        self.client = None


def _model_row():
    return {"round_number": 4, "parameters": {"version": 2, "roles": {"Doctor": _flat()}},
            "contributing_nodes": 3, "total_samples": 60, "real_nodes": 3}


def test_the_model_is_signed_for_the_peer_and_request_that_asked(hub):
    ts = int(time.time())
    headers = {"X-Federation-Node": NODE, "X-Federation-Timestamp": str(ts),
               "X-Federation-Signature": federation.request_signature(NODE, ts, "global-model", SECRET)}
    hub([_peer(), _model_row(), {"n": 5}])
    body = main.serve_global_model(_Request(headers))
    assert body["open_round"] == 5
    assert federation.verify_model_signature(NODE, ts, body, SECRET)
    assert not federation.verify_model_signature(NODE, ts + 1, body, SECRET)     # another request
    assert not federation.verify_model_signature("hospital-c", ts, body, SECRET)  # another peer


def test_an_unsigned_request_for_the_model_is_refused(hub):
    headers = {"X-Federation-Node": NODE, "X-Federation-Timestamp": str(int(time.time())),
               "X-Federation-Signature": "0" * 64}
    hub([_peer()])
    assert _refused(main.serve_global_model, _Request(headers))[0] == 401


# ═══ Peer administration ═════════════════════════════════════════════════════

def test_the_hubs_own_node_name_cannot_be_registered(hub):
    from app.schemas import RegisterPeerRequest
    hub([])
    req = RegisterPeerRequest(node_name=main.LOCAL_NODE)
    status, _ = _refused(main.register_federated_peer, req, {"user_id": "u1"})
    assert status == 400


def test_rotating_a_secret_issues_a_new_one_and_stores_it_encrypted(hub, monkeypatch):
    monkeypatch.setattr(main, "encrypt_data", lambda v: "enc:" + v)
    monkeypatch.setattr(main, "log_admin_action", lambda *a, **k: None)
    cur = hub([{"node_name": NODE}])
    out = main.rotate_federated_peer_secret("00000000-0000-0000-0000-000000000001",
                                            {"user_id": "u1", "public_user_id": "ADM-1"})
    assert len(out["shared_secret"]) == 64 and out["node_name"] == NODE
    (sql, params), = cur.statements("UPDATE FederatedPeers SET shared_secret_encrypted")
    assert params[0] == "enc:" + out["shared_secret"]   # never stored in the clear


# ═══ The round ═══════════════════════════════════════════════════════════════

def test_a_round_takes_only_active_peers_and_keeps_their_original_dates():
    import inspect
    src = inspect.getsource(main._federated_round)
    assert "JOIN FederatedPeers p ON p.node_name = r.node_name AND p.is_active" in src
    assert "r.created_at > CURRENT_TIMESTAMP - make_interval(days => %s)" in src
    # A carried-forward update is re-filed with its own created_at, so it ages out.
    assert "local_parameters, created_at)" in src and 'peer["created_at"]' in src
    # And the hub evaluates the result on its own data before detection uses it.
    assert "federation.evaluate_global_model(cur, global_params)" in src


def test_detection_at_the_hub_uses_only_a_round_that_passed_evaluation():
    from app import risk_engine
    import inspect
    assert "real_nodes >= 2 AND adopted" in inspect.getsource(risk_engine.usable_federated_model)


def test_a_plain_http_hub_elsewhere_is_flagged():
    assert federation.transport_warning("http://hub.example.org")
    assert federation.transport_warning("https://hub.example.org") is None
    assert federation.transport_warning("http://localhost:8001") is None
