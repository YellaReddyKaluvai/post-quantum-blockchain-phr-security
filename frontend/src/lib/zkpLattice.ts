/**
 * Post-quantum zero-knowledge consent proof — the prover, in the browser.
 *
 * A line-for-line port of backend/app/zkp_lattice.py (Lyubashevsky's
 * Fiat–Shamir with aborts under ML-DSA-65 parameters). The point of running it
 * here is that the consent token never leaves the doctor's device: the server
 * hands out a challenge, the browser proves knowledge of the token, and only
 * the proof is sent back. Byte-for-byte compatibility with the Python verifier
 * is checked by backend/tests/test_zkp_browser_vectors.py and
 * frontend/scripts/check-zkp.mjs against shared vectors.
 *
 * Every value fits a double: q < 2^23, so a product is < 2^46 and a sum of
 * five products < 2^49, all below 2^53.
 */
import { shake128, shake256 } from "@noble/hashes/sha3.js";

// ─── Parameters (ML-DSA-65) ──────────────────────────────────────────────────

const N = 256;
const Q = 8_380_417;
const K = 6;
const L = 5;
const ETA = 4;
const TAU = 49;
const GAMMA1 = 1 << 19;
const BETA = TAU * ETA;
const ZETA = 1753;

export const SCHEME = "mlwe-v1";
export const PREFIX = "mlwe1:";
const DOMAIN = new TextEncoder().encode("QuantumCare/ZKP/consent/mlwe/v1");

const SEED_BYTES = 32;
const CHALLENGE_BYTES = 32;
const T_BITS = 23;
const Z_BITS = 20;
const COMMITMENT_BYTES = 32 + (K * N * T_BITS) / 8;
const PROOF_BYTES = CHALLENGE_BYTES + ((L + K) * N * Z_BITS) / 8;
const MAX_ATTEMPTS = 1000;

type Poly = number[];
type Vec = Poly[];

export class ZKPError extends Error {}

// ─── Ring arithmetic in R_q = Z_q[X]/(X^256 + 1) ─────────────────────────────

const mod = (x: number) => ((x % Q) + Q) % Q;

function powMod(base: number, exp: number): number {
  let result = BigInt(1);
  let b = BigInt(base) % BigInt(Q);
  let e = BigInt(exp);
  const q = BigInt(Q);
  while (e > BigInt(0)) {
    if (e & BigInt(1)) result = (result * b) % q;
    b = (b * b) % q;
    e >>= BigInt(1);
  }
  return Number(result);
}

function brv8(i: number): number {
  let r = 0;
  for (let b = 0; b < 8; b++) r |= ((i >> b) & 1) << (7 - b);
  return r;
}

const ZETAS = Array.from({ length: N }, (_, i) => powMod(ZETA, brv8(i)));
const N_INV = powMod(N, Q - 2);

/** a·b mod q without leaving the exact-integer range of a double. */
function mulMod(a: number, b: number): number {
  return Number((BigInt(a) * BigInt(b)) % BigInt(Q));
}

function ntt(input: Poly): Poly {
  const a = input.slice();
  let k = 0;
  for (let len = 128; len >= 1; len >>= 1) {
    for (let start = 0; start < N; start += 2 * len) {
      const z = ZETAS[++k];
      for (let j = start; j < start + len; j++) {
        const t = (z * a[j + len]) % Q;          // < 2^46, exact
        a[j + len] = mod(a[j] - t);
        a[j] = (a[j] + t) % Q;
      }
    }
  }
  return a;
}

function intt(input: Poly): Poly {
  const a = input.slice();
  let k = N;
  for (let len = 1; len < N; len <<= 1) {
    for (let start = 0; start < N; start += 2 * len) {
      const z = Q - ZETAS[--k];
      for (let j = start; j < start + len; j++) {
        const t = a[j];
        a[j] = (t + a[j + len]) % Q;
        a[j + len] = (mod(t - a[j + len]) * z) % Q;
      }
    }
  }
  return a.map((x) => mulMod(x, N_INV));
}

const toNtt = (p: Poly) => ntt(p.map(mod));
const mulNtt = (a: Poly, b: Poly) => a.map((x, i) => (x * b[i]) % Q);
const center = (x: number) => { const r = mod(x); return r > Q >> 1 ? r - Q : r; };

function matVec(aHat: Poly[][], vHat: Vec): Vec {
  return aHat.map((row) => {
    const acc = new Array<number>(N).fill(0);
    row.forEach((aij, j) => {
      const vj = vHat[j];
      for (let n = 0; n < N; n++) acc[n] += (aij[n] * vj[n]) % Q;
    });
    return intt(acc.map((x) => x % Q));
  });
}

// ─── Sampling ────────────────────────────────────────────────────────────────

type Xof = { read: (n: number) => Uint8Array };

