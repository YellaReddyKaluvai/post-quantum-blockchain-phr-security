"""The lab runner consumes actual API envelopes and never rewrites existing keys."""
import importlib.util
from pathlib import Path

import pytest

script = Path(__file__).resolve().parents[2] / "scripts/federation_lab.py"
if not script.exists():
    pytest.skip("Repository-level lab runner is not included in the backend-only image", allow_module_level=True)
spec = importlib.util.spec_from_file_location("federation_lab", script)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def test_prepare_is_private_and_does_not_overwrite_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, "LAB", tmp_path)
    lab.prepare("a", local=True)
    first = (tmp_path / "a/.env").read_text()
    assert "API_PORT=8101" in first and "FEDERATION_MIN_PEERS=2" in first
    with pytest.raises(RuntimeError, match="already exists"):
        lab.prepare("a", local=True)
    assert (tmp_path / "a/.env").read_text() == first


def test_wire_reads_peer_envelope_and_joins_without_printing_secret(monkeypatch, capsys):
    class Node:
        def __init__(self, name):
            self.config = {"name": name}
            self.joined = None
        def call(self, method, path, body=None):
            if path.endswith("/peers") and method == "GET":
                return {"peers": [], "total": 0}
            if path.endswith("/peers"):
                return {"shared_secret": "never-print-this"}
            if method == "GET":
                return {"configured": False}
            self.joined = body
    nodes = [Node(n) for n in ("b", "a", "c")]
    monkeypatch.setattr(lab, "connect", lambda config: nodes)
    lab.wire({"hub": {"url": "https://hub.example"}})
    assert nodes[1].joined["shared_secret"] == "never-print-this"
    assert nodes[2].joined["hub_url"] == "https://hub.example"
    assert "never-print-this" not in capsys.readouterr().out


@pytest.mark.skipif(not __import__('os').getenv('FEDERATION_LAB_CONFIG'),
                    reason='requires three disposable seeded lab servers and FEDERATION_LAB_CONFIG')
def test_three_live_servers_wait_for_both_peers_then_train(tmp_path):
    import json
    import os
    config = json.loads(Path(os.environ['FEDERATION_LAB_CONFIG']).read_text())
    lab.wire(config)
    hub, a, c = lab.connect(config)
    before = hub.call('GET', '/api/admin/security/federated/status')
    assert before['require_fresh_updates'] and before['required_peer_submissions'] == 2
    assert before['pending_peer_submissions'] == 0
    with pytest.raises(RuntimeError, match='HTTP 409'):
        hub.call('POST', '/api/admin/security/federated/round')
    sent = a.call('POST', '/api/admin/federated/hub/submit')
    assert sent['classifier']['trained']
    with pytest.raises(RuntimeError, match='already submitted'):
        a.call('POST', '/api/admin/federated/hub/submit')
    with pytest.raises(RuntimeError, match='HTTP 409'):
        hub.call('POST', '/api/admin/security/federated/round')
    waiting = hub.call('GET', '/api/admin/security/federated/status')
    assert waiting['pending_peer_submissions'] == 1 and not waiting['ready_for_round']
    assert waiting['latest_round'] == before['latest_round']
    c.call('POST', '/api/admin/federated/hub/submit')
    result = hub.call('POST', '/api/admin/security/federated/round')
    assert result['real_peer_nodes'] == 2 and result['peer_nodes_simulated'] == 0
    assert len(result['classifier']['classifier_nodes']) == 3
    for peer in (a, c):
        pulled = peer.call('POST', '/api/admin/federated/hub/pull')
        assert pulled['hub_round'] == result['round'] and pulled['has_classifier']
    # The next round cannot silently reuse the completed round's updates.
    with pytest.raises(RuntimeError, match='HTTP 409'):
        hub.call('POST', '/api/admin/security/federated/round')
    report = lab.experiment(config, 2, tmp_path / 'results.json')
    assert len(report['snapshots']) == 3
    assert (tmp_path / 'results.csv').exists()
    for snapshot in report['snapshots']:
        for metrics in snapshot['nodes'].values():
            assert metrics['available'] and metrics['examples'] == 120
            assert metrics['training_examples'] == 80
