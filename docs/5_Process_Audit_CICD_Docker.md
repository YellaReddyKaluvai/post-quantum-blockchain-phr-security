# 5. Build, Test & Deployment

## Containerisation

| File | Contents |
|---|---|
| `backend/Dockerfile` | Python 3.12, liboqs, FastAPI under uvicorn |
| `frontend/Dockerfile` | Node 20, Next.js production build |
| `docker-compose.yml` | Backend, frontend, PostgreSQL 16 on one network |

Follow [INSTALL.md](../INSTALL.md) for configuration and the supported local
setup: containerized database/API with a host-run frontend. See
[DEPLOY.md](../DEPLOY.md) for the verified Vercel + Render deployment.

## CI/CD

`.github/workflows/deploy.yml` runs on push: installs dependencies, executes the
test suite, and builds both images.

## Test suite

The suite includes unit tests and opt-in live integration tests. Test counts
change as coverage grows; use `python -m pytest --collect-only` for the current
collection. Live checks require their configured databases, chain and storage
services. Missing integrations may be skipped; report skips explicitly.

| File | Covers |
|---|---|
| `test_crypto_pipeline.py` | ML-KEM round trip, ML-DSA signing and tamper rejection |
| `test_storage_and_anchoring.py` | S3 failure behaviour, anchor labelling |
| `test_clinical_validation.py` | Vitals bounds, appointment dates, break-glass reasons |
| `test_clinical_encryption.py` | Column encryption round trips |
| `test_request_bounds.py` | Pagination and malformed identifiers |
| `test_rbac_parity.py` | Backend/frontend permission agreement |
| `test_access_requests.py` | Consent lifecycle and its enforcement |
| `test_ai_security.py` | Detection, calibration, explanation, FedAvg |
| `test_delivery_and_adherence.py` | Imaging release scoping, adherence summaries |
| `test_ipfs.py` | Publishing, with and without a node |
| `test_federation.py` | Peer signature verification, parameter sanity |
| `test_zkp.py` | Legacy Schnorr proof: soundness and replay resistance |
| `test_zkp_lattice.py` | Post-quantum lattice proof: ring arithmetic, forgery and replay refusal, scheme separation |
| `test_ipfs_replication.py` | Replication to nodes and pinning services; only confirmed copies count |

**Every test asserts a refusal as well as a success.** A happy-path-only suite
would pass against a verifier hardcoded to return true — which this codebase
once shipped. The suite was therefore checked by mutation: reintroducing three
real past bugs (a signature verifier always returning true, an upload recording
a key it never wrote, a dropped vitals validator) failed 7, 1 and 2 tests
respectively.

## Local development

Use [INSTALL.md](../INSTALL.md), which covers tool versions, secret generation,
first administrator, frontend configuration, testing and troubleshooting.
Machine-specific paths are not prerequisites for another contributor.

## Demonstration dataset

`backend/generate_dataset.py` produces 500 users and ~8,400 clinical records in
37 seconds. Only names and clinical content are synthetic — every key is a
genuine ML-KEM/ML-DSA keypair and every encrypted column is really encrypted.
`--reset` removes only generated accounts, scoped by their
`@quantumcare-demo.invalid` marker.
