"""Replication to a real IPFS Pinning Service (spec §16).

Every other test of this path answers from a scripted fake of our own making,
which proves only that the client agrees with our reading of the specification.
Here the same client code talks to an independent implementation of the
[IPFS Pinning Service API](https://ipfs.github.io/pinning-services-api-spec/) —
ipfs-cluster, which CI runs beside the kubo node (.github/workflows/deploy.yml).
If our request shape, our status vocabulary or our polling were wrong against
the real specification, this is where it would show.

A commercial provider (Pinata, Filebase, …) speaks the same API; what cannot be
checked here is that provider's own availability, not the protocol.

    RUN_E2E=1 PINNING_SERVICE_URL=http://127.0.0.1:9097 IPFS_API_URL=… pytest
"""

import json
import os
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1" or not os.getenv("PINNING_SERVICE_URL"),
    reason="needs RUN_E2E=1 and a running pinning service (PINNING_SERVICE_URL)")


@pytest.fixture
def service(monkeypatch):
    """Configure the one pinning service, exactly as an operator would."""
    monkeypatch.setenv("IPFS_PINNING_SERVICES", json.dumps([{
        "name": "ci-cluster", "endpoint": os.environ["PINNING_SERVICE_URL"],
        "token": os.getenv("PINNING_SERVICE_TOKEN", "ci-not-authenticated"),
    }]))
    monkeypatch.setenv("IPFS_REPLICA_NODES", "")        # the service alone, so the result is unambiguous
    from app import ipfs_replication
    return ipfs_replication


def _publish(content: bytes) -> str:
    """Put a block on our own node and return its CID, so the service has an origin to fetch from."""
    from app import storage_service
    cid = storage_service.pin_to_ipfs(content, "replication-probe")
    assert cid, "the primary IPFS node did not return a CID"
    return cid


def test_a_real_pinning_service_accepts_our_request_and_reports_it_pinned(service):
    cid = _publish(f"pinning-service probe {uuid.uuid4()}".encode())

    results = service.replicate(cid, name="replication-probe")
    assert len(results) == 1, results
    outcome = results[0]
    assert outcome["error"] is None, outcome
    assert outcome["kind"] == "service" and outcome["target"] == "ci-cluster"
    # The spec's own vocabulary: queued → pinning → pinned. Anything else would
    # have been refused by _service_status before reaching here.
    assert outcome["status"] in {"queued", "pinning", "pinned"}, outcome
    assert outcome["request_id"], "the service must return a request id to poll"

    # Poll with the same code the scheduler uses. The content is already on the
    # node the cluster is attached to, so this settles quickly.
    target = next(t for t in service.targets() if t.name == "ci-cluster")
    deadline, status = time.time() + 120, outcome["status"]
    while status != "pinned" and time.time() < deadline:
        time.sleep(2)
        refreshed = service.refresh(target, outcome["request_id"])
        assert refreshed["error"] is None, refreshed
        status = refreshed["status"] or status
    assert status == "pinned", f"the service never confirmed the pin (last status: {status})"


def test_an_unknown_request_id_is_reported_not_guessed(service):
    """A status check for something the service has never heard of must come back
    as an error, not as a confident 'pinned'."""
    target = next(t for t in service.targets() if t.name == "ci-cluster")
    refreshed = service.refresh(target, "00000000-0000-4000-8000-000000000000")
    assert refreshed["status"] is None and refreshed["error"]
