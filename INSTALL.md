# Installation guide

This guide runs PostgreSQL and the Python API in Docker, with the Next.js
frontend on your host. The backend image builds liboqs, avoiding a separate
native cryptography installation. Use fictional data for demonstrations.

## Prerequisites

- Git and Python 3 (for generating local secrets).
- Docker Engine/Desktop with Compose v2, running Linux containers.
- Node.js 22 and npm, matching frontend CI.
- Free ports 8000 and 3000. PostgreSQL stays on Docker's internal network.
- Internet access for the first dependency and image builds.

## 1. Clone

```sh
git clone https://github.com/YellaReddyKaluvai/post-quantum-blockchain-phr-security.git
cd post-quantum-blockchain-phr-security
```

Run the following commands from this root unless stated otherwise.

## 2. Generate fresh local configuration

Compose reads `.env` in the repository root. This differs from `backend/.env`,
which a native Python process reads. This command refuses to replace an
existing file and does not print secrets:

```sh
python3 - <<'PYCONFIG'
import os
import secrets

values = {
    "DB_PASSWORD": secrets.token_hex(24),
    "SECRET_KEY": secrets.token_urlsafe(48),
    "ENCRYPTION_KEY": secrets.token_hex(16),
    "CONSENT_LEDGER_KEY": secrets.token_urlsafe(48),
    "NEXT_PUBLIC_BACKEND_URL": "",
    "SESSION_COOKIE_SECURE": "false",
    "SESSION_COOKIE_SAMESITE": "lax",
    "BLOCKCHAIN_RPC_URL": "",
    "IPFS_API_URL": "",
}
fd = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as file:
    file.write("".join(f"{key}={value}\n" for key, value in values.items()))
print("Created private .env; preserve it with your database backups.")
PYCONFIG
```

`ENCRYPTION_KEY` is exactly 32 characters, matching the current application
format. Preserve it once data exists. Changing `DB_PASSWORD` here does not
change the password in an already-initialized PostgreSQL volume. Do not commit
`.env`, keys, database dumps or generated account lists.

## 3. Start PostgreSQL and the API

```sh
docker compose up -d --build db backend
docker compose ps
docker compose logs --tail=50 backend
curl --fail http://localhost:8000/api/health
```

The first build compiles liboqs and can take several minutes. Expected health
response: `{"status":"ok"}`. The schema comes from `backend/db/init.sql`;
review logs for schema errors. Health is only a liveness check, so complete
the sign-in check below to verify database access too.

## 4. Create the first administrator

```sh
docker compose exec -e ADMIN_EMAIL=admin@example.com backend python seed_admin.py
```

Replace the example email with the intended administrator's email. With no
`ADMIN_PASSWORD` configured, this script generates a random password and
displays it once in your terminal. Save it privately with the printed User ID.
There is no universal administrator password. The script leaves an account
with the same email unchanged; running it again does not reset its password.

## 5. Start the frontend

In a second terminal, from the repository root:

```sh
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

If `.env.local` exists, inspect it instead of replacing it. The example sets
`BACKEND_ORIGIN=http://127.0.0.1:8000` and an explicitly empty
`NEXT_PUBLIC_BACKEND_URL`. Browsers request `/api/...` on the frontend origin;
Next.js forwards those requests to the API.

Open <http://localhost:3000> and sign in with the administrator **User ID**, not
email. Restart after environment changes; production builds must be rebuilt
because rewrites and public environment values are compiled in.

## 6. Verify the complete path

```sh
curl --fail http://localhost:3000/api/health
```

Register a fictional Patient at `/signup`. In the administrator Registrations
screen, approve that request and save the assigned User ID. Sign in as the
patient with that ID and the password chosen at registration. Confirm its
dashboard loads, then log out and confirm protected pages require sign-in.
Without SMTP, retrieve the assigned ID in the admin UI; do not rely on email.

## Tests

From the root with the backend running:

```sh
docker compose exec backend python -m pytest
cd frontend
npm run lint
node scripts/check-zkp.mjs
node scripts/check-vault.mjs
npm run build
```

Default backend tests may skip live integrations without opt-in flags and
services. The [CI workflow](.github/workflows/deploy.yml) defines the complete
integration setup, including disposable databases, chain, storage and browser
checks. Never point integration tests or dataset reset commands at production.

## Stop and resume

```sh
docker compose stop db backend
docker compose start db backend
```

Stop the frontend with Ctrl+C. Data remains in the `pgdata` volume.
`docker compose down --volumes` deletes that volume; it is not a normal restart.

## Optional integrations and troubleshooting

- **No chain, IPFS or S3:** supported baseline. Anchors can be local-simulated;
  a content identifier alone is not an IPFS copy. PostgreSQL stores the
  authoritative encrypted report copy.
- **Native Python setup:** use Python 3.12, `backend/requirements.txt`, the real
  liboqs library and `backend/.env.example`. Its example database port is 5433;
  change it for your server. Docker avoids the native library setup.
- **Connection refused:** inspect Compose status and API logs. Inside the
  backend container the database is `db:5432`, not localhost.
- **Login fails:** check schema errors, the assigned ID and approval status.
  A pending registration cannot log in.
- **Browser calls another computer's localhost:** keep
  `NEXT_PUBLIC_BACKEND_URL` explicitly empty and rebuild/restart the frontend.
- **Existing encrypted database:** preserve its encryption and ledger keys;
  do not generate replacement keys. See [migration guidance](DEPLOY.md).

See [the documentation index](docs/README.md) for architecture, IAM, federation
and schema details.
