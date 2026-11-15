"""The image's bundled contract must match the source we ship."""

import hashlib
from pathlib import Path

from app import chain_client


def test_bundled_contract_matches_source_and_loads_without_foundry_output(monkeypatch, tmp_path):
    source = Path(__file__).resolve().parents[2] / "contracts" / "PHR.sol"
    monkeypatch.setattr(chain_client, "_ARTIFACT_PATH", tmp_path / "missing.json")

    artifact = chain_client.load_contract_artifact()

    # The backend-only Docker image omits the repository-root Solidity source.
    # Check the source fingerprint when testing a full checkout; the image
    # still validates the bundled ABI and bytecode below.
    if source.exists():
        assert artifact["sourceSha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert artifact["compiler"] == "solc 0.8.20"
    assert artifact["bytecode"]["object"].startswith("0x")
    assert len(artifact["bytecode"]["object"]) > 1000
    functions = {item["name"] for item in artifact["abi"] if item["type"] == "function"}
    assert {"updateConsent", "consentStatus", "emergencyAccess", "logDataAccess"} <= functions
