"""Post-Quantum Cryptography services for QuantumCare.

Responsibilities (kept deliberately separate, per the project architecture):

  * ML-KEM (Kyber)    -> protects/establishes the AES data-encryption key
  * ML-DSA (Dilithium)-> digital signatures for authenticity + integrity

This module never encrypts medical payloads itself; AES-256 does that
(see ``crypto_utils.py``). Here we only deal with key material and signatures.

IMPORTANT — mechanism names:
liboqs 0.16 exposes the *standardised* NIST names. The legacy round-3 name
"Dilithium3" does NOT exist and raises ``MechanismNotSupportedError``. Using it
previously caused every signing keypair to silently degrade to a mock string,
which meant no real signatures were ever produced. Always use the constants
below rather than hardcoding names.
"""

import base64
import hashlib
import logging

from Crypto.Cipher import AES

from app.security import encrypt_data, decrypt_data

logger = logging.getLogger(__name__)

# Standardised NIST mechanism names as exposed by liboqs >= 0.10.
ML_KEM_ALG = "ML-KEM-768"   # FIPS 203 (formerly Kyber768)
ML_DSA_ALG = "ML-DSA-65"    # FIPS 204 (formerly Dilithium3)

try:
    import oqs
    OQS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on deployment environment
    oqs = None
    OQS_AVAILABLE = False
    logger.critical(
        "liboqs-python is not installed. Post-quantum key generation, signing "
        "and verification are UNAVAILABLE. Install liboqs-python before "
        "approving users or issuing medical documents."
    )


class PQCUnavailableError(RuntimeError):
    """Raised when a post-quantum operation is attempted without liboqs.

    We fail loudly rather than substituting mock key material: a fake keypair
    that looks real in the database is far more dangerous than an outright
    error, because it silently voids every downstream integrity guarantee.
    """


def pqc_available() -> bool:
    """True when real post-quantum primitives can actually be used."""
    if not OQS_AVAILABLE:
        return False
    try:
        return (
            ML_KEM_ALG in oqs.get_enabled_kem_mechanisms()
            and ML_DSA_ALG in oqs.get_enabled_sig_mechanisms()
        )
    except Exception:  # pragma: no cover - defensive
        return False


def _require_pqc() -> None:
    if not OQS_AVAILABLE:
        raise PQCUnavailableError(
            "liboqs-python is not installed; cannot perform post-quantum operations."
        )


def is_mock_key(value: str | None) -> bool:
    """Detect legacy placeholder key material left by the old mock fallback."""
    return bool(value) and value.startswith(("mock_mlkem_", "mock_mldsa_"))


# ─── Key generation (called on admin approval) ───────────────────────────────

def generate_mlkem_keypair() -> tuple[str, str]:
    """Generate an ML-KEM-768 keypair.

    Returns ``(public_key_b64, aes_encrypted_private_key)``.
    """
    _require_pqc()
    with oqs.KeyEncapsulation(ML_KEM_ALG) as kem:
        public_key = kem.generate_keypair()
        private_key = kem.export_secret_key()
    return (
        base64.b64encode(public_key).decode("utf-8"),
        encrypt_data(base64.b64encode(private_key).decode("utf-8")),
    )


def generate_mldsa_keypair() -> tuple[str, str]:
    """Generate an ML-DSA-65 keypair.

    Returns ``(public_key_b64, aes_encrypted_private_key)``.
    """
    _require_pqc()
    with oqs.Signature(ML_DSA_ALG) as sig:
        public_key = sig.generate_keypair()
        private_key = sig.export_secret_key()
    return (
        base64.b64encode(public_key).decode("utf-8"),
        encrypt_data(base64.b64encode(private_key).decode("utf-8")),
    )


# ─── Key encapsulation (protects the AES data-encryption key) ────────────────

def encapsulate_aes_key(recipient_mlkem_public_key: str) -> tuple[str, bytes]:
    """Encapsulate a fresh shared secret against a recipient's ML-KEM public key.

    Returns ``(ciphertext_b64, shared_secret_bytes)``. The 32-byte shared secret
    is used as the AES-256 data-encryption key; the ciphertext is what gets
    persisted so the recipient can recover that key later.
    """
    _require_pqc()
    if is_mock_key(recipient_mlkem_public_key):
        raise PQCUnavailableError(
            "Recipient holds legacy mock ML-KEM key material; re-issue their "
            "keypair before encapsulating."
        )
    public_key_bytes = base64.b64decode(recipient_mlkem_public_key)
    with oqs.KeyEncapsulation(ML_KEM_ALG) as kem:
        ciphertext, shared_secret = kem.encap_secret(public_key_bytes)
    return base64.b64encode(ciphertext).decode("utf-8"), shared_secret


