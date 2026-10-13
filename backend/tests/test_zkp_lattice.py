"""The post-quantum (lattice) zero-knowledge consent proof, and the scheme dispatch.

As with the Schnorr tests, the refusals matter more than the acceptances: a
verifier hardcoded to return True passes every completeness test. The ring
arithmetic is checked against a schoolbook reference first, because every
other property rests on it.
"""

import base64
import random

import pytest

from app import zkp_lattice as zl
from app import zkp_schnorr
from app import zkp_service
from app.zkp_lattice import ZKPError

CTX = "consent:patient-a"


@pytest.fixture(scope="module")
def issued():
    token, commitment = zl.issue_consent_token()
    challenge = zkp_service.make_challenge()
    return token, commitment, challenge, zl.prove(token, challenge, CTX)


def _schoolbook(a, b):
    """Reference multiplication in Z_q[X]/(X^256 + 1): X^256 wraps to −1."""
    out = [0] * zl.N
    for i, x in enumerate(a):
        for j, y in enumerate(b):
            if i + j < zl.N:
                out[i + j] += x * y
            else:
                out[i + j - zl.N] -= x * y
    return [v % zl.Q for v in out]


def _with_z(proof_b64, mutate):
    """Re-encode a proof after changing its response vector."""
    c_tilde, z = zl._decode_proof(proof_b64)
    mutate(z)
    return zl._encode_proof(c_tilde, z)


# ─── Ring arithmetic and parameters ──────────────────────────────────────────

def test_zeta_is_a_primitive_512th_root_of_unity():
    assert pow(zl.ZETA, 256, zl.Q) == zl.Q - 1


def test_ntt_round_trips():
    rng = random.Random(1)
    a = [rng.randrange(zl.Q) for _ in range(zl.N)]
    assert zl.intt(zl.ntt(a)) == a


@pytest.mark.parametrize("seed", [2, 3, 4])
def test_ntt_multiplication_matches_schoolbook(seed):
    rng = random.Random(seed)
    a = [rng.randrange(zl.Q) for _ in range(zl.N)]
    b = [rng.randrange(zl.Q) for _ in range(zl.N)]
    assert zl.intt(zl._mul_ntt(zl.ntt(a), zl.ntt(b))) == _schoolbook(a, b)


def test_beta_bounds_every_challenge_times_secret():
    """‖c·s‖∞ ≤ τ·η = β is what the rejection bound relies on."""
    assert zl.BETA == zl.TAU * zl.ETA
    _, s1, s2 = zl._expand_secret(b"\x07" * 32)
    c_hat = zl._to_ntt(zl.sample_in_ball(b"\x01" * 32))
    for s in s1 + s2:
        cs = [zl._center(v) for v in zl.intt(zl._mul_ntt(c_hat, zl._to_ntt(s)))]
        assert max(abs(v) for v in cs) <= zl.BETA


def test_challenges_have_exactly_tau_signed_ones():
    for i in range(5):
        c = zl.sample_in_ball(bytes([i]) * 32)
        assert sum(1 for v in c if v) == zl.TAU
        assert set(c) <= {-1, 0, 1}


def test_secret_coefficients_are_short():
    _, s1, s2 = zl._expand_secret(b"\x2a" * 32)
    assert all(-zl.ETA <= v <= zl.ETA for poly in s1 + s2 for v in poly)


# ─── Completeness ────────────────────────────────────────────────────────────

def test_an_honest_prover_is_accepted(issued):
    _, commitment, challenge, proof = issued
    assert zl.verify(commitment, proof["proof"], challenge, CTX) is True


def test_the_commitment_is_determined_by_the_token(issued):
    token, commitment, _, _ = issued
    assert zl.commitment_for(token) == commitment


def test_every_proof_is_different(issued):
    """Fresh masking y on every proof; reusing it would leak the secret."""
    token, commitment, challenge, first = issued
    second = zl.prove(token, challenge, CTX)
    assert first["proof"] != second["proof"]
    assert zl.verify(commitment, second["proof"], challenge, CTX)


