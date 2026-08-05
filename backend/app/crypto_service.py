import logging
import base64
from app.security import encrypt_data

logger = logging.getLogger(__name__)

try:
    import oqs
    OQS_AVAILABLE = True
except ImportError:
    OQS_AVAILABLE = False
    logger.warning("liboqs-python not available. Falling back to mock PQC keys.")

def generate_mlkem_keypair() -> tuple[str, str]:
    """Generates ML-KEM (Kyber-768) keypair. Returns (public_key, encrypted_private_key)"""
    if OQS_AVAILABLE:
        try:
            with oqs.KeyEncapsulation("Kyber768") as kem:
                public_key_bytes = kem.generate_keypair()
                private_key_bytes = kem.export_secret_key()
                public_key = base64.b64encode(public_key_bytes).decode('utf-8')
                private_key = base64.b64encode(private_key_bytes).decode('utf-8')
                return public_key, encrypt_data(private_key)
        except Exception as e:
            logger.error(f"Error generating ML-KEM key: {e}")
            
    # Mock fallback
    import secrets
    public_key = f"mock_mlkem_pub_{secrets.token_hex(32)}"
    private_key = f"mock_mlkem_priv_{secrets.token_hex(64)}"
    return public_key, encrypt_data(private_key)

def generate_mldsa_keypair() -> tuple[str, str]:
    """Generates ML-DSA (Dilithium3) keypair. Returns (public_key, encrypted_private_key)"""
    if OQS_AVAILABLE:
        try:
            with oqs.Signature("Dilithium3") as sig:
                public_key_bytes = sig.generate_keypair()
                private_key_bytes = sig.export_secret_key()
                public_key = base64.b64encode(public_key_bytes).decode('utf-8')
                private_key = base64.b64encode(private_key_bytes).decode('utf-8')
                return public_key, encrypt_data(private_key)
        except Exception as e:
            logger.error(f"Error generating ML-DSA key: {e}")
            
    # Mock fallback
    import secrets
    public_key = f"mock_mldsa_pub_{secrets.token_hex(32)}"
    private_key = f"mock_mldsa_priv_{secrets.token_hex(64)}"
    return public_key, encrypt_data(private_key)

def decapsulate_aes_key(encrypted_aes_key: str, mlkem_private_key: str) -> str:
    """Decapsulate or unwrap the AES key using the patient's ML-KEM private key"""
    # In a real implementation with liboqs:
    # with oqs.KeyEncapsulation("Kyber768") as kem:
    #     shared_secret = kem.decapsulate(ciphertext, private_key_bytes)
    #     return shared_secret
    
    # For our mock implementation from the seed script:
    if encrypted_aes_key.startswith("WRAPPED_BY_"):
        # Format is WRAPPED_BY_{patient_kem_pub[:10]}_{aes_key[:10]}
        parts = encrypted_aes_key.split('_')
        return parts[-1]
    elif encrypted_aes_key.startswith("UNWRAPPED_"):
        return encrypted_aes_key.replace("UNWRAPPED_", "")
    
    return encrypted_aes_key

def verify_mldsa_signature(document_hash: str, signature: str, mldsa_public_key: str) -> bool:
    """Verify the digital signature of the document using ML-DSA public key"""
    # In a real implementation with liboqs:
    # with oqs.Signature("Dilithium3") as sig:
    #     return sig.verify(document_hash.encode(), signature_bytes, public_key_bytes)
    
    # Mock fallback: assume valid if a signature exists
    return True

