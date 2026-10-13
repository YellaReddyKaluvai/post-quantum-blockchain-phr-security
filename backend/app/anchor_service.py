"""
Document integrity anchoring (blockchain audit trail).

Records a tamper-evident audit entry for a medical document: who did what, to
which document, when, and the SHA-256 digest of the document at that moment.
Never the document itself, and never key material — that is the whole point of
anchoring rather than storing.

How it writes
-------------
Anchors are submitted on-chain to ``contracts/PHR.sol`` via ``chain_client``,
and the resulting transaction hash and block number are stored alongside the
row in ``DocumentAnchors``.

If no chain is reachable the anchor still gets written, but with a
deterministic locally-derived hash and ``anchored_on='local-simulated'``. That
distinction is recorded on every row precisely so nothing downstream can
mistake a simulated anchor for a real on-chain one.
"""

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

ANCHOR_LOCAL = "local-simulated"


def _submit_to_chain(payload: dict) -> Optional[dict]:
    """Submit an anchor on-chain.

    Returns ``{"tx_hash", "block_number", "network"}`` on success, or None when
    the chain is unavailable so the caller can fall back to a local anchor.
    """
    from app.chain_client import get_chain_client
    from app.config import get_settings

    client = get_chain_client()
    if client is None:
        return None

    try:
        receipt = client.log_data_access(
            actor_public_id=payload.get("actor_public_id") or "SYSTEM",
            action=payload["action"],
            document_hash=payload["document_hash"],
        )
        if receipt["status"] != 1:
            logger.error("Anchor transaction reverted for %s", payload.get("document_id"))
            return None

        tx_hash = receipt["tx_hash"]
        if not tx_hash.startswith("0x"):
            tx_hash = "0x" + tx_hash
        return {
            "tx_hash": tx_hash,
            "block_number": receipt["block_number"],
            "network": get_settings().BLOCKCHAIN_NETWORK_NAME,
        }
    except Exception as exc:
        logger.error("On-chain anchor submission failed: %s", exc)
        return None


def _simulated_tx_hash(payload: dict) -> str:
    """A deterministic stand-in for a transaction hash.

    Derived from the anchor payload so the same event always yields the same
    value and a changed payload yields a different one — which preserves the
    tamper-evidence property locally even without a chain.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "0x" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def anchor_document(
    conn,
    *,
    document_type: str,
    document_id: str,
    document_hash: str,
    action: str,
    patient_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    actor_public_id: Optional[str] = None,
    report_id_public: Optional[str] = None,
) -> dict:
    """Write one integrity anchor. Returns the anchor record.

    Failures are logged and swallowed: an audit-trail problem must not abort
    the clinical action that triggered it, and the report itself already
    carries its own hash and signature.
    """
    payload = {
        "document_type": document_type,
        "document_id": str(document_id),
        "report_id_public": report_id_public,
        "patient_id": str(patient_id) if patient_id else None,
        "actor_public_id": actor_public_id,
        "action": action,
        "document_hash": document_hash,
    }

    receipt = _submit_to_chain(payload)
    if receipt:
        tx_hash = receipt["tx_hash"]
        anchored_on = receipt["network"]
        block_number = receipt["block_number"]
    else:
        tx_hash = _simulated_tx_hash(payload)
        anchored_on = ANCHOR_LOCAL
        block_number = None

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO DocumentAnchors
                    (document_type, document_id, report_id_public, patient_id,
                     actor_id, actor_public_id, action, document_hash, tx_hash,
                     anchored_on, block_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (document_type, document_id, report_id_public, patient_id,
                  actor_id, actor_public_id, action, document_hash, tx_hash,
                  anchored_on, block_number))
            conn.commit()
    except Exception as exc:
        logger.error("Failed to write document anchor for %s: %s", document_id, exc)

    return {
        "tx_hash": tx_hash,
        "anchored_on": anchored_on,
        "document_hash": document_hash,
        "block_number": block_number,
    }


# ─── Late anchoring of what was only anchored locally ────────────────────────
#
# Anchors written while no chain was reachable carry a locally derived hash and
# prove nothing to an outsider. Once a chain is available they can be anchored
# for real — but late, and that must be stated: an anchor written today proves
# the digest existed (as recorded in the database) by today's block, not at the
# row's original time. The on-chain action is prefixed LATE_ANCHOR: so the
# ledger itself says so, and the row keeps its original simulated hash and the
# time it was re-anchored.

_ANCHORED_TABLES = {"LabReport": "LabReports", "MedicalDocument": "MedicalDocuments",
                    "ImagingReport": "ImagingReports"}


def reanchor_local(conn, limit: int = 200) -> dict:
    """Anchor on-chain, now, up to ``limit`` digests that were only anchored locally."""
    from psycopg.rows import dict_row
    from app.chain_client import get_chain_client
    if get_chain_client() is None:
        return {"chain_available": False, "anchored": 0,
                "note": "No chain is reachable; nothing can be anchored on-chain yet."}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT id, document_type, document_id, report_id_public, patient_id,
                              actor_public_id, action, document_hash, tx_hash
                         FROM DocumentAnchors WHERE anchored_on = %s
                        ORDER BY created_at LIMIT %s""", (ANCHOR_LOCAL, limit))
        rows = cur.fetchall()
    anchored = 0
    for row in rows:
        receipt = _submit_to_chain({
            "document_type": row["document_type"], "document_id": str(row["document_id"]),
            "report_id_public": row["report_id_public"],
            "patient_id": str(row["patient_id"]) if row["patient_id"] else None,
            "actor_public_id": row["actor_public_id"],
            "action": f"LATE_ANCHOR:{row['action']}"[:60], "document_hash": row["document_hash"]})
        if not receipt:
            break                                     # the chain went away; the rest wait
        with conn.cursor() as cur:
            cur.execute("""UPDATE DocumentAnchors
                              SET original_tx_hash = tx_hash, tx_hash = %s, anchored_on = %s,
                                  block_number = %s, reanchored_at = CURRENT_TIMESTAMP
                            WHERE id = %s AND anchored_on = %s""",
                        (receipt["tx_hash"], receipt["network"], receipt["block_number"],
                         row["id"], ANCHOR_LOCAL))
            table = _ANCHORED_TABLES.get(row["document_type"])
            if table:
                # The document points at the real transaction from now on.
                cur.execute(f"UPDATE {table} SET blockchain_tx_hash = %s "
                            f"WHERE id = %s AND blockchain_tx_hash = %s",
                            (receipt["tx_hash"], row["document_id"], row["tx_hash"]))
        conn.commit()
        anchored += 1
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT COUNT(*) AS n FROM DocumentAnchors WHERE anchored_on = %s", (ANCHOR_LOCAL,))
        remaining = cur.fetchone()["n"]
    return {"chain_available": True, "anchored": anchored, "remaining_local": remaining,
            "note": ("Anchored late: each proves its digest, as recorded in the database, existed by "
                     "the block it landed in — not at its original time. The chain records them as "
                     "LATE_ANCHOR.")}
