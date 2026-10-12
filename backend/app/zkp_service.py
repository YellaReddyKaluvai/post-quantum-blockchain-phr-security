"""Zero-knowledge consent proofs (spec §17) — the entry point the API uses.

Two schemes prove the same statement ("I hold the consent token the patient's
approval issued") without the token ever crossing the wire:

* ``mlwe-v1`` (``zkp_lattice``) — lattice Fiat–Shamir with aborts under
  ML-DSA-65 parameters. **Post-quantum.** Every new consent is issued with it.
* ``schnorr-v1`` (``zkp_schnorr``) — the original discrete-log proof. Not
  post-quantum. Kept only so commitments issued before the switch still verify;
  nothing new is issued with it.

The commitment stored with a consent decides which verifier runs. A proof that
names the other scheme is refused outright rather than reinterpreted, so a
legacy proof can never be passed off against a lattice commitment or vice versa.
"""

from __future__ import annotations

from app import zkp_lattice, zkp_schnorr
from app.zkp_lattice import ZKPError  # noqa: F401 - re-exported for callers

SCHEME_LATTICE = zkp_lattice.SCHEME
SCHEME_SCHNORR = "schnorr-v1"


def scheme_of(commitment: str) -> str:
    """Which scheme a stored commitment belongs to."""
    return SCHEME_LATTICE if commitment.startswith(zkp_lattice.PREFIX) else SCHEME_SCHNORR


def is_post_quantum(commitment: str) -> bool:
    return scheme_of(commitment) == SCHEME_LATTICE


def issue_consent_token() -> tuple[str, str]:
    """Mint a consent token and its commitment. Always the post-quantum scheme."""
    return zkp_lattice.issue_consent_token()


def make_challenge() -> str:
    """A fresh single-use server nonce, binding one proof to one verification."""
    return zkp_schnorr.make_challenge()


def prove(token: str, challenge: str, context: str = "") -> dict[str, str]:
    """Produce a proof for whichever scheme the token belongs to. Prover side."""
    if token.startswith(zkp_lattice.PREFIX):
        return zkp_lattice.prove(token, challenge, context)
    return {"scheme": SCHEME_SCHNORR, **zkp_schnorr.prove(token, challenge, context)}


def verify(commitment: str, proof: dict, challenge: str, context: str = "") -> bool:
    """Verify a proof against a stored commitment. Never raises for a bad proof."""
    if not isinstance(commitment, str) or not isinstance(proof, dict):
        return False
    scheme = scheme_of(commitment)
    claimed = proof.get("scheme") or SCHEME_SCHNORR
    if claimed != scheme:
        return False
    if scheme == SCHEME_LATTICE:
        return zkp_lattice.verify(commitment, proof.get("proof"), challenge, context)
    return zkp_schnorr.verify(commitment, {"t": proof.get("t"), "s": proof.get("s")},
                              challenge, context)
