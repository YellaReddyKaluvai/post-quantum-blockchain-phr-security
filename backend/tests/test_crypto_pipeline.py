"""The security properties the whole system rests on.

These assert the guarantees, not the implementation: that a tampered document
is *rejected*, that a mock key is *refused*, that a wrong key *fails*. A test
that only checks the happy path would pass against a function that always
returns True, which is precisely the failure this codebase has had before.

Pure functions only — no database, no network, no running server — so they run
anywhere and fail for exactly one reason.
"""

import base64

import pytest

from app import crypto_service as cs


pytestmark = pytest.mark.skipif(
    not cs.pqc_available(),
    reason="liboqs unavailable; post-quantum primitives cannot be exercised",
)


# ─── Mechanisms ──────────────────────────────────────────────────────────────

def test_uses_standardised_nist_mechanism_names():
    """The legacy round-3 names are not what liboqs 0.16 exposes.

    Asking for "Dilithium3" raises MechanismNotSupportedError, which an earlier
    build swallowed — silently substituting placeholder keys so that nothing
    was ever really signed.
    """
    assert cs.ML_KEM_ALG == "ML-KEM-768"
    assert cs.ML_DSA_ALG == "ML-DSA-65"


def test_generated_keys_are_real_not_placeholders():
    kem_pub, kem_priv = cs.generate_mlkem_keypair()
    dsa_pub, dsa_priv = cs.generate_mldsa_keypair()

    assert not cs.is_mock_key(kem_pub)
    assert not cs.is_mock_key(dsa_pub)

    # FIPS 203 / 204 fixed public key sizes. A placeholder string cannot
    # accidentally satisfy these.
    assert len(base64.b64decode(kem_pub)) == 1184
    assert len(base64.b64decode(dsa_pub)) == 1952
    assert kem_priv and dsa_priv


def test_each_keypair_is_unique():
    first, _ = cs.generate_mlkem_keypair()
    second, _ = cs.generate_mlkem_keypair()
    assert first != second


# ─── ML-KEM: protecting the AES key ──────────────────────────────────────────

def test_kem_round_trip_recovers_the_same_secret():
    public_key, private_key = cs.generate_mlkem_keypair()
    ciphertext, sent = cs.encapsulate_aes_key(public_key)
    received = cs.decapsulate_aes_key(ciphertext, private_key)
    assert sent == received
    assert len(sent) == 32  # exactly an AES-256 key


def test_kem_ciphertext_is_useless_without_the_matching_private_key():
    public_key, _ = cs.generate_mlkem_keypair()
    _, other_private = cs.generate_mlkem_keypair()
    ciphertext, secret = cs.encapsulate_aes_key(public_key)

    # ML-KEM is designed to return a wrong secret rather than error on a bad
    # key, so the check is that it does not match — the AES unwrap then fails.
    wrong = cs.decapsulate_aes_key(ciphertext, other_private)
    assert wrong != secret


def test_encapsulating_against_a_mock_key_is_refused():
    with pytest.raises(cs.PQCUnavailableError):
        cs.encapsulate_aes_key("mock_mlkem_pub_deadbeef")


# ─── ML-DSA: authenticity and integrity ──────────────────────────────────────

def test_genuine_signature_verifies():
    public_key, private_key = cs.generate_mldsa_keypair()
    digest = cs.sha256_hex(b"a finalised lab report")
    signature = cs.sign_document_hash(digest, private_key)
    assert cs.verify_mldsa_signature(digest, signature, public_key) is True


def test_altered_digest_fails_verification():
    """The property that makes tampering detectable."""
    public_key, private_key = cs.generate_mldsa_keypair()
    signature = cs.sign_document_hash(cs.sha256_hex(b"original"), private_key)
    assert cs.verify_mldsa_signature(cs.sha256_hex(b"tampered"), signature, public_key) is False


def test_signature_from_another_signer_fails():
    _, impostor_private = cs.generate_mldsa_keypair()
    real_public, _ = cs.generate_mldsa_keypair()
    digest = cs.sha256_hex(b"discharge summary")
    forged = cs.sign_document_hash(digest, impostor_private)
    assert cs.verify_mldsa_signature(digest, forged, real_public) is False


def test_mock_public_key_never_verifies():
    """A placeholder key must read as INVALID, never as trusted."""
    _, private_key = cs.generate_mldsa_keypair()
    digest = cs.sha256_hex(b"anything")
    signature = cs.sign_document_hash(digest, private_key)
    assert cs.verify_mldsa_signature(digest, signature, "mock_mldsa_pub_deadbeef") is False