def test_accepted_responses_stay_inside_the_inner_box(issued):
    """The abort really happens. Without it roughly two proofs in three would
    publish a z outside the box, so eight in a row passing by luck is ~2^-12."""
    token, _, challenge, _ = issued
    for _ in range(8):
        _, z = zl._decode_proof(zl.prove(token, challenge, CTX)["proof"])
        assert max(abs(v) for poly in z for v in poly) < zl.GAMMA1 - zl.BETA


# ─── Soundness: the refusals ─────────────────────────────────────────────────

def test_the_wrong_token_is_rejected(issued):
    _, commitment, challenge, _ = issued
    other_token, _ = zl.issue_consent_token()
    assert zl.verify(commitment, zl.prove(other_token, challenge, CTX)["proof"], challenge, CTX) is False


def test_a_proof_does_not_transfer_to_another_commitment(issued):
    _, _, challenge, proof = issued
    _, other_commitment = zl.issue_consent_token()
    assert zl.verify(other_commitment, proof["proof"], challenge, CTX) is False


def test_a_proof_does_not_transfer_to_another_challenge(issued):
    """Replay resistance: otherwise the proof is a bearer token in disguise."""
    _, commitment, _, proof = issued
    assert zl.verify(commitment, proof["proof"], zkp_service.make_challenge(), CTX) is False


def test_a_proof_does_not_transfer_to_another_patient(issued):
    _, commitment, challenge, proof = issued
    assert zl.verify(commitment, proof["proof"], challenge, "consent:patient-b") is False


def test_a_tampered_response_is_rejected(issued):
    _, commitment, challenge, proof = issued

    def bump(z):
        z[0][0] += 1
    assert zl.verify(commitment, _with_z(proof["proof"], bump), challenge, CTX) is False


def test_a_tampered_challenge_hash_is_rejected(issued):
    _, commitment, challenge, proof = issued
    raw = bytearray(base64.b64decode(proof["proof"]))
    raw[0] ^= 0x01
    assert zl.verify(commitment, base64.b64encode(bytes(raw)).decode(), challenge, CTX) is False


def test_the_norm_check_rejects_on_its_own(issued, monkeypatch):
    """z exactly at γ1 − β is refused even when the hash is made to agree.

    Patching the hash isolates the bound: otherwise the changed z would also
    change w and the proof would fail on the hash, hiding a missing check.
    """
    _, commitment, challenge, proof = issued

    def push(z):
        z[3][7] = zl.GAMMA1 - zl.BETA
    pushed = _with_z(proof["proof"], push)
    c_tilde = base64.b64decode(pushed)[:zl.CHALLENGE_BYTES]
    monkeypatch.setattr(zl, "_challenge_hash", lambda *args: c_tilde)
    assert zl.verify(commitment, proof["proof"], challenge, CTX) is True   # control
    assert zl.verify(commitment, pushed, challenge, CTX) is False


def test_a_long_solution_is_rejected(issued):
    """Without the norm check anyone could solve for z2 directly. With it, they cannot."""
    _, commitment, _, _ = issued
    rho, t, _ = zl._decode_commitment(commitment)
    c_tilde = b"\x05" * zl.CHALLENGE_BYTES
    c_hat = zl._to_ntt(zl.sample_in_ball(c_tilde))
    z1 = [[0] * zl.N for _ in range(zl.L)]
    # Choose w = 0, so z2 = c·t: satisfies the equation but is nowhere near short.
    z2 = [[zl._center(v) for v in zl.intt(zl._mul_ntt(c_hat, zl._to_ntt(t_i)))] for t_i in t]
    zero_w = [[0] * zl.N for _ in range(zl.K)]
    assert zl._commitment_side(zl._expand_a(rho), z1 + z2, c_hat, t) == zero_w
    assert zl.check_transcript(commitment, zero_w, c_tilde, z1 + z2) is False


