# Deploying to Render

Three services from one blueprint: PostgreSQL, the FastAPI backend, and the
Next.js frontend.

## What runs, and what does not

| | In this deployment |
|---|---|
| Post-quantum crypto | ✅ ML-KEM-768 and ML-DSA-65, compiled from source in the image |
| Encryption at rest | ✅ AES-256-GCM and AES-256-CBC |
| All five portals | ✅ |
| AI security layer | ✅ |
| Zero-knowledge consent proofs | ✅ |
| **Blockchain anchoring** | ❌ No chain is reachable, so anchors are recorded as `local-simulated` |
| **IPFS publishing** | ❌ No node, so a content address is computed and nothing is pinned |
| **AWS S3** | ⚪ Optional — add credentials in the dashboard to enable |
| **Email** | ⚪ Optional — add SMTP credentials to enable |

The application reports each absent capability rather than implying it is
present. The admin dashboard shows storage and chain status honestly.

## Steps

1. **Push the blueprint** (already in the repository root as `render.yaml`).

2. **On Render**: New → Blueprint → connect this repository. Render reads
   `render.yaml` and creates all three services.

3. **Wait for the first backend build — 10 to 15 minutes.** liboqs has no wheel
   and is compiled from source. Later builds reuse that layer and take about a
   minute.

4. **Seed the database.** It starts empty. From the backend service's Shell tab:

   ```
   python3 generate_dataset.py
   ```

   500 users and roughly 8,400 clinical records. Credentials are written to
   `dataset_credentials.csv` in that container; the shared password is printed
   at the end.

5. **Open the frontend URL** and sign in.

## Free tier: two things to plan around

**Services sleep after 15 minutes idle**, and the next request takes roughly
50 seconds to wake them. Before a live demonstration, open the URL a minute
beforehand so the panel does not watch a cold start.

**A free PostgreSQL instance expires after 30 days.** Note the date. Upgrading
the database, or redeploying and re-seeding, both avoid losing the demonstration
data.

## Environment variables Render sets for you

`DATABASE_URL`, `SECRET_KEY` and `ENCRYPTION_KEY` are generated automatically.

**Do not regenerate `ENCRYPTION_KEY` once data exists.** Columns encrypted under
one key cannot be read with another, and there is no recovery — the data becomes
permanently unreadable.

## Adding S3 later

Set `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_S3_BUCKET` in the
backend service's Environment tab. Reports written after that get a cloud copy;
existing ones keep `s3_key` as NULL, which is recorded truthfully rather than as
a pointer to an object that was never written.
