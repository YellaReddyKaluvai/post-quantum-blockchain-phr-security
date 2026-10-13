"""AI security layer: local anomaly detection, risk scoring and explanation.

Scope (spec §18): this module reads *behavioural metadata* — who touched what,
when, how often, from where. It never sees clinical content. A detector that
needed to read diagnoses in order to spot misuse would itself be the largest
privacy hole in the system.

Method (spec §19)
-----------------
Unsupervised, robust, and explainable by construction.

For each actor we extract a small feature vector over a time window and compare
it against a baseline of the actor's own peer group (same role). Deviation is
measured with the **median absolute deviation** rather than mean and standard
deviation, because a handful of extreme actors would inflate a standard
deviation enough to hide themselves inside it — the exact case we are looking
for.

The per-feature deviations are the score *and* the explanation: each feature's
contribution is what the XAI layer reports (§22), so the explanation is derived
from the same arithmetic that produced the decision rather than reconstructed
afterwards by a second model.

What this is not
----------------
Not a diagnostic model. It makes no clinical judgement, and its output must
never gate care on its own (§23) — it is a risk signal that sits *after*
authentication, RBAC and consent, never in place of them.
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Feature weights. Deliberately explicit and readable rather than learned:
# a security control whose reasoning cannot be stated is hard to defend to the
# people it accuses, and these are the behaviours an insider-threat programme
# actually cares about.
FEATURE_WEIGHTS: dict[str, float] = {
    "records_accessed": 1.0,
    "distinct_patients": 1.6,   # breadth is the strongest insider-misuse signal
    "off_hours_ratio": 1.3,
    "failed_logins": 1.4,
    "emergency_declarations": 1.8,   # rare by design; frequency is meaningful
    "peak_burst": 1.1,
    "access_denied": 1.5,       # probing for records one is not entitled to
}

FEATURE_LABELS: dict[str, str] = {
    "records_accessed": "records opened",
    "distinct_patients": "distinct patients accessed",
    "off_hours_ratio": "share of activity outside working hours",
    "failed_logins": "failed sign-in attempts",
    "emergency_declarations": "emergency overrides declared",
    "peak_burst": "busiest single hour",
    "access_denied": "refused access attempts",
}

# Thresholds for the decision policy (§23). Configurable in one place so the
# policy is stated rather than scattered through the code.
TOP_SIGNALS = 3          # how many indicators drive the score
RISK_MEDIUM = 40.0
RISK_HIGH = 70.0

RESPONSE_BY_LEVEL = {
    "LOW": "MONITOR",
    "MEDIUM": "VERIFY",
    "HIGH": "ESCALATE",
}


@dataclass
class ActorWindow:
    """One actor's behaviour over one window."""
    actor_id: str
    actor_public_id: Optional[str]
    actor_role: Optional[str]
    features: dict[str, float] = field(default_factory=dict)


@dataclass
class Baseline:
    """Peer-group model parameters: a median and a scale per feature.

    These few numbers *are* the model. That matters for federation (§20):
    averaging them across hospitals shares what normal looks like without any
    institution sending a single record anywhere.
    """
    medians: dict[str, float]
    scales: dict[str, float]
    sample_count: int

    def to_parameters(self) -> dict[str, Any]:
        return {"medians": self.medians, "scales": self.scales,
                "sample_count": self.sample_count}

    @classmethod
    def from_parameters(cls, params: dict[str, Any]) -> "Baseline":
        return cls(medians=params.get("medians", {}),
                   scales=params.get("scales", {}),
                   sample_count=int(params.get("sample_count", 0)))


def _mad(values: list[float], median: float) -> float:
    """Median absolute deviation, scaled to be comparable to a std deviation.

    The 1.4826 factor makes MAD match sigma for normally distributed data, so
    the resulting score reads like a z-score without inheriting the mean's
    sensitivity to the outliers we are hunting.
    """
    if not values:
        return 0.0
    deviations = [abs(v - median) for v in values]
    return statistics.median(deviations) * 1.4826


