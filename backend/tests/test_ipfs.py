"""IPFS publishing.

The module previously computed a CID and pinned nothing, while a gateway link
in the UI implied otherwise. These tests hold the line on the distinction:
addressing content and publishing it are different operations, and the code
must say which one it did.

Every test runs whether or not a node is reachable — the suite must not depend
on a daemon being up.
"""

import io
import json
import os
import pytest

from app.storage_service import (
    generate_ipfs_cid_v0, is_ipfs_configured, ipfs_api_url,
    pin_to_ipfs, fetch_from_ipfs, ipfs_status, IPFSError,
)

NODE = bool(os.getenv("IPFS_API_URL"))
needs_node = pytest.mark.skipif(not NODE, reason="no IPFS node configured")


# ─── Content addressing works with no network at all ─────────────────────────

def test_cid_is_deterministic():
    assert generate_ipfs_cid_v0(b"same bytes") == generate_ipfs_cid_v0(b"same bytes")


def test_cid_changes_with_content():
    assert generate_ipfs_cid_v0(b"a") != generate_ipfs_cid_v0(b"b")


def test_cid_has_the_v0_shape():
    cid = generate_ipfs_cid_v0(b"payload")
    assert cid.startswith("Qm") and 44 <= len(cid) <= 48


def test_cid_needs_no_node():
    """Deliberate: a fingerprint must still be recordable when IPFS is down."""
    assert generate_ipfs_cid_v0(b"x")


# ─── An absent node is a configuration choice, not a failure ─────────────────

def test_pin_returns_none_when_no_node_is_configured(monkeypatch):
    """A hospital that does not run IPFS must still be able to file reports."""
    monkeypatch.delenv("IPFS_API_URL", raising=False)
    monkeypatch.delenv("IPFS_PINATA_JWT", raising=False)
    assert pin_to_ipfs(b"ciphertext", "x.enc") is None


def test_fetch_raises_when_no_node_is_configured(monkeypatch):
    """Retrieval is different: asking for content that cannot be had is an
    error, not a quiet None that the caller would treat as empty data."""
    monkeypatch.delenv("IPFS_API_URL", raising=False)
    monkeypatch.delenv("IPFS_PINATA_JWT", raising=False)
    with pytest.raises(IPFSError):
        fetch_from_ipfs("QmWhatever")


def test_status_distinguishes_unconfigured_from_unreachable(monkeypatch):
    monkeypatch.delenv("IPFS_API_URL", raising=False)
    monkeypatch.delenv("IPFS_PINATA_JWT", raising=False)
    s = ipfs_status()
    assert s["configured"] is False and s["connected"] is False
    assert "No IPFS node configured" in s["error"]

    monkeypatch.setenv("IPFS_API_URL", "http://127.0.0.1:1")   # nothing listens
    s = ipfs_status()
    assert s["configured"] is True and s["connected"] is False
    assert "unreachable" in s["error"]


def test_unreachable_node_raises_rather_than_pretending(monkeypatch):
    """The failure mode this module exists to avoid: reporting success for
    content that was never stored."""
    monkeypatch.setenv("IPFS_API_URL", "http://127.0.0.1:1")
    with pytest.raises(IPFSError):
        pin_to_ipfs(b"ciphertext", "x.enc")


def test_pinata_publishes_only_ciphertext_and_recovers_it(monkeypatch):
    """A provider upload is a real pin, and its gateway returns the same bytes."""
    from app import storage_service

    monkeypatch.delenv("IPFS_API_URL", raising=False)
    monkeypatch.setenv("IPFS_PINATA_JWT", "private-test-token")
    monkeypatch.setenv("IPFS_PINATA_GATEWAY_URL", "https://example.mypinata.cloud")
    uploaded = b"encrypted-payload-only"
    cid = "bafybeigdyrztpinataexample"
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        if request.full_url == "https://uploads.pinata.cloud/v3/files":
            assert request.get_header("Authorization") == "Bearer private-test-token"
            assert uploaded in request.data
            assert b"report.enc" not in request.data
            assert b'name="network"' in request.data
            assert b"public" in request.data
            return io.BytesIO(json.dumps({"data": {"cid": cid}}).encode())
        if request.full_url == f"https://example.mypinata.cloud/ipfs/{cid}":
            return io.BytesIO(uploaded)
        raise AssertionError(request.full_url)

    monkeypatch.setattr(storage_service.urllib.request, "urlopen", fake_urlopen)
    assert is_ipfs_configured()
    assert pin_to_ipfs(uploaded, "report.enc") == cid
    assert fetch_from_ipfs(cid) == uploaded
    assert len(requests) == 2


