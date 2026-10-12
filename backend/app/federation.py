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

Configuration (all three, or federation as a peer is off):

    FEDERATION_HUB_URL         e.g. https://hub.example-hospital.org
    FEDERATION_NODE_NAME       the name the hub registered this hospital under
    FEDERATION_SHARED_SECRET   the secret the hub issued at registration

Requests to the hub are signed with the shared secret and a timestamp, and the
hub refuses a signature more than five minutes old, so a captured request
cannot be replayed later to read the model.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from app import ai_security as aisec

logger = logging.getLogger(__name__)

MAX_CLOCK_SKEW_SECONDS = 300
LOCAL_WINDOW_HOURS = 720          # a month of behaviour per local update


class FederationError(RuntimeError):
    """The hub refused, failed, or could not be reached."""


def settings() -> dict[str, Optional[str]]:
    return {"hub_url": (os.getenv("FEDERATION_HUB_URL") or "").rstrip("/") or None,
            "node_name": os.getenv("FEDERATION_NODE_NAME") or None,
            "secret": os.getenv("FEDERATION_SHARED_SECRET") or None}


def is_configured() -> bool:
    s = settings()
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


# ─── Participant operations ──────────────────────────────────────────────────

def fit_local_update(cur) -> tuple[dict[str, Any], int]:
    """This hospital's per-role model, ready to share. Parameters only."""
    windows = aisec.extract_windows(cur, hours=LOCAL_WINDOW_HOURS)
    if not windows:
        raise FederationError("No local activity to learn from yet.")
    return aisec.role_parameters(aisec.fit_role_baselines(windows)), len(windows)


def pull_global_model() -> dict[str, Any]:
    """Fetch the hub's newest real-institution global model."""
    s = settings()
    if not is_configured():
        raise FederationError("Federation hub is not configured.")
    ts = int(time.time())
    status, payload = _http("GET", f"{s['hub_url']}/api/federated/global-model", headers={
        "X-Federation-Node": s["node_name"],
        "X-Federation-Timestamp": str(ts),
        "X-Federation-Signature": request_signature(s["node_name"], ts, "global-model", s["secret"]),
        "Accept": "application/json",
    })
    model = _json_or_raise(status, payload, "Pulling the global model")
    if not aisec.sane_parameters(model.get("parameters") or {}):
        raise FederationError("The hub's global model failed the plausibility check; not used.")
    return model


def submit_local_update(cur, round_number: Optional[int] = None) -> dict[str, Any]:
    """Fit locally, sign, and submit to the hub. Returns the hub's response."""
    s = settings()
    if not is_configured():
        raise FederationError("Federation hub is not configured.")
    params, samples = fit_local_update(cur)
    if round_number is None:
        # The hub opens round = its latest + 1; ask what that is rather than guess.
        try:
            round_number = int(pull_global_model().get("round_number") or 0) + 1
        except FederationError:
            round_number = 1
    signature = aisec.parameters_signature(s["node_name"], round_number, samples, params,
                                           s["secret"])
    body = json.dumps({"node_name": s["node_name"], "round_number": round_number,
                       "sample_count": samples, "parameters": params,
                       "signature": signature}).encode("utf-8")
    status, payload = _http("POST", f"{s['hub_url']}/api/federated/submit", body=body,
                            headers={"Content-Type": "application/json"})
    result = _json_or_raise(status, payload, "Submitting the local update")
    return {**result, "round_number": round_number, "sample_count": samples,
            "roles": sorted(params["roles"])}


def store_pulled_model(cur, model: dict[str, Any]) -> None:
    """Keep the hub's model so the risk engine can score with it."""
    s = settings()
    cur.execute(
        """INSERT INTO FederatedHubModels (hub_url, hub_round, parameters,
                                           contributing_nodes, total_samples, real_nodes)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (s["hub_url"], int(model.get("round_number") or 0), json.dumps(model["parameters"]),
         int(model.get("contributing_nodes") or 0), int(model.get("total_samples") or 0),
         int(model.get("real_nodes") or 0)))
