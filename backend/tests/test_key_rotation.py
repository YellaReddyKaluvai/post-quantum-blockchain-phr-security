"""Rotating ENCRYPTION_KEY without losing a single value.

Unit tests drive app.key_rotation over a fake connection; the last test runs it
against a real Postgres database it creates and drops (RUN_E2E, as in CI).
"""

import os
import re
import uuid
from pathlib import Path

import pytest

from app import key_rotation as kr
from app.security import decrypt_data_strict, encrypt_data, looks_encrypted

OLD = "a" * 32
NEW = "b1" * 16


# ─── Strict decryption ───────────────────────────────────────────────────────

def test_strict_decrypt_opens_only_with_the_right_key():
    value = encrypt_data("1990-05-05", OLD)
    assert looks_encrypted(value) and decrypt_data_strict(value, OLD) == "1990-05-05"
    with pytest.raises(ValueError):
        decrypt_data_strict(value, NEW)


@pytest.mark.parametrize("text", ["Hypertension", "a:b", "", "12:30 daily", None])
def test_plaintext_is_not_mistaken_for_ciphertext(text):
    assert not looks_encrypted(text)


# ─── Every encrypted column is covered ───────────────────────────────────────

def test_every_encrypted_column_in_the_schema_is_rotated():
    schema = (Path(__file__).resolve().parents[1] / "db" / "init.sql").read_text()
    declared = set(re.findall(r"\b(\w+_encrypted)\b", schema))
    covered = {c for _, _, cols in kr.ENCRYPTED_COLUMNS for c in cols}
    assert declared <= covered, declared - covered


def test_clinical_columns_match_the_fields_the_app_encrypts():
    from app.main import DIAGNOSIS_ENCRYPTED_FIELDS, PRESCRIPTION_ENCRYPTED_FIELDS
    columns = {t: cols for t, _, cols in kr.ENCRYPTED_COLUMNS}
    assert set(columns["Diagnoses"]) == set(DIAGNOSIS_ENCRYPTED_FIELDS)
    assert set(columns["Prescriptions"]) == set(PRESCRIPTION_ENCRYPTED_FIELDS)


# ─── Rotation over a fake connection ─────────────────────────────────────────

class Cursor:
    def __init__(self, tables):
        self.tables, self.updates, self._rows = tables, [], []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        m = re.match(r"SELECT \w+, .* FROM (\w+)$", sql)
        if m:
            self._rows = self.tables.get(m.group(1), [])
        elif sql.startswith("UPDATE"):
            self.updates.append((sql, params))

    def fetchall(self):
        return self._rows


class Conn:
    def __init__(self, tables):
        self.cur, self.commits, self.rollbacks = Cursor(tables), 0, 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _users():
    return {"Users": [("u1", encrypt_data("1990-05-05", OLD), None,
                       encrypt_data("kem-private", OLD), encrypt_data("dsa-private", OLD))],
            "Diagnoses": [("d1", encrypt_data("Asthma", OLD), "legacy plaintext note", None, None, None)]}


def test_rotation_reencrypts_every_value_and_verifies_it():
    conn = Conn(_users())
    report = kr.rotate(conn, OLD, NEW, apply=True)
    assert conn.commits == 1 and report.rotated == 4
    assert report.columns["Diagnoses.description"].unencrypted == 1     # left as it was
    written = [v for _, params in conn.cur.updates for v in params[:-1]]
    assert sorted(decrypt_data_strict(v, NEW) for v in written) == \
        sorted(["1990-05-05", "kem-private", "dsa-private", "Asthma"])


def test_a_dry_run_changes_nothing():
    conn = Conn(_users())
    assert kr.rotate(conn, OLD, NEW).rotated == 4
    assert not conn.cur.updates and conn.commits == 0 and conn.rollbacks == 1


def test_the_wrong_current_key_stops_before_anything_is_written():
    conn = Conn(_users())
    with pytest.raises(kr.RotationError, match="does not decrypt"):
        kr.rotate(conn, "c" * 32, NEW, apply=True)
    assert not conn.cur.updates and conn.commits == 0 and conn.rollbacks >= 1


@pytest.mark.parametrize("new", ["short", OLD, "0123456789abcdef0123456789abcdef"])
def test_unusable_new_keys_are_refused(new):
    with pytest.raises(kr.RotationError):
        kr.rotate(Conn({}), OLD, new, apply=True)


# ─── Against real Postgres ───────────────────────────────────────────────────

@pytest.mark.skipif(os.getenv("RUN_E2E") != "1", reason="needs RUN_E2E=1 and a Postgres server")
def test_rotation_against_a_real_database():
    """A throwaway database: schema from init.sql, one row in every encrypted
    table, rotated, then every value read back under the new key."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    base = conninfo_to_dict(os.environ["DATABASE_URL"])
    name = f"rotation_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(make_conninfo(**{**base, "dbname": "postgres"}), autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
    url = make_conninfo(**{**base, "dbname": name})
    try:
        with psycopg.connect(url) as conn:
            conn.execute((Path(__file__).resolve().parents[1] / "db" / "init.sql").read_text())
            pid = conn.execute(
                """INSERT INTO Users (full_name, email, password_hash, role, gender,
                                      date_of_birth_encrypted, blood_group_encrypted,
                                      mlkem_private_key_encrypted, mldsa_private_key_encrypted, status)
                   VALUES ('Rotation Patient', 'rot@example.com', 'x', 'Patient', 'Other',
                           %s, %s, %s, %s, 'Approved') RETURNING id""",
                (encrypt_data("1990-05-05", OLD), encrypt_data("O+", OLD),
                 encrypt_data("kem", OLD), encrypt_data("dsa", OLD))).fetchone()[0]
            conn.execute("""INSERT INTO Diagnoses (patient_id, title, description, visit_date)
                            VALUES (%s, %s, %s, CURRENT_DATE)""",
                         (pid, encrypt_data("Asthma", OLD), encrypt_data("Mild", OLD)))
            conn.execute("""INSERT INTO Prescriptions (patient_id, medicine_name, dosage, frequency,
                                                       duration, prescribed_date)
                            VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)""",
                         (pid, *(encrypt_data(v, OLD) for v in ("Salbutamol", "100mcg", "PRN", "30d"))))
            conn.execute("""INSERT INTO FederatedPeers (node_name, shared_secret_encrypted)
                            VALUES ('peer', %s)""", (encrypt_data("hmac-secret", OLD),))
            conn.commit()

            with pytest.raises(kr.RotationError):
                kr.rotate(conn, "c" * 32, NEW, apply=True)
            report = kr.rotate(conn, OLD, NEW, apply=True)
            assert report.rotated == 11

            row = conn.execute("SELECT date_of_birth_encrypted, mlkem_private_key_encrypted "
                               "FROM Users WHERE id = %s", (pid,)).fetchone()
            assert [decrypt_data_strict(v, NEW) for v in row] == ["1990-05-05", "kem"]
            med = conn.execute("SELECT medicine_name FROM Prescriptions").fetchone()[0]
            assert decrypt_data_strict(med, NEW) == "Salbutamol"
            with pytest.raises(ValueError):
                decrypt_data_strict(med, OLD)
    finally:
        with psycopg.connect(make_conninfo(**{**base, "dbname": "postgres"}), autocommit=True) as admin:
            admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
