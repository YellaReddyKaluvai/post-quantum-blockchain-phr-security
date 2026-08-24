"""
Document integrity anchoring (blockchain audit trail).

Records a tamper-evident audit entry for a medical document: who did what, to
which document, when, and the SHA-256 digest of the document at that moment.
Never the document itself, and never key material — that is the whole point of
anchoring rather than storing.

Current state
-------------
Entries are written to the ``DocumentAnchors`` table and the transaction hash
is derived deterministically from the anchor payload. This is a *local
simulation*, not an on-chain write: ``anchored_on`` records which it was, so
nothing downstream can mistake a simulated anchor for a real one.

``contracts/PHR.sol`` already defines the on-chain audit contract. The
integration point is ``_submit_to_chain`` below: give it a Web3 RPC endpoint
and a funded signer, have it call the contract's audit function with the same
payload, and return the real transaction hash. No other code needs to change.
"""

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

ANCHOR_LOCAL = "local-simulated"
ANCHOR_CHAIN = "ethereum"


def _submit_to_chain(payload: dict) -> Optional[str]:
    """Submit an anchor on-chain and return its transaction hash.

    INTEGRATION POINT — currently unimplemented. Wire a Web3 client to
    ``contracts/PHR.sol`` here and return the real tx hash; returning None
    makes the caller fall back to a simulated local anchor.
    """
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

    tx_hash = _submit_to_chain(payload)
    anchored_on = ANCHOR_CHAIN if tx_hash else ANCHOR_LOCAL
    if not tx_hash:
        tx_hash = _simulated_tx_hash(payload)

    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO DocumentAnchors
                    (document_type, document_id, report_id_public, patient_id,
                     actor_id, actor_public_id, action, document_hash, tx_hash, anchored_on)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (document_type, document_id, report_id_public, patient_id,
                  actor_id, actor_public_id, action, document_hash, tx_hash, anchored_on))
            conn.commit()
    except Exception as exc:
        logger.error("Failed to write document anchor for %s: %s", document_id, exc)

    return {"tx_hash": tx_hash, "anchored_on": anchored_on, "document_hash": document_hash}
