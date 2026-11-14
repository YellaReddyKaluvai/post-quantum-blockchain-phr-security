"""Explicit, local-only synthetic data for a disposable federation lab."""
import argparse
import json
import os
import random

from psycopg.types.json import Json

from app.database import get_db, init_db
from app.security import encrypt_data, hash_password, verify_password
from app.config import get_settings
from seed_admin import seed_admin


def behaviour(rng, threat, pattern):
    features = {"records_accessed": rng.randint(3, 25), "distinct_patients": rng.randint(1, 10),
                "off_hours_ratio": rng.uniform(0, .25), "failed_logins": rng.randint(0, 1),
                "emergency_declarations": 0, "peak_burst": rng.randint(1, 8),
                "access_denied": rng.randint(0, 1)}
    if threat:
        if pattern == 0:
            features.update(records_accessed=rng.randint(60, 300), distinct_patients=rng.randint(40, 150),
                            peak_burst=rng.randint(20, 80))
        elif pattern == 1:
            features.update(off_hours_ratio=rng.uniform(.65, 1), emergency_declarations=rng.randint(3, 9),
                            records_accessed=rng.randint(25, 80))
        else:
            features.update(failed_logins=rng.randint(8, 30), access_denied=rng.randint(8, 30))
    return features


def seed(node):
    if os.getenv("FEDERATION_LAB_MODE") != "true":
        raise RuntimeError("Synthetic seeding requires FEDERATION_LAB_MODE=true on a disposable database.")
    init_db()
    # Refuse mixed real/demo databases and reruns instead of contaminating results.
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT role, email, password_hash FROM Users")
        users = cur.fetchall()
        settings = get_settings()
        bootstrap_only = (len(users) == 1 and users[0][0] == "Administrator"
                          and users[0][1] == settings.ADMIN_EMAIL
                          and verify_password(settings.ADMIN_PASSWORD, users[0][2]))
        cur.execute("SELECT (SELECT COUNT(*) FROM SecurityLabels) + "
                    "(SELECT COUNT(*) FROM FederatedValidationLabels) + "
                    "(SELECT COUNT(*) FROM SecurityEvents)")
        if (users and not bootstrap_only) or cur.fetchone()[0]:
            raise RuntimeError("Lab seeding requires an empty database or its unused bootstrap admin. Existing data was not changed.")
    seed_admin()  # genuine PQC key generation and the configured random admin password
    rng = random.Random(100 + ord(node))
    pattern = "abc".index(node)
    with get_db() as conn, conn.cursor() as cur:
        cur.execute("SELECT user_id FROM Users WHERE email = %s", (get_settings().ADMIN_EMAIL,))
        admin_id = cur.fetchone()[0]
        # Disabled fictional actors supply activity baselines; no clinical records exist.
        for i in range(8):
            cur.execute("""INSERT INTO Users (user_id, full_name, email, password_hash, role, gender,
                          date_of_birth_encrypted, status)
                          VALUES (%s, %s, %s, %s, 'Doctor', 'Other', %s, 'Rejected') RETURNING id""",
                        (f"DOC-LAB-{node}-{i}", f"Synthetic {node} {i}", f"lab-{node}-{i}@example.invalid",
                         hash_password(os.urandom(24).hex()), encrypt_data("1980-01-01")))
            actor = cur.fetchone()[0]
            for event in range(10 + i):
                cur.execute("""INSERT INTO SecurityEvents (actor_id, actor_role, event_type, occurred_at, metadata)
                               VALUES (%s, 'Doctor', 'RECORD_ACCESS', CURRENT_TIMESTAMP - make_interval(hours => %s),
                                       '{"synthetic": true}'::jsonb)""", (actor, 1 + event % 8))
        # Each institution specialises in one threat pattern (non-IID data).
        training_keys = set()
        for i in range(80):
            label = i % 2
            features = behaviour(rng, label, pattern)
            training_keys.add(json.dumps(features, sort_keys=True))
            cur.execute("INSERT INTO SecurityLabels (actor_role, features, label, source) VALUES ('Doctor', %s, %s, 'SYNTHETIC_LAB')",
                        (Json(features), label))
        # Fresh examples covering all threat types, kept in a separate table.
        validation_rng = random.Random(900 + ord(node))
        for i in range(120):
            label = i % 2
            features = behaviour(validation_rng, label, (i // 2) % 3)
            assert json.dumps(features, sort_keys=True) not in training_keys
            cur.execute("INSERT INTO FederatedValidationLabels (features, label, source) VALUES (%s, %s, 'SYNTHETIC_LAB')",
                        (Json(features), label))
        conn.commit()
    print(json.dumps({"node": node, "admin_id": admin_id, "training_examples": 80,
                      "validation_examples": 120, "synthetic": True}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", choices=list("abc"), required=True)
    seed(parser.parse_args().node)
