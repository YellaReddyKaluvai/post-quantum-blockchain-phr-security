"""IPFS replication beyond the primary node.

The rule these tests hold: a replica counts only when the target itself says it
is pinned. A request that was merely accepted, a target that was unreachable,
and a configuration that could not be parsed must each be reported as exactly
that — never folded into a healthier-looking number.

No daemon or pinning account is needed: HTTP goes through one seam, replaced
here by a scripted fake that also records what was sent.
"""

import json

import pytest

from app import ipfs_replication as rep

PRIMARY = "http://primary:5001"
CID = "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG"
ORIGIN = "/ip4/10.0.0.5/tcp/4001/p2p/12D3KooWPrimary"


class FakeHTTP:
    """Scripted responses keyed by (method, url-prefix); every call is recorded."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, *, body=None, headers=None, timeout=None):
        self.calls.append({"method": method, "url": url, "body": body, "headers": headers or {}})
        for (m, prefix), response in self.routes.items():
            if m == method and url.startswith(prefix):
                if isinstance(response, Exception):
                    raise response
                status, payload = response
                return status, json.dumps(payload).encode() if not isinstance(payload, bytes) else payload
        raise rep.ReplicationError(f"unreachable: {url}")

    def urls(self, method=None):
        return [c["url"] for c in self.calls if method is None or c["method"] == method]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("IPFS_API_URL", PRIMARY)
    monkeypatch.delenv("IPFS_REPLICA_NODES", raising=False)
    monkeypatch.delenv("IPFS_PINNING_SERVICES", raising=False)
    return monkeypatch


def _service(name="pinata", endpoint="https://api.pinata.example/psa", token="secret-token"):
    return {"name": name, "endpoint": endpoint, "token": token}


def _primary_id():
    return {("POST", f"{PRIMARY}/api/v0/id"): (200, {"ID": "12D3KooWPrimary", "Addresses": [ORIGIN]})}


# ─── Configuration ───────────────────────────────────────────────────────────

def test_nothing_configured_means_no_targets(env):
    assert rep.targets() == []
    assert rep.is_configured() is False
    assert rep.schedule(CID) is False          # nothing to do, and nothing pretends otherwise


def test_nodes_and_services_are_both_read(env):
    env.setenv("IPFS_REPLICA_NODES", "http://replica-a:5001/, http://replica-b:5001")
    env.setenv("IPFS_PINNING_SERVICES", json.dumps([_service()]))
    found = rep.targets()
    assert [(t.kind, t.url) for t in found] == [
        ("node", "http://replica-a:5001"), ("node", "http://replica-b:5001"),
        ("service", "https://api.pinata.example/psa")]


@pytest.mark.parametrize("raw,fragment", [
    ("{not json", "not valid JSON"),
    ('{"name": "x"}', "must be a JSON list"),
    ('[{"name": "x", "endpoint": "https://e"}]', "needs name, endpoint and token"),
])
def test_bad_service_configuration_is_reported_not_ignored(env, raw, fragment):
    env.setenv("IPFS_PINNING_SERVICES", raw)
    assert any(fragment in e for e in rep.config_errors())
    assert rep.targets() == []                 # and the bad entry is not used


def test_service_tokens_are_never_reported(env):
    env.setenv("IPFS_PINNING_SERVICES", json.dumps([_service(token="do-not-leak")]))
    summary = rep.summarise([], rep.targets(), set())
    assert "do-not-leak" not in json.dumps(summary)


# ─── Replicating to a peer node ──────────────────────────────────────────────

def test_a_node_is_connected_to_us_then_asked_to_pin(env):
    env.setenv("IPFS_REPLICA_NODES", "http://replica:5001")
    fake = FakeHTTP({**_primary_id(),
                     ("POST", "http://replica:5001/api/v0/swarm/connect"): (200, {"Strings": ["ok"]}),
                     ("POST", "http://replica:5001/api/v0/pin/add"): (200, {"Pins": [CID]})})
    env.setattr(rep, "_http", fake)

    [result] = rep.replicate(CID)
    assert result["status"] == "pinned" and result["error"] is None
    connect, pin = fake.urls()[1], fake.urls()[2]
    assert "swarm/connect" in connect and "12D3KooWPrimary" in connect
    assert pin.endswith(f"pin/add?arg={CID}")


def test_a_node_that_does_not_confirm_the_pin_is_a_failure(env):
    env.setenv("IPFS_REPLICA_NODES", "http://replica:5001")
    env.setattr(rep, "_http", FakeHTTP({**_primary_id(),
                                        ("POST", "http://replica:5001/api/v0/pin/add"): (200, {"Pins": []})}))
    [result] = rep.replicate(CID)
    assert result["status"] == "failed" and "did not confirm" in result["error"]


def test_one_unreachable_target_does_not_stop_the_others(env):
    env.setenv("IPFS_REPLICA_NODES", "http://down:5001,http://up:5001")
    env.setattr(rep, "_http", FakeHTTP({**_primary_id(),
                                        ("POST", "http://up:5001/api/v0/pin/add"): (200, {"Pins": [CID]})}))
    results = {r["target"]: r for r in rep.replicate(CID)}
    assert results["node down:5001"]["status"] == "failed"
    assert results["node down:5001"]["error"]
    assert results["node up:5001"]["status"] == "pinned"


# ─── Replicating to a pinning service ────────────────────────────────────────

def test_a_service_gets_the_cid_our_origins_and_the_bearer_token(env):
    env.setenv("IPFS_PINNING_SERVICES", json.dumps([_service()]))
    fake = FakeHTTP({**_primary_id(),
                     ("POST", "https://api.pinata.example/psa/pins"):
                         (202, {"requestid": "req-1", "status": "queued"})})
    env.setattr(rep, "_http", fake)

    [result] = rep.replicate(CID, "report.enc")
    # Accepted is not pinned: the service has only queued the request.
    assert result["status"] == "queued" and result["request_id"] == "req-1"

    call = fake.calls[-1]
    sent = json.loads(call["body"])
    assert sent["cid"] == CID and sent["origins"] == [ORIGIN] and sent["name"] == "report.enc"
    assert call["headers"]["Authorization"] == "Bearer secret-token"


def test_a_service_error_is_a_failure_with_its_reason(env):
    env.setenv("IPFS_PINNING_SERVICES", json.dumps([_service()]))
    env.setattr(rep, "_http", FakeHTTP({**_primary_id(),
                                        ("POST", "https://api.pinata.example/psa/pins"):
                                            (401, {"error": {"reason": "UNAUTHORIZED"}})}))
    [result] = rep.replicate(CID)
    assert result["status"] == "failed" and "HTTP 401" in result["error"]


def test_an_unknown_service_status_is_not_trusted(env):
    env.setenv("IPFS_PINNING_SERVICES", json.dumps([_service()]))
    env.setattr(rep, "_http", FakeHTTP({**_primary_id(),
                                        ("POST", "https://api.pinata.example/psa/pins"):
                                            (202, {"requestid": "r", "status": "probably-fine"})}))
    [result] = rep.replicate(CID)
    assert result["status"] == "failed"


def test_refresh_reports_progress_and_keeps_state_when_the_check_fails(env):
    env.setenv("IPFS_PINNING_SERVICES", json.dumps([_service()]))
    [target] = rep.targets()
    env.setattr(rep, "_http", FakeHTTP({("GET", "https://api.pinata.example/psa/pins/req-1"):
                                        (200, {"requestid": "req-1", "status": "pinned"})}))
    assert rep.refresh(target, "req-1") == {"status": "pinned", "error": None}

    env.setattr(rep, "_http", FakeHTTP({}))   # the service is down
    update = rep.refresh(target, "req-1")
    # A failed status check says nothing about the pin; it must not downgrade it.
    assert update["status"] is None and update["error"]


# ─── Only content the primary node really holds is replicable ────────────────

def test_primary_pins_are_read_from_the_node(env):
    env.setattr(rep, "_http", FakeHTTP({("POST", f"{PRIMARY}/api/v0/pin/ls"):
                                        (200, {"Keys": {CID: {"Type": "recursive"}}})}))
    assert rep.primary_pins() == {CID}


def test_primary_pins_are_unknown_not_empty_when_the_node_is_down(env):
    """None, not an empty set: 'cannot tell' must not read as 'holds nothing'."""
    env.setattr(rep, "_http", FakeHTTP({}))
    assert rep.primary_pins() is None


# ─── The replication factor counts confirmed copies only ─────────────────────

def test_summary_counts_only_confirmed_copies(env):
    env.setenv("IPFS_REPLICA_NODES", "http://a:5001")
    env.setenv("IPFS_PINNING_SERVICES", json.dumps([_service()]))
    targets = rep.targets()
    node, service = targets[0].name, targets[1].name
    other = "QmOther"
    rows = [
        {"cid": CID, "target": node, "status": "pinned"},
        {"cid": CID, "target": service, "status": "pinned"},
        {"cid": other, "target": node, "status": "failed"},
        {"cid": other, "target": service, "status": "queued"},
        {"cid": CID, "target": "a target removed since", "status": "pinned"},
    ]
    s = rep.summarise(rows, targets, {CID, other})
    by_name = {t["name"]: t for t in s["targets"]}
    assert by_name[node] == {**by_name[node], "pinned": 1, "failed": 1, "in_progress": 0}
    assert by_name[service] == {**by_name[service], "pinned": 1, "in_progress": 1, "failed": 0}
    assert s["cids_published"] == 2
    assert s["cids_with_a_replica"] == 1        # the queued request does not count
    assert s["cids_on_every_target"] == 1
    assert s["min_copies"] == 1                 # `other` exists only on the primary node


def test_summary_with_nothing_published(env):
    s = rep.summarise([], [], set())
    assert s["cids_published"] == 0 and s["min_copies"] == 0
