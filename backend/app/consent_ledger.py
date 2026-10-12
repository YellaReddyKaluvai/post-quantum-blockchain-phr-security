"""Smart-contract consent verification (spec §7).

``PHR.sol`` has always had ``updateConsent`` and ``checkConsent``; nothing called
them, so consent lived in one Postgres row that anyone with database access
could flip. This module makes the contract the second witness:

    patient approves / withdraws ──► Consent row  +  updateConsent() on-chain
    doctor reads on the basis of consent ──► row says Authorized?
                                             └─► checkConsent() must agree

If the row says Authorized and the contract says otherwise, the row was changed
outside the application — access is refused and an incident opened. That is
the property a database alone cannot give: an administrator with SQL access can
rewrite a row, but not a mined transaction.

What goes on-chain: two pseudonymous references and a boolean. The references
are HMAC-SHA256 over the internal user id with the server's secret, so the
public ledger cannot be joined back to a person without that secret.

Honest limits
-------------
* Without a reachable chain the database decides alone, and every result says
  ``unverified`` rather than pretending to a check that did not happen.
* Consent recorded before this module existed has no on-chain entry and is
  likewise ``unverified`` until the patient's next decision writes one.
* The contract trusts its caller (the backend's key); it proves the state was
  not altered after it was written, not who decided it. The patient's own
  session decides, and the audit log records that.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import threading
import time
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

VERIFIED = "verified"
MISMATCH = "mismatch"
UNVERIFIED = "unverified"

# A chain read per chart open would put an RPC round-trip in front of every
# clinical read; a short cache keeps the check without the latency. A changed
# consent always rewrites the entry, so the cache never outlives a decision.
_CACHE_SECONDS = 30
_cache: dict[tuple[str, str], tuple[bool, float]] = {}
_cache_lock = threading.Lock()


def party_ref(user_id: str) -> str:
    """Pseudonymous on-chain reference for one party to a consent."""
    secret = get_settings().SECRET_KEY.encode("utf-8")
    return hmac.new(secret, f"consent-party:{user_id}".encode("utf-8"),
                    hashlib.sha256).hexdigest()[:32]


def _client():
    from app.chain_client import get_chain_client
    return get_chain_client()


def record(cur, *, consent_id: str, patient_id: str, doctor_id: str,
           authorized: bool) -> dict:
    """Write a consent decision on-chain and remember the transaction.

    Never raises: a chain outage must not stop a patient withdrawing consent.
    The database row is authoritative for access either way; this adds the
    tamper-evident copy when it can.
    """
    client = _client()
    if client is None:
        return {"recorded_on": "database-only", "tx_hash": None}
    try:
        receipt = client.update_consent(party_ref(patient_id), party_ref(doctor_id), authorized)
    except Exception as exc:  # noqa: BLE001
        logger.error("On-chain consent write failed for %s: %s", consent_id, exc)
        return {"recorded_on": "database-only", "tx_hash": None, "error": str(exc)}

    cur.execute(
        """UPDATE Consent SET onchain_tx_hash = %s, onchain_authorized = %s,
                              onchain_recorded_at = CURRENT_TIMESTAMP
            WHERE consent_id = %s""",
        (receipt["tx_hash"], bool(authorized), consent_id))
    with _cache_lock:
        _cache[(str(patient_id), str(doctor_id))] = (bool(authorized), time.monotonic())
    return {"recorded_on": "ethereum", "tx_hash": receipt["tx_hash"]}


def verify(cur, *, patient_id: str, doctor_id: str, db_authorized: bool) -> str:
    """Does the contract agree with the database about this consent?

    Returns ``verified``, ``mismatch`` or ``unverified`` (no chain, or no
    on-chain record for this pair yet).
    """
    cur.execute(
        """SELECT onchain_tx_hash FROM Consent
            WHERE patient_id = %s AND subject_user_id = %s AND subject_role = 'Doctor'""",
        (patient_id, doctor_id))
    row = cur.fetchone()
    tx = (row["onchain_tx_hash"] if isinstance(row, dict) else row[0]) if row else None
    if not tx:
        return UNVERIFIED

    key = (str(patient_id), str(doctor_id))
    with _cache_lock:
        cached = _cache.get(key)
    if cached and time.monotonic() - cached[1] < _CACHE_SECONDS:
        onchain: Optional[bool] = cached[0]
    else:
        client = _client()
        if client is None:
            return UNVERIFIED
        try:
            onchain = client.check_consent(party_ref(patient_id), party_ref(doctor_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("On-chain consent read failed: %s", exc)
            return UNVERIFIED
        with _cache_lock:
            _cache[key] = (onchain, time.monotonic())

    return VERIFIED if onchain == bool(db_authorized) else MISMATCH


def emergency(*, doctor_id: str, patient_id: str, resource_hash: str) -> Optional[str]:
    """Record a break-glass override through the contract's own emergency entry point."""
    client = _client()
    if client is None:
        return None
    try:
        return client.declare_emergency(party_ref(doctor_id), party_ref(patient_id),
                                        resource_hash)["tx_hash"]
    except Exception as exc:  # noqa: BLE001
        logger.error("On-chain emergency record failed: %s", exc)
        return None
