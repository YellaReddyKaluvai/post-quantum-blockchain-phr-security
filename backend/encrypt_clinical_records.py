"""Encrypt the clinical text in existing Diagnoses and Prescriptions rows.

Rows written before column encryption hold their clinical text in the clear.
This brings them in line with new rows.

Only content is encrypted. Dates and foreign keys stay readable because every
ORDER BY and JOIN depends on them, and nothing sorts, filters or searches on
the clinical text itself.

Safe to re-run: a value is skipped when it already decrypts, so a second pass
cannot double-encrypt. That check is exact rather than heuristic — guessing
from the shape of the string would misfire on clinical text that happens to
contain a colon.

Usage:
    python3 encrypt_clinical_records.py           # report only (no writes)
    python3 encrypt_clinical_records.py --apply   # perform the encryption
"""

import sys

from psycopg.rows import dict_row

from app.database import get_db
from app.security import encrypt_data, decrypt_data

TABLES = {
    "Diagnoses": ("title", "description", "symptoms", "doctor_notes", "recommended_tests"),
    "Prescriptions": ("medicine_name", "dosage", "frequency", "duration", "instructions"),
}


def already_encrypted(value: str) -> bool:
    """True when the value round-trips through decryption.

    ``decrypt_data`` returns its input unchanged when it cannot decrypt, so a
    changed result is proof the value was genuinely encrypted.
    """
    return bool(value) and decrypt_data(value) != value


def main() -> int:
    apply_changes = "--apply" in sys.argv

    with get_db() as conn:
        plan = {}
        for table, fields in TABLES.items():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"SELECT id, {', '.join(fields)} FROM {table}")
                rows = cur.fetchall()

            pending = []
            for r in rows:
                needs = {f: r[f] for f in fields if r[f] and not already_encrypted(r[f])}
                if needs:
                    pending.append((r["id"], needs))
            plan[table] = (len(rows), pending)

        print("Clinical text encryption\n")
        for table, (total, pending) in plan.items():
            print(f"  {table:<15} {total:>3} rows, {len(pending):>3} need encrypting")

        if not any(p for _, p in plan.values()):
            print("\nNothing to do — all clinical text is already encrypted.")
            return 0

        if not apply_changes:
            print("\nDry run. Re-run with --apply to encrypt.")
            return 0

        print("\nEncrypting...")
        total_fields = 0
        for table, (_, pending) in plan.items():
            for row_id, needs in pending:
                assignments = ", ".join(f"{f} = %s" for f in needs)
                values = [encrypt_data(v) for v in needs.values()]
                with conn.cursor() as cur:
                    cur.execute(f"UPDATE {table} SET {assignments} WHERE id = %s", values + [row_id])
                total_fields += len(needs)
            conn.commit()
            print(f"  {table}: {len(pending)} rows updated")

        print(f"\nDone. {total_fields} field(s) encrypted.")

        # Prove the round trip on real data rather than trusting the write.
        print("\nVerifying...")
        for table, fields in TABLES.items():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"SELECT {', '.join(fields)} FROM {table} LIMIT 1")
                r = cur.fetchone()
            if not r:
                continue
            sample = next((f for f in fields if r[f]), None)
            if sample:
                stored = r[sample]
                print(f"  {table}.{sample}: stored={stored[:28]}... decrypts to {decrypt_data(stored)[:36]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
