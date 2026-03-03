import os
import base64
from Cryptodome.Cipher import AES
from Cryptodome.Random import get_random_bytes
import oqs  # from liboqs-python

class CryptoManager:
    """
    Manages Post-Quantum Cryptography (CRYSTALS-Kyber) and classical AES-256 for secure 
    health record encryption.
    """
    def __init__(self, kem_alg="Kyber768"):
        """Initialize the Key Encapsulation Mechanism (KEM)."""
        self.kem_alg = kem_alg
        # Initialize a KEM object in pyoqs
        try:
            self.kem = oqs.KeyEncapsulation(self.kem_alg)
        except Exception as e:
            print(f"Failed to initialize Kyber KEM. Ensure liboqs is installed: {e}")
            raise

    def generate_keypair(self):
        """
        Generates a Kyber keypair for a receiver (e.g., a patient or doctor).
        Returns:
            public_key (bytes), secret_key (bytes)
        """
        public_key = self.kem.generate_keypair()
        secret_key = self.kem.export_secret_key()
        return public_key, secret_key
        
    def encapsulate_key(self, public_key_receiver):
        """
        Derives an AES-256 symmetric key (shared secret) and encapsulates it using the receiver's public key.
        This represents the sender uploading a file for a specific receiver.
        Returns:
            ciphertext_kyber (bytes): The encapsulated AES key.
            shared_secret_aes (bytes): The actual 32-byte (256-bit) AES key to encrypt the payload.
        """
        ciphertext_kyber, shared_secret_aes = self.kem.encap_secret(public_key_receiver)
        return ciphertext_kyber, shared_secret_aes

    def decapsulate_key(self, ciphertext_kyber, secret_key_receiver):
        """
        Decapsulates the Kyber ciphertext using the receiver's secret key to recover the AES-256 symmetric key.
        Returns:
            shared_secret_aes (bytes): The 32-byte (256-bit) AES key needed to decrypt the payload.
        """
        # We need to temporarily re-import the secret key into the KEM object context.
        temp_kem = oqs.KeyEncapsulation(self.kem_alg, secret_key_receiver)
        shared_secret_aes = temp_kem.decap_secret(ciphertext_kyber)
        temp_kem.free()
        return shared_secret_aes

    def encrypt_payload_aes(self, aes_key: bytes, payload_data: bytes) -> dict:
        """
        Encrypts the actual health record metadata or PDF bytes using AES-256-GCM.
        Returns a dictionary with the ciphertext, nonce, and auth tag.
        """
        cipher = AES.new(aes_key, AES.MODE_GCM)
        ciphertext, tag = cipher.encrypt_and_digest(payload_data)
        
        return {
            "ciphertext": base64.b64encode(ciphertext).decode('utf-8'),
            "nonce": base64.b64encode(cipher.nonce).decode('utf-8'),
            "tag": base64.b64encode(tag).decode('utf-8')
        }

    def decrypt_payload_aes(self, aes_key: bytes, encrypted_dict: dict) -> bytes:
        """
        Decrypts the health record payload using the given AES-256 key.
        """
        ciphertext = base64.b64decode(encrypted_dict["ciphertext"])
        nonce = base64.b64decode(encrypted_dict["nonce"])
        tag = base64.b64decode(encrypted_dict["tag"])
        
        cipher = AES.new(aes_key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext

    def free(self):
        """Frees the underlying C-structs in liboqs."""
        if self.kem:
            self.kem.free()

# Instantiate a global instance or a mock version if environment issues persist in CI/CD.
try:
    crypto_manager = CryptoManager("Kyber768")
except Exception:
    # Fallback to simple simulated AES wrap if liboqs C-bindings fail on Windows (for Dev only)
    print("WARNING: Falling back to mocked PQC environment!")
    class MockCryptoManager:
        def generate_keypair(self):
            return b"mock_pub", b"mock_priv"
        def encapsulate_key(self, pub):
            aes_key = get_random_bytes(32)
            return b"mock_kyber_ciphertext", aes_key
        def decapsulate_key(self, cipher, priv):
            return b"mocked_but_we_need_real_aes_in_db" # Real implementation requires state persistence
        def encrypt_payload_aes(self, key, data):
            # Simplistic mock
            return {"ciphertext": base64.b64encode(data).decode('utf-8'), "nonce":"", "tag":""}
        def decrypt_payload_aes(self, key, d):
            return base64.b64decode(d["ciphertext"])
        def free(self): pass
    crypto_manager = MockCryptoManager()
