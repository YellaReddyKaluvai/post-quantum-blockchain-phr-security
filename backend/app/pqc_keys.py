"""Versioned PQC keys: rotation preserves old documents; explicit revocation withholds them."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from psycopg.rows import dict_row
from app.database import get_db
from app.security import get_current_session
from app.account_security import Credentials, authenticated_user, throttle, audit
from app.crypto_service import generate_mlkem_keypair, generate_mldsa_keypair, PQCUnavailableError

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
        cur.execute("""SELECT k.version, k.created_at, k.revoked_at,
            k.version = u.pqc_key_version AS current FROM PqcKeyVersions k
            JOIN Users u ON u.id = k.user_id WHERE k.user_id = %s ORDER BY k.version DESC""", (session["user_id"],))
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
        cur.execute("""UPDATE Users SET pqc_key_version = %s, mlkem_public_key = %s,
            mlkem_private_key_encrypted = %s, mldsa_public_key = %s,
            mldsa_private_key_encrypted = %s WHERE id = %s""",
                    (version, kem_pub, kem_priv, dsa_pub, dsa_priv, user["id"]))
        if body.revoke_previous:
            cur.execute("UPDATE PqcKeyVersions SET revoked_at = NOW() WHERE user_id = %s AND version = %s",
                        (user["id"], user["pqc_key_version"]))
        audit(cur, user["id"], "PQC_KEYS_ROTATED")
        conn.commit()
    return {"version": version, "message": "New keys are active. Historical keys remain versioned; revoked versions cannot release records."}


@router.post("/revoke")
def revoke(body: RevokeRequest, session=Depends(get_current_session)):
    throttle("account-security", session["user_id"])
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        lock_keys(cur)
        user = authenticated_user(cur, session, body)
        if body.version >= user["pqc_key_version"]:
            raise HTTPException(409, "Rotate the current keys before revoking them.")
        cur.execute("UPDATE PqcKeyVersions SET revoked_at = COALESCE(revoked_at, NOW()) WHERE user_id = %s AND version = %s RETURNING version",
                    (user["id"], body.version))
        if not cur.fetchone():
            raise HTTPException(404, "Key version not found.")
        audit(cur, user["id"], "PQC_KEYS_REVOKED")
        conn.commit()
    return {"message": "Key version revoked. Records encrypted or signed with it will be withheld."}
