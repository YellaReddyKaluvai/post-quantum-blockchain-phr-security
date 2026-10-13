"""Re-issue post-quantum keypairs for users still holding mock key material.

Background: an earlier build requested the mechanism "Dilithium3", which does
not exist in liboqs 0.16. The failure was swallowed by a broad ``except`` and
the code fell back to placeholder strings such as ``mock_mldsa_pub_...``. Any
account approved by that build therefore has key columns that *look* populated
but carry no cryptographic value.

This script finds those accounts and issues real ML-KEM-768 / ML-DSA-65 keys.

Usage:
    python3 reissue_mock_pqc_keys.py           # report only (no writes)
    python3 reissue_mock_pqc_keys.py --apply   # perform the re-issue
"""

import sys

from app.database import get_db
from app.crypto_service import (
    generate_mlkem_keypair,
    generate_mldsa_keypair,
    is_mock_key,
    pqc_available,
)

MOCK_PREFIXES = ("mock_mlkem_%", "mock_mldsa_%")


def find_affected(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, user_id, full_name, role, mlkem_public_key, mldsa_public_key
            FROM Users
            WHERE mlkem_public_key LIKE 'mock_mlkem_%'
               OR mldsa_public_key LIKE 'mock_mldsa_%'
            ORDER BY created_at
            """
        )
        return cur.fetchall()


def main() -> int:
    apply_changes = "--apply" in sys.argv

    if not pqc_available():
        print("ERROR: real post-quantum primitives are unavailable (liboqs).")
        print("Refusing to run — re-issuing keys now would just write more mocks.")
        return 1

    with get_db() as conn:
        affected = find_affected(conn)

        if not affected:
            print("No accounts with mock key material. Nothing to do.")
            return 0

        print(f"Found {len(affected)} account(s) holding mock key material:\n")
        for row in affected:
            uid, public_id, name, role, kem_pub, dsa_pub = row
            flags = []
            if is_mock_key(kem_pub):
                flags.append("ML-KEM")
            if is_mock_key(dsa_pub):
                flags.append("ML-DSA")
            print(f"  {public_id or '(unapproved)':<18} {name:<24} {role:<15} mock: {', '.join(flags)}")

        if not apply_changes:
            print("\nDry run. Re-run with --apply to issue real keypairs.")
            return 0

        print("\nRe-issuing keypairs...")
        with conn.cursor() as cur:
            for row in affected:
                uid, public_id, name, role, kem_pub, dsa_pub = row
                kem_public, kem_private = generate_mlkem_keypair()
                dsa_public, dsa_private = generate_mldsa_keypair()
                cur.execute(
                    """
                    UPDATE Users
                    SET mlkem_public_key = %s,
                        mlkem_private_key_encrypted = %s,
                        mldsa_public_key = %s,
                        mldsa_private_key_encrypted = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (kem_public, kem_private, dsa_public, dsa_private, uid),
                )
                print(f"  re-issued: {public_id or uid} ({name})")
            conn.commit()

        print(
            "\nDone. Note: documents signed under the old mock keys can never be "
            "verified — they were never genuinely signed."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
