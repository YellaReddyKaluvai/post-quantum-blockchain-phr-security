"""Blockchain upkeep: carrying consent to a new contract, anchoring late what was
only anchored locally, and trusting only our own contracts' events.

Runs without a chain: contracts, receipts and cursors are fakes. The real
contract is exercised in CI's on-chain end-to-end run.
"""

import contextlib

import pytest

from app import anchor_service
from app.chain_client import ChainClient
from app.consent_ledger import party_ref


# ═══ migrate_contract.plan: the old contract decides, not the database ═══════

class _OldContract:
    def __init__(self, granted_pairs):
        self.granted = granted_pairs
        outer = self

        class _Fns:
            def checkConsent(self, patient_ref, doctor_ref):
                class _Call:
                    def call(_self):
                        return (patient_ref, doctor_ref) in outer.granted
                return _Call()

        self.functions = _Fns()


def test_consent_is_carried_from_the_old_contract_and_disagreements_listed():
    from migrate_contract import plan
    rows = [
        {"consent_id": "c1", "patient_id": "p1", "subject_user_id": "d1", "status": "Authorized"},
        {"consent_id": "c2", "patient_id": "p2", "subject_user_id": "d2", "status": "Revoked"},
        # Edited in SQL to Authorized after the patient withdrew on-chain:
        {"consent_id": "c3", "patient_id": "p3", "subject_user_id": "d3", "status": "Authorized"},
    ]
    old = _OldContract({(party_ref("p1"), party_ref("d1"))})
    carry, disagree = plan(old, rows)
    assert [(c["consent_id"], g) for c, g in carry] == [("c1", True), ("c2", False), ("c3", False)]
    assert [d["consent_id"] for d in disagree] == ["c3"]          # the chain's answer is carried
    assert disagree[0]["old_contract_says"] == "withdrawn"


# ═══ Late anchoring ═════════════════════════════════════════════════════════

class _Cursor:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.db.executed.append((sql, params))
        self.last = sql

    def fetchall(self):
        return [dict(r) for r in self.db.local]

    def fetchone(self):
        return {"n": len(self.db.local) - self.db.anchored}


class _Conn:
    def __init__(self, local):
        self.local, self.executed, self.anchored, self.commits = local, [], 0, 0

    def cursor(self, **_):
        return _Cursor(self)

    def commit(self):
        self.commits += 1


def _anchor(i, doc_type="LabReport"):
    return {"id": f"a{i}", "document_type": doc_type, "document_id": f"d{i}", "report_id_public": None,
            "patient_id": None, "actor_public_id": "LAB-1", "action": "REPORT_UPLOADED",
            "document_hash": f"{i:064x}", "tx_hash": f"0xsim{i}"}


def test_local_anchors_are_written_late_and_say_so(monkeypatch):
    monkeypatch.setattr("app.chain_client.get_chain_client", lambda: object())
    sent = []

    def submit(payload):
        sent.append(payload)
        return {"tx_hash": f"0xreal{len(sent)}", "block_number": 100 + len(sent), "network": "anvil-local"}

    monkeypatch.setattr(anchor_service, "_submit_to_chain", submit)
    conn = _Conn([_anchor(1), _anchor(2, "ConsentDecision")])
    result = anchor_service.reanchor_local(conn)
    assert result["anchored"] == 2 and result["chain_available"]
    assert all(p["action"] == "LATE_ANCHOR:REPORT_UPLOADED" for p in sent)   # the chain says "late"
    updates = [p for q, p in conn.executed if q.startswith("UPDATE DocumentAnchors")]
    assert updates[0][:3] == ("0xreal1", "anvil-local", 101)
    # The lab report now points at the real transaction, only if it pointed at the simulated one.
    (q, p), = [(q, p) for q, p in conn.executed if q.startswith("UPDATE LabReports")]
    assert "blockchain_tx_hash = %s" in q and p == ("0xreal1", "d1", "0xsim1")


def test_without_a_chain_nothing_is_pretended(monkeypatch):
    monkeypatch.setattr("app.chain_client.get_chain_client", lambda: None)
    result = anchor_service.reanchor_local(_Conn([_anchor(1)]))
    assert result == {"chain_available": False, "anchored": 0, "note": result["note"]}


def test_a_chain_that_fails_midway_leaves_the_rest_local(monkeypatch):
    monkeypatch.setattr("app.chain_client.get_chain_client", lambda: object())
    replies = iter([{"tx_hash": "0xreal", "block_number": 7, "network": "anvil-local"}, None])
    monkeypatch.setattr(anchor_service, "_submit_to_chain", lambda payload: next(replies))
    result = anchor_service.reanchor_local(_Conn([_anchor(1), _anchor(2), _anchor(3)]))
    assert result["anchored"] == 1


# ═══ Only our contracts' events count ══════════════════════════════════════

def test_audit_events_from_another_contract_are_ignored():
    client = object.__new__(ChainClient)
    client.trusted_addresses = {"0xours", "0xourold"}
    seen = {}

    class _Event:
        def process_receipt(self, receipt):
            seen["logs"] = receipt["logs"]
            return [{"args": {"resourceHash": log["data"]}} for log in receipt["logs"]]

    class _Events:
        def AuditLogged(self):
            return _Event()

    client.contract = type("C", (), {"events": _Events()})()
    receipt = {"status": 1, "logs": [{"address": "0xOURS", "data": "h1"},
                                     {"address": "0xlookalike", "data": "h1"},
                                     {"address": "0xOurOld", "data": "h2"}]}
    events = client.audit_events(receipt)
    assert [e["args"]["resourceHash"] for e in events] == ["h1", "h2"]
    assert all(log["address"].lower() in client.trusted_addresses for log in seen["logs"])


@pytest.fixture(autouse=True)
def _no_chain_singleton():
    with contextlib.suppress(Exception):
        from app.chain_client import reset_chain_client
        reset_chain_client()
    yield