def decapsulate_aes_key(encrypted_aes_key: str, mlkem_private_key_encrypted: str) -> bytes:
    """Recover the AES data-encryption key from an ML-KEM ciphertext.

    ``mlkem_private_key_encrypted`` is the AES-encrypted private key exactly as
    stored in the ``Users`` table.
    """
    _require_pqc()
    private_key_b64 = decrypt_data(mlkem_private_key_encrypted)
    private_key_bytes = base64.b64decode(private_key_b64)
    ciphertext = base64.b64decode(encrypted_aes_key)
    with oqs.KeyEncapsulation(ML_KEM_ALG, private_key_bytes) as kem:
        return kem.decap_secret(ciphertext)


# ─── AES-256-GCM bulk encryption of the medical document ─────────────────────
#
# ML-KEM protects the key; AES protects the document. The KEM shared secret is
# used directly as the AES-256 key (ML-KEM-768 emits exactly 32 bytes), so the
# two halves of the hybrid scheme meet here.

def derive_aes_key(shared_secret: bytes) -> bytes:
    """Derive a 32-byte AES-256 key from a KEM shared secret.

    ML-KEM-768 already yields 32 bytes, but hashing keeps the key the right
    length if the mechanism is ever changed, and avoids using the raw secret
    for two purposes.
    """
    return hashlib.sha256(shared_secret).digest()


def encrypt_document(plaintext: bytes, aes_key: bytes) -> dict[str, str]:
    """AES-256-GCM encrypt a document. Returns base64 ciphertext, nonce and tag."""
    cipher = AES.new(aes_key, AES.MODE_GCM)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return {
        "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
        "nonce": base64.b64encode(cipher.nonce).decode("utf-8"),
        "tag": base64.b64encode(tag).decode("utf-8"),
    }


def decrypt_document(ciphertext_b64: str, aes_key: bytes, nonce_b64: str, tag_b64: str) -> bytes:
    """AES-256-GCM decrypt with authentication.

    Raises ``ValueError`` if the ciphertext or tag was altered — GCM's
    authentication check is what makes tampering with stored data detectable.
    """
    cipher = AES.new(aes_key, AES.MODE_GCM, nonce=base64.b64decode(nonce_b64))
    return cipher.decrypt_and_verify(base64.b64decode(ciphertext_b64), base64.b64decode(tag_b64))


def sha256_hex(payload: bytes) -> str:
    """SHA-256 hex digest used as the document's integrity fingerprint."""
    return hashlib.sha256(payload).hexdigest()


# ─── Digital signatures (authenticity + integrity) ───────────────────────────

def sign_document_hash(document_hash: str, mldsa_private_key_encrypted: str) -> str:
    """Sign a document's SHA-256 hash with the signer's ML-DSA private key.

    ``document_hash`` is the hex digest; it is signed as raw ASCII bytes so the
    verifier can reproduce the message from the stored hash alone.
    Returns a base64 signature.
    """
    _require_pqc()
    private_key_b64 = decrypt_data(mldsa_private_key_encrypted)
    private_key_bytes = base64.b64decode(private_key_b64)
    with oqs.Signature(ML_DSA_ALG, private_key_bytes) as sig:
        signature = sig.sign(document_hash.encode("utf-8"))
    return base64.b64encode(signature).decode("utf-8")


def verify_mldsa_signature(document_hash: str, signature: str, mldsa_public_key: str) -> bool:
    """Verify an ML-DSA signature over a document hash.

    Returns False (never raises) on any malformed or mock input, so callers can
    treat the result as a straightforward integrity verdict.
    """
    if not (document_hash and signature and mldsa_public_key):
        return False
    if is_mock_key(mldsa_public_key):
        logger.warning(
            "Signature verification attempted against legacy mock ML-DSA key; "
            "treating as INVALID."
        )
        return False
    if not OQS_AVAILABLE:
        logger.error("Cannot verify signature: liboqs-python unavailable.")
        return False
    try:
        public_key_bytes = base64.b64decode(mldsa_public_key)
        signature_bytes = base64.b64decode(signature)
        with oqs.Signature(ML_DSA_ALG) as sig:
            return bool(sig.verify(document_hash.encode("utf-8"), signature_bytes, public_key_bytes))
    except Exception as exc:
        logger.warning(f"ML-DSA signature verification failed: {exc}")
        return False
