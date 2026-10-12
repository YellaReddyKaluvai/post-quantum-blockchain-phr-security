"""Post-quantum zero-knowledge consent proof — lattice Fiat–Shamir with aborts.

What this proves
----------------
The same statement as the Schnorr proof it supersedes: "I hold the consent
token issued when this patient approved my access" — shown without sending the
token. What changes is the hard problem underneath. Schnorr hides the token
behind a discrete logarithm, which Shor's algorithm recovers. This hides it
behind Module-LWE and binds every proof with Module-SIS: the lattice problems
ML-DSA-65 already relies on everywhere else in the system.

The protocol
------------
Lyubashevsky's identification scheme made non-interactive with Fiat–Shamir
"with aborts". Arithmetic is in R_q = Z_q[X]/(X^256 + 1), q = 8 380 417.

    setup     ξ  <- 32 random bytes                    the consent token (secret)
              (ρ, σ) = SHAKE256(ξ)
              A  = ExpandA(ρ)        in R_q^(6×5)       public matrix
              s1 <- S_η^5,  s2 <- S_η^6   from σ        short secret vectors
              t  = A·s1 + s2                            commitment = (ρ, t)

    prove     y1 <- [-γ1+1, γ1]^5,  y2 <- [-γ1+1, γ1]^6    fresh every attempt
              w  = A·y1 + y2
              c̃ = H(tr, w, challenge, context);   c = SampleInBall(c̃)
              z  = y + c·s
              if ‖z‖∞ ≥ γ1 − β: discard everything and retry   <- the abort
              proof = (c̃, z)

    verify    ‖z‖∞ < γ1 − β
              c̃ == H(tr, A·z1 + z2 − c·t, challenge, context)

Verification works because A·z1 + z2 − c·t = A·y1 + y2 + c·(A·s1 + s2) − c·t = w.

Why the abort is what makes it zero-knowledge
---------------------------------------------
On its own, z = y + c·s leaks s: y is uniform on a box, so z is that box shifted
by c·s, and enough samples reveal the shift. Rejecting every z outside the
smaller box ‖z‖∞ < γ1 − β removes the shift entirely. Because ‖c·s‖∞ ≤ τ·η = β,
every value in the inner box is reached by exactly one y whatever s is — so an
accepted z is uniform on the inner box and independent of the secret. The
acceptance probability is independent of s for the same reason, so the number
of retries leaks nothing either. ``simulate_transcript`` makes the property
executable: it produces accepting transcripts with no secret at all.

Parameters
----------
Taken from ML-DSA-65 (FIPS 204): q, n = 256, (k, l) = (6, 5), η = 4, τ = 49,
γ1 = 2^19. Recovering the token from the commitment is Module-LWE at ML-DSA-65's
dimensions. Two accepting proofs that share w yield a Module-SIS solution of
ℓ∞ norm below 2γ1 in the same 6×12 module — the same shape and order of bound
as in ML-DSA-65's own analysis. The challenge space has C(256,49)·2^49 ≈ 2^225
elements, so guessing c is not an option.

Unlike ML-DSA nothing is compressed — no HighBits, no hint — so a proof carries
z2 in full and is about 7 KB rather than 3.3 KB. That buys a construction short
enough to read and check line by line, which matters more here than bytes.

Honest limits
-------------
* This is Lyubashevsky's 2012 construction with ML-DSA-65 parameters. It is not
  itself a NIST-standardised scheme, and this implementation has not been
  independently reviewed.
* Python's big-integer arithmetic is not constant-time. Only the prover touches
  the secret, and it runs on the doctor's side; the server only verifies, which
  involves public values alone.
* Soundness is the usual *relaxed* lattice notion: a cheating prover would yield
  a short solution to A·z̄1 + z̄2 = c̄·t rather than necessarily the original
  (s1, s2). Every Fiat–Shamir-with-aborts scheme, ML-DSA included, gives exactly
  this guarantee.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets

# ─── Parameters (ML-DSA-65) ──────────────────────────────────────────────────

N = 256
Q = 8_380_417
K, L = 6, 5                 # A is K×L; s1, y1, z1 have L entries; s2, y2, z2 have K
ETA = 4                     # secret coefficients lie in [-η, η]
TAU = 49                    # nonzero ±1 coefficients in a challenge
GAMMA1 = 1 << 19            # masking range for y
BETA = TAU * ETA            # bound on ‖c·s‖∞
ZETA = 1753                 # primitive 512th root of unity mod q

SCHEME = "mlwe-v1"
PREFIX = "mlwe1:"           # marks tokens and commitments of this scheme
_DOMAIN = b"QuantumCare/ZKP/consent/mlwe/v1"

SEED_BYTES = 32
CHALLENGE_BYTES = 32
_T_BITS = 23                # q < 2^23
_Z_BITS = 20                # γ1 − z lies in [0, 2^20)
COMMITMENT_BYTES = 32 + K * N * _T_BITS // 8                   # 4 448
PROOF_BYTES = CHALLENGE_BYTES + (L + K) * N * _Z_BITS // 8     # 7 072

# Each attempt is accepted with probability ≈ e^(−n·(k+l)·β/γ1) ≈ 0.35, so about
# three attempts are typical. A thousand consecutive aborts has probability
# below 2^-600; reaching it means the sampler itself is broken.
MAX_ATTEMPTS = 1000


class ZKPError(ValueError):
    """A token, commitment or proof was malformed.

    Never raised for a proof that is well-formed but does not verify: that is an
    expected outcome, reported as ``False``.
    """


# ─── Ring arithmetic in R_q = Z_q[X]/(X^256 + 1) ─────────────────────────────

def _brv8(i: int) -> int:
    return int(f"{i:08b}"[::-1], 2)


_ZETAS = [pow(ZETA, _brv8(i), Q) for i in range(N)]
_N_INV = pow(N, -1, Q)


def ntt(a: list[int]) -> list[int]:
    """Forward number-theoretic transform (the FIPS 204 ordering).

    In this domain multiplication in R_q is coefficient-wise, which turns each
    256×256 schoolbook product into 256 multiplications.
    """
    a = list(a)
    k = 0
    length = 128
    while length >= 1:
        for start in range(0, N, 2 * length):
            k += 1
            z = _ZETAS[k]
            for j in range(start, start + length):
                t = z * a[j + length] % Q
                a[j + length] = (a[j] - t) % Q
                a[j] = (a[j] + t) % Q
        length >>= 1
    return a


def intt(a: list[int]) -> list[int]:
    """Inverse transform; ``intt(ntt(f)) == f mod q``."""
    a = list(a)
    k = N
    length = 1
    while length < N:
        for start in range(0, N, 2 * length):
            k -= 1
            z = Q - _ZETAS[k]
            for j in range(start, start + length):
                t = a[j]
                a[j] = (t + a[j + length]) % Q
                a[j + length] = (t - a[j + length]) * z % Q
        length <<= 1
    return [x * _N_INV % Q for x in a]


def _to_ntt(poly: list[int]) -> list[int]:
    return ntt([x % Q for x in poly])


def _mul_ntt(a_hat: list[int], b_hat: list[int]) -> list[int]:
    return [x * y % Q for x, y in zip(a_hat, b_hat)]


def _center(x: int) -> int:
    """Representative of x mod q in (-q/2, q/2]."""
    x %= Q
    return x - Q if x > Q // 2 else x


def _mat_vec(a_hat: list[list[list[int]]], v_hat: list[list[int]]) -> list[list[int]]:
    """A·v for A in the NTT domain and v already transformed; result in normal form."""
    out = []
    for row in a_hat:
        acc = [0] * N
        for a_ij, v_j in zip(row, v_hat):
            for n in range(N):
                acc[n] += a_ij[n] * v_j[n]
        out.append(intt([x % Q for x in acc]))
    return out


def _inf_norm(vec: list[list[int]]) -> int:
    return max(abs(_center(x)) for poly in vec for x in poly)


# ─── Sampling ────────────────────────────────────────────────────────────────

class _XOF:
    """Read a SHAKE output stream incrementally.

    ``hashlib`` cannot squeeze in stages, but SHAKE output of length n is a
    prefix of every longer output, so re-digesting at a larger size continues
    the same stream.
    """

    def __init__(self, ctor, data: bytes, initial: int = 840):
        self._ctor, self._data = ctor, data
        self._buf = ctor(data).digest(initial)
        self._pos = 0

    def read(self, n: int) -> bytes:
        while self._pos + n > len(self._buf):
            self._buf = self._ctor(self._data).digest(2 * len(self._buf))
        out = self._buf[self._pos:self._pos + n]
        self._pos += n
        return out


def _expand_a(rho: bytes) -> list[list[list[int]]]:
    """The public K×L matrix, sampled directly in the NTT domain from ρ."""
    a_hat = []
    for i in range(K):
        row = []
        for j in range(L):
            xof = _XOF(hashlib.shake_128, rho + bytes([j, i]))
            coeffs: list[int] = []
            while len(coeffs) < N:
                b = xof.read(3)
                v = (b[0] | (b[1] << 8) | (b[2] << 16)) & 0x7FFFFF
                if v < Q:
                    coeffs.append(v)
            row.append(coeffs)
        a_hat.append(row)
    return a_hat


def _sample_eta(sigma: bytes, nonce: int) -> list[int]:
    """A polynomial with coefficients uniform on [-η, η] (rejection on nibbles)."""
    xof = _XOF(hashlib.shake_256, sigma + nonce.to_bytes(2, "little"), initial=272)
    coeffs: list[int] = []
    while len(coeffs) < N:
        byte = xof.read(1)[0]
        for nibble in (byte & 0x0F, byte >> 4):
            if nibble < 9 and len(coeffs) < N:
                coeffs.append(ETA - nibble)
    return coeffs


def sample_in_ball(c_tilde: bytes) -> list[int]:
    """The challenge polynomial: exactly τ coefficients ±1, the rest 0 (FIPS 204 SampleInBall)."""
    xof = _XOF(hashlib.shake_256, c_tilde, initial=136)
    signs = int.from_bytes(xof.read(8), "little")
    c = [0] * N
    for i in range(N - TAU, N):
        while True:
            j = xof.read(1)[0]
            if j <= i:
                break
        c[i] = c[j]
        c[j] = 1 - 2 * (signs & 1)
        signs >>= 1
    return c


def _sample_mask() -> list[int]:
    """Uniform on [-γ1+1, γ1]: γ1 minus a uniform 20-bit value."""
    return [GAMMA1 - secrets.randbits(_Z_BITS) for _ in range(N)]


# ─── Encoding ────────────────────────────────────────────────────────────────

def _pack(values: list[int], bits: int) -> bytes:
    """Little-endian bit packing, eight values (= ``bits`` bytes) at a time."""
    out = bytearray()
    for g in range(0, len(values), 8):
        acc = 0
        for k, v in enumerate(values[g:g + 8]):
            acc |= v << (bits * k)
        out += acc.to_bytes(bits, "little")
    return bytes(out)


def _unpack(data: bytes, bits: int, count: int) -> list[int]:
    mask = (1 << bits) - 1
    values = []
    for g in range(count // 8):
        acc = int.from_bytes(data[g * bits:(g + 1) * bits], "little")
        values.extend((acc >> (bits * k)) & mask for k in range(8))
    return values


def _flatten(vec: list[list[int]]) -> list[int]:
    return [x for poly in vec for x in poly]


def _split(flat: list[int], polys: int) -> list[list[int]]:
    return [flat[i * N:(i + 1) * N] for i in range(polys)]


def _b64decode(text: str) -> bytes:
    try:
        return base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ZKPError("Not valid base64.") from exc


def _decode_token(token: str) -> bytes:
    if not isinstance(token, str) or not token.startswith(PREFIX):
        raise ZKPError("Not a lattice consent token.")
    try:
        seed = bytes.fromhex(token[len(PREFIX):])
    except ValueError as exc:
        raise ZKPError("Malformed consent token.") from exc
    if len(seed) != SEED_BYTES:
        raise ZKPError("Consent token has the wrong length.")
    return seed


def _commitment_bytes(rho: bytes, t: list[list[int]]) -> bytes:
    return rho + _pack(_flatten(t), _T_BITS)


def _encode_commitment(rho: bytes, t: list[list[int]]) -> str:
    return PREFIX + base64.b64encode(_commitment_bytes(rho, t)).decode("ascii")


def _decode_commitment(commitment: str) -> tuple[bytes, list[list[int]], bytes]:
    """Returns ``(ρ, t, raw_bytes)``; refuses anything not exactly well-formed."""
    if not isinstance(commitment, str) or not commitment.startswith(PREFIX):
        raise ZKPError("Not a lattice commitment.")
    raw = _b64decode(commitment[len(PREFIX):])
    if len(raw) != COMMITMENT_BYTES:
        raise ZKPError("Commitment has the wrong length.")
    flat = _unpack(raw[32:], _T_BITS, K * N)
    if any(v >= Q for v in flat):
        raise ZKPError("Commitment coefficient out of range.")
    return raw[:32], _split(flat, K), raw


def _encode_proof(c_tilde: bytes, z: list[list[int]]) -> str:
    return base64.b64encode(c_tilde + _pack([GAMMA1 - v for v in _flatten(z)], _Z_BITS)).decode("ascii")


def _decode_proof(proof: str) -> tuple[bytes, list[list[int]]]:
    if not isinstance(proof, str):
        raise ZKPError("Proof must be a string.")
    raw = _b64decode(proof)
    if len(raw) != PROOF_BYTES:
        raise ZKPError("Proof has the wrong length.")
    flat = _unpack(raw[CHALLENGE_BYTES:], _Z_BITS, (L + K) * N)
    return raw[:CHALLENGE_BYTES], _split([GAMMA1 - v for v in flat], L + K)


# ─── Key material ────────────────────────────────────────────────────────────

def _expand_secret(seed: bytes) -> tuple[bytes, list[list[int]], list[list[int]]]:
    material = hashlib.shake_256(_DOMAIN + b"/keygen" + seed).digest(96)
    rho, sigma = material[:32], material[32:]
    s1 = [_sample_eta(sigma, i) for i in range(L)]
    s2 = [_sample_eta(sigma, L + i) for i in range(K)]
    return rho, s1, s2


def _public_t(a_hat, s1, s2) -> list[list[int]]:
    as1 = _mat_vec(a_hat, [_to_ntt(p) for p in s1])
    return [[(x + e) % Q for x, e in zip(as1[i], s2[i])] for i in range(K)]


def _tr(commitment_bytes: bytes) -> bytes:
    """A digest of the whole commitment, so every proof is bound to one public key."""
    return hashlib.shake_256(_DOMAIN + b"/tr" + commitment_bytes).digest(64)


def _challenge_hash(tr: bytes, w: list[list[int]], challenge: str, context: str) -> bytes:
    """Fiat–Shamir hash, domain-separated and length-prefixed.

    Length prefixes stop an attacker sliding the boundary between two fields to
    get the same digest from different inputs.
    """
    h = hashlib.shake_256()
    h.update(_DOMAIN)
    for part in (tr, _pack(_flatten(w), _T_BITS), challenge.encode(), context.encode()):
        h.update(len(part).to_bytes(4, "big"))
        h.update(part)
    return h.digest(CHALLENGE_BYTES)


def issue_consent_token() -> tuple[str, str]:
    """Mint a consent token and its public commitment.

    Returns ``(token, commitment)``. The token goes to the doctor once and is
    never stored in the clear; only the commitment is persisted.
    """
    token = PREFIX + secrets.token_bytes(SEED_BYTES).hex()
    return token, commitment_for(token)


def commitment_for(token: str) -> str:
    """The public commitment a token corresponds to (deterministic)."""
    rho, s1, s2 = _expand_secret(_decode_token(token))
    return _encode_commitment(rho, _public_t(_expand_a(rho), s1, s2))


# ─── Prove / verify ──────────────────────────────────────────────────────────

def prove(token: str, challenge: str, context: str = "") -> dict[str, str]:
    """Produce a proof of knowledge of the token. Runs on the prover's side."""
    rho, s1, s2 = _expand_secret(_decode_token(token))
    a_hat = _expand_a(rho)
    tr = _tr(_commitment_bytes(rho, _public_t(a_hat, s1, s2)))
    s_hat = [_to_ntt(p) for p in s1 + s2]

    for _ in range(MAX_ATTEMPTS):
        y1 = [_sample_mask() for _ in range(L)]
        y2 = [_sample_mask() for _ in range(K)]
        ay1 = _mat_vec(a_hat, [_to_ntt(p) for p in y1])
        w = [[(x + y) % Q for x, y in zip(ay1[i], y2[i])] for i in range(K)]

        c_tilde = _challenge_hash(tr, w, challenge, context)
        c_hat = _to_ntt(sample_in_ball(c_tilde))
        z = [[y + _center(cs) for y, cs in zip(y_poly, intt(_mul_ntt(c_hat, s_poly)))]
             for y_poly, s_poly in zip(y1 + y2, s_hat)]

        # The abort. A rejected attempt is discarded whole — y, w, c̃ and z — and
        # nothing about it leaves this function; publishing rejected transcripts
        # would undo the zero-knowledge property.
        if max(abs(v) for poly in z for v in poly) >= GAMMA1 - BETA:
            continue
        return {"scheme": SCHEME, "proof": _encode_proof(c_tilde, z)}

    raise ZKPError("Rejection sampling did not terminate; the sampler is broken.")


