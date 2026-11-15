"""Versioned PQC keys: rotation preserves old documents; explicit revocation withholds them."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from psycopg.rows import dict_row
from app.database import get_db
from app.security import get_current_session
from app.account_security import Credentials, authenticated_user, throttle, audit
from app.crypto_service import (
    generate_mlkem_keypair,
    generate_mldsa_keypair,
    PQCUnavailableError,
)

router = APIRouter(prefix="/api/auth/keys", tags=["PQC key lifecycle"])


def lock_keys(cur):
    # Issuance and rotation must agree which version encrypted/signed the row.
    # One transaction lock is intentionally conservative for this research app.
    cur.execute("SELECT pg_advisory_xact_lock(714290311)")


class RotationRequest(Credentials):
    revoke_previous: bool = False


class RevokeRequest(Credentials):
    version: int = Field(ge=1)


@router.get("")
def history(session=Depends(get_current_session)):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT k.version, k.created_at, k.revoked_at,
            k.version = u.pqc_key_version AS current FROM PqcKeyVersions k
            JOIN Users u ON u.id = k.user_id WHERE k.user_id = %s ORDER BY k.version DESC""",
            (session["user_id"],),
        )
        return cur.fetchall()


@router.post("/rotate")
def rotate(body: RotationRequest, session=Depends(get_current_session)):
    throttle("account-security", session["user_id"])
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        lock_keys(cur)
        user = authenticated_user(cur, session, body)
        try:
            kem_pub, kem_priv = generate_mlkem_keypair()
            dsa_pub, dsa_priv = generate_mldsa_keypair()
        except PQCUnavailableError as exc:
            raise HTTPException(503, str(exc)) from exc
        version = user["pqc_key_version"] + 1
        cur.execute(
            """UPDATE Users SET pqc_key_version = %s, mlkem_public_key = %s,
            mlkem_private_key_encrypted = %s, mldsa_public_key = %s,
            mldsa_private_key_encrypted = %s WHERE id = %s""",
            (version, kem_pub, kem_priv, dsa_pub, dsa_priv, user["id"]),
        )
        if body.revoke_previous:
            cur.execute(
                "UPDATE PqcKeyVersions SET revoked_at = NOW() WHERE user_id = %s AND version = %s",
                (user["id"], user["pqc_key_version"]),
            )
        audit(cur, user["id"], "PQC_KEYS_ROTATED")
        conn.commit()
    return {
        "version": version,
        "message": "New keys are active. Historical keys remain versioned; revoked versions cannot release records.",
    }


@router.post("/revoke")
def revoke(body: RevokeRequest, session=Depends(get_current_session)):
    throttle("account-security", session["user_id"])
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        lock_keys(cur)
        user = authenticated_user(cur, session, body)
        if body.version >= user["pqc_key_version"]:
            raise HTTPException(409, "Rotate the current keys before revoking them.")
        cur.execute(
            "UPDATE PqcKeyVersions SET revoked_at = COALESCE(revoked_at, NOW()) WHERE user_id = %s AND version = %s RETURNING version",
            (user["id"], body.version),
        )
        if not cur.fetchone():
            raise HTTPException(404, "Key version not found.")
        audit(cur, user["id"], "PQC_KEYS_REVOKED")
        conn.commit()
    return {
        "message": "Key version revoked. Records encrypted or signed with it will be withheld."
    }


class MigrateRecordsRequest(Credentials):
    version: int = Field(ge=1)
    limit: int = Field(default=20, ge=1, le=100)


