"""The browser prover and the server's verifier agree, byte for byte.

frontend/src/lib/zkpLattice.ts is a port of app/zkp_lattice.py so the consent
token can stay in the doctor's browser. A port that drifted by one bit would
produce proofs the server rejects — or, worse, a commitment for a different
key. tests/fixtures/zkp_vectors.json holds a fixed token, the commitment and a
proof from this implementation, and a proof made by the TypeScript prover
(frontend/scripts/check-zkp.mjs --write). Each side checks the other's.
"""

import json
from pathlib import Path

from app import zkp_lattice, zkp_service

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "zkp_vectors.json").read_text())


def test_the_commitment_is_reproduced():
    assert zkp_lattice.commitment_for(VECTORS["token"]) == VECTORS["commitment"]


def test_a_proof_made_in_the_browser_verifies_on_the_server():
    proof = {"scheme": "mlwe-v1", "proof": VECTORS["browser_proof"]}
    assert zkp_service.verify(VECTORS["commitment"], proof, VECTORS["challenge"], VECTORS["context"])


def test_the_browser_proof_is_bound_to_its_challenge_and_patient():
    proof = {"scheme": "mlwe-v1", "proof": VECTORS["browser_proof"]}
    assert not zkp_service.verify(VECTORS["commitment"], proof, "another-challenge", VECTORS["context"])
    assert not zkp_service.verify(VECTORS["commitment"], proof, VECTORS["challenge"], "consent:other")
