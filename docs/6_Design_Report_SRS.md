# 6. Software Requirements Specification

## Purpose

Protect electronic health records against both classical and quantum
adversaries, while letting five clinical roles do their jobs. The design rule
throughout: **the system never claims a protection it did not actually apply.**

## Functional requirements

| # | Requirement | Status |
|---|---|---|
| FR-1 | Self-contained authentication with Argon2id and revocable sessions | ✅ |
| FR-2 | Registration requires administrator approval before an account is usable | ✅ |
| FR-3 | Post-quantum keypairs issued on approval, never before | ✅ |
| FR-4 | Role-based access control enforced server-side on every endpoint | ✅ |
| FR-5 | Patients read their own records and nobody else's | ✅ |
| FR-6 | Doctors without a treating relationship must request access | ✅ |
| FR-7 | Patient approval or refusal is enforced by the backend | ✅ |
| FR-8 | Consent revocation blocks reads immediately | ✅ |
| FR-9 | Emergency access overrides revocation, time-boxed and audited | ✅ |
| FR-10 | Doctors order investigations; technicians file structured reports | ✅ |
| FR-11 | Every document encrypted, hashed, signed and anchored | ✅ |
| FR-12 | Integrity re-verified before any document is released | ✅ |
| FR-13 | Patients notified of reports, documents, decisions and overrides | ✅ |
| FR-14 | Nurses record vitals, notes and medication rounds | ✅ |
| FR-15 | Abnormal vitals alert the treating doctor automatically | ✅ |
| FR-16 | Behavioural anomaly detection over access metadata | ✅ |
| FR-17 | Every AI decision carries a human-readable explanation | ✅ |
| FR-18 | Security alerts escalate to incident and compliance records | ✅ |
| FR-19 | Federated aggregation of model parameters between institutions | ✅ Real; peers simulated until one registers |
| FR-20 | Zero-knowledge proof of consent without revealing identifiers | ✅ |
| FR-21 | Complete audit trail across every privileged action | ✅ |

## Non-functional requirements

**Quantum resilience.** ML-KEM-768 (FIPS 203) and ML-DSA-65 (FIPS 204) as
standardised by NIST, via liboqs 0.16. Verified by key sizes: 1,184-byte ML-KEM
public keys, 1,952-byte ML-DSA public keys, 3,309-byte signatures — exactly the
FIPS figures.

> The legacy round-3 name `Dilithium3` does **not** exist in liboqs 0.16.
> Requesting it fails, and an earlier version of this system swallowed that
> failure and substituted placeholder keys — so no real signature was ever
> produced. Mechanism names are now constants and the failure is fatal.

**Confidentiality.** AES-256-GCM for documents, AES-256-CBC for clinical
columns. Grepping the database for a condition name returns 0 rows across 810
diagnoses.

**Integrity.** SHA-256 digests re-checked on read; GCM authentication tags make
tampering detectable rather than merely unlikely; digests anchored on-chain so a
database-level rewrite stops agreeing with the ledger.

**Performance.** At 515 users and ~9,300 records: patient records 4 ms, lab
reports 8 ms, admin user list 8 ms at both page 1 and page 26. Single-machine
figures — meaningful as relative measurements, not production throughput.

**Auditability.** Every privileged action recorded with actor, target, time and
basis. Break-glass and consent decisions additionally anchored on-chain.

## Explicit non-goals

- **Not a diagnostic system.** The AI layer performs security anomaly detection
  and makes no clinical judgement.
- **Not a public IPFS deployment.** Content is genuinely pinned to a node; that
  is not replication across the public network.
- **Not a live multi-hospital federation.** The aggregation is real and peers
  authenticate; until a second institution registers, peer nodes are simulated
  and flagged as such in both the database and the API response.
