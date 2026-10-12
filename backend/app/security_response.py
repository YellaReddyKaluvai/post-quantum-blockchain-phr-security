"""Alert & response (spec §24) and incident / compliance records (§25).

Until now the only way an alert or incident came into being was a periodic
anomaly analysis. A report whose digest no longer matched, a signature that did
not verify, a doctor repeatedly refused entry to records — each was logged and
then forgotten. This module is where every security source reports, so the
admin queue reflects what actually happened rather than only what a model
scored:

    source                      → alert      → incident (compliance record)
    ─────────────────────────────────────────────────────────────────────────
    integrity failure (digest)  → HIGH       → always: the stored record changed
    signature failure (ML-DSA)  → HIGH       → always: authenticity is unprovable
    on-chain consent mismatch   → HIGH       → always: consent state was altered
    repeated refused access     → MEDIUM     → no, unless the risk engine escalates
    emergency (break-glass)     → by risk    → always: every override is reviewed
    anomaly / risk engine       → MEDIUM/HIGH→ HIGH only

Records carry identifiers, resource names and the explanation — never clinical
content. An incident says *that* report LR-… failed its integrity check, not
what the report said.

Every function here writes through the caller's cursor and leaves committing to
the caller, except ``commit_before_refusal``: a request that is about to be
refused raises, and ``get_db`` rolls back on an exception, so the evidence of
the refusal would vanish with it unless committed first.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Sources, as stored on alerts and incidents so an administrator can tell a
# statistical judgement from a cryptographic fact at a glance.
SOURCE_ANOMALY = "LOCAL_ANOMALY"
SOURCE_FEDERATED = "FEDERATED_IDS"
SOURCE_RISK_GATE = "RISK_GATE"
SOURCE_INTEGRITY = "INTEGRITY_CHECK"
SOURCE_SIGNATURE = "SIGNATURE_CHECK"
SOURCE_CONSENT_LEDGER = "CONSENT_LEDGER"
SOURCE_ACCESS_CONTROL = "ACCESS_CONTROL"
SOURCE_EMERGENCY = "EMERGENCY_ACCESS"

# Refused-access threshold: one refusal is a mistyped search, several in an hour
# is someone looking for records they were not given.
DENIAL_ALERT_THRESHOLD = 3
DENIAL_WINDOW_MINUTES = 60


def commit_before_refusal(cur) -> None:
    """Persist alerts/incidents written so far, before the caller raises."""
    try:
        cur.connection.commit()
    except Exception as exc:  # noqa: BLE001 - never mask the refusal itself
        logger.error("Could not commit security records before refusal: %s", exc)


def next_incident_ref(cur) -> str:
    """INC-<year>-<n>, numbered from the highest existing reference this year.

    Counting rows would hand out a duplicate the moment one incident is deleted
    or two are opened concurrently; reading the maximum does not.
    """
    year = datetime.now(timezone.utc).year
    cur.execute(
        """SELECT COALESCE(MAX(CAST(split_part(incident_ref, '-', 3) AS INTEGER)), 0) AS n
             FROM SecurityIncidents WHERE incident_ref LIKE %s""",
        (f"INC-{year}-%",))
    row = cur.fetchone()
    n = (row["n"] if isinstance(row, dict) else row[0]) or 0
    return f"INC-{year}-{n + 1:05d}"


def _recent_open_alert(cur, actor_id: Optional[str], source: str, title_prefix: str,
                       minutes: int) -> Optional[str]:
    """An unacknowledged alert of the same kind for the same actor, if one is recent.

    Raising a fresh alert on every request from an actor already under review
    buries the queue; one open alert per actor and kind is enough to act on.
    """
    cur.execute(
        """SELECT id FROM SecurityAlerts
            WHERE acknowledged_at IS NULL AND source = %s
              AND actor_id IS NOT DISTINCT FROM %s::uuid
              AND title LIKE %s
              AND created_at > NOW() - make_interval(mins => %s)
            ORDER BY created_at DESC LIMIT 1""",
        (source, actor_id, title_prefix + "%", minutes))
    row = cur.fetchone()
    if not row:
        return None
    return str(row["id"] if isinstance(row, dict) else row[0])


def raise_alert_once(cur, *, severity: str, title: str, summary: str, response: str,
                     source: str, actor_id: Optional[str] = None,
                     assessment_id: Optional[str] = None,
                     dedupe_minutes: int = 0) -> tuple[str, bool]:
    """Open one alert. Returns ``(alert_id, created)``; ``created`` is False when an
    open alert of the same kind for the same actor was reused."""
    if dedupe_minutes:
        existing = _recent_open_alert(cur, actor_id, source, title, dedupe_minutes)
        if existing:
            return existing, False
    cur.execute(
        """INSERT INTO SecurityAlerts (assessment_id, actor_id, severity, title, summary,
                                       response, source)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (assessment_id, actor_id, severity, title[:200], summary, response, source))
    row = cur.fetchone()
    return str(row["id"] if isinstance(row, dict) else row[0]), True


