"""Upgrade legacy encrypted/plain clinical columns to authenticated GCM.

Stop writers and back up the database first. Dry-run by default. A malformed
recognized ciphertext aborts the entire transaction. Does not change key material.
"""
import argparse
from app.database import get_db
from app.key_rotation import ENCRYPTED_COLUMNS
from app.security import encrypt_data, decrypt_data_strict, looks_encrypted


def upgrade(conn, apply=False):
    count = 0
    with conn.cursor() as cur:
        cur.execute("LOCK TABLE " + ", ".join(t for t, _, _ in ENCRYPTED_COLUMNS) + " IN EXCLUSIVE MODE")
        for table, pk, columns in ENCRYPTED_COLUMNS:
            cur.execute(f"SELECT {pk}, {', '.join(columns)} FROM {table}")
            for row in cur.fetchall():
                for column, value in zip(columns, row[1:]):
                    if not value or value.startswith("gcm2:"):
                        if value:
                            decrypt_data_strict(value)  # detect corrupted v2 during dry runs too
                        continue
                    plain = decrypt_data_strict(value) if looks_encrypted(value) else value
                    encrypted = encrypt_data(plain)
                    assert decrypt_data_strict(encrypted) == plain
                    count += 1
                    if apply:
                        cur.execute(f"UPDATE {table} SET {column} = %s WHERE {pk} = %s", (encrypted, row[0]))
        if apply:
            conn.commit()
        else:
            conn.rollback()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with get_db() as conn:
        print({"columns_upgraded" if args.apply else "columns_to_upgrade": upgrade(conn, args.apply)})
