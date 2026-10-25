# Deploy QuantumCare: Vercel + Render

The hosted demonstration uses one public Vercel frontend URL, a Render Docker
API and Render PostgreSQL. The backend is **Python/FastAPI**, not Node.js.

- Frontend: <https://post-quantum-blockchain-phr-securit.vercel.app>
- API health: <https://quantumcare-api.onrender.com/api/health>
- Local setup: [INSTALL.md](INSTALL.md)

## 1. Provision the database

Create PostgreSQL in the same Render workspace and region as the backend.
The current hosted instance uses PostgreSQL 18. Keep its **internal connection
URL** in Render's secret settings; do not put it in Git or frontend variables.
External database access can remain blocked for normal application operation.

For a fresh empty database, the API initializes `backend/db/init.sql`.
For an existing database, follow the migration section before starting the API.

## 2. Create the Render API

Connect this repository and use:

| Setting | Value |
|---|---|
| Branch | `main` |
| Runtime | Docker |
| Dockerfile | `./backend/Dockerfile` |
| Docker context | `./backend` |
| Health check | `/api/health` |
| Region | Same as PostgreSQL |

The image compiles liboqs 0.16.0 and checks ML-KEM-768 / ML-DSA-65 availability.
The first build takes several minutes; later builds reuse cached layers.

Set these environment variables privately in Render:

| Variable | Value or rule |
|---|---|
| `DATABASE_URL` | Internal hosted PostgreSQL connection URL |
| `SECRET_KEY` | Stable random secret, at least 32 characters |
| `ENCRYPTION_KEY` | Stable secret of exactly 32 characters; preserve for existing data |
| `CONSENT_LEDGER_KEY` | Stable independent random secret; preserve existing ledger references |
| `ADMIN_EMAIL` | Initial administrator's email |
| `ADMIN_PASSWORD` | Private random password of at least 12 characters |
| `CORS_ORIGINS` | Exact HTTPS frontend origin |
| `SESSION_COOKIE_SECURE` | `true` |
| `SESSION_COOKIE_SAMESITE` | `lax` for the frontend proxy setup |
| `BLOCKCHAIN_ENABLED` | `false` for the baseline without a hosted chain |
| `IPFS_API_URL` | Empty without an IPFS node |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET` | Empty without S3 |
| `SMTP_HOST` | Empty without a mail server |

For a fresh database, create the first administrator before serving requests.
The current service uses this **Render Docker Command** (Render's field format;
not a shell command to paste into your terminal):

```text
/bin/sh -c python seed_admin.py && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

The seed script leaves an existing account with the same email unchanged.
Record its printed User ID; login uses that ID, not email. `ADMIN_PASSWORD`
is used at account creation and changing that setting does not reset an
existing user's password. Do not publish administrator credentials.

## 3. Connect the existing Vercel project

Use the repository's `frontend` directory as the Next.js project root. For an
existing frontend, update that project rather than creating another one.

Set **Production** environment variables:

```dotenv
BACKEND_ORIGIN=https://quantumcare-api.onrender.com
NEXT_PUBLIC_BACKEND_URL=
```

Substitute your API URL for a different deployment. The second variable must
be explicitly empty: leaving it absent falls back to localhost in the client.
Redeploy after setting either value. `next.config.ts` builds the `/api/:path*`
rewrite, and public environment values are compiled into the browser bundle.

Users visit the frontend URL only. Browser requests and session cookies stay
on that origin; Vercel forwards API traffic to Render. Keep database and
cryptographic secrets exclusively on the backend.

## 4. Verify before handing over

```sh
curl --fail https://quantumcare-api.onrender.com/api/health
curl --fail https://post-quantum-blockchain-phr-securit.vercel.app/api/health
```

Both should return `{"status":"ok"}`. This alone does not prove database access.
Verify administrator login, dashboard data, Secure/HttpOnly session cookies,
logout and rejection of unauthenticated administrator API requests. Register
and approve a fictional patient, then verify its login too. Review service logs
for database, schema or cryptography errors.

These sign-in/session/database checks were performed on the hosted baseline
on 24–25 October 2026. This does not establish that every clinical workflow or
optional integration has been tested on that deployment.

## Migrating an existing PostgreSQL database

1. Confirm the correct source host/database and inspect schema and table counts.
   A database name alone does not show whether application records exist.
2. Take a private backup with a PostgreSQL client compatible with the source
   version. Store credentials in a password prompt or protected credential
   file, never committed commands or documentation.
3. Preserve the effective `ENCRYPTION_KEY` and `CONSENT_LEDGER_KEY`, and any
   external S3/IPFS objects. A database dump does not include those services
   or a local blockchain's state.
4. Restore into a new empty hosted database using `pg_restore --no-owner
   --no-privileges --exit-on-error`. Arrange the provider's supported access
   method; keep any temporary network access restricted and remove it afterward.
5. Compare schema and row counts and verify authenticated reads and decryption.
   Stop application writes for the final cutover, or plan a consistent final
   export. Preserve the source until the destination has been verified.

The local `pqc_hospital` inspected during this deployment contained no
application tables or records. There were no records to restore, so the hosted
schema was initialized with fresh keys. Do not infer that another database is
empty or regenerate keys for a populated database.

## Optional capabilities and limits

| Capability | Hosted baseline |
|---|---|
| Post-quantum libraries and PostgreSQL | Enabled |
| Real blockchain anchoring | Disabled; local-simulated anchors are not on-chain proof |
| IPFS publishing | Not configured; a CID alone is not a pinned copy |
| S3 secondary copies | Not configured; database copy remains authoritative |
| SMTP delivery | Not configured; do not rely on approval emails |

Real blockchain operation needs a reachable EVM RPC, chain ID, deployed
`PHR_Security` contract and funded private signer. The backend-only image does
not include `contracts/out/PHR.sol/PHR_Security.json`; supply the artifact and
contract configuration before enabling the integration. Never use the public
Anvil development key on a real network. See the blockchain section of the
[README](README.md) and the [architecture guide](docs/1_Architecture_Proof.md).

Free Render services can sleep when idle, delaying the next request. The
current free PostgreSQL instance expires **23 November 2026**; arrange an
upgrade or a verified migration before then. Confirm current dates and plans
in the provider dashboard. Do not treat the demo as permanent data storage.

## Existing all-Render blueprint

`render.yaml` describes a separate three-service layout and would also create
a Render frontend. It is not the configuration used by the existing Vercel
site. Review it before reuse, including secrets, secure cookies, administrator
setup and the frontend's **build-time** backend origin. A runtime-only
`BACKEND_ORIGIN` change cannot repair an already-compiled Next.js rewrite.

The [local installation guide](INSTALL.md) deliberately runs the frontend on
the host so its proxy destination is set before compilation. The all-Render
blueprint and all-container frontend path were not revalidated during the
Vercel deployment. Do not run the demo dataset generator over production data.

## Provider references

- [Render Docker services and command format](https://render.com/docs/docker)
- [Render PostgreSQL connections](https://render.com/docs/postgresql-creating-connecting)
- [Vercel rewrites](https://vercel.com/docs/rewrites)
