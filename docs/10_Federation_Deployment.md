# Federated learning: one computer first, then three laptops

The system trains a security threat classifier from investigated incidents.
It does **not** train a diagnosis model on patients' medical documents. Each
hospital keeps its events, feature examples and labels locally. Only signed
baseline parameters, classifier weights and sample counts cross the federation
boundary. The existing post-quantum document pipeline remains separate; the
federation protocol uses per-peer HMAC-SHA256, not ML-DSA signatures or secure
aggregation.

## Architecture

| Laptop | Role | Local data |
|---|---|---|
| A | Training participant `hospital-a` | Its own database, labels and keys |
| B | Hub **and** training participant | Its own database, labels and keys |
| C | Training participant `hospital-c` | Its own database, labels and keys |

There are three trainers in total; a fourth coordinator machine is unnecessary.
A and C discover B's signed open round and global classifier, train locally,
and send signed updates. B trains from the same previous classifier and performs
sample-weighted robust FedAvg. A and C pull and locally evaluate the result.
The adoption gate decides which model scores activity; the next training round
always starts from the newest global weights, even if detection retained an
older model.

The prepared lab uses `FEDERATION_LOCAL_EPOCHS=10` to limit local drift when
institutions have different training distributions. Full local-only reference
models still fit for 200 epochs. Existing deployments keep 200 local epochs
unless explicitly configured; the setting accepts 1–1000. All participating
lab nodes should use the same setting.

The prepared lab sets `FEDERATION_REQUIRE_FRESH_UPDATES=true` and
`FEDERATION_MIN_PEERS=2`. B refuses to finish until both participants submit to
the current round. No old updates or simulated peers fill a missing laptop's
place. Duplicate submissions and submissions to completed rounds are rejected.
Concurrent aggregation/submission is serialized with a PostgreSQL transaction
lock. Default deployments retain the older carry-forward aggregation policy
unless strict mode is enabled; closed rounds are immutable in either mode.

## Before connecting laptops: test on one computer

Install Git, Python 3.10+ and Docker with Docker Compose v2 (Docker Desktop on
Windows/macOS). Run these commands from the repository root. On Windows use
`py` instead of `python` if necessary.

```sh
git clone https://github.com/YellaReddyKaluvai/post-quantum-blockchain-phr-security.git
cd post-quantum-blockchain-phr-security
# Until the implementation PR is merged:
git switch feat/three-laptop-federated-learning
python scripts/federation_lab.py local --rounds 3
```

The first build compiles liboqs and the frontend and can take several minutes.
This command creates three isolated Compose projects (each with API, frontend,
PostgreSQL, network and volume), generates independent keys/passwords, seeds
fictional local data, registers peers, and runs three HTTP training rounds.
It needs enough memory/disk for three copies of the application. It connects the API containers to a shared Docker network using the hostname
`hospital-b`; the three databases stay on their separate private networks.

| Node | Dashboard | API |
|---|---|---|
| A | http://localhost:3101 | http://localhost:8101 |
| B | http://localhost:3102 | http://localhost:8102 |
| C | http://localhost:3103 | http://localhost:8103 |

Admin IDs are printed during seeding. Passwords are in each
`lab-data/<node>/.env` (`ADMIN_PASSWORD`). The runner also writes private
`login.json` files. `lab-data/` is ignored by Git: do not publish its credentials.

Each node gets 80 synthetic training examples concentrating on a different
threat pattern (record sweeps, unusual hours, or repeated access failures), and
120 newly generated validation examples covering all three patterns. Validation
lives in `FederatedValidationLabels`, which training never queries. The seed
command requires explicit lab mode and refuses populated databases (an unused
bootstrap administrator is allowed so interrupted setup can resume).
It never imports real PHRs. Use these deployments only as disposable labs.

A measured three-round run is checked in as
[JSON](federation-results/three-node-synthetic.json) and
[CSV](federation-results/three-node-synthetic.csv). It used three Docker APIs and
three PostgreSQL containers on one machine, 10 local epochs per round, and no DP
noise. Candidate validation accuracy changed from local-only 66.7% to 79.2%,
80.8%, and 79.2% at B/A/C respectively. B and C adopted round 3; A's in-sample
adoption check rejected it, so A continued scoring with its local model.
The global weight hash agreed across all three sites and changed every round.
Each database retained exactly 80 training and 120 validation rows after sharing.
These are reproducible synthetic experiment results, not three physical laptops.

