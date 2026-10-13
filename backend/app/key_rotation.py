"""Re-encrypt every ENCRYPTION_KEY-protected column under a new key.

Databases created with the example key in .env.example hold personal fields,
clinical text and every user's post-quantum private keys under a key anyone can
read in this repository. Changing ENCRYPTION_KEY alone would make all of it
unreadable — including the ML-KEM private keys that unlock every report — so the
data has to move to the new key first. This module does that, all or nothing:

* every value is decrypted with the old key by a *strict* decrypt — one that
  fails rather than returning its input — so a wrong old key stops the run at
  the first value instead of re-encrypting garbage;
* every re-encrypted value is decrypted again with the new key and compared
  before anything is written;
* the tables are locked against writes, and the whole run is one transaction:
  any failure rolls back and nothing changes.

Values that are not in encrypt_data's format (clinical rows written before
column encryption existed) are reported and left as they are.

Run it with the server stopped — see rotate_encryption_key.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import _PUBLIC_ENCRYPTION_KEYS
from app.security import decrypt_data_strict, encrypt_data, looks_encrypted

# (table, primary key, encrypted columns). Every column written through
# encrypt_data — test_key_rotation keeps this in step with the code that writes them.
ENCRYPTED_COLUMNS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("Users", "id", ("date_of_birth_encrypted", "blood_group_encrypted",
                     "mlkem_private_key_encrypted", "mldsa_private_key_encrypted")),
    ("Diagnoses", "id", ("title", "description", "symptoms", "doctor_notes", "recommended_tests")),
    ("Prescriptions", "id", ("medicine_name", "dosage", "frequency", "duration", "instructions")),
    ("Consent", "consent_id", ("zkp_token_encrypted",)),
    ("FederatedPeers", "id", ("shared_secret_encrypted",)),
)


class RotationError(RuntimeError):
    """The rotation cannot proceed; nothing was changed."""


@dataclass
class ColumnReport:
    rotated: int = 0
    empty: int = 0
    unencrypted: int = 0


@dataclass
class RotationReport:
    applied: bool
    columns: dict[str, ColumnReport] = field(default_factory=dict)

    @property
    def rotated(self) -> int:
        return sum(c.rotated for c in self.columns.values())


def check_new_key(old_key: str, new_key: str) -> None:
    if len(new_key) != 32:
        raise RotationError("The new key must be exactly 32 characters "
                            '(python -c "import secrets; print(secrets.token_hex(16))").')
    if new_key == old_key:
        raise RotationError("The new key is the same as the current one.")
    if new_key in _PUBLIC_ENCRYPTION_KEYS:
        raise RotationError("The new key is a published example key.")


def rotate(conn, old_key: str, new_key: str, *, apply: bool = False) -> RotationReport:
    """Re-encrypt every column in ENCRYPTED_COLUMNS from ``old_key`` to ``new_key``.

    With ``apply=False`` (a dry run) every value is still decrypted and
    re-encrypted in memory — proving the old key opens all of it — and the
    transaction is rolled back. With ``apply=True`` it is committed.
    """
    check_new_key(old_key, new_key)
    report = RotationReport(applied=apply)
    try:
        with conn.cursor() as cur:
            if apply:
                cur.execute("LOCK TABLE " + ", ".join(t for t, _, _ in ENCRYPTED_COLUMNS)
                            + " IN EXCLUSIVE MODE")
            for table, pk, columns in ENCRYPTED_COLUMNS:
                for col in columns:
                    report.columns[f"{table}.{col}"] = ColumnReport()
                cur.execute(f"SELECT {pk}, {', '.join(columns)} FROM {table}")
                for row in cur.fetchall():
                    key, values = row[0], row[1:]
                    updates = {}
                    for col, value in zip(columns, values):
                        tally = report.columns[f"{table}.{col}"]
                        if not value:
                            tally.empty += 1
                            continue
                        if not looks_encrypted(value):
                            tally.unencrypted += 1
                            continue
                        try:
                            plain = decrypt_data_strict(value, old_key)
                        except ValueError as exc:
                            raise RotationError(
                                f"{table}.{col} ({pk}={key}) does not decrypt under the current "
                                "key — is ENCRYPTION_KEY the key this data was written with? "
                                "Nothing was changed.") from exc
                        fresh = encrypt_data(plain, new_key)
                        if decrypt_data_strict(fresh, new_key) != plain:
                            raise RotationError(f"Re-encryption check failed for {table}.{col}.")
                        updates[col] = fresh
                        tally.rotated += 1
                    if updates and apply:
                        cur.execute(
                            f"UPDATE {table} SET " + ", ".join(f"{c} = %s" for c in updates)
                            + f" WHERE {pk} = %s",
                            (*updates.values(), key))
        if apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        conn.rollback()
        raise
    return report
