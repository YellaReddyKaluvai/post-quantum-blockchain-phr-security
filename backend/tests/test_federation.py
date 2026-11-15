"""Federated peer submissions.

Federation moves model parameters between institutions, so a peer that can post
arbitrary medians can drag the global baseline wherever it likes and silently
blind every participant's detector. These tests are mostly about refusing
submissions, because accepting a bad one is the failure that matters.
"""

import pytest

from app.ai_security import (
    FEATURE_WEIGHTS, parameters_signature, verify_parameters_signature,
    sane_parameters, federated_average,
)


def _params(median=4.0, scale=2.0):
    return {
        "medians": {k: median for k in FEATURE_WEIGHTS},
        "scales": {k: scale for k in FEATURE_WEIGHTS},
        "sample_count": 100,
    }


SECRET = "a" * 64


# ─── Submission authentication ───────────────────────────────────────────────

def test_an_honest_submission_verifies():
    p = _params()
    sig = parameters_signature("peer", 1, 100, p, SECRET)
    assert verify_parameters_signature("peer", 1, 100, p, SECRET, sig) is True


def test_the_signature_covers_the_parameters():
    """Otherwise a peer could sign benign values and send poisoned ones."""
    sig = parameters_signature("peer", 1, 100, _params(), SECRET)
    assert verify_parameters_signature("peer", 1, 100, _params(median=999.0),
                                       SECRET, sig) is False


def test_the_signature_covers_the_sample_count():
    """Sample count is the FedAvg weight. Left unsigned, a peer could claim a
    million samples and dominate the global model on its own."""
    sig = parameters_signature("peer", 1, 100, _params(), SECRET)
    assert verify_parameters_signature("peer", 1, 9_999_999, _params(),
                                       SECRET, sig) is False


def test_the_signature_covers_the_node_name():
    sig = parameters_signature("peer-a", 1, 100, _params(), SECRET)
    assert verify_parameters_signature("peer-b", 1, 100, _params(), SECRET, sig) is False


def test_the_signature_covers_the_round():
    sig = parameters_signature("peer", 1, 100, _params(), SECRET)
    assert verify_parameters_signature("peer", 2, 100, _params(), SECRET, sig) is False


def test_another_peers_secret_does_not_verify():
    sig = parameters_signature("peer", 1, 100, _params(), SECRET)
    assert verify_parameters_signature("peer", 1, 100, _params(), "b" * 64, sig) is False


@pytest.mark.parametrize("sig", ["", None, "0" * 64, "not-a-signature"])
def test_forged_signatures_are_refused(sig):
    assert verify_parameters_signature("peer", 1, 100, _params(), SECRET, sig) is False


def test_key_order_does_not_change_the_signature():
    """Signing canonical JSON, so a reordered payload still verifies. Otherwise
    honest submissions would fail for no reason."""
    a = {"medians": {k: 1.0 for k in FEATURE_WEIGHTS},
         "scales": {k: 1.0 for k in FEATURE_WEIGHTS}}
    b = {"scales": {k: 1.0 for k in reversed(list(FEATURE_WEIGHTS))},
         "medians": {k: 1.0 for k in reversed(list(FEATURE_WEIGHTS))}}
    assert parameters_signature("p", 1, 5, a, SECRET) == parameters_signature("p", 1, 5, b, SECRET)


# ─── Plausibility floor ──────────────────────────────────────────────────────

def test_honest_parameters_are_accepted():
    assert sane_parameters(_params()) is True


@pytest.mark.parametrize("bad", [
    {},
    {"medians": {}, "scales": {}},
    {"medians": None, "scales": None},
    {"medians": "not a dict", "scales": {}},
])
def test_structurally_wrong_parameters_are_refused(bad):
    assert sane_parameters(bad) is False


def test_negative_medians_are_refused():
    """No honest detector reports a negative count of records opened."""
    p = _params(median=-1.0)
    assert sane_parameters(p) is False


def test_a_zero_scale_is_refused():
    """A zero scale divides by zero downstream and would flag every actor."""
    assert sane_parameters(_params(scale=0.0)) is False


def test_absurd_magnitudes_are_refused():
    assert sane_parameters(_params(median=1e9)) is False
    assert sane_parameters(_params(scale=1e9)) is False


def test_a_missing_feature_is_refused():
    p = _params()
    p["medians"].pop(next(iter(FEATURE_WEIGHTS)))
    assert sane_parameters(p) is False


# ─── Aggregation over real peers ─────────────────────────────────────────────

def test_a_real_peer_moves_the_global_model():
    local = _params(median=4.0)
    peer = _params(median=10.0)
    out = federated_average([("local", 100, local), ("peer", 100, peer)])
    feature = next(iter(FEATURE_WEIGHTS))
    assert 6.0 < out["medians"][feature] < 8.0


def test_sample_count_decides_influence():
    """FedAvg weighting: a large institution counts for more than a small one."""
    small = _params(median=100.0)
    large = _params(median=10.0)
    out = federated_average([("small", 1, small), ("large", 999, large)])
    assert out["medians"][next(iter(FEATURE_WEIGHTS))] < 12.0
