# Running the federation on three machines

Federated learning is implemented and runs on every push to this repository
(three servers, three databases, two training rounds). The only thing CI cannot
supply is *independence*: all three of its hospitals are ours. This guide puts
the same protocol on three real machines, which is as close to a real
federation as you can get without another institution.

**Three machines, not two.** Two is the minimum the protocol accepts
(`real_nodes >= 2`), but with two nodes a dishonest hospital can only be
*capped*, never excluded — there is no majority to judge it against. At three,
the outlier rule in `federated_classifier.aggregate` sets a poisoned update
aside and names it in the round report. That is the thing worth demonstrating.

The hub trains on its own data too, so three machines means **hub + two
participants**, not hub + three.

```
   Hospital A  (participant)  ─┐
                               ├──►  Hospital B  (hub)  ──► global model ──┐
   Hospital C  (participant)  ─┘                                           │
          ▲                                                                │
          └──────────────── pull, evaluate locally, adopt ◄────────────────┘
```

---

## 1. What each machine needs

- Docker and Docker Compose
- This repository
- All three on the same network, able to reach each other by IP
- One free port each for 3000 (dashboard) and 8000 (API)

Find each machine's address once and write them down:

```bash
hostname -I | awk '{print $1}'        # Linux
ipconfig getifaddr en0                 # macOS
```

This guide calls them `A_IP`, `B_IP` (the hub) and `C_IP`.

---

## 2. Set up each machine

Do this on **all three**, changing only the names.

### Generate that hospital's own secrets

Each hospital is a separate institution: it must **not** share keys with the
others. Generate a fresh set on every machine.

```bash
cd Pqc_implementation
cp backend/.env.example .env
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> .env
python3 -c "import secrets; print('ENCRYPTION_KEY=' + secrets.token_hex(16))" >> .env
python3 -c "import secrets; print('CONSENT_LEDGER_KEY=' + secrets.token_urlsafe(32))" >> .env
printf 'ADMIN_EMAIL=admin@hospital-b.example\nDB_PASSWORD=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(16))')" >> .env
```

`ENCRYPTION_KEY` must be exactly 32 characters — `token_hex(16)` gives that.
Compose refuses to start without `SECRET_KEY` and `ENCRYPTION_KEY`, deliberately:
unset, the application would fall back to a key published in this repository.

### Start it

```bash
docker compose up --build -d
docker compose exec backend python seed_admin.py
```

`seed_admin.py` prints the administrator's User ID and, if you did not set
`ADMIN_PASSWORD`, a generated password **shown once**. Write both down.

Open `http://<that machine's IP>:3000` from any machine on the network and sign
in. The dashboard reaches the API through its own origin, so it works from
another laptop — you do not need to be sitting at the machine.

---

## 3. Wire the federation

### On the hub (Hospital B): register the other two

Admin → **Federation Peers** → *Register a peer*.

Do it twice, with node names `hospital-a` and `hospital-c`. Each registration
shows a 64-character secret **once**. Copy each one to the machine it belongs
to, over something you trust — not a group chat.

### On each participant (A and C): join

Admin → **AI Security** → *Federated IDS* → fill in:

| Field | Value |
|---|---|
| Hub URL | `http://B_IP:8000` |
| Node name | `hospital-a` (or `hospital-c`) — exactly as registered |
| Shared secret | the one the hub issued for that name |

The panel warns if the hub URL is plain `http://`. On a closed lab network that
is acceptable — every message is signed either way, so nothing can be altered
unnoticed; what is exposed is the model parameters themselves. For anything
public, put the hub behind HTTPS.

### Turn on differential privacy

On each participant, in `.env`:

```
FEDERATION_DP_EPSILON=1.0
FEDERATION_DP_TOTAL_EPSILON=10.0
```

Then `docker compose up -d`. Without the first, the panel correctly reports
that no privacy guarantee holds. The second caps the total spend across all
rounds, after which the hospital shares baselines only.

