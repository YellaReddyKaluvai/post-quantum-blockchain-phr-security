"""Federated learning (spec §20–21): the trained threat classifier, its
privacy and robustness controls, adoption of a global model, and its place in
detection. The live three-hospital run is tests/test_federation_live.py.
"""

import math
import random

import pytest

from app import ai_security as aisec
from app import federated_classifier as fl
from app import federation, risk_engine


def _behaviour(rng: random.Random, threat: bool) -> dict:
    if threat:   # a sweep: many patients, out of hours, probing refused records
        return {"records_accessed": rng.randint(60, 300), "distinct_patients": rng.randint(40, 150),
                "off_hours_ratio": rng.uniform(0.4, 0.9), "failed_logins": rng.randint(0, 6),
                "emergency_declarations": rng.randint(0, 2), "peak_burst": rng.randint(20, 80),
                "access_denied": rng.randint(3, 12)}
    return {"records_accessed": rng.randint(3, 25), "distinct_patients": rng.randint(1, 10),
            "off_hours_ratio": rng.uniform(0.0, 0.25), "failed_logins": rng.randint(0, 1),
            "emergency_declarations": 0, "peak_burst": rng.randint(1, 8),
            "access_denied": rng.randint(0, 1)}


def _examples(seed: int, threats: int, benign: int) -> list[tuple[dict, int]]:
    rng = random.Random(seed)
    data = [(_behaviour(rng, True), 1) for _ in range(threats)]
    data += [(_behaviour(rng, False), 0) for _ in range(benign)]
    rng.shuffle(data)
    return data


# ═══ The classifier itself ══════════════════════════════════════════════════

def test_local_training_learns_to_separate_threats_from_normal_work():
    clf = fl.train(_examples(1, 10, 30))
    held_out = fl.evaluate(clf, _examples(2, 20, 60))
    assert held_out["accuracy"] >= 0.9 and held_out["recall"] >= 0.9


def test_too_few_labels_are_not_trained_on():
    assert not fl.trainable(_examples(3, 1, 10))          # one threat is not a pattern
    assert not fl.trainable(_examples(3, 2, 2))           # four examples are too few
    assert fl.trainable(_examples(3, 2, 4))


def test_a_prediction_explains_itself_by_feature():
    clf = fl.train(_examples(4, 10, 30))
    sweep = _behaviour(random.Random(9), True)
    assert fl.predict(clf, sweep) > 0.8
    why = fl.explain(clf, sweep)
    assert why and all(w["contribution"] > 0 and w["source"] == "FEDERATED_CLASSIFIER" for w in why)
    assert {w["feature"] for w in why} & {"distinct_patients", "access_denied", "records_accessed",
                                          "peak_burst", "off_hours_ratio"}


def test_parameters_round_trip_and_carry_no_training_data():
    clf = fl.train(_examples(5, 6, 6))
    params = clf.to_parameters()
    assert set(params) == {"features", "weights", "bias", "samples", "rounds", "nodes"}
    assert fl.sane_classifier(params)
    again = fl.Classifier.from_parameters(params)
    assert again.weights == pytest.approx(clf.weights, abs=1e-5)


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(weights=p["weights"][:-1]),
    lambda p: p.update(bias=float("nan")),
    lambda p: p.update(weights=[1e9] * len(p["weights"])),
    lambda p: p.update(features=list(reversed(p["features"]))),
    lambda p: p.update(samples=0),
])
def test_implausible_classifier_parameters_are_refused(mutate):
    params = fl.train(_examples(6, 6, 6)).to_parameters()
    mutate(params)
    assert not fl.sane_classifier(params)


def test_a_classifier_rides_only_alongside_baselines():
    clf = fl.train(_examples(7, 6, 6)).to_parameters()
    baselines = {"Doctor": {"medians": {k: 1.0 for k in aisec.FEATURE_WEIGHTS},
                            "scales": {k: 1.0 for k in aisec.FEATURE_WEIGHTS}, "sample_count": 4}}
    assert aisec.sane_parameters({"version": 2, "roles": baselines, "classifier": clf})
    assert not aisec.sane_parameters({"version": 2, "classifier": clf})
    bad = dict(clf, weights=[0.0])
    assert not aisec.sane_parameters({"version": 2, "roles": baselines, "classifier": bad})


# ═══ Federated training across hospitals ════════════════════════════════════

