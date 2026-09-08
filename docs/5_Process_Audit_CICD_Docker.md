# 5. Build, Test & Deployment

## Containerisation

| File | Contents |
|---|---|
| `backend/Dockerfile` | Python 3.12, liboqs, FastAPI under uvicorn |
| `frontend/Dockerfile` | Node 20, Next.js production build |
| `docker-compose.yml` | Backend, frontend, PostgreSQL 16 on one network |

```bash
docker compose up --build
```

## CI/CD

`.github/workflows/deploy.yml` runs on push: installs dependencies, executes the
test suite, and builds both images.

## Test suite

**203 tests**, no database or running server required.

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
| `test_zkp.py` | Proof soundness and replay resistance |

**Every test asserts a refusal as well as a success.** A happy-path-only suite
would pass against a verifier hardcoded to return true — which this codebase
once shipped. The suite was therefore checked by mutation: reintroducing three
real past bugs (a signature verifier always returning true, an upload recording
a key it never wrote, a dropped vitals validator) failed 7, 1 and 2 tests
respectively.

## Local development

No Homebrew and no sudo on the development machine. Portable toolchain in
`~/devtools`: Node, PostgreSQL 16 (port 5433), Python 3.12, CMake, Foundry,
kubo (IPFS).

```bash
# database
pg_ctl -D ~/devtools/pgdata -o "-p 5433" start
# chain
anvil
# ipfs
IPFS_PATH=~/devtools/ipfs-repo ipfs daemon
# backend
cd backend && uvicorn app.main:app --reload
# frontend
cd frontend && npm run dev
```

## Demonstration dataset

`backend/generate_dataset.py` produces 500 users and ~8,400 clinical records in
37 seconds. Only names and clinical content are synthetic — every key is a
genuine ML-KEM/ML-DSA keypair and every encrypted column is really encrypted.
`--reset` removes only generated accounts, scoped by their
`@quantumcare-demo.invalid` marker.