Results are saved after the baseline and every completed round:

- `lab-data/results.json`: per-node accuracy, precision, recall, F1, log loss,
  confusion counts, candidate global metrics and weight hash, adopted model,
  round duration and aggregation exclusions.
- `lab-data/results.csv`: round-by-round comparison for a spreadsheet/chart.
- Admin → **AI Security → Federated IDS**: fresh-update count, round, contributors,
  model in use, candidate global model, separate validation comparison, and model rollback controls.
  Federation state refreshes every ten seconds.

A lower log loss indicates better probability estimates even when accuracy is
unchanged. Improvements are measured, not guaranteed: heterogeneous data,
aggregation exclusions and privacy noise can reduce performance. These synthetic
results demonstrate distributed training, not clinical accuracy or performance
on independent hospitals. Training-fit accuracy and the existing adoption gate
are in-sample checks; only the separate validation metrics are holdout results.
Repeated validation during model selection is not a final blind test set.

To repeat rounds without resetting databases:

```sh
python scripts/federation_lab.py run --rounds 3
```

If setup was interrupted, use `start`, `seed` (only if still empty), `wire` and
`run` to continue. `prepare` refuses to overwrite keys. If registration succeeded
but joining failed, the hub UI can rotate the peer secret so you can join through
the participant UI; the runner never silently rotates an existing peer's key.
If the local run stopped before writing `experiment.json`, create it using the
three `login.json` files in the format below; use API ports 8102/8101/8103 and
`http://hospital-b:8000` as each participant's `hub_url`.
Run `python scripts/federation_lab.py link-local` after recreating local containers
so their API network connections are restored.

## Prepare the real laptops independently

**The laptops do not need to be connected yet.** Clone/check out the same branch
on all three. On A run:

```sh
python scripts/federation_lab.py prepare --node a
python scripts/federation_lab.py start --node a
python scripts/federation_lab.py seed --node a
```

On B use `--node b`; on C use `--node c`. Without `--local-ports`, every laptop
uses API port **8000** and dashboard port **3000**. Each generates its own
credentials and database. Do not copy another laptop's `.env`, volume or keys.
The seed step is for a synthetic demonstration only. For existing hospitals,
use their actual investigated incident labels and the normal administrator
setup instead; do not enable lab seeding on those databases. All nodes must
upgrade together because the participant now requires `/api/federated/round-state`.

## Connect all three laptops now

**This is the point when the physical laptops must be connected.** Preparation,
building and local seeding can finish first. Joining peers and running a
cross-laptop round require simultaneous connectivity.

1. Connect A, B and C to the same trusted Wi-Fi/Ethernet LAN. Avoid guest Wi-Fi
   with client isolation. Keep B awake. Synchronize all clocks (signatures allow
   at most five minutes of skew).
2. Find B's LAN IPv4 address: `ipconfig` on Windows, `ipconfig getifaddr en0` on
   macOS, or `hostname -I` on Linux. For example, `192.168.1.20`.
3. Permit inbound TCP **8000 on B** from A and C on the private network. For
   dashboard access from another laptop allow **3000** on that laptop. Do not
   expose PostgreSQL; Compose keeps it internal. No router port forwarding is
   needed. The optional centralized runner also needs APIs 8000 on A and C.
4. If an HTTP proxy is configured on your laptops, append B's IP to `FEDERATION_NO_PROXY`
   in A/C's `lab-data/<node>/.env` and run `start` again before joining.
   From A and C open `http://B_IP:8000/api/health`. From a browser on each laptop
   open its own `http://localhost:3000`. Plain HTTP is for the synthetic trusted
   lab; use HTTPS or a private encrypted tunnel for sensitive deployments.
5. On B: Admin → **Federation Peers** → register `hospital-a` and `hospital-c`.
   Each secret is shown once. Give it only to the corresponding participant.
6. On A/C: Admin → **AI Security → Federated IDS** → join with hub URL
   `http://B_IP:8000`, matching node name and its issued secret.