function xof(kind: "128" | "256", data: Uint8Array): Xof {
  const h = (kind === "128" ? shake128 : shake256).create({});
  h.update(data);
  return { read: (n: number) => h.xof(n) };
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((s, p) => s + p.length, 0));
  let o = 0;
  for (const p of parts) { out.set(p, o); o += p.length; }
  return out;
}

function expandA(rho: Uint8Array): Poly[][] {
  const aHat: Poly[][] = [];
  for (let i = 0; i < K; i++) {
    const row: Poly[] = [];
    for (let j = 0; j < L; j++) {
      const stream = xof("128", concat(rho, Uint8Array.of(j, i)));
      const coeffs: Poly = [];
      while (coeffs.length < N) {
        const b = stream.read(3);
        const v = (b[0] | (b[1] << 8) | (b[2] << 16)) & 0x7fffff;
        if (v < Q) coeffs.push(v);
      }
      row.push(coeffs);
    }
    aHat.push(row);
  }
  return aHat;
}

function sampleEta(sigma: Uint8Array, nonce: number): Poly {
  const stream = xof("256", concat(sigma, Uint8Array.of(nonce & 0xff, nonce >> 8)));
  const coeffs: Poly = [];
  while (coeffs.length < N) {
    const byte = stream.read(1)[0];
    for (const nibble of [byte & 0x0f, byte >> 4]) {
      if (nibble < 9 && coeffs.length < N) coeffs.push(ETA - nibble);
    }
  }
  return coeffs;
}

function sampleInBall(cTilde: Uint8Array): Poly {
  const stream = xof("256", cTilde);
  let signs = BigInt(0);
  stream.read(8).forEach((b, i) => { signs |= BigInt(b) << BigInt(8 * i); });
  const c = new Array<number>(N).fill(0);
  for (let i = N - TAU; i < N; i++) {
    let j: number;
    do { j = stream.read(1)[0]; } while (j > i);
    c[i] = c[j];
    c[j] = 1 - 2 * Number(signs & BigInt(1));
    signs >>= BigInt(1);
  }
  return c;
}

/** Uniform on [-γ1+1, γ1]: γ1 minus a uniform 20-bit value, from the OS CSPRNG. */
function sampleMask(): Poly {
  const words = new Uint32Array(N);
  crypto.getRandomValues(words);
  return Array.from(words, (w) => GAMMA1 - (w & 0xfffff));
}

// ─── Encoding ────────────────────────────────────────────────────────────────

function pack(values: number[], bits: number): Uint8Array {
  const out = new Uint8Array((values.length * bits) / 8);
  let o = 0;
  for (let g = 0; g < values.length; g += 8) {
    let acc = BigInt(0);
    for (let k = 0; k < 8; k++) acc |= BigInt(values[g + k]) << BigInt(bits * k);
    for (let b = 0; b < bits; b++) { out[o++] = Number(acc & BigInt(0xff)); acc >>= BigInt(8); }
  }
  return out;
}

function unpack(data: Uint8Array, bits: number, count: number): number[] {
  const mask = (BigInt(1) << BigInt(bits)) - BigInt(1);
  const values: number[] = [];
  for (let g = 0; g < count / 8; g++) {
    let acc = BigInt(0);
    for (let b = bits - 1; b >= 0; b--) acc = (acc << BigInt(8)) | BigInt(data[g * bits + b]);
    for (let k = 0; k < 8; k++) values.push(Number((acc >> BigInt(bits * k)) & mask));
  }
  return values;
}

const flatten = (v: Vec) => v.flat();
const split = (flat: number[], polys: number): Vec =>
  Array.from({ length: polys }, (_, i) => flat.slice(i * N, (i + 1) * N));

function toBase64(bytes: Uint8Array): string {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function fromBase64(text: string): Uint8Array {
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(text)) throw new ZKPError("Not valid base64.");
  return Uint8Array.from(atob(text), (c) => c.charCodeAt(0));
}

function decodeToken(token: string): Uint8Array {
  if (typeof token !== "string" || !token.startsWith(PREFIX)) throw new ZKPError("Not a lattice consent token.");
  const hex = token.slice(PREFIX.length);
  if (!/^[0-9a-fA-F]*$/.test(hex) || hex.length % 2) throw new ZKPError("Malformed consent token.");
  const seed = Uint8Array.from(hex.match(/../g) ?? [], (h) => parseInt(h, 16));
  if (seed.length !== SEED_BYTES) throw new ZKPError("Consent token has the wrong length.");
  return seed;
}

const commitmentBytes = (rho: Uint8Array, t: Vec) => concat(rho, pack(flatten(t), T_BITS));

function decodeCommitment(commitment: string): { rho: Uint8Array; t: Vec; raw: Uint8Array } {
  if (typeof commitment !== "string" || !commitment.startsWith(PREFIX)) throw new ZKPError("Not a lattice commitment.");
  const raw = fromBase64(commitment.slice(PREFIX.length));
  if (raw.length !== COMMITMENT_BYTES) throw new ZKPError("Commitment has the wrong length.");
  const flat = unpack(raw.subarray(32), T_BITS, K * N);
  if (flat.some((v) => v >= Q)) throw new ZKPError("Commitment coefficient out of range.");
  return { rho: raw.subarray(0, 32), t: split(flat, K), raw };
}

