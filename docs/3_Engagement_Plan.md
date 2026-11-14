# 3. Development Plan & Progress

## Completed

| Phase | Work |
|---|---|
| **1. Foundation** | PostgreSQL schema, FastAPI skeleton, Next.js portals, Argon2id auth, RBAC |
| **2. Post-quantum core** | liboqs integration, ML-KEM-768 + ML-DSA-65 key management, AES-256-GCM documents |
| **3. Clinical workflow** | 9 lab panels, doctor→lab→patient pipeline, PDF generation, notifications |
| **4. Integrity & storage** | `PHR.sol` anchoring, S3 ciphertext storage, digest verification on read |
| **5. Consent & emergency** | Revocation enforced on reads, time-boxed break-glass, on-chain declarations |
| **6. Nurse module** | Vitals, notes, medication rounds; abnormal-vitals alerting |
| **7. Column encryption** | Diagnoses and prescriptions encrypted at rest |
| **8. Access requests** | Doctor→patient request flow, backend-enforced decisions |
| **9. AI security layer** | Anomaly detection, XAI, alerts, incidents, FedAvg |
| **10. Publishing & proofs** | Real IPFS pinning, authenticated federation peers, ZK consent proofs |
| **11. Scale & verification** | 500-user dataset, 203 tests, full endpoint and cross-role sweeps |
| **12. Closing the gaps** | Post-quantum (lattice) consent proof, IPFS replication to nodes and pinning services, federation-peer admin screen, dead table removed; 263 tests |

## Current state

The implementation includes versioned PQC keys, authenticated column migration,
account MFA/recovery, appointments, attachments, verified email and refresh sessions.
See [the completion guide](12_Completion_and_Rollout.md) for exact policy and rollout requirements.
Source counts and test totals change with each commit; use that commit's CI run rather
than the older static counts in this document.

## Remaining operational validation

- Provision and verify production SMTP, object storage, blockchain RPC/contract and IPFS replication.
- Run an encrypted backup/restore drill with the matching application keys.
- Run and record the three-physical-laptop experiment; checked-in federation metrics are synthetic containers.
- Apply migrations and verify the intended policy flags in the deployed environment.

These are deployment/evidence tasks. They are not claims that a live infrastructure service was provisioned by source changes.