def fit_baseline(windows: list[ActorWindow]) -> Baseline:
    """Learn what normal looks like for this peer group."""
    medians: dict[str, float] = {}
    scales: dict[str, float] = {}
    for feature in FEATURE_WEIGHTS:
        values = [w.features.get(feature, 0.0) for w in windows]
        if not values:
            medians[feature], scales[feature] = 0.0, 1.0
            continue
        med = statistics.median(values)
        scale = _mad(values, med)
        # A zero scale means the peer group is uniform on this feature. Falling
        # back to 1.0 keeps the arithmetic finite; without it a single unit of
        # deviation would divide by zero and flag everyone.
        medians[feature] = med
        scales[feature] = scale if scale > 1e-6 else 1.0
    return Baseline(medians=medians, scales=scales, sample_count=len(windows))


def score(window: ActorWindow, baseline: Baseline) -> tuple[float, str, list[dict]]:
    """Score one actor against a baseline.

    Returns ``(risk_score, risk_level, explanation)``. The explanation lists
    every feature that pushed the score up, largest contribution first, in
    plain language — this is the Explainable AI output (§22) and it is computed
    from the same deviations that produced the score.
    """
    contributions: list[dict] = []
    total = 0.0

    for feature, weight in FEATURE_WEIGHTS.items():
        observed = float(window.features.get(feature, 0.0))
        median = float(baseline.medians.get(feature, 0.0))
        scale = float(baseline.scales.get(feature, 1.0)) or 1.0

        # One-sided: only unusually *high* activity is suspicious. A doctor who
        # opened fewer records than their peers is not a security concern, and
        # scoring them as one would bury the real signals in noise.
        deviation = max(0.0, (observed - median) / scale)
        capped = min(deviation, 6.0)          # one wild feature must not dominate
        contribution = capped * weight
        total += contribution

        if deviation >= 1.5:
            contributions.append({
                "feature": feature,
                "label": FEATURE_LABELS[feature],
                "observed": round(observed, 2),
                "peer_median": round(median, 2),
                "deviations": round(deviation, 2),
                "contribution": round(contribution, 2),
            })

    # Score from the strongest few signals, not the average across all of them.
    # Normalising over every feature meant an actor had to be anomalous on
    # nearly every dimension to reach HIGH, so a doctor sweeping 140 charts at
    # 03:00 with 11 failed sign-ins scored merely "review". Real misuse is
    # extreme on a subset — breadth plus timing, or failures plus volume — and
    # a security analyst reasons from the worst indicators, not their mean.
    ranked = sorted((c["contribution"] for c in contributions), reverse=True)
    top = ranked[:TOP_SIGNALS]
    top_weights = sorted(FEATURE_WEIGHTS.values(), reverse=True)[:TOP_SIGNALS]
    max_possible = sum(6.0 * w for w in top_weights)
    total = sum(top)
    risk = round(min(100.0, (total / max_possible) * 100.0), 2) if max_possible else 0.0
    level = "HIGH" if risk >= RISK_HIGH else "MEDIUM" if risk >= RISK_MEDIUM else "LOW"
    contributions.sort(key=lambda c: c["contribution"], reverse=True)
    return risk, level, contributions


def narrate(level: str, contributions: list[dict]) -> str:
    """Turn attributions into a sentence a human can act on.

    "ACCESS BLOCKED" tells an administrator nothing and is explicitly called
    out as insufficient in §22. This answers *why*.
    """
    if not contributions:
        return "Behaviour is consistent with this role's usual pattern."
    parts = []
    for c in contributions[:3]:
        parts.append(
            f"{c['label']} was {c['observed']:g} against a peer median of "
            f"{c['peer_median']:g} ({c['deviations']:g}× the usual spread)"
        )
    lead = {"HIGH": "Flagged as high risk", "MEDIUM": "Flagged for review",
            "LOW": "Noted"}[level]
    return lead + " because " + "; ".join(parts) + "."


# ─── Feature extraction from real activity ───────────────────────────────────

