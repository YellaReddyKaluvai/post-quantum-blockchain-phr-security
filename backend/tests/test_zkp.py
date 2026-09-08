"""The zero-knowledge consent proof.

A ZKP that only ever gets tested on the happy path proves nothing: a verifier
hardcoded to return True passes every completeness test. What matters here is
that it *refuses* — the wrong token, a replayed challenge, a different context,
a value outside the group.
"""

import pytest

from app.zkp_service import (
    P, Q, G, ZKPError,
    issue_consent_token, make_challenge, prove, verify,
)


# ─── Group parameters ────────────────────────────────────────────────────────

def test_p_is_a_safe_prime_shape():
    """p = 2q + 1, so the quadratic residues form a prime-order subgroup."""
    assert P == 2 * Q + 1


def test_generator_lies_in_the_prime_order_subgroup():
    """g must generate the subgroup of order q, not the whole group.

    Working outside a prime-order subgroup is what opens small-subgroup
    attacks, so this is asserted rather than assumed.
    """
    assert pow(G, Q, P) == 1
    assert G != 1


# ─── Completeness ────────────────────────────────────────────────────────────

def test_an_honest_prover_is_accepted():
    token, commitment = issue_consent_token()
    ch = make_challenge()
    assert verify(commitment, prove(token, ch, "ctx"), ch, "ctx") is True


def test_every_proof_is_different():
    """The per-proof nonce must be fresh. Reusing r across two proofs on the
    same key lets an observer solve for the secret directly."""
    token, commitment = issue_consent_token()
    ch = make_challenge()
    first, second = prove(token, ch, "ctx"), prove(token, ch, "ctx")
    assert first["t"] != second["t"] and first["s"] != second["s"]
    assert verify(commitment, first, ch, "ctx")
    assert verify(commitment, second, ch, "ctx")


# ─── Soundness: the refusals ─────────────────────────────────────────────────

def test_the_wrong_token_is_rejected():
    _, commitment = issue_consent_token()
    other_token, _ = issue_consent_token()
    ch = make_challenge()
    assert verify(commitment, prove(other_token, ch, "ctx"), ch, "ctx") is False


def test_a_proof_does_not_transfer_to_another_challenge():
    """Replay resistance. Without this the proof is a bearer token in disguise."""
    token, commitment = issue_consent_token()
    proof = prove(token, make_challenge(), "ctx")
    assert verify(commitment, proof, make_challenge(), "ctx") is False


def test_a_proof_does_not_transfer_to_another_context():
    """Context binds the proof to one patient relationship, so a proof for one
    patient cannot be presented for another."""
    token, commitment = issue_consent_token()
    ch = make_challenge()
    proof = prove(token, ch, "consent:patient-a")
    assert verify(commitment, proof, ch, "consent:patient-b") is False


def test_a_tampered_response_is_rejected():
    token, commitment = issue_consent_token()
    ch = make_challenge()
    proof = prove(token, ch, "ctx")
    proof["s"] = format((int(proof["s"], 16) + 1) % Q, "x")
    assert verify(commitment, proof, ch, "ctx") is False


def test_a_tampered_commitment_is_rejected():
    token, commitment = issue_consent_token()
    ch = make_challenge()
    proof = prove(token, ch, "ctx")
    proof["t"] = format((int(proof["t"], 16) * 2) % P, "x")
    assert verify(commitment, proof, ch, "ctx") is False


# ─── Malformed input must be refused, not crash ──────────────────────────────

@pytest.mark.parametrize("proof", [
    {},
    {"t": "1"},
    {"t": "zz", "s": "1"},
    {"t": "1", "s": "1"},            # t = 1 is outside the accepted range
    {"t": "0", "s": "0"},
    {"t": None, "s": None},
])
def test_malformed_proofs_return_false(proof):
    _, commitment = issue_consent_token()
    assert verify(commitment, proof, make_challenge(), "ctx") is False


def test_values_outside_the_subgroup_are_rejected():
    """A t that is not a quadratic residue is not in the prime-order subgroup,
    and accepting it would invite a small-subgroup attack."""
    token, commitment = issue_consent_token()
    ch = make_challenge()
    proof = prove(token, ch, "ctx")
    non_residue = 3 if pow(3, Q, P) != 1 else 5
    proof["t"] = format(non_residue, "x")
    assert verify(commitment, proof, ch, "ctx") is False


@pytest.mark.parametrize("bad", ["", "not-hex", "0", "1"])
def test_malformed_tokens_are_refused_loudly(bad):
    """A bad token is a caller error and should raise, unlike a failed
    verification, which is an expected outcome."""
    with pytest.raises(ZKPError):
        prove(bad, make_challenge(), "ctx")


# ─── The property that makes it zero-knowledge ───────────────────────────────

def test_the_proof_does_not_contain_the_token():
    """The whole point: the secret must not appear in what is transmitted."""
    token, commitment = issue_consent_token()
    ch = make_challenge()
    proof = prove(token, ch, "ctx")
    assert token not in proof["t"]
    assert token not in proof["s"]
    assert token not in (proof["t"] + proof["s"])


def test_tokens_are_unpredictable():
    tokens = {issue_consent_token()[0] for _ in range(20)}
    assert len(tokens) == 20


def test_challenges_are_unpredictable():
    assert len({make_challenge() for _ in range(50)}) == 50