def test_pinata_status_checks_authentication_without_exposing_token(monkeypatch):
    from app import storage_service

    monkeypatch.delenv("IPFS_API_URL", raising=False)
    monkeypatch.setenv("IPFS_PINATA_JWT", "private-test-token")
    monkeypatch.setenv("IPFS_PINATA_GATEWAY_URL", "https://example.mypinata.cloud")

    def fake_urlopen(request, timeout):
        assert request.full_url == "https://api.pinata.cloud/data/testAuthentication"
        assert request.get_header("Authorization") == "Bearer private-test-token"
        return io.BytesIO(b'{"message":"Congratulations!"}')

    monkeypatch.setattr(storage_service.urllib.request, "urlopen", fake_urlopen)
    status = ipfs_status()
    assert status["configured"] and status["connected"]
    assert status["provider"] == "pinata"
    assert "private-test-token" not in json.dumps(status)


# ─── Against a live node ─────────────────────────────────────────────────────

@needs_node
def test_status_reports_a_live_node():
    s = ipfs_status()
    if not s["connected"]:
        pytest.skip("configured but not running")
    assert s["peer_id"]
    from app import ipfs_replication
    if ipfs_replication.is_configured():
        assert "replicated to the targets" in s["scope"]
    else:
        assert "not the same as being replicated" in s["scope"]


@needs_node
def test_publish_and_retrieve_round_trip():
    if not ipfs_status()["connected"]:
        pytest.skip("configured but not running")
    payload = b"ENCRYPTED-" + os.urandom(64)
    cid = pin_to_ipfs(payload, "roundtrip.enc")
    assert cid and cid.startswith("Qm")
    assert fetch_from_ipfs(cid) == payload


@needs_node
def test_node_cid_differs_from_the_raw_fingerprint():
    """Not a bug, and asserted so nobody 'fixes' it.

    generate_ipfs_cid_v0 hashes the raw bytes; `ipfs add` wraps them in a UnixFS
    node and hashes that. Both are valid CIDv0 values addressing different
    objects, so the published CID is the one recorded.
    """
    if not ipfs_status()["connected"]:
        pytest.skip("configured but not running")
    payload = b"UNIXFS-FRAMING-" + os.urandom(32)
    assert pin_to_ipfs(payload, "framing.enc") != generate_ipfs_cid_v0(payload)


# ─── Replication to a second, independent node ───────────────────────────────

needs_replica = pytest.mark.skipif(not os.getenv("IPFS_REPLICA_NODES"),
                                   reason="no replica node configured")


@needs_node
@needs_replica
def test_a_published_document_is_replicated_to_a_second_node():
    """Run against two real kubo daemons in CI. The replica's own pin list is
    the evidence — not this application's record that it asked."""
    import json
    from app import ipfs_replication

    if not ipfs_status()["connected"]:
        pytest.skip("configured but not running")
    payload = b"REPLICA-" + os.urandom(64)
    cid = pin_to_ipfs(payload, "replica.enc")
    assert cid in (ipfs_replication.primary_pins() or set())

    results = ipfs_replication.replicate(cid, "replica.enc")
    assert results and all(r["status"] == "pinned" for r in results), results

    for target in ipfs_replication.targets():
        status, body = ipfs_replication._http(
            "POST", f"{target.url}/api/v0/pin/ls?arg={cid}&type=recursive", timeout=30)
        assert status == 200 and cid in json.loads(body)["Keys"], (target.name, body[:200])
