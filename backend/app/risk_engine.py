"""Inline AI risk assessment in the access path (spec §8, §23).

Until now the AI layer only ran when an administrator pressed "Analyse", so a
record could be opened by someone already behaving anomalously and nothing in
the access path would notice. This module puts the risk score where the spec
puts it — after authorization and consent, before release:

    authenticated → RBAC → relationship / consent → RISK → release

It is a signal, never a substitute. A low score cannot open a record that
consent closed, and the policy below decides what a high score does. The
default never blocks care outright: HIGH risk asks the user to prove they are
still themselves (re-enter their password) and raises an alert, which stops a
stolen session without stopping a busy clinician.

Policy (environment, read on every decision so it can be changed without code):

    RISK_POLICY_MEDIUM            monitor | verify            default monitor
    RISK_POLICY_HIGH              monitor | verify | block    default verify
    RISK_POLICY_EMERGENCY_HIGH    monitor | verify | block    default monitor
    STEP_UP_MINUTES               how long a re-verification lasts   default 10
    RISK_WINDOW_HOURS             behaviour window scored           default 24
    RISK_MIN_PEERS                peers needed for a fair baseline  default 3

    monitor = allow, record, alert if MEDIUM/HIGH
    verify  = allow only after a recent password re-verification
    block   = refuse, alert and open an incident

Emergency access has its own HIGH policy because refusing a genuine emergency
is a clinical harm; by default it is allowed and the compliance record that
every override gets is marked HIGH instead.

Which baseline: the federated model for the actor's role when one exists that a
*real* peer institution contributed to (or one pulled from a federation hub);
otherwise this hospital's own. A model built only from simulated peers is
never used to judge a real person.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app import ai_security as aisec

logger = logging.getLogger(__name__)

ACTIONS = ("allow", "monitor", "verify", "block")
SOURCE_LOCAL = "LOCAL_ANOMALY"
SOURCE_FEDERATED = "FEDERATED_IDS"


# ─── Policy ──────────────────────────────────────────────────────────────────

def _env_choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = (os.getenv(name) or default).strip().lower()
    if value not in allowed:
        logger.error("%s=%r is not one of %s; using %r", name, value, allowed, default)
        return default
    return value


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def policy() -> dict[str, Any]:
    """The decision policy in force, as configured."""
    return {
        "LOW": "allow",
        "MEDIUM": _env_choice("RISK_POLICY_MEDIUM", "monitor", ("monitor", "verify")),
        "HIGH": _env_choice("RISK_POLICY_HIGH", "verify", ("monitor", "verify", "block")),
        "EMERGENCY_HIGH": _env_choice("RISK_POLICY_EMERGENCY_HIGH", "monitor",
                                      ("monitor", "verify", "block")),
        "step_up_minutes": _env_int("STEP_UP_MINUTES", 10),
        "window_hours": _env_int("RISK_WINDOW_HOURS", 24),
        "min_peers": _env_int("RISK_MIN_PEERS", 3),
        "thresholds": {"MEDIUM": aisec.RISK_MEDIUM, "HIGH": aisec.RISK_HIGH},
    }


def decide(level: str, emergency: bool = False) -> str:
    """Map a risk level to an action under the configured policy."""
    p = policy()
    if level == "HIGH":
        return p["EMERGENCY_HIGH"] if emergency else p["HIGH"]
    if level == "MEDIUM":
        # Emergencies are never held up for a medium score.
        return "monitor" if emergency else p["MEDIUM"]
    return "allow"


@dataclass
class Decision:
    level: str
    risk: float
    action: str
    contributions: list[dict] = field(default_factory=list)
    narrative: str = ""
    baseline_source: str = SOURCE_LOCAL
    baseline_samples: int = 0
    note: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {"risk_level": self.level, "risk_score": self.risk, "action": self.action,
                "explanation": self.contributions, "narrative": self.narrative,
                "baseline": self.baseline_source, "baseline_samples": self.baseline_samples,
                "note": self.note}


# ─── Baselines ───────────────────────────────────────────────────────────────

class _BaselineCache:
    """Per-role baselines, refreshed at most every ``ttl`` seconds.

    Fitting every peer group on every request would turn each chart open into a
    scan of the whole event table; behaviour baselines do not move that fast.
    """

    def __init__(self, ttl: int = 900):
        self.ttl = ttl
        self._lock = threading.Lock()
        self._fitted_at = 0.0
        self._local: dict[str, aisec.Baseline] = {}
        self._federated: Optional[dict] = None
        self._federated_label: Optional[str] = None

    def invalidate(self) -> None:
        with self._lock:
            self._fitted_at = 0.0

    def _refresh(self, cur, window_hours: int) -> None:
        windows = aisec.extract_windows(cur, hours=window_hours)
        self._local = aisec.fit_role_baselines(windows)
        self._federated, self._federated_label = usable_federated_model(cur)
        self._fitted_at = time.monotonic()

    def get(self, cur, role: str, window_hours: int,
            min_peers: int) -> tuple[Optional[aisec.Baseline], str, int]:
        with self._lock:
            if time.monotonic() - self._fitted_at > self.ttl:
                try:
                    self._refresh(cur, window_hours)
                except Exception as exc:  # noqa: BLE001 - a stale baseline beats none
                    logger.error("Risk baseline refresh failed: %s", exc)
            local, federated = self._local, self._federated
        return select_baseline(role, local, federated, min_peers)


def select_baseline(role: str, local: dict[str, aisec.Baseline], federated: Optional[dict],
                    min_peers: int) -> tuple[Optional[aisec.Baseline], str, int]:
    """Choose the baseline a role is judged against.

    The federated (global) model when it describes this role with enough
    samples — it already includes this hospital's own contribution — otherwise
    this hospital's local model, otherwise none. Returns ``(baseline, source,
    samples)``.
    """
    fed = aisec.baseline_for_role(federated, role) if federated else None
    if fed is not None and fed.sample_count >= min_peers:
        return fed, SOURCE_FEDERATED, fed.sample_count
    mine = local.get(role)
    if mine is not None and mine.sample_count >= min_peers:
        return mine, SOURCE_LOCAL, mine.sample_count
    return None, SOURCE_LOCAL, mine.sample_count if mine else 0


_cache = _BaselineCache(ttl=_env_int("RISK_BASELINE_TTL_SECONDS", 900))


def invalidate_baselines() -> None:
    """Drop cached baselines, e.g. after a federated round produced a new model."""
    _cache.invalidate()


def usable_federated_model(cur) -> tuple[Optional[dict], Optional[str]]:
    """The newest global model that real institutions — not simulations — built.

    Either a local round that included at least one real peer, or a model
    pulled from a federation hub. Returns ``(parameters, label)``.
    """
    candidates = []
    try:
        cur.execute(
            """SELECT parameters, created_at, round_number FROM FederatedGlobalModel
                WHERE real_nodes >= 2 ORDER BY round_number DESC LIMIT 1""")
        row = cur.fetchone()
        if row:
            candidates.append((row["created_at"], row["parameters"],
                               f"local round {row['round_number']}"))
        cur.execute(
            """SELECT parameters, pulled_at, hub_round FROM FederatedHubModels
                ORDER BY pulled_at DESC LIMIT 1""")
        row = cur.fetchone()
        if row:
            candidates.append((row["pulled_at"], row["parameters"],
                               f"hub round {row['hub_round']}"))
    except Exception as exc:  # noqa: BLE001 - federation is an enhancement
        logger.warning("Federated model lookup failed: %s", exc)
        return None, None
    if not candidates:
        return None, None
    _, params, label = max(candidates, key=lambda c: c[0])
    return params, label


# ─── Evaluation ──────────────────────────────────────────────────────────────

def evaluate(cur, actor_id: str, role: str, emergency: bool = False) -> Decision:
    """Score one actor now and decide what the policy says to do."""
    p = policy()
    windows = aisec.extract_windows(cur, hours=p["window_hours"], actor_id=actor_id)
    window = windows[0] if windows else aisec.ActorWindow(
        actor_id=actor_id, actor_public_id=None, actor_role=role,
        features={k: 0.0 for k in aisec.FEATURE_WEIGHTS})

    baseline, source, samples = _cache.get(cur, role, p["window_hours"], p["min_peers"])
    if baseline is None:
        # Too few peers in this role to say what normal is. Scoring anyway would
        # flag whoever happens to be busiest; better to say so and allow.
        return Decision(level="LOW", risk=0.0, action="allow", baseline_source=source,
                        baseline_samples=samples,
                        narrative="Not enough peer activity in this role to judge.",
                        note="insufficient-baseline")

    risk, level, contributions = aisec.score(window, baseline)
    return Decision(level=level, risk=risk, action=decide(level, emergency),
                    contributions=contributions,
                    narrative=aisec.narrate(level, contributions),
                    baseline_source=source, baseline_samples=samples)


def step_up_valid(cur, user_id: str) -> bool:
    """Has this user re-entered their password recently enough?"""
    minutes = policy()["step_up_minutes"]
    cur.execute(
        """SELECT 1 FROM StepUpVerifications
            WHERE user_id = %s AND verified_at > NOW() - make_interval(mins => %s)""",
        (user_id, minutes))
    return cur.fetchone() is not None


def record_step_up(cur, user_id: str) -> None:
    cur.execute(
        """INSERT INTO StepUpVerifications (user_id, verified_at)
           VALUES (%s, CURRENT_TIMESTAMP)
           ON CONFLICT (user_id) DO UPDATE SET verified_at = CURRENT_TIMESTAMP""",
        (user_id,))
