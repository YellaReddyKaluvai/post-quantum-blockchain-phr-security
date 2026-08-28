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