def _commitment_side(a_hat, z: list[list[int]], c_hat: list[int], t: list[list[int]]) -> list[list[int]]:
    """A·z1 + z2 − c·t, i.e. the w an honest prover must have hashed."""
    az1 = _mat_vec(a_hat, [_to_ntt(p) for p in z[:L]])
    w = []
    for i in range(K):
        ct = intt(_mul_ntt(c_hat, _to_ntt(t[i])))
        w.append([(az1[i][n] + z[L + i][n] - ct[n]) % Q for n in range(N)])
    return w


def verify(commitment: str, proof: str, challenge: str, context: str = "") -> bool:
    """Check a proof against the stored commitment. Runs on the verifier's side.

    Returns False rather than raising for any invalid proof, including a
    malformed one: a failed verification is an expected outcome.
    """
    try:
        rho, t, raw = _decode_commitment(commitment)
        c_tilde, z = _decode_proof(proof)
    except ZKPError:
        return False

    # The bound is half the security argument, not a formality. Without it
    # anyone could pick z1, then set z2 = w + c·t − A·z1 for any w they like:
    # the equation only means something when z is short.
    if max(abs(v) for poly in z for v in poly) >= GAMMA1 - BETA:
        return False

    w = _commitment_side(_expand_a(rho), z, _to_ntt(sample_in_ball(c_tilde)), t)
    # The values are public, but constant-time comparison is a cheap habit.
    return hmac.compare_digest(c_tilde, _challenge_hash(_tr(raw), w, challenge, context))