# ─── Malformed input is refused, not crashed on ──────────────────────────────

@pytest.mark.parametrize("bad", [
    "", "not base64!", base64.b64encode(b"short").decode(),
    base64.b64encode(b"\x00" * (zl.PROOF_BYTES + 1)).decode(),
])
def test_malformed_proofs_return_false(issued, bad):
    _, commitment, challenge, _ = issued
    assert zl.verify(commitment, bad, challenge, CTX) is False


@pytest.mark.parametrize("bad", [None, 12, ["x"]])
def test_non_string_proofs_return_false(issued, bad):
    _, commitment, challenge, _ = issued
    assert zl.verify(commitment, bad, challenge, CTX) is False


def test_malformed_commitments_return_false(issued):
    _, commitment, challenge, proof = issued
    raw = base64.b64decode(commitment[len(zl.PREFIX):])
    out_of_range = bytearray(raw)
    out_of_range[32:35] = b"\xff\xff\x7f"                  # first t coefficient = 2^23 − 1 ≥ q
    for bad in ["", "abc", zl.PREFIX + "!!", zl.PREFIX + base64.b64encode(raw[:-1]).decode(),
                zl.PREFIX + base64.b64encode(bytes(out_of_range)).decode()]:
        assert zl.verify(bad, proof["proof"], challenge, CTX) is False


@pytest.mark.parametrize("bad", ["", "deadbeef", zl.PREFIX + "zz", zl.PREFIX + "ab" * 31])
def test_malformed_tokens_are_refused_loudly(bad):
    with pytest.raises(ZKPError):
        zl.prove(bad, "challenge", CTX)


# ─── Zero-knowledge ──────────────────────────────────────────────────────────

def test_the_proof_does_not_contain_the_token(issued):
    token, commitment, _, proof = issued
    seed = bytes.fromhex(token[len(zl.PREFIX):])
    assert seed not in base64.b64decode(proof["proof"])
    assert seed not in base64.b64decode(commitment[len(zl.PREFIX):])


def test_accepting_transcripts_exist_without_the_token(issued):
    """The honest-verifier simulator: transcripts made with no secret verify too.

    This is the zero-knowledge property made executable. Simulated z is uniform on
    the inner box — the same distribution rejection sampling gives a real prover —
    so a real transcript cannot carry information about the token.
    """
    _, commitment, _, _ = issued
    for i in range(3):
        c_tilde = bytes([i]) * zl.CHALLENGE_BYTES
        w, z = zl.simulate_transcript(commitment, c_tilde)
        assert zl.check_transcript(commitment, w, c_tilde, z) is True


# ─── Why this is a proof *of knowledge*: special soundness ──────────────────
#
# The simulator above shows a transcript reveals nothing. On its own that would
# also be true of a scheme that proves nothing at all. The other half is
# soundness: anyone who can answer two different challenges on ONE commitment
# must hold the secret, because the two answers give it up.
#
#     z  = y + c·s          z' = y + c'·s
#     z − z' = (c − c')·s   ← the extractor's output, with y gone
#
# That is the whole security argument made executable. A cheat who guesses one
# challenge cannot do it twice on the same w without knowing s.


