"""The trained half of the federated IDS (spec §20–21): a threat classifier.

The per-role baselines in ai_security describe what *normal* looks like and
flag departures from it. They learn nothing from outcomes: a pattern an
investigator has already confirmed as an insider sweep scores the same as one
already dismissed as a busy night shift. This module adds the missing piece —
a model trained on investigated incidents — and makes its training federated:

    Hospital A ── closed incidents with a verdict ──► local labels
                  local training (from the current global weights)
                  clip the update · optional Gaussian noise (DP) ──► hub
    Hospital B ── … ──► hub          Hospital C ── … ──► hub
                                     FedAvg, with each node's weight capped and
                                     outlying updates set aside
                  ◄── global classifier ── evaluated on local labels before
                                           it is adopted (see federation.py)

The model is logistic regression over the same seven behavioural features the
anomaly detector uses, log-scaled. That is a deliberate choice, not a
placeholder: it trains from tens of labelled examples, its update is a handful
of numbers that FedAvg averages exactly, and every prediction decomposes into
per-feature contributions — so Explainable AI (§22) works for it the same way
it works for the anomaly score.

What leaves a hospital: eight numbers (seven weights and a bias) and a sample
count. Never a feature vector, a label, an identifier or an event.

Differential privacy, stated precisely: with FEDERATION_DP_EPSILON set, each
round's update is clipped to L2 norm ``clip`` and Gaussian noise with
σ = clip·√(2 ln(1.25/δ))/ε is added — the Gaussian mechanism, (ε, δ)-DP per
round *with respect to the update vector*. Repeated rounds compose; no
privacy accounting across rounds is claimed.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Any, Optional

from app.ai_security import FEATURE_LABELS, FEATURE_WEIGHTS

FEATURES: tuple[str, ...] = tuple(FEATURE_WEIGHTS)

MIN_TRAINING_LABELS = 6          # and at least two of each class
MIN_PER_CLASS = 2
DEFAULT_CLIP = 5.0               # L2 bound on one round's update
SAMPLE_CAP_RATIO = 5.0           # no node counts for more than 5× the (lower) median node
OUTLIER_FACTOR = 3.0             # an update this many median distances away is set aside
_rng = random.SystemRandom()


@dataclass
class Classifier:
    weights: list[float]
    bias: float
    samples: int = 0             # labelled examples behind it
    rounds: int = 0              # federated rounds it has been through
    nodes: int = 1               # institutions whose training it combines

    def to_parameters(self) -> dict[str, Any]:
        return {"features": list(FEATURES), "weights": [round(w, 6) for w in self.weights],
                "bias": round(self.bias, 6), "samples": int(self.samples),
                "rounds": int(self.rounds), "nodes": int(self.nodes)}

    @classmethod
    def from_parameters(cls, params: dict[str, Any]) -> "Classifier":
        return cls(weights=[float(w) for w in params["weights"]], bias=float(params["bias"]),
                   samples=int(params.get("samples", 0)), rounds=int(params.get("rounds", 0)),
                   nodes=int(params.get("nodes", 1)))

    @classmethod
    def zero(cls) -> "Classifier":
        return cls(weights=[0.0] * len(FEATURES), bias=0.0)


def sane_classifier(params: Any) -> bool:
    """Reject classifier parameters an honest participant could not have sent."""
    if not isinstance(params, dict):
        return False
    weights, bias, samples = params.get("weights"), params.get("bias"), params.get("samples")
    if params.get("features", list(FEATURES)) != list(FEATURES):
        return False
    if not isinstance(weights, list) or len(weights) != len(FEATURES):
        return False
    values = [*weights, bias]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and abs(v) <= 100 for v in values):
        return False
    return isinstance(samples, int) and 1 <= samples <= 1_000_000


# ─── Features and prediction ─────────────────────────────────────────────────

def vectorize(features: dict[str, float]) -> list[float]:
    """log1p of each behavioural feature: counts span orders of magnitude."""
    return [math.log1p(max(0.0, float(features.get(f, 0.0)))) for f in FEATURES]


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def predict(clf: Classifier, features: dict[str, float]) -> float:
    """Probability that this behaviour matches a confirmed threat."""
    x = vectorize(features)
    return _sigmoid(clf.bias + sum(w * v for w, v in zip(clf.weights, x)))


def explain(clf: Classifier, features: dict[str, float], top: int = 3) -> list[dict]:
    """Per-feature contributions to the log-odds — the XAI view of a prediction."""
    x = vectorize(features)
    items = [{"feature": f, "label": FEATURE_LABELS.get(f, f),
              "observed": round(float(features.get(f, 0.0)), 3),
              "weight": round(w, 3), "contribution": round(w * v, 3),
              "source": "FEDERATED_CLASSIFIER"}
             for f, w, v in zip(FEATURES, clf.weights, x)]
    items.sort(key=lambda i: i["contribution"], reverse=True)
    return [i for i in items if i["contribution"] > 0][:top]


# ─── Local training ──────────────────────────────────────────────────────────

def trainable(examples: list[tuple[dict, int]]) -> bool:
    positives = sum(1 for _, y in examples if y == 1)
    negatives = len(examples) - positives
    return (len(examples) >= MIN_TRAINING_LABELS
            and positives >= MIN_PER_CLASS and negatives >= MIN_PER_CLASS)


def train(examples: list[tuple[dict, int]], init: Optional[Classifier] = None, *,
          epochs: int = 200, lr: float = 0.3, l2: float = 0.01) -> Classifier:
    """Full-batch gradient descent on class-balanced logistic loss.

    Starting from ``init`` (the current global model) is what makes repeated
    rounds FedAvg rather than independent fits: each round refines the shared
    weights on local data. Deterministic for a given input.
    """
    if not examples:
        raise ValueError("no labelled examples")
    xs = [vectorize(f) for f, _ in examples]
    ys = [1 if y else 0 for _, y in examples]
    pos = sum(ys)
    neg = len(ys) - pos
    # Class weights so a rare confirmed threat is not drowned out.
    cw = {1: len(ys) / (2 * pos) if pos else 0.0, 0: len(ys) / (2 * neg) if neg else 0.0}
    base = init or Classifier.zero()
    w, b = list(base.weights), base.bias
    n = len(xs)
    for _ in range(epochs):
        gw = [0.0] * len(w)
        gb = 0.0
        for x, y in zip(xs, ys):
            err = (_sigmoid(b + sum(wi * xi for wi, xi in zip(w, x))) - y) * cw[y]
            for i, xi in enumerate(x):
                gw[i] += err * xi
            gb += err
        w = [wi - lr * (g / n + l2 * wi) for wi, g in zip(w, gw)]
        b -= lr * gb / n
    return Classifier(weights=w, bias=b, samples=n, rounds=base.rounds, nodes=1)


def evaluate(clf: Classifier, examples: list[tuple[dict, int]]) -> dict[str, Any]:
    """Accuracy, precision and recall at p ≥ 0.5 on labelled examples."""
    tp = fp = tn = fn = 0
    for features, y in examples:
        hit = predict(clf, features) >= 0.5
        if hit and y:
            tp += 1
        elif hit:
            fp += 1
        elif y:
            fn += 1
        else:
            tn += 1
    n = tp + fp + tn + fn
    return {"examples": n,
            "accuracy": round((tp + tn) / n, 3) if n else None,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None}


# ─── Leaving the hospital: clipping and differential privacy ─────────────────

def privatize(local: Classifier, base: Optional[Classifier], *, clip: float = DEFAULT_CLIP,
              epsilon: Optional[float] = None, delta: float = 1e-5) -> tuple[Classifier, dict]:
    """Bound one round's update and, if ``epsilon`` is set, add Gaussian noise.

    The update is ``local − base``. Clipping alone bounds how far one hospital
    can move the global model in a round (a robustness control). Noise on top
    is the Gaussian mechanism. Returns the classifier to send and a record of
    what was applied, which is reported alongside the submission.
    """
    base = base or Classifier.zero()
    update = [lw - bw for lw, bw in zip(local.weights, base.weights)] + [local.bias - base.bias]
    norm = math.sqrt(sum(u * u for u in update))
    scale = min(1.0, clip / norm) if norm > 0 else 1.0
    update = [u * scale for u in update]
    sigma = None
    if epsilon:
        sigma = clip * math.sqrt(2 * math.log(1.25 / delta)) / epsilon
        update = [u + _rng.gauss(0.0, sigma) for u in update]
    sent = Classifier(weights=[bw + u for bw, u in zip(base.weights, update[:-1])],
                      bias=base.bias + update[-1], samples=local.samples,
                      rounds=base.rounds, nodes=1)
    return sent, {"update_norm": round(norm, 4), "clipped": scale < 1.0, "clip": clip,
                  "dp": bool(epsilon), "epsilon": epsilon, "delta": delta if epsilon else None,
                  "noise_sigma": round(sigma, 4) if sigma else None}


# ─── Privacy accounting across rounds ────────────────────────────────────────
#
# One noised release is the Gaussian mechanism with L2 sensitivity ``clip`` and
# noise ``sigma``, which satisfies ρ-zero-concentrated DP with ρ = clip²/(2σ²)
# (Bun & Steinke 2016, Prop. 1.6). zCDP composes by adding ρ, and ρ-zCDP implies
# (ρ + 2·√(ρ·ln(1/δ)), δ)-DP (Prop. 1.3). That is the whole accountant: sum the
# ρ of every release this hospital has made, convert once. The unit protected
# is this hospital's set of labelled incidents within one release.

def release_rho(clip: float, sigma: float) -> float:
    return clip * clip / (2.0 * sigma * sigma)


def epsilon_from_rho(rho: float, delta: float) -> float:
    if rho <= 0:
        return 0.0
    return rho + 2.0 * math.sqrt(rho * math.log(1.0 / delta))


# ─── At the hub: robust FedAvg ───────────────────────────────────────────────

def _vector(clf: Classifier) -> list[float]:
    return [*clf.weights, clf.bias]


def aggregate(nodes: list[tuple[str, Classifier]], previous_rounds: int = 0) -> tuple[Optional[Classifier], dict]:
    """FedAvg over the participants' classifiers, defended against one bad node.

    * Each node is weighted by its labelled examples, but no node may count for
      more than SAMPLE_CAP_RATIO × the lower median node — a participant cannot buy
      the global model by inflating its sample count. The lower median, because
      with two nodes the ordinary median is their mean, which the liar sets.
    * With three or more nodes, an update further than OUTLIER_FACTOR × the
      median distance from the coordinate-wise median is set aside for that
      round and reported.

    These are standard, limited defences; they bound the damage a single
    participant can do in a round rather than prove robustness against a
    coordinated attack.
    """
    report: dict[str, Any] = {"excluded": [], "capped": []}
    if not nodes:
        return None, report
    kept = list(nodes)
    if len(kept) >= 3:
        vectors = [_vector(c) for _, c in kept]
        median_vec = [statistics.median(col) for col in zip(*vectors)]
        dists = [math.dist(v, median_vec) for v in vectors]
        typical = statistics.median(dists) or 1e-9
        limit = max(OUTLIER_FACTOR * typical, 0.5)
        report["excluded"] = [name for (name, _), d in zip(kept, dists) if d > limit]
        kept = [(n, c) for (n, c), d in zip(kept, dists) if d <= limit]
    counts = [max(1, c.samples) for _, c in kept]
    cap = SAMPLE_CAP_RATIO * statistics.median_low(counts)
    weights = []
    for (name, _), n in zip(kept, counts):
        if n > cap:
            report["capped"].append(name)
        weights.append(min(n, cap))
    total = sum(weights)
    dim = len(FEATURES) + 1
    avg = [sum(wt * _vector(c)[i] for wt, (_, c) in zip(weights, kept)) / total for i in range(dim)]
    return Classifier(weights=avg[:-1], bias=avg[-1], samples=sum(c.samples for _, c in kept),
                      rounds=previous_rounds + 1, nodes=len(kept)), report