FEATURE_SQL = """
WITH window_events AS (
    SELECT actor_id, actor_public_id, actor_role::text AS actor_role,
           event_type, subject_patient_id, occurred_at
      FROM SecurityEvents
     WHERE occurred_at >= %s AND occurred_at < %s
       AND actor_id IS NOT NULL
       AND (%s::uuid IS NULL OR actor_id = %s::uuid)
),
per_actor AS (
    SELECT actor_id,
           MAX(actor_public_id) AS actor_public_id,
           MAX(actor_role)      AS actor_role,
           COUNT(*) FILTER (WHERE event_type = 'RECORD_ACCESS')        AS records_accessed,
           COUNT(DISTINCT subject_patient_id) FILTER
                (WHERE event_type = 'RECORD_ACCESS')                   AS distinct_patients,
           COUNT(*) FILTER (WHERE event_type = 'LOGIN_FAILED')         AS failed_logins,
           COUNT(*) FILTER (WHERE event_type = 'EMERGENCY_ACCESS')     AS emergency_declarations,
           COUNT(*) FILTER (WHERE event_type = 'ACCESS_DENIED')        AS access_denied,
           COUNT(*)                                                    AS total_events,
           COUNT(*) FILTER (
               WHERE EXTRACT(HOUR FROM occurred_at) >= 22
                  OR EXTRACT(HOUR FROM occurred_at) < 6)               AS off_hours_events
      FROM window_events
     GROUP BY actor_id
),
bursts AS (
    SELECT actor_id, MAX(cnt) AS peak_burst FROM (
        SELECT actor_id, date_trunc('hour', occurred_at) AS hr, COUNT(*) AS cnt
          FROM window_events GROUP BY actor_id, hr
    ) hourly GROUP BY actor_id
)
SELECT a.*, COALESCE(b.peak_burst, 0) AS peak_burst
  FROM per_actor a LEFT JOIN bursts b ON b.actor_id = a.actor_id
"""


def extract_windows(cur, hours: int = 24, actor_id: Optional[str] = None,
                    end: Optional[datetime] = None) -> list[ActorWindow]:
    """Build one feature vector per active actor over the last `hours`.

    With ``actor_id`` only that actor's window is built — the inline risk check
    in the access path scores one person per request and must stay cheap.
    """
    # ``end`` lets a window be taken as it stood at a past moment — the label
    # an investigator gives an incident describes behaviour *then*, not now.
    end = end or datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    cur.execute(FEATURE_SQL, (start, end, actor_id, actor_id))
    windows = []
    for r in cur.fetchall():
        total = float(r["total_events"]) or 1.0
        windows.append(ActorWindow(
            actor_id=str(r["actor_id"]),
            actor_public_id=r["actor_public_id"],
            actor_role=r["actor_role"],
            features={
                "records_accessed": float(r["records_accessed"]),
                "distinct_patients": float(r["distinct_patients"]),
                "off_hours_ratio": float(r["off_hours_events"]) / total,
                "failed_logins": float(r["failed_logins"]),
                "emergency_declarations": float(r["emergency_declarations"]),
                "peak_burst": float(r["peak_burst"]),
                "access_denied": float(r["access_denied"]),
            },
        ))
    return windows