def raise_alert(cur, **kwargs) -> str:
    """Open one alert, or return the matching open one when deduplicating."""
    return raise_alert_once(cur, **kwargs)[0]


def open_incident(cur, *, event_type: str, risk_level: str, detection_source: str,
                  explanation: str, response: str, actor_id: Optional[str] = None,
                  affected_resource: Optional[str] = None, alert_id: Optional[str] = None,
                  audit_reference: Optional[str] = None,
                  blockchain_tx_hash: Optional[str] = None) -> str:
    """Open a compliance record and return its reference."""
    ref = next_incident_ref(cur)
    cur.execute(
        """INSERT INTO SecurityIncidents (incident_ref, alert_id, actor_id, event_type,
                                          affected_resource, risk_level, detection_source,
                                          explanation, response, audit_reference,
                                          blockchain_tx_hash)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (ref, alert_id, actor_id, event_type, (affected_resource or "")[:160] or None,
         risk_level, detection_source, explanation, response, audit_reference,
         blockchain_tx_hash))
    logger.warning("Incident %s opened: %s (%s)", ref, event_type, risk_level)
    return ref


def _open_incident_for(cur, event_type: str, resource: str) -> Optional[str]:
    """An incident already open for this event on this resource, if any.

    Each retry of a tampered report must not open a new incident; one open
    record per failure per resource is what an investigator needs.
    """
    cur.execute(
        """SELECT incident_ref FROM SecurityIncidents
            WHERE event_type = %s AND affected_resource = %s AND status <> 'Closed'
            ORDER BY created_at DESC LIMIT 1""",
        (event_type, resource[:160]))
    row = cur.fetchone()
    if not row:
        return None
    return row["incident_ref"] if isinstance(row, dict) else row[0]


def _event(cur, *, actor_id, actor_public_id, actor_role, event_type, patient_id=None,
           resource=None, ip_address=None, metadata=None) -> None:
    from app.ai_security import record_security_event
    record_security_event(cur, actor_id=actor_id, actor_public_id=actor_public_id,
                          actor_role=actor_role, event_type=event_type,
                          subject_patient_id=patient_id, resource=resource,
                          ip_address=ip_address, metadata=metadata)


# ─── Cryptographic failures: always an incident ──────────────────────────────

def integrity_failure(cur, *, resource: str, detail: str, actor_id=None,
                      actor_public_id=None, actor_role=None, patient_id=None) -> str:
    """A stored record no longer matches the digest recorded when it was signed."""
    _event(cur, actor_id=actor_id, actor_public_id=actor_public_id, actor_role=actor_role,
           event_type="INTEGRITY_FAILURE", patient_id=patient_id, resource=resource,
           metadata={"detail": detail})
    existing = _open_incident_for(cur, "INTEGRITY_FAILURE", resource)
    if existing:
        return existing
    alert = raise_alert(
        cur, severity="HIGH", source=SOURCE_INTEGRITY, actor_id=None,
        title=f"Integrity failure — {resource}",
        summary=(f"{resource} failed its integrity check when it was opened: {detail} "
                 "It was not released. The stored record differs from what was signed."),
        response="ESCALATE")
    return open_incident(
        cur, event_type="INTEGRITY_FAILURE", risk_level="HIGH",
        detection_source=SOURCE_INTEGRITY, affected_resource=resource, alert_id=alert,
        explanation=detail, response="Release withheld; investigate the storage layer.",
        actor_id=None)


def signature_failure(cur, *, resource: str, detail: str, actor_id=None,
                      actor_public_id=None, actor_role=None, patient_id=None) -> str:
    """An ML-DSA signature over a stored document does not verify."""
    _event(cur, actor_id=actor_id, actor_public_id=actor_public_id, actor_role=actor_role,
           event_type="SIGNATURE_FAILURE", patient_id=patient_id, resource=resource,
           metadata={"detail": detail})
    existing = _open_incident_for(cur, "SIGNATURE_FAILURE", resource)
    if existing:
        return existing
    alert = raise_alert(
        cur, severity="HIGH", source=SOURCE_SIGNATURE, actor_id=None,
        title=f"Signature verification failed — {resource}",
        summary=(f"The ML-DSA signature on {resource} did not verify: {detail} "
                 "Its authenticity cannot be shown, so it was not released as trusted."),
        response="ESCALATE")
    return open_incident(
        cur, event_type="SIGNATURE_FAILURE", risk_level="HIGH",
        detection_source=SOURCE_SIGNATURE, affected_resource=resource, alert_id=alert,
        explanation=detail, response="Release withheld; re-verify the signer's key.",
        actor_id=None)


def consent_ledger_mismatch(cur, *, patient_id: str, doctor_id: str, detail: str) -> str:
    """The consent state in the database disagrees with the on-chain record."""
    existing = _open_incident_for(cur, "CONSENT_LEDGER_MISMATCH", f"Consent:{patient_id}")
    if existing:
        return existing
    alert = raise_alert(
        cur, severity="HIGH", source=SOURCE_CONSENT_LEDGER, actor_id=doctor_id,
        title="Consent state disagrees with the blockchain",
        summary=detail, response="ESCALATE", dedupe_minutes=60)
    return open_incident(
        cur, event_type="CONSENT_LEDGER_MISMATCH", risk_level="HIGH",
        detection_source=SOURCE_CONSENT_LEDGER, affected_resource=f"Consent:{patient_id}",
        alert_id=alert, explanation=detail, actor_id=doctor_id,
        response="Access refused; the database consent row may have been altered.")


# ─── Behavioural rules ───────────────────────────────────────────────────────

def access_denied(cur, *, actor_id: str, actor_public_id: Optional[str], actor_role: str,
                  resource: str, reason: str, patient_id: Optional[str] = None,
                  ip_address: Optional[str] = None) -> Optional[str]:
    """Record a refused access, and alert when one actor keeps being refused.

    Returns the alert id when the threshold was crossed.
    """
    _event(cur, actor_id=actor_id, actor_public_id=actor_public_id, actor_role=actor_role,
           event_type="ACCESS_DENIED", patient_id=patient_id, resource=resource,
           ip_address=ip_address, metadata={"reason": reason})
    cur.execute(
        """SELECT COUNT(*) AS n FROM SecurityEvents
            WHERE actor_id = %s AND event_type = 'ACCESS_DENIED'
              AND occurred_at > NOW() - make_interval(mins => %s)""",
        (actor_id, DENIAL_WINDOW_MINUTES))
    row = cur.fetchone()
    count = row["n"] if isinstance(row, dict) else row[0]
    if count < DENIAL_ALERT_THRESHOLD:
        return None
    return raise_alert(
        cur, severity="MEDIUM", source=SOURCE_ACCESS_CONTROL, actor_id=actor_id,
        title=f"Repeated refused access — {actor_public_id or 'unknown actor'}",
        summary=(f"{actor_public_id or 'An actor'} was refused access {count} times in the "
                 f"last {DENIAL_WINDOW_MINUTES} minutes (latest: {resource} — {reason}). "
                 "Repeated attempts on records one is not entitled to are an insider-threat "
                 "signal."),
        response="VERIFY", dedupe_minutes=DENIAL_WINDOW_MINUTES)


FAILED_LOGIN_ALERT_THRESHOLD = 5
FAILED_LOGIN_WINDOW_MINUTES = 15


def failed_login(cur, *, user_id: Optional[str], public_user_id: Optional[str],
                 role: Optional[str], ip_address: Optional[str] = None) -> Optional[str]:
    """Record a failed sign-in, and alert on a burst against one account.

    These were written to AuthLogs only, which the detector never reads — so
    the "failed sign-in attempts" feature it scores could only ever be fed by
    a one-off backfill. Every attempt now reaches the AI layer as it happens.
    """
    _event(cur, actor_id=user_id, actor_public_id=public_user_id, actor_role=role,
           event_type="LOGIN_FAILED", resource="login", ip_address=ip_address)
    if not user_id:
        return None
    cur.execute(
        """SELECT COUNT(*) AS n FROM SecurityEvents
            WHERE actor_id = %s AND event_type = 'LOGIN_FAILED'
              AND occurred_at > NOW() - make_interval(mins => %s)""",
        (user_id, FAILED_LOGIN_WINDOW_MINUTES))
    row = cur.fetchone()
    count = row["n"] if isinstance(row, dict) else row[0]
    if count < FAILED_LOGIN_ALERT_THRESHOLD:
        return None
    return raise_alert(
        cur, severity="MEDIUM", source=SOURCE_ACCESS_CONTROL, actor_id=user_id,
        title=f"Repeated failed sign-ins — {public_user_id or 'unknown account'}",
        summary=(f"{count} failed sign-in attempts against {public_user_id or 'an account'} "
                 f"in {FAILED_LOGIN_WINDOW_MINUTES} minutes. Possible password guessing; "
                 "consider contacting the account holder."),
        response="VERIFY", dedupe_minutes=FAILED_LOGIN_WINDOW_MINUTES)


def emergency_compliance_record(cur, *, actor_id: str, actor_public_id: Optional[str],
                                patient_id: str, emergency_id: str, risk_level: str,
                                risk_explanation: str, tx_hash: Optional[str]) -> str:
    """Every break-glass declaration gets a compliance record for review.

    The override is not blocked — in an emergency it must work — so review is
    the control. Opening the record automatically means an override cannot be
    left unexamined because nobody thought to look.
    """
    severity = "HIGH" if risk_level == "HIGH" else "MEDIUM"
    alert = raise_alert(
        cur, severity=severity, source=SOURCE_EMERGENCY, actor_id=actor_id,
        title=f"Emergency access declared — {actor_public_id or 'unknown actor'}",
        summary=("Break-glass access was declared and must be reviewed. "
                 f"Behavioural risk at the time: {risk_level}. {risk_explanation}"),
        response="ESCALATE" if risk_level == "HIGH" else "MONITOR")
    return open_incident(
        cur, event_type="EMERGENCY_ACCESS", risk_level=risk_level,
        detection_source=SOURCE_EMERGENCY, affected_resource=f"Patient:{patient_id}",
        alert_id=alert, actor_id=actor_id, audit_reference=f"EmergencyAccess:{emergency_id}",
        explanation=risk_explanation, blockchain_tx_hash=tx_hash,
        response="Access granted (time-boxed); review the stated reason.")