def _transcript(token, server_challenge, y, ctx=CTX):
    """One interactive transcript (w, c̃, z) for a chosen mask y — the step prove()
    takes internally, exposed here so two challenges can share one commitment."""
    rho, s1, s2 = zl._expand_secret(zl._decode_token(token))
    a_hat = zl._expand_a(rho)
    t = zl._public_t(a_hat, s1, s2)
    tr = zl._tr(zl._commitment_bytes(rho, t))
    y1, y2 = y[:zl.L], y[zl.L:]
    ay1 = zl._mat_vec(a_hat, [zl._to_ntt(poly) for poly in y1])
    w = [[(x + y_) % zl.Q for x, y_ in zip(ay1[i], y2[i])] for i in range(zl.K)]
    c_tilde = zl._challenge_hash(tr, w, server_challenge, ctx)
    c_hat = zl._to_ntt(zl.sample_in_ball(c_tilde))
    s_hat = [zl._to_ntt(poly) for poly in s1 + s2]
    z = [[yy + zl._center(cs) for yy, cs in zip(y_poly, zl.intt(zl._mul_ntt(c_hat, s_poly)))]
         for y_poly, s_poly in zip(y, s_hat)]
    return w, c_tilde, z


def test_two_answers_to_one_commitment_give_up_the_secret(issued):
    """Special soundness: two accepting transcripts sharing a commitment extract
    the witness. This is what makes the proof one *of knowledge* rather than a
    statement anyone could make."""
    token, commitment, _, _ = issued
    rho, s1, s2 = zl._expand_secret(zl._decode_token(token))
    secret = s1 + s2

    for _ in range(zl.MAX_ATTEMPTS):
        y = [zl._sample_mask() for _ in range(zl.L + zl.K)]
        w, c1, z1 = _transcript(token, "challenge-one", y)
        w2, c2, z2 = _transcript(token, "challenge-two", y)
        assert w == w2                       # the same commitment, by construction
        if c1 == c2 or max(zl._inf_norm(z1), zl._inf_norm(z2)) >= zl.GAMMA1 - zl.BETA:
            continue                         # an abort, exactly as the prover would
        break
    else:
        pytest.fail("no pair of accepting transcripts was found")

    # Both are accepted by the verifier, on the one commitment.
    assert zl.check_transcript(commitment, w, c1, z1) is True
    assert zl.check_transcript(commitment, w, c2, z2) is True

    # The extractor: subtract, and the mask cancels.
    extracted = [[a - b for a, b in zip(p1, p2)] for p1, p2 in zip(z1, z2)]
    delta_c = [x - y_ for x, y_ in zip(zl.sample_in_ball(c1), zl.sample_in_ball(c2))]
    dc_hat = zl._to_ntt(delta_c)
    expected = [[zl._center(v) for v in zl.intt(zl._mul_ntt(dc_hat, zl._to_ntt(poly)))]
                for poly in secret]
    assert extracted == expected, "z − z' must equal (c − c')·s"

    # And it is a witness for the public statement: A·Δz1 + Δz2 = Δc·t.
    t = zl._public_t(zl._expand_a(rho), s1, s2)
    a_hat = zl._expand_a(rho)
    left = zl._mat_vec(a_hat, [zl._to_ntt(poly) for poly in extracted[:zl.L]])
    left = [[(left[i][n] + extracted[zl.L + i][n]) % zl.Q for n in range(zl.N)]
            for i in range(zl.K)]
    right = [[v % zl.Q for v in zl.intt(zl._mul_ntt(dc_hat, zl._to_ntt(t[i])))]
             for i in range(zl.K)]
    assert left == right

    # Nothing was extracted from one transcript alone: a single z is the mask
    # plus the secret, and the mask is never published.
    assert extracted != [list(poly) for poly in secret]


def test_one_transcript_alone_extracts_nothing(issued):
    """The counterpart: with a single accepting transcript the same subtraction
    yields nothing, because there is no second answer to cancel the mask."""
    token, commitment, challenge, _ = issued
    rho, s1, s2 = zl._expand_secret(zl._decode_token(token))
    proof = zl.prove(token, challenge, CTX)
    _, z = zl._decode_proof(proof["proof"])
    # z on its own is uniform on the inner box; it matches no secret coefficient
    # pattern, and the secret's coefficients are tiny (|s| ≤ η) while z is not.
    assert zl._inf_norm(z) > zl.ETA * 1000
    assert all(abs(v) <= zl.ETA for poly in s1 + s2 for v in poly)