---

## 4. Give each hospital something to learn from

A hospital trains a classifier from **its own investigated incidents**. The
threshold is in `federated_classifier.py`:

> at least **6 closed incidents**, with at least **2 of each verdict**
> (confirmed threat / false positive)

Below that, that hospital contributes behaviour baselines but no classifier
weights — correct behaviour, not a fault. A classifier fitted to three examples
would teach the federation noise.

On **each** machine, as an administrator:

1. Admin → AI Security → *Run Analysis*, so risk assessments and alerts exist.
2. Open each incident, close it, and set a **verdict**.
3. Aim for ~10 incidents per hospital with a mix of both verdicts.

Give the three hospitals *different* patterns — that is the entire point. One
with insider-style record sweeps, one with out-of-hours access, one with
repeated refused attempts. The federated model should end up better than any of
them alone, and you can show that.

---

## 5. Run a round

1. **A and C:** AI Security → *Train & submit local update*. The response says
   how many labels were used and whether noise was applied.
2. **B (hub):** AI Security → *Run federated round*. Check the report: it should
   say **2 real peers, 0 simulated**, and name the contributing nodes.
3. **A and C:** *Pull & evaluate global model*. Each evaluates it against its
   own data and adopts it only if detection does not get worse.

Repeat for a second round — each hospital now trains starting from the global
weights, which is what makes it federated learning rather than one average.

To automate: `FEDERATION_ROUND_INTERVAL_MINUTES=10` on the hub,
`FEDERATION_SYNC_INTERVAL_MINUTES=10` on the participants.

---

## 6. What to show in a viva

| Claim | Where to show it |
|---|---|
| Three independent deployments | Three machines, three databases, three key sets |
| Only parameters cross the boundary | Hub database: `SELECT COUNT(*) FROM SecurityLabels` is **0**; `FederatedRounds.local_parameters` holds medians and weights, no names |
| Robust aggregation | Round report: `baselines_capped`, `baselines_excluded`, `classifier_excluded` |
| A poisoned hospital is excluded | Suspend one peer mid-demo, or let a node submit wild values — with 3 nodes it is set aside |
| Differential privacy | Classifier panel: ε spent so far, composed across rounds, against the budget |
| A bad model is not adopted | The adoption gate refuses a global model that would make local detection worse |
| Detection actually uses it | Status: `LIVE_FEDERATION`, and "Detection is scoring against: hub round N" |

---

## 7. When it does not work

| Symptom | Cause |
|---|---|
| Compose exits with "set SECRET_KEY in .env" | Working as intended — generate the keys in step 2 |
| Participant: 502 on submit | The hub is unreachable. `curl http://B_IP:8000/api/health` from that machine; check the firewall on port 8000 |
| Participant: 401 | Node name or secret does not match what the hub registered. Rotate the secret on the hub and re-join |
| Participant: 403 | That peer is suspended on the hub |
| Participant: 409 on submit | A submission for that round was already accepted — replay protection. Wait for the next round |
| Hub: "0 real peers, 3 simulated" | Nobody has submitted yet. Simulated peers only pad a round before the first real one, and never score anyone |
| Submit says "baselines only" | Fewer than 6 investigated incidents, or fewer than 2 of one verdict |
| Dashboard loads, every call fails | You pointed `NEXT_PUBLIC_BACKEND_URL` at `localhost`. Leave it unset so the browser calls `/api` on the host that served the page |

---

## Honest limits

- Three machines you own is **not** a federation of independent institutions.
  It proves the protocol and the privacy boundary; it does not prove other
  institutions will join. Say that in the report.
- To make it literally true, one node has to be run by someone else — another
  project group or department is enough, and the setup above is all they need.
- The `docker-compose.yml` fixes behind this guide were derived from the code
  but have not been run here (no Docker on the authoring machine). The
  federation protocol itself is exercised on every CI run.
