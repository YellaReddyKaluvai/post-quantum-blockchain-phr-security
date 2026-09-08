"""The AI security layer: detection, calibration, explanation and federation.

Each test asserts a property the layer would be worthless without. A detector
that flags everyone is as useless as one that flags no one, so both failure
directions are covered.
"""

import pytest

from app.ai_security import (
    ActorWindow, Baseline, fit_baseline, score, narrate, federated_average,
    FEATURE_WEIGHTS, RISK_MEDIUM, RISK_HIGH, TOP_SIGNALS,
)


def _w(actor="a", **features):
    base = {k: 0.0 for k in FEATURE_WEIGHTS}
    base.update(features)
    return ActorWindow(actor_id=actor, actor_public_id=actor, actor_role="Doctor",
                       features=base)


def _typical_group(n=12):
    return [_w(f"d{i}", records_accessed=3, distinct_patients=2,
               off_hours_ratio=0.05, peak_burst=4) for i in range(n)]


# ─── Baseline ────────────────────────────────────────────────────────────────

def test_baseline_scale_is_never_zero():
    """A uniform peer group must not make every deviation infinite."""
    b = fit_baseline(_typical_group())
    assert all(v > 0 for v in b.scales.values())


def test_baseline_resists_a_single_extreme_actor():
    """The reason for MAD over standard deviation.

    One actor 100x the others must not widen the baseline enough to hide
    inside it — that is exactly the actor being looked for.
    """
    group = _typical_group()
    clean = fit_baseline(group)
    group.append(_w("insider", records_accessed=300, distinct_patients=300))
    polluted = fit_baseline(group)
    assert polluted.scales["distinct_patients"] <= clean.scales["distinct_patients"] * 2


# ─── Scoring ─────────────────────────────────────────────────────────────────

def test_ordinary_behaviour_scores_low():
    group = _typical_group()
    b = fit_baseline(group)
    risk, level, _ = score(group[0], b)
    assert level == "LOW" and risk < RISK_MEDIUM


def test_doing_less_than_peers_is_not_suspicious():
    """Scoring is one-sided. A quiet clinician is not a security concern, and
    flagging them would bury the real signals."""
    b = fit_baseline(_typical_group())
    risk, level, contributions = score(_w("quiet", records_accessed=0), b)
    assert level == "LOW" and contributions == []


def test_insider_sweep_scores_high():
    """The calibration regression.

    Originally this scored MEDIUM: normalising across all six features meant an
    actor had to be anomalous on nearly every dimension. A doctor opening 140
    charts at 03:00 with 11 failed sign-ins is a textbook insider pattern and
    must reach HIGH.
    """
    group = _typical_group()
    insider = _w("insider", records_accessed=141, distinct_patients=140,
                 failed_logins=11, off_hours_ratio=0.95, peak_burst=140)
    b = fit_baseline(group + [insider])
    risk, level, contributions = score(insider, b)
    assert level == "HIGH", f"expected HIGH, got {level} at {risk}"
    assert risk >= RISK_HIGH
    assert contributions[0]["feature"] in {"distinct_patients", "records_accessed"}


def test_score_is_bounded():
    b = fit_baseline(_typical_group())
    risk, _, _ = score(_w("x", **{k: 1e9 for k in FEATURE_WEIGHTS}), b)
    assert 0.0 <= risk <= 100.0


def test_only_the_strongest_signals_drive_the_score():
    b = fit_baseline(_typical_group())
    _, _, contributions = score(
        _w("x", records_accessed=200, distinct_patients=200, failed_logins=50,
           off_hours_ratio=1.0, peak_burst=200, emergency_declarations=20), b)
    assert len(contributions) >= TOP_SIGNALS


# ─── Explainable AI ──────────────────────────────────────────────────────────

def test_explanation_names_the_actual_features():
    """"ACCESS BLOCKED" is explicitly insufficient. The output must say why."""
    group = _typical_group()
    insider = _w("insider", distinct_patients=200, records_accessed=200, peak_burst=180)
    b = fit_baseline(group + [insider])
    _, level, contributions = score(insider, b)
    text = narrate(level, contributions)
    assert "distinct patients accessed" in text
    assert "peer median" in text
    for c in contributions:
        assert {"observed", "peer_median", "deviations", "contribution"} <= set(c)


def test_explanation_is_ordered_by_contribution():
    group = _typical_group()
    insider = _w("insider", distinct_patients=200, records_accessed=50, peak_burst=90)
    b = fit_baseline(group + [insider])
    _, _, contributions = score(insider, b)
    values = [c["contribution"] for c in contributions]
    assert values == sorted(values, reverse=True)


def test_normal_behaviour_gets_a_plain_explanation():
    assert "usual pattern" in narrate("LOW", [])


# ─── Federated aggregation ───────────────────────────────────────────────────

def test_fedavg_weights_by_sample_count():
    """A large hospital must count for more than a small one."""
    a = {"medians": {"records_accessed": 10.0}, "scales": {"records_accessed": 2.0}}
    b = {"medians": {"records_accessed": 20.0}, "scales": {"records_accessed": 2.0}}
    out = federated_average([("big", 90, a), ("small", 10, b)])
    assert 10.0 < out["medians"]["records_accessed"] < 12.0


def test_fedavg_reports_participation():
    a = {"medians": {}, "scales": {}}
    out = federated_average([("x", 5, a), ("y", 7, a)])
    assert out["contributing_nodes"] == 2 and out["total_samples"] == 12


def test_fedavg_handles_no_nodes():
    assert federated_average([])["contributing_nodes"] == 0


def test_only_parameters_are_aggregated():
    """The privacy property that makes federating worthwhile.

    Aggregation output must contain model parameters and counts — never an
    identifier, a record, or an event.
    """
    params = {"medians": {"records_accessed": 4.0}, "scales": {"records_accessed": 1.0}}
    out = federated_average([("hospital-a", 10, params)])
    assert set(out) == {"medians", "scales", "contributing_nodes", "total_samples"}


def test_baseline_round_trips_through_parameters():
    """Federation serialises baselines, so the round trip must be lossless."""
    b = fit_baseline(_typical_group())
    again = Baseline.from_parameters(b.to_parameters())
    assert again.medians == b.medians and again.scales == b.scales
