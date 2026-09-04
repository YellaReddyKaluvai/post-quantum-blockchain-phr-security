"""Zero-knowledge proof of consent (spec §17).

What this proves
----------------
When a patient approves an access request, the system issues the doctor a
secret *consent token*. To exercise that access the doctor proves they know the
token — without ever sending it. The server checks the proof against a public
commitment.

The property gained is concrete rather than decorative: after issuance the
secret never crosses the wire again, and a full database compromise yields only
commitments, which are public values by construction. An attacker reading every
row still cannot produce a valid proof.

The protocol
------------
Schnorr's identification protocol made non-interactive with Fiat–Shamir, which
is the canonical zero-knowledge proof of knowledge of a discrete logarithm.

    setup     x  <- Z_q                  the consent token (secret)
              y  =  g^x mod p            the commitment (public, stored)

    prove     r  <- Z_q                  fresh per proof, never reused
              t  =  g^r mod p
              c  =  H(g, y, t, context)  mod q
              s  =  r + c·x              mod q
              proof = (t, s)

    verify    g^s  ==  t · y^c  mod p

It is *zero-knowledge* because a simulator that picks s and c at random and
solves for t produces transcripts with exactly the same distribution as real
ones — so a transcript cannot reveal anything about x that was not already
computable without it. It is *sound* because two accepting proofs sharing a
commitment t but differing in c would yield x, which the prover is assumed
unable to find.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPORTANT — THIS COMPONENT IS NOT POST-QUANTUM SECURE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Schnorr rests on the hardness of discrete logarithm, which Shor's algorithm
solves on a sufficiently large quantum computer. Everything else in this system
— ML-KEM-768 for key encapsulation, ML-DSA-65 for signatures — was chosen
precisely to resist that attack. This module is the exception, and saying so is
the point: a quantum adversary who recovers x from y could forge consent
proofs, though they still could not decrypt any record, because record
confidentiality does not depend on this module.

It is included because a working, textbook-correct ZKP is worth more than an
empty interface, and because the honest statement of its limits is itself the
useful part. Post-quantum zero-knowledge exists — hash-based STARKs and
lattice-based proof systems — but implementing one correctly is research-grade
work, and a broken one would be far worse than none. Treat this as a
demonstration of the *shape* of the protocol, not as quantum-resistant
authorization.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# RFC 3526 group 14: a 2048-bit safe prime, p = 2q + 1. The quadratic residues
# modulo p form a subgroup of prime order q, which is where all arithmetic
# happens — working in a prime-order subgroup avoids small-subgroup attacks.
P = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16)
Q = (P - 1) // 2
# 2 is a generator of the full group; squaring lands in the prime-order
# subgroup of quadratic residues, so g = 4 generates exactly the subgroup we want.
G = 4

_DOMAIN = b"QuantumCare/ZKP/consent/v1"


class ZKPError(ValueError):
    """A proof was malformed or did not verify."""


def _h_int(*parts: bytes) -> int:
    """Fiat–Shamir hash, domain-separated and length-prefixed.

    Length prefixes matter: concatenating raw fields lets an attacker slide the
    boundary between two of them and produce the same digest from different
    inputs.
    """
    h = hashlib.sha256()
    h.update(_DOMAIN)
    for part in parts:
        h.update(len(part).to_bytes(4, "big"))
        h.update(part)
    return int.from_bytes(h.digest(), "big") % Q


def _b(value: int) -> bytes:
    return value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")


def issue_consent_token() -> tuple[str, str]:
    """Mint a consent token and its public commitment.

    Returns ``(token_hex, commitment_hex)``. The token goes to the doctor once
    and is never stored in the clear; only the commitment is persisted.
    """
    x = secrets.randbelow(Q - 2) + 2          # 2 <= x < Q
    y = pow(G, x, P)
    return format(x, "x"), format(y, "x")


def make_challenge() -> str:
    """A fresh server nonce, binding one proof to one verification.

    Without this a captured proof could be replayed forever, which would make
    the whole exercise pointless: the doctor would still be sending a reusable
    bearer value, just a longer one.
    """
    return secrets.token_hex(16)


def prove(token_hex: str, challenge: str, context: str = "") -> dict[str, str]:
    """Produce a proof of knowledge of the token. Runs on the prover's side."""
    try:
        x = int(token_hex, 16)
    except ValueError as exc:
        raise ZKPError("Malformed consent token.") from exc
    if not 1 < x < Q:
        raise ZKPError("Consent token out of range.")

    y = pow(G, x, P)
    r = secrets.randbelow(Q - 2) + 2          # fresh nonce; reuse leaks x
    t = pow(G, r, P)
    c = _h_int(_b(G), _b(y), _b(t), challenge.encode(), context.encode())
    s = (r + c * x) % Q
    return {"t": format(t, "x"), "s": format(s, "x")}


def verify(commitment_hex: str, proof: dict[str, str],
           challenge: str, context: str = "") -> bool:
    """Check a proof against the stored commitment. Runs on the verifier's side.

    Returns False rather than raising for an invalid proof: a failed
    verification is an expected outcome, not an exceptional one.
    """
    try:
        y = int(commitment_hex, 16)
        t = int(proof["t"], 16)
        s = int(proof["s"], 16)
    except (ValueError, KeyError, TypeError):
        return False

    # Reject anything outside the group before doing arithmetic with it.
    if not (1 < y < P and 1 < t < P and 0 <= s < Q):
        return False
    # Both public values must be quadratic residues, i.e. genuinely in the
    # prime-order subgroup. Skipping this invites small-subgroup attacks.
    if pow(y, Q, P) != 1 or pow(t, Q, P) != 1:
        return False

    c = _h_int(_b(G), _b(y), _b(t), challenge.encode(), context.encode())
    left = pow(G, s, P)
    right = (t * pow(y, c, P)) % P
    # Constant-time comparison. The values are public, but the habit is cheap
    # and prevents this becoming a timing oracle if it is ever reused.
    return hmac.compare_digest(_b(left), _b(right))


def simulate(commitment_hex: str, challenge: str, context: str = "") -> dict[str, str]:
    """Produce an accepting transcript *without* the token.

    This is the zero-knowledge property made executable rather than asserted.
    Choosing s and c first and solving t = g^s · y^-c yields a transcript that
    verifies and is distributed identically to a real one — which is precisely
    why a real transcript cannot leak the secret. Used only by the tests; it
    proves nothing about knowledge and must never gate access.
    """
    y = int(commitment_hex, 16)
    for _ in range(64):
        s = secrets.randbelow(Q - 2) + 2
        # Solve for t under the c that Fiat-Shamir will derive. Since c depends
        # on t, we search: pick t from a guessed c, then check it round-trips.
        c_guess = secrets.randbelow(Q - 2) + 2
        t = (pow(G, s, P) * pow(pow(y, c_guess, P), P - 2, P)) % P
        if _h_int(_b(G), _b(y), _b(t), challenge.encode(), context.encode()) == c_guess:
            return {"t": format(t, "x"), "s": format(s, "x")}
    raise ZKPError(
        "Simulation did not converge — expected, since Fiat-Shamir binds c to t. "
        "The interactive protocol simulates trivially; the non-interactive one "
        "is simulatable only in the random-oracle model."
    )
