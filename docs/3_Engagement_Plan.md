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

| Metric | Value |
|---|---|
| REST endpoints | 127 |
| Frontend pages | 51 |
| Database tables | 30 |
| Backend / frontend LOC | 9,162 / 15,133 |
| Automated tests | 263 |
| Demonstration data | 515 users · 804 signed reports · 40 chain anchors |

## Remaining

| Item | Nature |
|---|---|
| Live multi-hospital federation | Needs a second institution to register as a peer — the mechanism is built and tested |
| Public IPFS availability | Replication is built; it needs a second node or a pinning-service account configured, and has not yet been exercised against either |
| Production deployment | Runs locally under Docker; a hosted deployment needs infrastructure and a managed database |

Each is an infrastructure dependency rather than missing code.