7. On A/C: **Train & submit local update**. On B wait for **2/2 fresh updates**,
   then **Run Round**. On A/C: **Pull & evaluate global model**.
8. Repeat steps 7 for at least three rounds. Compare the local-only validation
   metrics with the currently used model on each dashboard.

You have now tested real network communication across three laptops. Three
machines belonging to one project still do not establish independent institutions.

### Optional automated cross-laptop experiment

Instead of registering peers manually, create `lab-data/experiment.json` on
one trusted computer with the following shape (replace every placeholder):

```json
{
  "hub": {"name": "hospital-b", "url": "http://B_IP:8000", "user_id": "B_ADMIN_ID", "password": "B_ADMIN_PASSWORD"},
  "a": {"name": "hospital-a", "url": "http://A_IP:8000", "user_id": "A_ADMIN_ID", "password": "A_ADMIN_PASSWORD", "hub_url": "http://B_IP:8000"},
  "c": {"name": "hospital-c", "url": "http://C_IP:8000", "user_id": "C_ADMIN_ID", "password": "C_ADMIN_PASSWORD", "hub_url": "http://B_IP:8000"}
}
```

Keep this file private: it grants administrator access to all three labs. Run:

```sh
python scripts/federation_lab.py wire --config lab-data/experiment.json
python scripts/federation_lab.py run --config lab-data/experiment.json --rounds 3
```

The runner orchestrates admin API calls; raw training/validation data remains on
each laptop. It collects model metrics only. If a laptop is offline it stops
with an error and preserves completed results. Retrying `run` reuses an already
accepted submission for the currently open round.

## Verify dropout handling and privacy boundaries

- Submit from A only, then press Run Round on B: expect HTTP 409 and a message
  waiting for two fresh peers. Submit from C and retry: the round completes.
- Re-submit from the same node before aggregation: the duplicate is refused.
- Stop C after a completed round: B must not count its previous update as fresh.
- On each lab database, `SecurityLabels` remains 80 rows and
  `FederatedValidationLabels` remains 120. B also has its **own** labels; a hub
  with zero labels is not required and would not train a third classifier.
- The global model should report three classifier contributors; check exclusions
  separately. Suspending a node is an authorization test, not proof that the
  statistical outlier rule detected poisoning.

For automatic background rounds, set `FEDERATION_ROUND_INTERVAL_MINUTES=1` on B
and `FEDERATION_SYNC_INTERVAL_MINUTES=1` on A/C in their lab `.env` files, then
`start` each affected node. Keep the manual runner off while schedulers run.
Strict quorum prevents partial rounds. The privacy ledger accounts for classifier
noise when configured; baseline summaries are **not** differentially private,
and raw-data locality alone is not a formal privacy guarantee. The synthetic
experiment leaves DP noise off so the measured learning changes are repeatable.

## Troubleshooting and shutdown

| Symptom | Check |
|---|---|
| Cannot reach hub health endpoint | LAN IP, firewall, Wi-Fi isolation, B asleep, backend health |
| 401/403 on model exchange | Exact node name, active peer, shared secret, clock skew |
| 409 waiting for updates | Submit on both A and C for the current round; old updates do not count |
| 409 duplicate/closed round | Aggregate then start the next round; do not overwrite history |
| Baselines only | At least 6 training labels and 2 of each verdict are required |
| No validation dataset | Expected on existing deployments; do not label training fit as holdout accuracy |
| Dashboard API fails | Rebuild frontend; the Docker build must use `BACKEND_ORIGIN=http://backend:8000` |
| Global model not adopted | Read the local evaluation reasons; the prior model remains in use |
| Seed refused | It protects nonempty databases; use a fresh lab project, never clear patient data |

```sh
python scripts/federation_lab.py status --node b
python scripts/federation_lab.py stop --node a
python scripts/federation_lab.py stop --node b
python scripts/federation_lab.py stop --node c
```

Stop retains volumes and keys. Do not run `down -v` unless you intentionally
want to delete that disposable lab's database. For automated regression tests,
see `backend/tests/test_federation_experiment.py`, `test_federation_hub.py`, and
the existing opt-in three-hospital `test_federation_live.py`.
