"""Federated learning between hospitals — the participant side (spec §20–21).

The hub side already existed: ``/api/federated/submit`` accepted signed
parameters and a round averaged them. What did not exist was everything a
*participating* hospital needs, so the loop could never close:

    Hospital B (this module, as a peer)              Hospital A (the hub)
    ───────────────────────────────────              ─────────────────────
    fit per-role baselines on local activity
    sign them (HMAC, per-peer secret)  ── submit ──► /api/federated/submit
                                                     run_federated_round: FedAvg
                       ◄── pull (signed request) ── /api/federated/global-model
    store as FederatedHubModels
    risk engine scores with the global model   ← "updated local models"

Only per-role medians and scales cross the boundary — no record, event or
identifier. The same instance can be a hub for others and a peer of a hub.

What is shared is two models' parameters: per-role behaviour baselines, and —
once this hospital has investigated enough incidents — the weights of a threat
classifier trained here (federated_classifier), clipped and optionally noised
for differential privacy before they leave. A pulled global model is evaluated
on local data and adopted only if it does not make detection here worse.

Configuration — either all three environment variables, or the same three
entered by an administrator (Admin → AI Security → Federated IDS), stored in
FederationParticipation with the secret encrypted:

    FEDERATION_HUB_URL         e.g. https://hub.example-hospital.org
    FEDERATION_NODE_NAME       the name the hub registered this hospital under
    FEDERATION_SHARED_SECRET   the secret the hub issued at registration

Optional:

    FEDERATION_DP_EPSILON             per-round ε for Gaussian noise on the
                                      classifier update; unset = clipping only
    FEDERATION_SYNC_INTERVAL_MINUTES  pull + train + submit on a schedule; 0 = off

Requests to the hub are signed with the shared secret and a timestamp, and the
hub refuses a signature more than five minutes old, so a captured request
cannot be replayed later to read the model. Submissions carry a signed
timestamp too, and the hub accepts only one newer than the last it took from
that peer. The hub signs the model it returns, bound to the requesting node
and its timestamp, so a model altered or replayed in transit is refused here
before it is even evaluated.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from app import ai_security as aisec
from app import federated_classifier as fl

logger = logging.getLogger(__name__)

MAX_CLOCK_SKEW_SECONDS = 300
LOCAL_WINDOW_HOURS = 720          # a month of behaviour per local update


class FederationError(RuntimeError):
    """The hub refused, failed, or could not be reached."""


_db_settings: Optional[dict[str, Optional[str]]] = None    # last read of FederationParticipation
_last_submission_ts = 0          # the hub accepts only a newer one; two in one second must differ


def refresh_settings(cur) -> None:
    """Re-read the administrator-entered participation, if any."""
    global _db_settings
    from app.security import decrypt_data
    cur.execute("SELECT hub_url, node_name, shared_secret_encrypted FROM FederationParticipation "
                "WHERE id = 1")
    row = cur.fetchone()
    if not row:
        _db_settings = None
        return
    hub, node, secret = ((row["hub_url"], row["node_name"], row["shared_secret_encrypted"])
                         if isinstance(row, dict) else row)
    _db_settings = {"hub_url": hub.rstrip("/"), "node_name": node, "secret": decrypt_data(secret)}


def settings(cur=None) -> dict[str, Optional[str]]:
    """Environment first (it is the operator's override); else what an admin entered.

    Pass ``cur`` to re-read the database copy — every request path that uses
    the federation does, so a change made on one server process reaches all.
    """
    env = {"hub_url": (os.getenv("FEDERATION_HUB_URL") or "").rstrip("/") or None,
           "node_name": os.getenv("FEDERATION_NODE_NAME") or None,
           "secret": os.getenv("FEDERATION_SHARED_SECRET") or None}
    if env["hub_url"] and env["node_name"] and env["secret"]:
        return {**env, "source": "environment"}
    if cur is not None:
        try:
            refresh_settings(cur)
        except Exception as exc:  # noqa: BLE001 - federation is an enhancement
            logger.warning("Could not read federation participation: %s", exc)
    if _db_settings:
        return {**_db_settings, "source": "database"}
    return {**env, "source": None}


def is_configured(cur=None) -> bool:
    s = settings(cur)
    return bool(s["hub_url"] and s["node_name"] and s["secret"])


# ─── Request authentication (both sides) ─────────────────────────────────────

def request_signature(node_name: str, timestamp: int, purpose: str, secret: str) -> str:
    message = f"{node_name}|{timestamp}|{purpose}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_request_signature(node_name: str, timestamp: str, purpose: str,
                             secret: str, signature: str, now: Optional[float] = None) -> bool:
    """Constant-time check, with a freshness window against replay."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs((now if now is not None else time.time()) - ts) > MAX_CLOCK_SKEW_SECONDS:
        return False
    expected = request_signature(node_name, ts, purpose, secret)
    return hmac.compare_digest(expected, signature or "")


def model_signature(node_name: str, timestamp: int, model: dict, secret: str) -> str:
    """The hub's HMAC over the global model it hands one peer for one request."""
    body = {k: v for k, v in model.items() if k != "signature"}
    canonical = json.dumps({"node": node_name, "ts": int(timestamp), "model": body},
                           sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_model_signature(node_name: str, timestamp: int, model: dict, secret: str) -> bool:
    return hmac.compare_digest(model_signature(node_name, timestamp, model, secret),
                               str(model.get("signature") or ""))


def transport_warning(hub_url: Optional[str]) -> Optional[str]:
    """Plain HTTP to a hub that is not on this machine exposes the exchange.

    Every message is HMAC-authenticated either way, so it cannot be altered
    unnoticed; but the parameters themselves would travel unencrypted.
    """
    from urllib.parse import urlparse
    if not hub_url:
        return None
    parsed = urlparse(hub_url)
    if parsed.scheme == "https" or (parsed.hostname or "") in ("localhost", "127.0.0.1", "::1"):
        return None
    return ("The hub is reached over plain HTTP. Messages are signed, so they cannot be altered "
            "unnoticed, but model parameters travel unencrypted; use an https:// hub URL.")


# ─── HTTP ────────────────────────────────────────────────────────────────────

def _http(method: str, url: str, *, body: Optional[bytes] = None,
          headers: Optional[dict] = None, timeout: int = 30) -> tuple[int, bytes]:
    """One HTTP exchange. The single seam the tests replace."""
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001
        raise FederationError(f"{method} {url} failed: {exc}") from exc


def _json_or_raise(status: int, payload: bytes, what: str) -> dict:
    try:
        data = json.loads(payload.decode("utf-8") or "{}")
    except ValueError:
        data = {}
    if not 200 <= status < 300:
        detail = data.get("detail") if isinstance(data, dict) else None
        raise FederationError(f"{what}: hub returned HTTP {status}"
                              + (f" — {detail}" if detail else ""))
    return data


# ─── Local training data ─────────────────────────────────────────────────────

def load_labels(cur, limit: int = 5000) -> list[tuple[dict, int]]:
    """Investigated incidents as training examples: (behaviour window, verdict)."""
    cur.execute("SELECT features, label FROM SecurityLabels ORDER BY created_at DESC LIMIT %s",
                (limit,))
    rows = cur.fetchall() or []
    out = []
    for r in rows:
        features, label = (r["features"], r["label"]) if isinstance(r, dict) else (r[0], r[1])
        if isinstance(features, str):
            features = json.loads(features)
        out.append((features, int(label)))
    return out


def active_global_classifier(cur) -> Optional[fl.Classifier]:
    """The classifier of the global model this hospital has adopted, if any."""
    cur.execute("SELECT parameters FROM FederatedHubModels WHERE active ORDER BY pulled_at DESC LIMIT 1")
    row = cur.fetchone()
    params = (row["parameters"] if isinstance(row, dict) else row[0]) if row else None
    if isinstance(params, str):
        params = json.loads(params)
    if params and fl.sane_classifier(params.get("classifier")):
        return fl.Classifier.from_parameters(params["classifier"])
    return None


def dp_epsilon() -> Optional[float]:
    """FEDERATION_DP_EPSILON: per-round ε for the Gaussian mechanism; unset = clipping only."""
    raw = (os.getenv("FEDERATION_DP_EPSILON") or "").strip()
    try:
        value = float(raw) if raw else None
    except ValueError:
        logger.error("FEDERATION_DP_EPSILON=%r is not a number; differential privacy is off", raw)
        return None
    return value if value and value > 0 else None


ACCOUNTING_DELTA = 1e-5


def dp_total_budget() -> Optional[float]:
    """FEDERATION_DP_TOTAL_EPSILON: the most privacy loss, over all rounds, this
    hospital will spend on releasing classifier updates; unset = no cap."""
    raw = (os.getenv("FEDERATION_DP_TOTAL_EPSILON") or "").strip()
    try:
        value = float(raw) if raw else None
    except ValueError:
        logger.error("FEDERATION_DP_TOTAL_EPSILON=%r is not a number; no budget is enforced", raw)
        return None
    return value if value and value > 0 else None


def privacy_spent(cur) -> dict[str, Any]:
    """What every classifier release so far has cost, composed across rounds (zCDP).

    A release made without noise has no finite cost: it is counted, and while
    any exists no overall guarantee is claimed.
    """
    cur.execute("""SELECT COUNT(*) FILTER (WHERE rho IS NOT NULL) AS noised,
                          COUNT(*) FILTER (WHERE rho IS NULL) AS unnoised,
                          COALESCE(SUM(rho), 0) AS rho
                     FROM FederatedPrivacyLedger""")
    row = cur.fetchone()
    if isinstance(row, dict):
        row = (row["noised"], row["unnoised"], row["rho"])
    noised, unnoised, rho = row or (0, 0, 0)
    noised, unnoised, rho = int(noised or 0), int(unnoised or 0), float(rho or 0)
    budget = dp_total_budget()
    epsilon = fl.epsilon_from_rho(rho, ACCOUNTING_DELTA)
    return {"releases_noised": noised, "releases_without_noise": unnoised, "rho": round(rho, 6),
            "epsilon_total": None if unnoised else round(epsilon, 4), "delta": ACCOUNTING_DELTA,
            "budget_epsilon": budget,
            "budget_remaining": (round(max(0.0, budget - epsilon), 4) if budget and not unnoised else None),
            "accounting": "zCDP composition of the Gaussian mechanism (Bun & Steinke 2016)"}


def _record_release(cur, purpose: str, privacy: dict, labels: int) -> None:
    sigma = privacy.get("noise_sigma")
    rho = fl.release_rho(privacy["clip"], sigma) if sigma else None
    cur.execute("""INSERT INTO FederatedPrivacyLedger (purpose, epsilon, delta, sigma, clip, rho, labels)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (purpose, privacy.get("epsilon"), privacy.get("delta"), sigma, privacy["clip"], rho, labels))


def train_for_submission(cur, base: Optional[fl.Classifier],
                         purpose: str = "submission") -> tuple[Optional[dict], dict]:
    """Train the local classifier from ``base`` and prepare it to leave the hospital.

    Returns ``(classifier_parameters or None, report)``. Without enough
    investigated incidents nothing is trained, and the update carries
    baselines only — a classifier fitted to three examples would teach the
    federation noise.
    """
    examples = load_labels(cur)
    threats = sum(1 for _, y in examples if y)
    report: dict[str, Any] = {"labels": len(examples), "threats": threats,
                              "benign": len(examples) - threats, "trained": False}
    if not fl.trainable(examples):
        report["note"] = (f"Needs {fl.MIN_TRAINING_LABELS} investigated incidents with at least "
                          f"{fl.MIN_PER_CLASS} of each verdict; baselines only this round.")
        return None, report
    epsilon, budget = dp_epsilon(), dp_total_budget()
    if budget is not None:
        spent = privacy_spent(cur)
        if epsilon is None or spent["releases_without_noise"]:
            report["note"] = ("A total privacy budget is set, so the classifier is shared only with "
                              "differential-privacy noise (set FEDERATION_DP_EPSILON); baselines only.")
            return None, report
        sigma = fl.DEFAULT_CLIP * math.sqrt(2 * math.log(1.25 / ACCOUNTING_DELTA)) / epsilon
        after = fl.epsilon_from_rho(spent["rho"] + fl.release_rho(fl.DEFAULT_CLIP, sigma), ACCOUNTING_DELTA)
        if after > budget:
            report["note"] = (f"Privacy budget reached: another release would bring the total to "
                              f"ε={after:.2f} (budget {budget}); baselines only.")
            report["privacy_spent"] = spent
            return None, report
    local = fl.train(examples, init=base)
    sent, privacy = fl.privatize(local, base, clip=fl.DEFAULT_CLIP, epsilon=epsilon,
                                 delta=ACCOUNTING_DELTA)
    # Counted when prepared, even if the submission then fails: over-counting is the safe side.
    _record_release(cur, purpose, privacy, len(examples))
    report.update({"trained": True, "local_fit": fl.evaluate(local, examples),
                   "started_from": "global model" if base else "zero", "privacy": privacy,
                   "privacy_spent": privacy_spent(cur)})
    return sent.to_parameters(), report


# ─── Participant operations ──────────────────────────────────────────────────

def fit_local_update(cur) -> tuple[dict[str, Any], int, dict]:
    """This hospital's update: per-role baselines plus, when it has enough
    investigated incidents, its locally trained classifier. Parameters only."""
    windows = aisec.extract_windows(cur, hours=LOCAL_WINDOW_HOURS)
    if not windows:
        raise FederationError("No local activity to learn from yet.")
    classifier, report = train_for_submission(cur, active_global_classifier(cur))
    params = aisec.role_parameters(aisec.fit_role_baselines(windows), classifier)
    return params, len(windows), report


def pull_global_model(cur=None) -> dict[str, Any]:
    """Fetch the hub's newest real-institution global model."""
    s = settings(cur)
    if not (s["hub_url"] and s["node_name"] and s["secret"]):
        raise FederationError("Federation hub is not configured.")
    ts = int(time.time())
    status, payload = _http("GET", f"{s['hub_url']}/api/federated/global-model", headers={
        "X-Federation-Node": s["node_name"],
        "X-Federation-Timestamp": str(ts),
        "X-Federation-Signature": request_signature(s["node_name"], ts, "global-model", s["secret"]),
        "Accept": "application/json",
    })
    model = _json_or_raise(status, payload, "Pulling the global model")
    if not verify_model_signature(s["node_name"], ts, model, s["secret"]):
        raise FederationError("The global model was not signed by the hub for this request "
                              "(altered or replayed in transit); not used.")
    if not aisec.sane_parameters(model.get("parameters") or {}):
        raise FederationError("The hub's global model failed the plausibility check; not used.")
    return model


def submit_local_update(cur, round_number: Optional[int] = None) -> dict[str, Any]:
    """Fit and train locally, sign, and submit to the hub. Returns the hub's response."""
    s = settings(cur)
    if not (s["hub_url"] and s["node_name"] and s["secret"]):
        raise FederationError("Federation hub is not configured.")
    params, samples, training = fit_local_update(cur)
    if round_number is None:
        # The hub says which round is open; an older hub only its latest + 1.
        try:
            model = pull_global_model(cur)
            round_number = int(model.get("open_round") or 0) or int(model.get("round_number") or 0) + 1
        except FederationError:
            round_number = 1
    global _last_submission_ts
    ts = _last_submission_ts = max(int(time.time()), _last_submission_ts + 1)
    signature = aisec.parameters_signature(s["node_name"], round_number, samples, params,
                                           s["secret"], ts)
    body = json.dumps({"node_name": s["node_name"], "round_number": round_number,
                       "sample_count": samples, "parameters": params, "timestamp": ts,
                       "signature": signature}).encode("utf-8")
    status, payload = _http("POST", f"{s['hub_url']}/api/federated/submit", body=body,
                            headers={"Content-Type": "application/json"})
    result = _json_or_raise(status, payload, "Submitting the local update")
    return {**result, "round_number": round_number, "sample_count": samples,
            "roles": sorted(params["roles"]), "classifier": training}


# ─── Adopting a global model: evaluate it on local data first ────────────────

ADOPT_MAX_HIGH_SHARE = 0.25       # a model flagging more than this share of local actors…
ADOPT_HIGH_SHARE_MARGIN = 0.15    # …and this much more than the local model does, is refused
ADOPT_MIN_ACTORS = 5             # fewer local actors than this cannot show a model is wrong here
ADOPT_MIN_ACCURACY = 0.5
ADOPT_ACCURACY_MARGIN = 0.2


def evaluate_global_model(cur, parameters: dict[str, Any]) -> dict[str, Any]:
    """Would this global model make detection here better or worse?

    Two checks, each on this hospital's own data, neither of which leaves it:

    * baselines — score the last week's local actors with the global model and
      with the local one. A global model that would flag far more of them HIGH
      is describing some other hospital's normal, not this one's.
    * classifier — on locally investigated incidents, the global classifier must
      beat chance and not fall far below a classifier trained here alone.

    A check without local data to run on passes, and says so.
    """
    evaluation: dict[str, Any] = {"adopt": True, "reasons": []}
    windows = aisec.extract_windows(cur, hours=24 * 7)
    local = aisec.fit_role_baselines(windows)
    min_peers = max(1, int(os.getenv("RISK_MIN_PEERS", "3") or 3))
    scored = high_global = high_local = 0
    for w in windows:
        role = w.actor_role or "Unknown"
        gb = aisec.baseline_for_role(parameters, role)
        if gb is None or gb.sample_count < min_peers:
            continue    # detection would not use it either (risk_engine.select_baseline)
        scored += 1
        high_global += aisec.score(w, gb)[1] == "HIGH"
        lb = local.get(role)
        high_local += bool(lb and lb.sample_count >= 3 and aisec.score(w, lb)[1] == "HIGH")
    if scored >= ADOPT_MIN_ACTORS:
        g, l_ = high_global / scored, high_local / scored
        ok = g <= max(ADOPT_MAX_HIGH_SHARE, l_ + ADOPT_HIGH_SHARE_MARGIN)
        evaluation["baselines"] = {"actors_scored": scored, "high_share_global": round(g, 3),
                                   "high_share_local": round(l_, 3), "ok": ok}
        if not ok:
            evaluation["reasons"].append(
                f"would flag {g:.0%} of this hospital's actors HIGH (local model: {l_:.0%})")
    else:
        evaluation["baselines"] = {"actors_scored": scored, "ok": True,
                                   "note": f"fewer than {ADOPT_MIN_ACTORS} comparable local actors "
                                           "this week; not enough to judge the baselines"}

    clf_params = parameters.get("classifier")
    if clf_params:
        examples = load_labels(cur)
        has_both = 0 < sum(y for _, y in examples) < len(examples)
        if len(examples) >= 4 and has_both:
            global_fit = fl.evaluate(fl.Classifier.from_parameters(clf_params), examples)
            local_fit = fl.evaluate(fl.train(examples), examples) if fl.trainable(examples) else None
            ok = (global_fit["accuracy"] >= ADOPT_MIN_ACCURACY and
                  (local_fit is None or
                   global_fit["accuracy"] >= local_fit["accuracy"] - ADOPT_ACCURACY_MARGIN))
            evaluation["classifier"] = {"global": global_fit, "local": local_fit, "ok": ok}
            if not ok:
                evaluation["reasons"].append(
                    f"classifier accuracy on local incidents {global_fit['accuracy']:.0%}"
                    + (f" vs {local_fit['accuracy']:.0%} trained locally" if local_fit else ""))
        else:
            evaluation["classifier"] = {"ok": True,
                                        "note": "too few investigated incidents here to evaluate it"}
    evaluation["adopt"] = not evaluation["reasons"]
    return evaluation


def store_pulled_model(cur, model: dict[str, Any]) -> dict[str, Any]:
    """Keep the hub's model with its evaluation; make it the active one only if it passed."""
    s = settings(cur)
    evaluation = evaluate_global_model(cur, model["parameters"])
    if evaluation["adopt"]:
        cur.execute("UPDATE FederatedHubModels SET active = FALSE WHERE active")
    cur.execute(
        """INSERT INTO FederatedHubModels (hub_url, hub_round, parameters, contributing_nodes,
                                           total_samples, real_nodes, evaluation, adopted, active,
                                           decided_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP) RETURNING id""",
        (s["hub_url"], int(model.get("round_number") or 0), json.dumps(model["parameters"]),
         int(model.get("contributing_nodes") or 0), int(model.get("total_samples") or 0),
         int(model.get("real_nodes") or 0), json.dumps(evaluation),
         evaluation["adopt"], evaluation["adopt"]))
    row = cur.fetchone()
    evaluation["model_id"] = str(row["id"] if isinstance(row, dict) else row[0]) if row else None
    return evaluation


def sync(cur) -> dict[str, Any]:
    """One scheduled exchange: pull (and evaluate) the global model, then submit.

    Pulling first means this round's local training starts from the newest
    global weights — the repeated-rounds part of FedAvg.
    """
    result: dict[str, Any] = {"at": int(time.time())}
    try:
        model = pull_global_model(cur)
        evaluation = store_pulled_model(cur, model)
        result["pulled"] = {"hub_round": model.get("round_number"), "adopted": evaluation["adopt"],
                            "reasons": evaluation["reasons"]}
    except FederationError as exc:
        result["pulled"] = {"error": str(exc)}
    try:
        submitted = submit_local_update(cur)
        result["submitted"] = {"round": submitted["round_number"],
                               "classifier_trained": submitted["classifier"]["trained"]}
    except FederationError as exc:
        result["submitted"] = {"error": str(exc)}
    cur.execute("UPDATE FederationParticipation SET last_sync_at = CURRENT_TIMESTAMP, "
                "last_sync_result = %s WHERE id = 1", (json.dumps(result),))
    return result