def test_three_hospitals_federate_a_classifier_that_works_on_all_their_data():
    """Each hospital has a handful of investigated incidents. Several FedAvg
    rounds — every hospital starting from the global weights — give one model
    that classifies held-out behaviour from all three hospitals."""
    hospitals = [_examples(10, 2, 10), _examples(11, 3, 6), _examples(12, 2, 8)]
    test_sets = [_examples(20 + i, 15, 45) for i in range(3)]
    global_clf = None
    for _ in range(4):
        updates = [(f"h{i}", fl.train(data, init=global_clf, epochs=60))
                   for i, data in enumerate(hospitals)]
        global_clf, report = fl.aggregate(updates, previous_rounds=global_clf.rounds if global_clf else 0)
        assert report["excluded"] == []
    assert global_clf.rounds == 4 and global_clf.nodes == 3
    assert global_clf.samples == sum(len(h) for h in hospitals)
    for test in test_sets:
        assert fl.evaluate(global_clf, test)["accuracy"] >= 0.9


def test_fedavg_weights_by_examples_but_caps_any_one_node():
    a = fl.Classifier(weights=[1.0] * 7, bias=1.0, samples=10)
    b = fl.Classifier(weights=[3.0] * 7, bias=3.0, samples=30)
    avg, _ = fl.aggregate([("a", a), ("b", b)])
    assert avg.weights[0] == pytest.approx(2.5)            # 10:30 weighting
    liar = fl.Classifier(weights=[9.0] * 7, bias=9.0, samples=1_000_000)
    capped, report = fl.aggregate([("a", a), ("b", b), ("liar", liar)])
    assert "liar" in report["capped"] or "liar" in report["excluded"]
    assert capped.weights[0] < 9.0 * 0.9                   # it cannot buy the model


def test_an_outlying_update_is_set_aside():
    honest = [(f"h{i}", fl.Classifier(weights=[1.0 + i * 0.05] * 7, bias=0.5, samples=10))
              for i in range(3)]
    poisoned = ("evil", fl.Classifier(weights=[-40.0] * 7, bias=-40.0, samples=10))
    avg, report = fl.aggregate(honest + [poisoned])
    assert report["excluded"] == ["evil"] and avg.nodes == 3
    assert all(w > 0.9 for w in avg.weights)


# ═══ What leaves the hospital: clipping and differential privacy ════════════

def test_an_update_is_clipped_to_a_bounded_step():
    base = fl.Classifier.zero()
    big = fl.Classifier(weights=[30.0] * 7, bias=30.0, samples=12)
    sent, info = fl.privatize(big, base, clip=5.0)
    norm = math.sqrt(sum(w * w for w in sent.weights) + sent.bias ** 2)
    assert info["clipped"] and norm == pytest.approx(5.0) and not info["dp"]


def test_without_epsilon_nothing_is_noised():
    clf = fl.Classifier(weights=[0.1] * 7, bias=0.1, samples=8)
    assert fl.privatize(clf, None)[0].weights == pytest.approx(clf.weights)


def test_with_epsilon_gaussian_noise_of_the_stated_scale_is_added():
    clf = fl.Classifier(weights=[0.1] * 7, bias=0.1, samples=8)
    sent, info = fl.privatize(clf, None, clip=1.0, epsilon=1.0, delta=1e-5)
    assert info["dp"] and info["noise_sigma"] == pytest.approx(math.sqrt(2 * math.log(1.25e5)), rel=1e-3)
    assert sent.weights != pytest.approx(clf.weights)


def test_dp_epsilon_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv("FEDERATION_DP_EPSILON", "2.5")
    assert federation.dp_epsilon() == 2.5
    for bad in ("", "0", "-1", "lots"):
        monkeypatch.setenv("FEDERATION_DP_EPSILON", bad)
        assert federation.dp_epsilon() is None


# ═══ Adopting a pulled model: evaluated here first ══════════════════════════

def _window(role="Doctor", **features):
    base = {k: 0.0 for k in aisec.FEATURE_WEIGHTS}
    base.update(features)
    return aisec.ActorWindow(actor_id="a", actor_public_id="DOC-1", actor_role=role, features=base)


@pytest.fixture
def local_hospital(monkeypatch):
    rng = random.Random(30)
    windows = [_window(**_behaviour(rng, False)) for _ in range(12)]
    labels = _examples(31, 6, 12)
    monkeypatch.setattr(aisec, "extract_windows", lambda cur, hours=24, **k: windows)
    monkeypatch.setattr(federation, "load_labels", lambda cur, limit=5000: labels)
    return windows, labels


def _global(windows, classifier=None):
    params = aisec.role_parameters(aisec.fit_role_baselines(windows),
                                   classifier.to_parameters() if classifier else None)
    return params


def test_a_global_model_that_fits_local_data_is_adopted(local_hospital):
    windows, labels = local_hospital
    good = fl.train(_examples(32, 10, 20))
    evaluation = federation.evaluate_global_model(None, _global(windows, good))
    assert evaluation["adopt"] and evaluation["classifier"]["ok"]