@router.post("/migrate-records")
def migrate_records(body: MigrateRecordsRequest, session=Depends(get_current_session)):
    """Re-encrypt a bounded batch under the current recipient key; keep signed plaintext digests."""
    from app.crypto_service import (
        decapsulate_aes_key,
        encapsulate_aes_key,
        derive_aes_key,
        decrypt_document,
        encrypt_document,
        sha256_hex,
    )
    from app.storage_service import download_file_from_s3, store_encrypted_document
    from app.storage_service import fetch_from_ipfs
    from psycopg import sql

    throttle("account-security", session["user_id"], limit=30)
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        lock_keys(cur)
        user = authenticated_user(cur, session, body)
        if body.version >= user["pqc_key_version"]:
            raise HTTPException(409, "Select a historical recipient key version.")
        cur.execute(
            "SELECT mlkem_private_key_encrypted FROM PqcKeyVersions WHERE user_id=%s AND version=%s AND revoked_at IS NULL",
            (user["id"], body.version),
        )
        old = cur.fetchone()
        if not old:
            raise HTTPException(
                409,
                "Historical key unavailable or revoked; it cannot be used for migration.",
            )
        migrated = 0
        for table, column in (
            ("MedicalDocuments", "encrypted_content"),
            ("LabReports", "encrypted_document"),
            ("ImagingReports", "encrypted_image"),
        ):
            cur.execute(
                sql.SQL(
                    "SELECT * FROM {} WHERE patient_id=%s AND recipient_key_version=%s AND encrypted_aes_key IS NOT NULL ORDER BY id LIMIT %s FOR UPDATE"
                ).format(sql.Identifier(table.lower())),
                (user["id"], body.version, body.limit - migrated),
            )
            rows = cur.fetchall()
            for row in rows:
                ciphertext = row[column]
                try:
                    if not ciphertext and row.get("s3_key"):
                        ciphertext = download_file_from_s3(row["s3_key"]).decode()
                    if not ciphertext and row.get("ipfs_cid"):
                        ciphertext = fetch_from_ipfs(row["ipfs_cid"]).decode()
                    if not ciphertext:
                        raise ValueError("Missing ciphertext")
                    shared = decapsulate_aes_key(
                        row["encrypted_aes_key"], old["mlkem_private_key_encrypted"]
                    )
                    plain = decrypt_document(
                        ciphertext,
                        derive_aes_key(shared),
                        row["encryption_nonce"],
                        row["encryption_tag"],
                    )
                    if sha256_hex(plain) != row["document_hash"]:
                        raise ValueError("Digest mismatch")
                    kem, new_shared = encapsulate_aes_key(user["mlkem_public_key"])
                    encrypted = encrypt_document(plain, derive_aes_key(new_shared))
                    if (
                        decrypt_document(
                            encrypted["ciphertext"],
                            derive_aes_key(new_shared),
                            encrypted["nonce"],
                            encrypted["tag"],
                        )
                        != plain
                    ):
                        raise ValueError("Verification failed")
                    cid, s3 = store_encrypted_document(
                        encrypted["ciphertext"].encode(), f"migrated-{row['id']}"
                    )
                except Exception as exc:
                    raise HTTPException(
                        409,
                        "A record could not be authenticated or migrated; the database batch was rolled back.",
                    ) from exc
                cur.execute(
                    sql.SQL(
                        "UPDATE {} SET {}=%s,encrypted_aes_key=%s,encryption_nonce=%s,encryption_tag=%s,recipient_key_version=%s,ipfs_cid=%s,s3_key=%s WHERE id=%s"
                    ).format(sql.Identifier(table.lower()), sql.Identifier(column)),
                    (
                        encrypted["ciphertext"],
                        kem,
                        encrypted["nonce"],
                        encrypted["tag"],
                        user["pqc_key_version"],
                        cid,
                        s3,
                        row["id"],
                    ),
                )
                migrated += 1
        remaining = 0
        for table in ("medicaldocuments", "labreports", "imagingreports"):
            cur.execute(
                sql.SQL(
                    "SELECT COUNT(*) AS n FROM {} WHERE patient_id=%s AND recipient_key_version=%s AND encrypted_aes_key IS NOT NULL"
                ).format(sql.Identifier(table)),
                (user["id"], body.version),
            )
            remaining += cur.fetchone()["n"]
        audit(cur, user["id"], "PQC_RECORDS_MIGRATED")
        conn.commit()
    return {
        "migrated": migrated,
        "remaining": remaining,
        "message": f"Migrated {migrated} records; {remaining} remain. Signer versions and signed digests are unchanged.",
    }
