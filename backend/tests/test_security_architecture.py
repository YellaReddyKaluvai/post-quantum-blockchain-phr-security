"""The connected security architecture: risk gate, alert & response, consent
ledger, federation participant, and the authorization fixes in the access path.

Everything here runs without a database, chain or hub: SQL goes through a fake
cursor that records what was executed and answers from a script, and HTTP goes
through each module's single ``_http`` seam. The end-to-end flow against a real
database and real liboqs is test_e2e_flow.py, which CI runs inside the image.
"""

import contextlib
import inspect
import json
import time
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app import ai_security as aisec
from app import consent_ledger, federation, risk_engine
from app import security_response as secresp


class FakeConnection:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1

    def transaction(self):
        return contextlib.nullcontext()


class FakeCursor:
    """Records SQL; answers fetchone() from a queue of scripted rows."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.executed: list[tuple[str, tuple]] = []
        self.connection = FakeConnection()

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def statements(self, fragment):
        return [sql for sql, _ in self.executed if fragment in sql]


def _window(**features):
    base = {k: 0.0 for k in aisec.FEATURE_WEIGHTS}
    base.update(features)
    return aisec.ActorWindow(actor_id="a1", actor_public_id="DOC-1", actor_role="Doctor",
                             features=base)


def _typical_baseline():
    group = [_window(records_accessed=3, distinct_patients=2, off_hours_ratio=0.05,
                     peak_burst=4) for _ in range(12)]
    return aisec.fit_baseline(group)


def _flat(median=4.0, scale=2.0, samples=10):
    return {"medians": {k: median for k in aisec.FEATURE_WEIGHTS},
            "scales": {k: scale for k in aisec.FEATURE_WEIGHTS},
            "sample_count": samples}


# ═══ Risk policy (§23) ═══════════════════════════════════════════════════════

@pytest.fixture
def clean_policy_env(monkeypatch):
    for name in ("RISK_POLICY_MEDIUM", "RISK_POLICY_HIGH", "RISK_POLICY_EMERGENCY_HIGH",
                 "RISK_MIN_PEERS", "STEP_UP_MINUTES"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_default_policy_never_blocks(clean_policy_env):
    """Out of the box no score refuses care; HIGH asks for re-verification."""
    assert risk_engine.decide("LOW") == "allow"
    assert risk_engine.decide("MEDIUM") == "monitor"
    assert risk_engine.decide("HIGH") == "verify"
    assert "block" not in {risk_engine.decide(l) for l in ("LOW", "MEDIUM", "HIGH")}


def test_emergencies_are_not_held_up_by_default(clean_policy_env):
    assert risk_engine.decide("HIGH", emergency=True) == "monitor"
    assert risk_engine.decide("MEDIUM", emergency=True) == "monitor"


def test_policy_is_configurable(clean_policy_env):
    clean_policy_env.setenv("RISK_POLICY_HIGH", "block")
    clean_policy_env.setenv("RISK_POLICY_MEDIUM", "verify")
    clean_policy_env.setenv("RISK_POLICY_EMERGENCY_HIGH", "block")
    assert risk_engine.decide("HIGH") == "block"
    assert risk_engine.decide("MEDIUM") == "verify"
    assert risk_engine.decide("HIGH", emergency=True) == "block"
    assert risk_engine.decide("MEDIUM", emergency=True) == "monitor"


def test_an_invalid_policy_value_falls_back_to_the_safe_default(clean_policy_env):
    clean_policy_env.setenv("RISK_POLICY_HIGH", "obliterate")
    assert risk_engine.decide("HIGH") == "verify"


# ─── Which baseline judges a role ────────────────────────────────────────────

def test_a_real_federated_model_is_preferred():
    local = {"Doctor": aisec.Baseline.from_parameters(_flat(median=1.0, samples=5))}
    federated = {"version": 2, "roles": {"Doctor": _flat(median=9.0, samples=50)}}
    baseline, source, samples = risk_engine.select_baseline("Doctor", local, federated, 3)
    assert source == risk_engine.SOURCE_FEDERATED and samples == 50
    assert baseline.medians["records_accessed"] == 9.0


def test_local_is_used_when_the_federation_does_not_describe_the_role():
    local = {"Nurse": aisec.Baseline.from_parameters(_flat(samples=5))}
    federated = {"version": 2, "roles": {"Doctor": _flat(samples=50)}}
    _, source, _ = risk_engine.select_baseline("Nurse", local, federated, 3)
    assert source == risk_engine.SOURCE_LOCAL


def test_too_few_peers_means_no_judgement():
    """Scoring two technicians against each other just flags the busier one."""
    local = {"Lab Technician": aisec.Baseline.from_parameters(_flat(samples=2))}
    baseline, _, samples = risk_engine.select_baseline("Lab Technician", local, None, 3)
    assert baseline is None and samples == 2


def test_insufficient_baseline_allows_and_says_why(monkeypatch, clean_policy_env):
    monkeypatch.setattr(aisec, "extract_windows", lambda *a, **k: [])
    monkeypatch.setattr(risk_engine._cache, "get", lambda *a, **k: (None, "LOCAL_ANOMALY", 1))
    d = risk_engine.evaluate(FakeCursor(), "a1", "Doctor")
    assert d.action == "allow" and d.note == "insufficient-baseline"


def test_an_insider_sweep_is_challenged_with_an_explanation(monkeypatch, clean_policy_env):
    insider = _window(records_accessed=140, distinct_patients=140, off_hours_ratio=0.9,
                      failed_logins=11, peak_burst=140, access_denied=9)
    monkeypatch.setattr(aisec, "extract_windows", lambda *a, **k: [insider])
    monkeypatch.setattr(risk_engine._cache, "get",
                        lambda *a, **k: (_typical_baseline(), "LOCAL_ANOMALY", 12))
    d = risk_engine.evaluate(FakeCursor(), "a1", "Doctor")
    assert d.level == "HIGH" and d.action == "verify"
    assert "distinct patients accessed" in d.narrative       # XAI: the why, not just the verdict
    assert d.contributions and d.contributions[0]["deviations"] > 1.5


def test_refused_access_attempts_are_a_scored_feature():
    assert "access_denied" in aisec.FEATURE_WEIGHTS
    assert "ACCESS_DENIED" in aisec.FEATURE_SQL


# ═══ Alert & response, incidents (§24, §25) ══════════════════════════════════

def test_incident_refs_continue_from_the_highest_this_year():
    cur = FakeCursor([{"n": 41}])
    assert secresp.next_incident_ref(cur) == f"INC-{datetime.now(timezone.utc).year}-00042"


def test_one_refusal_is_recorded_but_does_not_alert():
    cur = FakeCursor([{"n": 1}])
    assert secresp.access_denied(cur, actor_id="d1", actor_public_id="DOC-1", actor_role="Doctor",
                                 resource="patient_chart", reason="no consent") is None
    assert cur.statements("INSERT INTO SecurityEvents")
    assert not cur.statements("INSERT INTO SecurityAlerts")


def test_repeated_refusals_raise_an_alert():
    cur = FakeCursor([{"n": secresp.DENIAL_ALERT_THRESHOLD}, None, {"id": "alert-1"}])
    alert = secresp.access_denied(cur, actor_id="d1", actor_public_id="DOC-1", actor_role="Doctor",
                                  resource="patient_chart", reason="no consent")
    assert alert == "alert-1"
    sql, params = next((q, p) for q, p in cur.executed if "INSERT INTO SecurityAlerts" in q)
    assert params[2] == "MEDIUM" and params[-1] == secresp.SOURCE_ACCESS_CONTROL


def test_an_open_alert_is_reused_not_duplicated():
    cur = FakeCursor([{"id": "existing"}])
    alert_id, created = secresp.raise_alert_once(
        cur, severity="HIGH", title="HIGH risk at access — DOC-1", summary="x", response="VERIFY",
        source=secresp.SOURCE_RISK_GATE, actor_id="d1", dedupe_minutes=60)
    assert (alert_id, created) == ("existing", False)
    assert not cur.statements("INSERT INTO SecurityAlerts")


def test_an_integrity_failure_always_opens_an_incident():
    cur = FakeCursor([None, {"id": "a1"}, {"n": 0}])
    ref = secresp.integrity_failure(cur, resource="LabReport LR-1", detail="digest mismatch",
                                    actor_id="p1", actor_role="Patient")
    assert ref.startswith("INC-")
    incident = next(p for q, p in cur.executed if "INSERT INTO SecurityIncidents" in q)
    assert incident[3] == "INTEGRITY_FAILURE" and incident[5] == "HIGH"
    # The reader who discovered the tampering is not blamed for it.
    alert = next(p for q, p in cur.executed if "INSERT INTO SecurityAlerts" in q)
    assert alert[1] is None


def test_retrying_a_tampered_record_does_not_open_a_new_incident():
    cur = FakeCursor([{"incident_ref": "INC-2026-00007"}])
    ref = secresp.signature_failure(cur, resource="LabReport LR-1", detail="bad signature")
    assert ref == "INC-2026-00007"
    assert not cur.statements("INSERT INTO SecurityIncidents")
    assert cur.statements("INSERT INTO SecurityEvents")   # the attempt is still recorded


def test_a_burst_of_failed_sign_ins_raises_an_alert():
    cur = FakeCursor([{"n": secresp.FAILED_LOGIN_ALERT_THRESHOLD}, None, {"id": "a9"}])
    assert secresp.failed_login(cur, user_id="u1", public_user_id="DOC-1", role="Doctor") == "a9"


def test_every_emergency_gets_a_compliance_record():
    cur = FakeCursor([{"id": "a1"}, {"n": 3}])
    ref = secresp.emergency_compliance_record(
        cur, actor_id="d1", actor_public_id="DOC-1", patient_id="p1", emergency_id="e1",
        risk_level="LOW", risk_explanation="Behaviour is consistent.", tx_hash="0xabc")
    assert ref.endswith("00004")
    incident = next(p for q, p in cur.executed if "INSERT INTO SecurityIncidents" in q)
    assert incident[3] == "EMERGENCY_ACCESS" and incident[-1] == "0xabc"


def test_a_refusal_is_committed_before_it_is_raised():
    cur = FakeCursor()
    secresp.commit_before_refusal(cur)
    assert cur.connection.commits == 1


# ═══ Smart-contract consent (§7) ═════════════════════════════════════════════

class FakeChain:
    def __init__(self, onchain=True, fail=False):
        self.onchain, self.fail, self.writes = onchain, fail, []

    def check_consent(self, patient_ref, doctor_ref):
        if self.fail:
            raise ConnectionError("node down")
        return self.onchain

    def update_consent(self, patient_ref, doctor_ref, authorized):
        self.writes.append((patient_ref, doctor_ref, authorized))
        return {"tx_hash": "0xfeed"}


@pytest.fixture(autouse=False)
def ledger(monkeypatch):
    consent_ledger._cache.clear()
    yield monkeypatch
    consent_ledger._cache.clear()


def test_on_chain_references_are_pseudonymous():
    patient = "8b5f0a3e-1111-4222-8333-944455556666"
    ref = consent_ledger.party_ref(patient)
    assert len(ref) == 32 and patient not in ref
    assert ref == consent_ledger.party_ref(patient)
    assert ref != consent_ledger.party_ref("8b5f0a3e-1111-4222-8333-944455556667")


def test_consent_without_an_on_chain_record_is_unverified(ledger):
    cur = FakeCursor([{"onchain_tx_hash": None}])
    assert consent_ledger.verify(cur, patient_id="p", doctor_id="d", db_authorized=True) == "unverified"


def test_agreement_with_the_chain_verifies(ledger):
    ledger.setattr(consent_ledger, "_client", lambda: FakeChain(onchain=True))
    cur = FakeCursor([{"onchain_tx_hash": "0x1"}])
    assert consent_ledger.verify(cur, patient_id="p", doctor_id="d", db_authorized=True) == "verified"


def test_a_row_the_chain_contradicts_is_a_mismatch(ledger):
    """The row says Authorized; the contract says the patient withdrew."""
    ledger.setattr(consent_ledger, "_client", lambda: FakeChain(onchain=False))
    cur = FakeCursor([{"onchain_tx_hash": "0x1"}])
    assert consent_ledger.verify(cur, patient_id="p", doctor_id="d", db_authorized=True) == "mismatch"


@pytest.mark.parametrize("client", [None, FakeChain(fail=True)])
def test_an_unreachable_chain_is_reported_as_unverified_not_as_agreement(ledger, client):
    ledger.setattr(consent_ledger, "_client", lambda: client)
    cur = FakeCursor([{"onchain_tx_hash": "0x1"}])
    assert consent_ledger.verify(cur, patient_id="p", doctor_id="d", db_authorized=True) == "unverified"


def test_recording_without_a_chain_says_so_and_writes_nothing(ledger):
    ledger.setattr(consent_ledger, "_client", lambda: None)
    cur = FakeCursor()
    assert consent_ledger.record(cur, consent_id="c", patient_id="p", doctor_id="d",
                                 authorized=False)["recorded_on"] == "database-only"
    assert not cur.executed


def test_recording_writes_pseudonyms_and_remembers_the_transaction(ledger):
    chain = FakeChain()
    ledger.setattr(consent_ledger, "_client", lambda: chain)
    cur = FakeCursor()
    out = consent_ledger.record(cur, consent_id="c", patient_id="p", doctor_id="d", authorized=True)
    assert out == {"recorded_on": "ethereum", "tx_hash": "0xfeed"}
    assert chain.writes == [(consent_ledger.party_ref("p"), consent_ledger.party_ref("d"), True)]
    assert cur.statements("UPDATE Consent SET onchain_tx_hash")


# ═══ Federation: per-role models and the participant protocol (§20–21) ═══════

def test_fedavg_runs_per_role_weighted_by_that_roles_samples():
    a = {"version": 2, "roles": {"Doctor": _flat(median=2.0, samples=90),
                                 "Nurse": _flat(median=5.0, samples=10)}}
    b = {"version": 2, "roles": {"Doctor": _flat(median=12.0, samples=10)}}
    out = aisec.federated_average_roles([("A", 100, a), ("B", 10, b)])
    doctor = out["roles"]["Doctor"]["medians"]["records_accessed"]
    assert 2.5 < doctor < 3.5                      # A's 90 doctors outweigh B's 10
    assert out["roles"]["Nurse"]["medians"]["records_accessed"] == 5.0
    assert out["roles"]["Doctor"]["contributing_nodes"] == 2


def test_an_older_flat_model_is_kept_out_of_role_models():
    v1 = _flat(median=50.0, samples=100)
    v2 = {"version": 2, "roles": {"Doctor": _flat(median=2.0, samples=10)}}
    out = aisec.federated_average_roles([("old", 100, v1), ("new", 10, v2)])
    assert out["roles"]["Doctor"]["medians"]["records_accessed"] == 2.0
    assert out["roles"][aisec.ALL_ROLES]["medians"]["records_accessed"] == 50.0
    # ALL is only a fallback for a role nobody described.
    assert aisec.baseline_for_role(out, "Nurse").medians["records_accessed"] == 50.0
    assert aisec.baseline_for_role(out, "Doctor").medians["records_accessed"] == 2.0


@pytest.mark.parametrize("params,ok", [
    ({"version": 2, "roles": {"Doctor": _flat()}}, True),
    ({"version": 2, "roles": {}}, False),
    ({"version": 2, "roles": {"Doctor": {"medians": {}, "scales": {}}}}, False),
    ({"version": 2, "roles": {"Doctor": {"version": 2, "roles": {"x": _flat()}}}}, False),
    ({"version": 2, "roles": {"x" * 41: _flat()}}, False),
    ({"version": 2, "roles": "not a dict"}, False),
])
def test_per_role_submissions_get_the_same_plausibility_floor(params, ok):
    assert aisec.sane_parameters(params) is ok


def test_hub_requests_are_signed_fresh_and_bound_to_their_purpose():
    now = time.time()
    sig = federation.request_signature("hospital-b", int(now), "global-model", "s3cret")
    assert federation.verify_request_signature("hospital-b", str(int(now)), "global-model",
                                               "s3cret", sig, now=now)
    assert not federation.verify_request_signature("hospital-b", str(int(now)), "global-model",
                                                   "other", sig, now=now)
    assert not federation.verify_request_signature("hospital-b", str(int(now)), "submit",
                                                   "s3cret", sig, now=now)
    # Replayed after the freshness window.
    assert not federation.verify_request_signature("hospital-b", str(int(now)), "global-model",
                                                   "s3cret", sig, now=now + 3600)
    assert not federation.verify_request_signature("hospital-b", "yesterday", "global-model",
                                                   "s3cret", sig, now=now)


@pytest.fixture
def participant(monkeypatch):
    monkeypatch.setenv("FEDERATION_HUB_URL", "https://hub.example")
    monkeypatch.setenv("FEDERATION_NODE_NAME", "hospital-b")
    monkeypatch.setenv("FEDERATION_SHARED_SECRET", "s3cret")
    return monkeypatch


def test_not_configured_is_refused_plainly(monkeypatch):
    for name in ("FEDERATION_HUB_URL", "FEDERATION_NODE_NAME", "FEDERATION_SHARED_SECRET"):
        monkeypatch.delenv(name, raising=False)
    assert federation.is_configured() is False
    with pytest.raises(federation.FederationError):
        federation.pull_global_model()


def test_a_submission_carries_only_signed_parameters(participant):
    params = {"version": 2, "roles": {"Doctor": _flat(samples=7)}}
    participant.setattr(federation, "fit_local_update", lambda cur: (params, 7))
    sent = {}

    def fake_http(method, url, *, body=None, headers=None, timeout=30):
        if method == "GET":
            return 200, json.dumps({"round_number": 4, "parameters": params}).encode()
        sent.update(json.loads(body))
        return 200, b'{"accepted": true}'

    participant.setattr(federation, "_http", fake_http)
    out = federation.submit_local_update(FakeCursor())
    assert out["round_number"] == 5                     # the hub's next round
    assert set(sent) == {"node_name", "round_number", "sample_count", "parameters", "signature"}
    assert aisec.verify_parameters_signature("hospital-b", 5, 7, sent["parameters"], "s3cret",
                                             sent["signature"])


def test_a_global_model_that_fails_the_plausibility_floor_is_not_used(participant):
    bad = {"round_number": 2, "parameters": {"version": 2, "roles": {"Doctor": _flat(median=-5)}}}
    participant.setattr(federation, "_http", lambda *a, **k: (200, json.dumps(bad).encode()))
    with pytest.raises(federation.FederationError, match="plausibility"):
        federation.pull_global_model()


def test_a_hub_refusal_is_surfaced_with_its_reason(participant):
    participant.setattr(federation, "_http",
                        lambda *a, **k: (401, b'{"detail": "Signature verification failed."}'))
    with pytest.raises(federation.FederationError, match="401.*Signature"):
        federation.pull_global_model()


# ═══ Request schemas ═════════════════════════════════════════════════════════

def test_closing_an_incident_requires_a_resolution():
    from app.schemas import IncidentUpdateRequest
    with pytest.raises(ValidationError):
        IncidentUpdateRequest(status="Closed")
    with pytest.raises(ValidationError):
        IncidentUpdateRequest(status="Closed", resolution="   ")
    with pytest.raises(ValidationError):
        IncidentUpdateRequest(status="Reopened")
    assert IncidentUpdateRequest(status="Investigating").resolution is None
    assert IncidentUpdateRequest(status="Closed", resolution="False positive").status == "Closed"


def test_break_glass_requires_identity_verification():
    from app.schemas import EmergencyAccessRequest
    with pytest.raises(ValidationError):
        EmergencyAccessRequest(patient_id="p", reason="Patient unresponsive in A&E; history needed.")


# ═══ Access-path guards (source-level, like test_access_requests.py) ═════════

def _src(name):
    import app.main as main
    return inspect.getsource(getattr(main, name))


@pytest.mark.parametrize("endpoint", ["create_diagnosis", "create_prescription",
                                      "create_consultation", "create_medical_document"])
def test_chart_writes_need_the_same_entitlement_as_reads(endpoint):
    """A write used to need nothing, and then counted as a treating relationship."""
    assert "_require_write_access" in _src(endpoint)


def test_ordering_a_test_needs_entitlement_to_the_patient():
    src = _src("create_lab_test_request")
    assert "_doctor_patient_authorization" in src and "_deny(" in src


def test_a_report_must_answer_the_request_it_claims_to():
    src = _src("create_structured_lab_report")
    assert 'subject["requested_panel"] != panel["code"]' in src
    assert "accepted_by" in src


def test_break_glass_is_verified_limited_scored_and_recorded():
    src = _src("declare_emergency_access")
    for required in ("verify_password", "EMERGENCY_MAX_PER_DAY", "_security_gate",
                     "emergency_compliance_record", "consent_ledger.emergency"):
        assert required in src, required


@pytest.mark.parametrize("endpoint", ["download_patient_lab_report", "download_doctor_lab_report",
                                      "get_patient_imaging_image", "get_doctor_imaging_image",
                                      "get_imaging_image", "get_patient_document_content",
                                      "get_medical_document_content"])
def test_every_release_checks_integrity_and_signature(endpoint):
    assert "_release_verified" in _src(endpoint)


def test_an_unverified_signature_is_no_longer_released_with_a_warning():
    assert "Releasing report" not in _src("download_patient_lab_report")


@pytest.mark.parametrize("endpoint", ["get_doctor_patient_detail", "download_doctor_lab_report",
                                      "get_doctor_imaging_image", "get_patient_adherence"])
def test_clinician_reads_pass_the_risk_gate(endpoint):
    assert "_security_gate" in _src(endpoint)


def test_failed_sign_ins_reach_the_ai_layer():
    assert "secresp.failed_login" in _src("login")
