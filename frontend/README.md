# QuantumCare frontend

Next.js App Router frontend for Patient, Doctor, Nurse, Lab Technician and
Administrator portals. Pages live in `src/app`, shared UI in `src/components`,
and API/session utilities in `src/lib`.

Follow [INSTALL.md](../INSTALL.md) to start the database and API. From this directory:

```sh
cp .env.example .env.local
npm ci
npm run dev
```

Keep `NEXT_PUBLIC_BACKEND_URL` explicitly empty for same-origin `/api` requests.
`BACKEND_ORIGIN` selects the API destination in `next.config.ts`. Never put
server secrets in `NEXT_PUBLIC_*`. Production environment changes require a new build.

```sh
npm run lint
node scripts/check-zkp.mjs
node scripts/check-vault.mjs
npm run build
npm start
```

Use Node.js 22 as in CI. See [deployment](../DEPLOY.md) for Vercel and Render,
and [contribution guidance](../CONTRIBUTING.md) before making changes.