def test_a_poisoned_classifier_is_refused_on_local_incidents(local_hospital):
    windows, _ = local_hospital
    good = fl.train(_examples(33, 10, 20))
    inverted = fl.Classifier(weights=[-w for w in good.weights], bias=-good.bias, samples=30)
    evaluation = federation.evaluate_global_model(None, _global(windows, inverted))
    assert not evaluation["adopt"] and "classifier accuracy" in evaluation["reasons"][0]


def test_baselines_that_would_flag_this_hospitals_normal_staff_are_refused(local_hospital):
    windows, _ = local_hospital
    tiny = {"Doctor": {"medians": {k: 0.0 for k in aisec.FEATURE_WEIGHTS},
                       "scales": {k: 0.01 for k in aisec.FEATURE_WEIGHTS}, "sample_count": 50}}
    evaluation = federation.evaluate_global_model(None, {"version": 2, "roles": tiny})
    assert not evaluation["adopt"] and evaluation["baselines"]["high_share_global"] > 0.5


class _Cur:
    def __init__(self):
        self.sql = []

    def execute(self, sql, params=None):
        self.sql.append((" ".join(sql.split()), params))

    def fetchone(self):
        return {"id": "m1"}


def test_a_refused_model_is_kept_for_review_but_not_made_active(local_hospital, monkeypatch):
    monkeypatch.setattr(federation, "evaluate_global_model",
                        lambda cur, p: {"adopt": False, "reasons": ["worse here"]})
    cur = _Cur()
    federation.store_pulled_model(cur, {"round_number": 3, "parameters": {"version": 2, "roles": {}}})
    assert not any("SET active = FALSE" in q for q, _ in cur.sql)    # the current model stays
    insert = next(p for q, p in cur.sql if q.startswith("INSERT INTO FederatedHubModels"))
    assert insert[-2:] == (False, False)                             # adopted, active


# ═══ The classifier in detection ════════════════════════════════════════════

def test_the_classifier_raises_the_level_the_baseline_misses():
    clf = fl.train(_examples(40, 10, 30))
    sweep = _window(**_behaviour(random.Random(41), True))
    lenient = aisec.Baseline(medians={k: 500.0 for k in aisec.FEATURE_WEIGHTS},
                             scales={k: 500.0 for k in aisec.FEATURE_WEIGHTS}, sample_count=10)
    d = risk_engine.assess(sweep, lenient, "LOCAL_ANOMALY", 10, clf, "federated classifier (test)")
    assert d.level == "HIGH" and d.baseline_source == risk_engine.SOURCE_CLASSIFIER
    assert d.threat_probability > 0.7 and "investigators confirmed" in d.narrative
    assert d.contributions[0]["source"] == "FEDERATED_CLASSIFIER"


def test_the_classifier_scores_a_role_too_small_for_a_baseline():
    clf = fl.train(_examples(42, 10, 30))
    d = risk_engine.assess(_window(**_behaviour(random.Random(43), False)), None,
                           "LOCAL_ANOMALY", 1, clf, "local classifier")
    assert d.note is None and d.level == "LOW" and d.threat_probability < 0.5


def test_with_neither_model_nothing_is_scored():
    d = risk_engine.assess(_window(), None, "LOCAL_ANOMALY", 1, None, None)
    assert d.note == "insufficient-baseline" and d.risk == 0.0


# ═══ Participation: environment first, else what an administrator entered ══

def test_participation_entered_by_an_admin_is_used_when_the_environment_is_silent(monkeypatch):
    from app.security import encrypt_data
    for name in ("FEDERATION_HUB_URL", "FEDERATION_NODE_NAME", "FEDERATION_SHARED_SECRET"):
        monkeypatch.delenv(name, raising=False)

    class Cur:
        def execute(self, *a):
            pass

        def fetchone(self):
            return {"hub_url": "https://hub.example/", "node_name": "hospital-c",
                    "shared_secret_encrypted": encrypt_data("s" * 32)}

    monkeypatch.setattr(federation, "_db_settings", None)
    s = federation.settings(Cur())
    assert (s["hub_url"], s["node_name"], s["secret"], s["source"]) == \
        ("https://hub.example", "hospital-c", "s" * 32, "database")
    monkeypatch.setenv("FEDERATION_HUB_URL", "https://env-hub.example")
    monkeypatch.setenv("FEDERATION_NODE_NAME", "from-env")
    monkeypatch.setenv("FEDERATION_SHARED_SECRET", "e" * 32)
    assert federation.settings(Cur())["source"] == "environment"


def test_an_incident_verdict_becomes_a_training_label():
    import inspect
    from app import main
    from app.schemas import IncidentUpdateRequest
    assert "_label_from_incident" in inspect.getsource(main.update_security_incident)
    req = IncidentUpdateRequest(status="Closed", resolution="Confirmed by HR.", verdict="confirmed_threat")
    assert req.verdict == "confirmed_threat"
    with pytest.raises(Exception):
        IncidentUpdateRequest(status="Closed", resolution="x", verdict="probably")