# ─── Zero-knowledge, made executable ─────────────────────────────────────────

def simulate_transcript(commitment: str, c_tilde: bytes) -> tuple[list[list[int]], list[list[int]]]:
    """An accepting interactive transcript ``(w, z)`` for challenge ``c̃``, made without the token.

    The honest-verifier simulator: pick z uniformly on the inner box — exactly
    the distribution an honest prover's accepted z has — and solve for
    w = A·z1 + z2 − c·t. Real and simulated transcripts are identically
    distributed, which is why a real one cannot reveal the secret. Used by the
    tests; it proves nothing about knowledge and must never gate access.
    """
    rho, t, _ = _decode_commitment(commitment)
    bound = GAMMA1 - BETA - 1
    z = [[secrets.randbelow(2 * bound + 1) - bound for _ in range(N)] for _ in range(L + K)]
    w = _commitment_side(_expand_a(rho), z, _to_ntt(sample_in_ball(c_tilde)), t)
    return w, z


def check_transcript(commitment: str, w: list[list[int]], c_tilde: bytes, z: list[list[int]]) -> bool:
    """The interactive verifier: ‖z‖∞ < γ1 − β and A·z1 + z2 − c·t == w."""
    rho, t, _ = _decode_commitment(commitment)
    if max(abs(v) for poly in z for v in poly) >= GAMMA1 - BETA:
        return False
    return _commitment_side(_expand_a(rho), z, _to_ntt(sample_in_ball(c_tilde)), t) == \
        [[x % Q for x in poly] for poly in w]