def record_security_event(cur, *, actor_id, actor_public_id=None, actor_role=None,
                          event_type: str, subject_patient_id=None,
                          resource=None, ip_address=None, metadata=None) -> None:
    """Emit one behavioural event for the AI layer.

    Called from the healthcare workflow itself (§18) so the detector sees real
    activity. Deliberately cheap and non-throwing: security telemetry must
    never be the reason a clinician cannot open a chart.
    """
    import json
    from app.audit_service import inet_or_none
    try:
        # A savepoint, so a failed insert cannot poison the caller's transaction:
        # Postgres aborts the whole transaction on any error, and swallowing the
        # exception alone would leave every later statement in the request failing.
        with cur.connection.transaction():
            cur.execute(
                """INSERT INTO SecurityEvents (actor_id, actor_public_id, actor_role, event_type,
                                               subject_patient_id, resource, ip_address, metadata)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (actor_id, actor_public_id, actor_role, event_type, subject_patient_id,
                 resource, inet_or_none(ip_address), json.dumps(metadata or {})),
            )
    except Exception as exc:     # noqa: BLE001 - telemetry must not break care
        import logging
        logging.getLogger(__name__).warning("Security event %s not recorded: %s", event_type, exc)


# ─── Federated averaging (spec §20/§21) ──────────────────────────────────────

def federated_average(node_parameters: list[tuple[str, int, dict]]) -> dict[str, Any]:
    """Aggregate local baselines into a global model using FedAvg.

    Each entry is ``(node_name, sample_count, parameters)``. Nodes are weighted
    by how many actors they observed, so a large hospital counts for more than
    a small one — this is the standard FedAvg weighting.

    What crosses the boundary is only the medians and scales computed locally.
    No record, no identifier and no event ever leaves the institution that
    produced it, which is the entire reason to federate rather than pool.
    """
    if not node_parameters:
        return {"medians": {}, "scales": {}, "contributing_nodes": 0, "total_samples": 0}

    total = sum(max(1, n) for _, n, _ in node_parameters)
    medians: dict[str, float] = {}
    scales: dict[str, float] = {}

    for feature in FEATURE_WEIGHTS:
        m_acc = s_acc = 0.0
        for _name, count, params in node_parameters:
            weight = max(1, count) / total
            m_acc += float(params.get("medians", {}).get(feature, 0.0)) * weight
            s_acc += float(params.get("scales", {}).get(feature, 1.0)) * weight
        medians[feature] = round(m_acc, 4)
        scales[feature] = round(s_acc if s_acc > 1e-6 else 1.0, 4)

    return {"medians": medians, "scales": scales,
            "contributing_nodes": len(node_parameters), "total_samples": total}


# ─── Per-role models (spec §21) ──────────────────────────────────────────────
#
# Detection compares each actor with their own role, so the federated model has
# to be per role as well. A single all-roles baseline would describe nobody: it
# would average doctors' chart reads with technicians' report filings and then
# flag both groups for being themselves. Version 2 parameters therefore carry
# one baseline per role:
#
#     {"version": 2, "roles": {"Doctor": {medians, scales, sample_count}, …}}
#
# Version 1 (one flat baseline) is still accepted from older peers. It is
# aggregated into its own "ALL" bucket, which is used only for a role that no
# version-2 participant has described.

PARAMETERS_VERSION = 2
ALL_ROLES = "ALL"


def fit_role_baselines(windows: list[ActorWindow]) -> dict[str, Baseline]:
    """One baseline per role, fitted from that role's own actors."""
    by_role: dict[str, list[ActorWindow]] = {}
    for w in windows:
        by_role.setdefault(w.actor_role or "Unknown", []).append(w)
    return {role: fit_baseline(group) for role, group in by_role.items()}


def role_parameters(baselines: dict[str, Baseline],
                    classifier: Optional[dict] = None) -> dict[str, Any]:
    """Version-2 parameters: what this institution shares, and all it shares.

    ``classifier`` (federated_classifier) adds the trained threat model's
    weights when this hospital has enough investigated incidents to train one.
    """
    params: dict[str, Any] = {"version": PARAMETERS_VERSION,
                              "roles": {role: b.to_parameters() for role, b in baselines.items()}}
    if classifier:
        params["classifier"] = classifier
    return params


def as_role_parameters(parameters: dict[str, Any]) -> dict[str, dict]:
    """Read either version as ``{role: flat_parameters}``."""
    if isinstance(parameters, dict) and isinstance(parameters.get("roles"), dict):
        return parameters["roles"]
    return {ALL_ROLES: parameters}


def federated_average_roles(node_parameters: list[tuple[str, int, dict]]) -> dict[str, Any]:
    """FedAvg run separately for every role any participant described.

    Within a role each node is weighted by the number of actors it observed *in
    that role*, so a hospital with forty doctors and two technicians shapes the
    doctor model far more than the technician model — which is the point.
    """
    per_role: dict[str, list[tuple[str, int, dict]]] = {}
    for name, count, params in node_parameters:
        for role, flat in as_role_parameters(params).items():
            samples = int(flat.get("sample_count", 0) or count or 0)
            per_role.setdefault(role, []).append((name, samples, flat))

    roles = {}
    for role, nodes in per_role.items():
        agg = federated_average(nodes)
        roles[role] = {"medians": agg["medians"], "scales": agg["scales"],
                       "sample_count": agg["total_samples"],
                       "contributing_nodes": agg["contributing_nodes"]}
    return {"version": PARAMETERS_VERSION, "roles": roles,
            "contributing_nodes": len(node_parameters),
            "total_samples": sum(max(1, c) for _, c, _ in node_parameters)}


def baseline_for_role(parameters: dict[str, Any], role: str) -> Optional[Baseline]:
    """The baseline a global model holds for ``role``, falling back to ALL."""
    roles = as_role_parameters(parameters)
    flat = roles.get(role) or roles.get(ALL_ROLES)
    if not flat or not flat.get("medians"):
        return None
    return Baseline.from_parameters(flat)


# ─── Peer submission integrity (spec §21) ────────────────────────────────────

def parameters_signature(node_name: str, round_number: int, sample_count: int,
                         parameters: dict, shared_secret: str) -> str:
    """HMAC over a peer's submission.

    Federation moves model parameters between institutions, so a peer that can
    submit arbitrary medians can drag the global baseline wherever it likes and
    silently blind every hospital's detector. Authenticating the submission is
    therefore not optional book-keeping — it is the control that stops one
    compromised node degrading everyone else's security.

    Signing a canonical JSON form rather than the raw request body means the
    signature survives key reordering and whitespace, which would otherwise
    make valid submissions fail for no reason.
    """
    import hmac
    import json as _json
    canonical = _json.dumps(
        {"node": node_name, "round": round_number,
         "samples": sample_count, "parameters": parameters},
        sort_keys=True, separators=(",", ":"),
    )
    return hmac.new(shared_secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def verify_parameters_signature(node_name: str, round_number: int, sample_count: int,
                                parameters: dict, shared_secret: str,
                                signature: str) -> bool:
    """Constant-time check of a peer's submission signature."""
    import hmac
    expected = parameters_signature(node_name, round_number, sample_count,
                                    parameters, shared_secret)
    return hmac.compare_digest(expected, signature or "")


def sane_parameters(parameters: dict) -> bool:
    """Reject a submission that could not have come from an honest detector.

    A peer sending negative scales or absurd medians would poison the global
    model, so obviously impossible values are refused before aggregation. This
    is a floor, not a defence against a subtle adversary — robust aggregation
    against a determined poisoner is its own research problem, and pretending
    otherwise would be the kind of overclaim this project has been correcting.
    """
    if not isinstance(parameters, dict):
        return False
    if "classifier" in parameters:
        from app.federated_classifier import sane_classifier
        if "roles" not in parameters or not sane_classifier(parameters["classifier"]):
            return False
    if "roles" in parameters:
        roles = parameters.get("roles")
        if not isinstance(roles, dict) or not roles or len(roles) > 20:
            return False
        return all(isinstance(role, str) and len(role) <= 40 and sane_parameters(flat)
                   and "roles" not in flat
                   for role, flat in roles.items())
    medians = parameters.get("medians")
    scales = parameters.get("scales")
    if not isinstance(medians, dict) or not isinstance(scales, dict):
        return False
    for feature in FEATURE_WEIGHTS:
        m, s = medians.get(feature), scales.get(feature)
        if not isinstance(m, (int, float)) or not isinstance(s, (int, float)):
            return False
        if m < 0 or s <= 0:
            return False
        if m > 1e6 or s > 1e6:
            return False
    return True