def test_real_and_simulated_responses_have_the_same_distribution(issued):
    """The zero-knowledge claim, measured rather than asserted: an accepted real
    z and a simulated one are both uniform on the inner box, so a transcript
    carries no information about which token produced it."""
    token, commitment, _, _ = issued
    bound = zl.GAMMA1 - zl.BETA - 1
    buckets = 16

    def histogram(samples):
        counts = [0] * buckets
        for v in samples:
            idx = min(buckets - 1, int((v + bound) * buckets // (2 * bound + 1)))
            counts[idx] += 1
        return counts

    real, simulated = [], []
    for i in range(6):
        _, z = zl._decode_proof(zl.prove(token, f"challenge-{i}", CTX)["proof"])
        real += [v for poly in z for v in poly]
        _, zs = zl.simulate_transcript(commitment, bytes([i]) * zl.CHALLENGE_BYTES)
        simulated += [v for poly in zs for v in poly]

    assert len(real) == len(simulated) > 10_000
    expected = len(real) / buckets
    # Both are flat: no bucket strays far from the uniform expectation. (A loose
    # bound — this is a smoke test for a biased sampler, not a formal statistic.)
    for counts, name in ((histogram(real), "real"), (histogram(simulated), "simulated")):
        for n in counts:
            assert 0.75 * expected < n < 1.25 * expected, f"{name} z is not uniform: {counts}"

    # And they sit on the same support, which is what the simulator argument needs.
    assert max(abs(v) for v in real) <= bound
    assert max(abs(v) for v in simulated) <= bound


def test_tokens_are_unpredictable():
    assert len({zl.issue_consent_token()[0] for _ in range(5)}) == 5


# ─── The service dispatches by commitment, and never across schemes ──────────

def test_new_consents_are_issued_post_quantum():
    token, commitment = zkp_service.issue_consent_token()
    assert zkp_service.scheme_of(commitment) == zkp_service.SCHEME_LATTICE
    assert zkp_service.is_post_quantum(commitment)
    challenge = zkp_service.make_challenge()
    assert zkp_service.verify(commitment, zkp_service.prove(token, challenge, CTX), challenge, CTX)


def test_legacy_schnorr_commitments_still_verify():
    token, commitment = zkp_schnorr.issue_consent_token()
    assert zkp_service.scheme_of(commitment) == zkp_service.SCHEME_SCHNORR
    assert not zkp_service.is_post_quantum(commitment)
    challenge = zkp_service.make_challenge()
    proof = zkp_service.prove(token, challenge, CTX)
    assert proof["scheme"] == zkp_service.SCHEME_SCHNORR
    assert zkp_service.verify(commitment, proof, challenge, CTX)
    # Older clients send t and s with no scheme field; they keep working.
    assert zkp_service.verify(commitment, {"t": proof["t"], "s": proof["s"]}, challenge, CTX)


def test_a_proof_is_never_accepted_under_the_other_scheme(issued):
    _, lattice_commitment, challenge, lattice_proof = issued
    s_token, s_commitment = zkp_schnorr.issue_consent_token()
    schnorr_proof = zkp_service.prove(s_token, challenge, CTX)
    assert zkp_service.verify(lattice_commitment, schnorr_proof, challenge, CTX) is False
    assert zkp_service.verify(s_commitment, lattice_proof, challenge, CTX) is False
    # Relabelling a proof does not help either.
    assert zkp_service.verify(lattice_commitment, {**schnorr_proof, "scheme": "mlwe-v1"},
                              challenge, CTX) is False


@pytest.mark.parametrize("proof", [None, "x", {}, {"scheme": "mlwe-v1"}, {"scheme": "unknown"}])
def test_service_rejects_junk_without_raising(issued, proof):
    _, commitment, challenge, _ = issued
    assert zkp_service.verify(commitment, proof, challenge, CTX) is False
