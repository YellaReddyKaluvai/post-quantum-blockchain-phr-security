"""Smart-contract consent verification (spec §7).

``PHR.sol`` has always had ``updateConsent`` and ``checkConsent``; nothing called
them, so consent lived in one Postgres row that anyone with database access
could flip. This module makes the contract the second witness:

    patient approves / withdraws ──► Consent row  +  updateConsent() on-chain
    doctor reads on the basis of consent ──► row says Authorized?
                                             └─► checkConsent() must agree

If the row and the contract disagree in the dangerous direction — the patient
withdrew on-chain but the database no longer says so, or the row says
Authorized where the contract says withdrawn — the row was changed outside the
application: access is refused and an incident opened. That is the property a
database alone cannot give: an administrator with SQL access can rewrite or
delete a row, but not a mined transaction.

The contract keeps three states (never decided / granted / withdrawn), so the
chain itself says whether it holds a record. Asking the database whether there
is an on-chain record to check would let the same SQL edit skip the check.

What goes on-chain: two pseudonymous references and a boolean. The references
are HMAC-SHA256 over the internal user id with CONSENT_LEDGER_KEY, so the
public ledger cannot be joined back to a person without that key. It is a key
of its own, not the session key, so rotating sessions never breaks verification.

Honest limits
-------------
* Without a reachable chain the database decides alone, and every result says
  ``unverified`` rather than pretending to a check that did not happen.
* Consent recorded before this module existed has no on-chain entry and is
  likewise ``unverified`` until the patient's next decision writes one.
* A contract deployed before ``consentStatus`` existed cannot answer; every
  result is then ``unverified`` until it is redeployed.
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

# What the contract holds for a (patient, doctor) pair.
GRANTED = "granted"
REVOKED = "revoked"
NONE = "none"

# A chain read per chart open would put an RPC round-trip in front of every
# clinical read; a short cache keeps the check without the latency. A changed
# consent always rewrites the entry, so the cache never outlives a decision.
_CACHE_SECONDS = 30
_cache: dict[tuple[str, str], tuple[str, float]] = {}
_cache_lock = threading.Lock()


def party_ref(user_id: str) -> str:
    """Pseudonymous on-chain reference for one party to a consent."""
    secret = get_settings().CONSENT_LEDGER_KEY.encode("utf-8")
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
        _cache[(str(patient_id), str(doctor_id))] = (GRANTED if authorized else REVOKED,
                                                     time.monotonic())
    return {"recorded_on": "ethereum", "tx_hash": receipt["tx_hash"]}


def chain_state(patient_id: str, doctor_id: str) -> Optional[str]:
    """What the contract holds for this pair — granted, revoked or none — or
    None when the chain cannot be asked (disabled, unreachable, old contract)."""
    key = (str(patient_id), str(doctor_id))
    with _cache_lock:
        cached = _cache.get(key)
    if cached and time.monotonic() - cached[1] < _CACHE_SECONDS:
        return cached[0]
    client = _client()
    if client is None:
        return None
    try:
        state = client.consent_status(party_ref(patient_id), party_ref(doctor_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("On-chain consent read failed: %s", exc)
        return None
    with _cache_lock:
        _cache[key] = (state, time.monotonic())
    return state


def verify(cur, *, patient_id: str, doctor_id: str, db_authorized: bool) -> str:
    """Does the contract agree with the database about this consent?

    Returns ``verified``, ``mismatch`` or ``unverified`` (no chain, or no
    on-chain decision for this pair yet). ``cur`` is accepted for callers that
    hold one; the answer deliberately does not depend on the database.
    """
    state = chain_state(patient_id, doctor_id)
    if state in (None, NONE):
        return UNVERIFIED
    return VERIFIED if (state == GRANTED) == bool(db_authorized) else MISMATCH


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
