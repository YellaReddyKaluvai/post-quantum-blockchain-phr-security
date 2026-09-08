"""IPFS publishing.

The module previously computed a CID and pinned nothing, while a gateway link
in the UI implied otherwise. These tests hold the line on the distinction:
addressing content and publishing it are different operations, and the code
must say which one it did.

Every test runs whether or not a node is reachable — the suite must not depend
on a daemon being up.
"""

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
    assert pin_to_ipfs(b"ciphertext", "x.enc") is None


def test_fetch_raises_when_no_node_is_configured(monkeypatch):
    """Retrieval is different: asking for content that cannot be had is an
    error, not a quiet None that the caller would treat as empty data."""
    monkeypatch.delenv("IPFS_API_URL", raising=False)
    with pytest.raises(IPFSError):
        fetch_from_ipfs("QmWhatever")


def test_status_distinguishes_unconfigured_from_unreachable(monkeypatch):
    monkeypatch.delenv("IPFS_API_URL", raising=False)
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


# ─── Against a live node ─────────────────────────────────────────────────────

@needs_node
def test_status_reports_a_live_node():
    s = ipfs_status()
    if not s["connected"]:
        pytest.skip("configured but not running")
    assert s["peer_id"]
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
