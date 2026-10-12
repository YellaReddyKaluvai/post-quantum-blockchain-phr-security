import os
import secrets
import sys

# Ensure the backend directory is in sys.path so we can import from app
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.database import get_db, init_db
from app.config import _PUBLIC_ADMIN_PASSWORDS, get_settings
from app.security import hash_password, encrypt_data
from app.crypto_service import generate_mlkem_keypair, generate_mldsa_keypair
from app.user_id_service import generate_user_id

def seed_admin():
    settings = get_settings()
    
    print("Initializing database...")
    init_db()
    
    print("Seeding administrator account...")
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM Users WHERE email = %s", (settings.ADMIN_EMAIL,))
            if cur.fetchone():
                print(f"Admin account with email {settings.ADMIN_EMAIL} already exists.")
                return
                
            # Never a password published in this repository. Without one set,
            # generate a random password and show it exactly once.
            password = settings.ADMIN_PASSWORD
            generated = password in _PUBLIC_ADMIN_PASSWORDS or len(password) < 12
            if generated:
                password = secrets.token_urlsafe(18)

            # Need to generate user_id
            user_id = generate_user_id("Administrator")
            pwd_hash = hash_password(password)
            dob_enc = encrypt_data("1980-01-01") # Dummy DOB for admin
            
            kem_pub, kem_priv = generate_mlkem_keypair()
            dsa_pub, dsa_priv = generate_mldsa_keypair()
            
            cur.execute("""
                INSERT INTO Users (
                    user_id, full_name, email, password_hash, role, gender, 
                    date_of_birth_encrypted, status,
                    mlkem_public_key, mlkem_private_key_encrypted,
                    mldsa_public_key, mldsa_private_key_encrypted,
                    approved_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'Approved', %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                user_id, "System Administrator", settings.ADMIN_EMAIL, pwd_hash, "Administrator", "Other",
                dob_enc, kem_pub, kem_priv, dsa_pub, dsa_priv
            ))
            conn.commit()
            print(f"Successfully seeded admin account with User ID: {user_id} and Email: {settings.ADMIN_EMAIL}")
            if generated:
                print("ADMIN_PASSWORD was unset, a published default or under 12 characters,")
                print(f"so this password was generated. It is shown only once: {password}")

if __name__ == "__main__":
    seed_admin()
