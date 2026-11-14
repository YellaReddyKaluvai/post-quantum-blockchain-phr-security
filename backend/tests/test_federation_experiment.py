"""Regression checks for signed round discovery and honest experiment metrics."""
import json

import pytest
from app import federation, federated_classifier as fl


@pytest.fixture
def participant(monkeypatch):
    monkeypatch.setenv("FEDERATION_HUB_URL", "https://hub.example")
    monkeypatch.setenv("FEDERATION_NODE_NAME", "hospital-a")
    monkeypatch.setenv("FEDERATION_SHARED_SECRET", "test-shared-secret")
    return monkeypatch


def test_network_failure_does_not_train_or_fall_back_to_round_one(participant):
    def fail(*args, **kwargs):
        raise federation.FederationError("offline")
    participant.setattr(federation, "_http", fail)
    participant.setattr(federation, "fit_local_update", lambda *args: pytest.fail("trained while hub offline"))
    with pytest.raises(federation.FederationError, match="offline"):
        federation.submit_local_update(None)


def test_bootstrap_uses_signed_round_not_assumed_one(participant):
    sent = {}
    participant.setattr(federation, "fit_local_update", lambda cur, base: ({"roles": {}}, 8, {}))
    def http(method, url, **kwargs):
        if method == "GET":
            assert url.endswith("/round-state")
            headers = kwargs["headers"]
            body = {"round_number": 0, "parameters": None, "open_round": 4}
            body["signature"] = federation.model_signature("hospital-a", int(headers["X-Federation-Timestamp"]),
                                                          body, "test-shared-secret")
            return 200, json.dumps(body).encode()
        sent.update(json.loads(kwargs["body"]))
        return 200, b'{"accepted":true}'
    participant.setattr(federation, "_http", http)
    federation.submit_local_update(None)
    assert sent["round_number"] == 4


def test_training_uses_latest_hub_weights_even_if_not_adopted(participant):
    base = fl.Classifier(weights=[.1] * len(fl.FEATURES), bias=-1, samples=20, rounds=4, nodes=3)
    participant.setattr(federation, "pull_global_model", lambda cur, **kwargs:
                        {"open_round": 5, "parameters": {"classifier": base.to_parameters()}})
    def fit(cur, init):
        assert init.to_parameters() == base.to_parameters()
        return {"roles": {}}, 8, {}
    participant.setattr(federation, "fit_local_update", fit)
    participant.setattr(federation, "_http", lambda *args, **kwargs: (200, b'{"accepted":true}'))
    assert federation.submit_local_update(None)["round_number"] == 5


def test_metrics_report_confusion_f1_and_loss():
    result = fl.evaluate(fl.Classifier.zero(), [({}, 0), ({}, 1)])
    assert (result["tp"], result["fp"], result["tn"], result["fn"]) == (1, 1, 0, 0)
    assert result["accuracy"] == .5 and result["f1"] == .667
    assert result["log_loss"] == pytest.approx(.693147)


def test_validation_never_becomes_training_data(monkeypatch):
    class Cursor:
        def execute(self, sql):
            assert "FederatedValidationLabels" in sql or "candidates" in sql
        def fetchall(self):
            return [{"features": {"records_accessed": 500}, "label": 1}]
        def fetchone(self):
            return None
    train_data = [({}, 0)] * 3 + [({"records_accessed": 100}, 1)] * 3
    monkeypatch.setattr(federation, "load_labels", lambda cur: train_data)
    real_train = fl.train
    def train(examples):
        assert examples is train_data
        return real_train(examples)
    monkeypatch.setattr(fl, "train", train)
    from app import risk_engine
    monkeypatch.setattr(risk_engine, "usable_federated_model", lambda cur: (None, None))
    monkeypatch.setattr(risk_engine, "_choose_classifier", lambda *args: (None, None))
    result = federation.validation_metrics(Cursor())
    assert result["examples"] == 1 and result["training_examples"] == 6