@pytest.mark.parametrize("digest,signature,public_key", [
    ("", "sig", "key"),
    ("digest", "", "key"),
    ("digest", "sig", ""),
    ("digest", "not-base64!!", "also-not-base64!!"),
])
def test_malformed_input_returns_false_rather_than_raising(digest, signature, public_key):
    """Callers treat the result as a verdict, so it must never explode."""
    assert cs.verify_mldsa_signature(digest, signature, public_key) is False


# ─── AES-256-GCM: protecting the document ────────────────────────────────────

def test_document_round_trip():
    key = cs.derive_aes_key(b"\x01" * 32)
    plaintext = b"%PDF-1.4 fake report body"
    box = cs.encrypt_document(plaintext, key)
    assert cs.decrypt_document(box["ciphertext"], key, box["nonce"], box["tag"]) == plaintext


def test_ciphertext_does_not_leak_the_plaintext():
    key = cs.derive_aes_key(b"\x02" * 32)
    box = cs.encrypt_document(b"Patient has Type 2 Diabetes Mellitus", key)
    assert b"Diabetes" not in base64.b64decode(box["ciphertext"])


def test_tampered_ciphertext_is_rejected():
    """GCM's tag is what makes altered stored bytes detectable."""
    key = cs.derive_aes_key(b"\x03" * 32)
    box = cs.encrypt_document(b"original findings", key)

    raw = bytearray(base64.b64decode(box["ciphertext"]))
    raw[0] ^= 0xFF  # flip one bit
    tampered = base64.b64encode(bytes(raw)).decode()

    with pytest.raises(ValueError):
        cs.decrypt_document(tampered, key, box["nonce"], box["tag"])


def test_wrong_key_cannot_decrypt():
    box = cs.encrypt_document(b"confidential", cs.derive_aes_key(b"\x04" * 32))
    with pytest.raises(ValueError):
        cs.decrypt_document(box["ciphertext"], cs.derive_aes_key(b"\x05" * 32), box["nonce"], box["tag"])


def test_same_plaintext_encrypts_differently_each_time():
    """A fresh nonce per encryption; identical reports must not look identical."""
    key = cs.derive_aes_key(b"\x06" * 32)
    first = cs.encrypt_document(b"same body", key)
    second = cs.encrypt_document(b"same body", key)
    assert first["ciphertext"] != second["ciphertext"]
    assert first["nonce"] != second["nonce"]


# ─── SHA-256 fingerprint ─────────────────────────────────────────────────────

def test_digest_is_stable_and_sensitive():
    assert cs.sha256_hex(b"report") == cs.sha256_hex(b"report")
    # A single changed byte must produce a different fingerprint.
    assert cs.sha256_hex(b"report") != cs.sha256_hex(b"reporr")
    assert len(cs.sha256_hex(b"report")) == 64


# ─── The full hybrid pipeline ────────────────────────────────────────────────

def test_end_to_end_hybrid_protection():
    """Exactly the path a finalised report takes, and the one an attacker faces.

    The document is AES-encrypted, its key is protected against the patient's
    ML-KEM public key, and its digest is signed by the technician's ML-DSA key.
    Recovering it requires the patient's private key; trusting it requires the
    technician's signature to verify.
    """
    patient_pub, patient_priv = cs.generate_mlkem_keypair()
    tech_pub, tech_priv = cs.generate_mldsa_keypair()
    report = b"%PDF-1.4 CBC: Haemoglobin 10.2 g/dL"

    digest = cs.sha256_hex(report)
    kem_ciphertext, shared = cs.encapsulate_aes_key(patient_pub)
    box = cs.encrypt_document(report, cs.derive_aes_key(shared))
    signature = cs.sign_document_hash(digest, tech_priv)

    # An authorised reader recovers it exactly.
    recovered_key = cs.derive_aes_key(cs.decapsulate_aes_key(kem_ciphertext, patient_priv))
    recovered = cs.decrypt_document(box["ciphertext"], recovered_key, box["nonce"], box["tag"])

    assert recovered == report
    assert cs.sha256_hex(recovered) == digest
    assert cs.verify_mldsa_signature(digest, signature, tech_pub) is True

    # An attacker holding only the stored material recovers nothing.
    _, attacker_priv = cs.generate_mlkem_keypair()
    attacker_key = cs.derive_aes_key(cs.decapsulate_aes_key(kem_ciphertext, attacker_priv))
    with pytest.raises(ValueError):
        cs.decrypt_document(box["ciphertext"], attacker_key, box["nonce"], box["tag"])