// ─── Key material ────────────────────────────────────────────────────────────

const enc = (s: string) => new TextEncoder().encode(s);

function expandSecret(seed: Uint8Array): { rho: Uint8Array; s1: Vec; s2: Vec } {
  const material = shake256(concat(DOMAIN, enc("/keygen"), seed), { dkLen: 96 });
  const rho = material.subarray(0, 32);
  const sigma = material.subarray(32);
  return {
    rho,
    s1: Array.from({ length: L }, (_, i) => sampleEta(sigma, i)),
    s2: Array.from({ length: K }, (_, i) => sampleEta(sigma, L + i)),
  };
}

function publicT(aHat: Poly[][], s1: Vec, s2: Vec): Vec {
  const as1 = matVec(aHat, s1.map(toNtt));
  return as1.map((row, i) => row.map((x, n) => mod(x + s2[i][n])));
}

const trOf = (commitment: Uint8Array) => shake256(concat(DOMAIN, enc("/tr"), commitment), { dkLen: 64 });

function lengthPrefixed(part: Uint8Array): Uint8Array {
  const len = new Uint8Array(4);
  new DataView(len.buffer).setUint32(0, part.length, false);
  return concat(len, part);
}

function challengeHash(tr: Uint8Array, w: Vec, challenge: string, context: string): Uint8Array {
  return shake256(concat(DOMAIN, ...[tr, pack(flatten(w), T_BITS), enc(challenge), enc(context)].map(lengthPrefixed)),
    { dkLen: CHALLENGE_BYTES });
}

/** The public commitment a token corresponds to (deterministic). */
export function commitmentFor(token: string): string {
  const { rho, s1, s2 } = expandSecret(decodeToken(token));
  return PREFIX + toBase64(commitmentBytes(rho, publicT(expandA(rho), s1, s2)));
}

// ─── Prove / verify ──────────────────────────────────────────────────────────

export function prove(token: string, challenge: string, context = ""): { scheme: string; proof: string } {
  const { rho, s1, s2 } = expandSecret(decodeToken(token));
  const aHat = expandA(rho);
  const tr = trOf(commitmentBytes(rho, publicT(aHat, s1, s2)));
  const sHat = [...s1, ...s2].map(toNtt);

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    const y1 = Array.from({ length: L }, sampleMask);
    const y2 = Array.from({ length: K }, sampleMask);
    const ay1 = matVec(aHat, y1.map(toNtt));
    const w = ay1.map((row, i) => row.map((x, n) => mod(x + y2[i][n])));

    const cTilde = challengeHash(tr, w, challenge, context);
    const cHat = toNtt(sampleInBall(cTilde));
    const z = [...y1, ...y2].map((y, i) => {
      const cs = intt(mulNtt(cHat, sHat[i]));
      return y.map((v, n) => v + center(cs[n]));
    });

    // The abort: a rejected attempt is discarded whole and nothing about it
    // leaves this function. Publishing it would undo the zero-knowledge property.
    if (z.some((p) => p.some((v) => Math.abs(v) >= GAMMA1 - BETA))) continue;
    return { scheme: SCHEME, proof: toBase64(concat(cTilde, pack(flatten(z).map((v) => GAMMA1 - v), Z_BITS))) };
  }
  throw new ZKPError("Rejection sampling did not terminate; the sampler is broken.");
}

/** Check a proof locally before sending it. The server runs the same check. */
export function verify(commitment: string, proof: string, challenge: string, context = ""): boolean {
  try {
    const { rho, t, raw } = decodeCommitment(commitment);
    const bytes = fromBase64(proof);
    if (bytes.length !== PROOF_BYTES) return false;
    const cTilde = bytes.subarray(0, CHALLENGE_BYTES);
    const z = split(unpack(bytes.subarray(CHALLENGE_BYTES), Z_BITS, (L + K) * N).map((v) => GAMMA1 - v), L + K);
    if (z.some((p) => p.some((v) => Math.abs(v) >= GAMMA1 - BETA))) return false;

    const cHat = toNtt(sampleInBall(cTilde));
    const az1 = matVec(expandA(rho), z.slice(0, L).map(toNtt));
    const w = t.map((ti, i) => {
      const ct = intt(mulNtt(cHat, toNtt(ti)));
      return az1[i].map((x, n) => mod(x + z[L + i][n] - ct[n]));
    });
    const expected = challengeHash(trOf(raw), w, challenge, context);
    let diff = 0;
    for (let i = 0; i < CHALLENGE_BYTES; i++) diff |= expected[i] ^ cTilde[i];
    return diff === 0;
  } catch {
    return false;
  }
}
