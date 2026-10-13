"""Storage and audit-anchor behaviour must never overstate what happened.

Every bug these cover was real. Uploads used to swallow failures and return
the object key anyway, so the database recorded cloud copies that did not
exist. Downloads returned b"MOCK_ENCRYPTED_PAYLOAD_FROM_S3" on failure,
feeding garbage into the decryption path. Anchors could be presented as
on-chain when no chain had been reached.

The shared property: when something did not happen, the system must say so.
"""

import pytest

from app import storage_service as ss
from app import anchor_service as anch


# ─── Configuration honesty ───────────────────────────────────────────────────

def test_placeholder_credentials_count_as_unconfigured(monkeypatch):
    """Shipped defaults must not read as credentials that merely failed."""
    class FakeSettings:
        AWS_ACCESS_KEY_ID = "AKIA_MOCK_QUANTUMCARE_AWS_KEY"
        AWS_SECRET_ACCESS_KEY = "mock_aws_secret_key_quantumcare_pqc"
        AWS_S3_BUCKET = "bucket"
        AWS_REGION = "eu-north-1"

    monkeypatch.setattr(ss, "get_settings", lambda: FakeSettings())
    ss.reset_client()
    assert ss.is_s3_configured() is False

    status = ss.storage_status()
    assert status["configured"] is False
    assert status["connected"] is False
    assert status["error"]


def test_missing_bucket_counts_as_unconfigured(monkeypatch):
    class FakeSettings:
        AWS_ACCESS_KEY_ID = "AKIAREALLOOKINGKEY123"
        AWS_SECRET_ACCESS_KEY = "a-real-looking-secret-value"
        AWS_S3_BUCKET = ""
        AWS_REGION = "eu-north-1"

    monkeypatch.setattr(ss, "get_settings", lambda: FakeSettings())
    ss.reset_client()
    assert ss.is_s3_configured() is False


def test_unconfigured_storage_raises_instead_of_pretending(monkeypatch):
    class FakeSettings:
        AWS_ACCESS_KEY_ID = "mock"
        AWS_SECRET_ACCESS_KEY = "mock"
        AWS_S3_BUCKET = "bucket"
        AWS_REGION = "eu-north-1"

    monkeypatch.setattr(ss, "get_settings", lambda: FakeSettings())
    ss.reset_client()

    with pytest.raises(ss.StorageError):
        ss.upload_to_aws_s3(b"ciphertext", "report.enc")
    with pytest.raises(ss.StorageError):
        ss.download_file_from_s3("phr_records/report.enc")


def test_download_never_substitutes_placeholder_bytes(monkeypatch):
    """The old code returned a literal placeholder that then hit AES-GCM."""
    class FakeSettings:
        AWS_ACCESS_KEY_ID = "mock"
        AWS_SECRET_ACCESS_KEY = "mock"
        AWS_S3_BUCKET = "bucket"
        AWS_REGION = "eu-north-1"

    monkeypatch.setattr(ss, "get_settings", lambda: FakeSettings())
    ss.reset_client()

    try:
        result = ss.download_file_from_s3("phr_records/missing.enc")
    except ss.StorageError:
        return  # correct: refused rather than invented
    pytest.fail(f"download returned {result!r} instead of raising")


# ─── A failed upload must not be recorded as a stored object ─────────────────

def test_failed_upload_yields_no_object_key(monkeypatch):
    """A key is a promise the object exists. No upload, no key."""
    class FakeSettings:
        AWS_ACCESS_KEY_ID = "mock"
        AWS_SECRET_ACCESS_KEY = "mock"
        AWS_S3_BUCKET = "bucket"
        AWS_REGION = "eu-north-1"
        IPFS_GATEWAY_URL = ""

    monkeypatch.setattr(ss, "get_settings", lambda: FakeSettings())
    ss.reset_client()

    cid, s3_key = ss.store_encrypted_document(b"ciphertext", "LR-2026-000001_CBC")

    assert s3_key is None, "recorded a key for an object that was never uploaded"
    # The content address is derived locally, so it is still available.
    assert cid.startswith("Qm")


# ─── Content addressing ──────────────────────────────────────────────────────

def test_cid_is_deterministic_and_content_bound():
    same = ss.generate_ipfs_cid_v0(b"identical bytes")
    assert same == ss.generate_ipfs_cid_v0(b"identical bytes")
    assert same != ss.generate_ipfs_cid_v0(b"different bytes")
    assert same.startswith("Qm")


def test_cid_matches_the_ipfs_multihash_format():
    """CIDv0 is base58(0x12 0x20 || sha256), which is why it starts 'Qm'."""
    import base64
    import hashlib

    payload = b"encrypted report"
    cid = ss.generate_ipfs_cid_v0(payload)

    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for char in cid:
        number = number * 58 + alphabet.index(char)
    decoded = number.to_bytes((number.bit_length() + 7) // 8, "big")

    assert decoded[:2] == b"\x12\x20"          # sha2-256, 32 bytes
    assert decoded[2:] == hashlib.sha256(payload).digest()
    assert base64  # keep the import meaningful under linting


# ─── Anchoring ───────────────────────────────────────────────────────────────

def test_anchor_falls_back_locally_and_says_so(monkeypatch):
    """An unreachable chain must never yield an anchor that looks on-chain."""
    monkeypatch.setattr(anch, "_submit_to_chain", lambda payload: None)

    written = {}

    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params): written["params"] = params

    class FakeConn:
        def cursor(self): return FakeCursor()
        def commit(self): pass

    result = anch.anchor_document(
        FakeConn(),
        document_type="LabReport", document_id="11111111-1111-1111-1111-111111111111",
        document_hash="a" * 64, action="REPORT_FINALIZED",
    )

    assert result["anchored_on"] == anch.ANCHOR_LOCAL
    assert result["block_number"] is None
    assert result["tx_hash"].startswith("0x")
    assert anch.ANCHOR_LOCAL in written["params"]


def test_simulated_hash_is_bound_to_the_payload():
    """Even locally, a changed document must change the anchor."""
    base = {"document_id": "abc", "action": "REPORT_FINALIZED", "document_hash": "a" * 64}
    changed = {**base, "document_hash": "b" * 64}

    assert anch._simulated_tx_hash(base) == anch._simulated_tx_hash(base)
    assert anch._simulated_tx_hash(base) != anch._simulated_tx_hash(changed)


def test_anchor_failure_does_not_abort_the_clinical_action(monkeypatch):
    """An audit-trail problem must not block care being recorded."""
    monkeypatch.setattr(anch, "_submit_to_chain", lambda payload: None)

    class ExplodingConn:
        def cursor(self): raise RuntimeError("database is down")
        def commit(self): pass

    result = anch.anchor_document(
        ExplodingConn(),
        document_type="LabReport", document_id="22222222-2222-2222-2222-222222222222",
        document_hash="c" * 64, action="REPORT_FINALIZED",
    )
    assert result["document_hash"] == "c" * 64
