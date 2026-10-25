# Demonstration scripts

Run from `backend/` with the virtualenv active.

## Post-quantum verification

```bash
python3 demo/prove_pqc.py
```

Six sections, every figure measured at run time:

1. liboqs genuinely provides ML-KEM-768 and ML-DSA-65, and the legacy names
   `Kyber768` / `Dilithium3` are confirmed absent
2. Generated key sizes checked against the published FIPS 203/204 parameters
3. A live ML-KEM encapsulation round trip
4. A live ML-DSA signature, **and** rejection of a tampered digest
5. AES-256-GCM under an ML-KEM-derived key, **and** rejection of altered ciphertext
6. The live database: key sizes, signature sizes, and how many reports use each
   algorithm

The refusals in 4 and 5 matter more than the successes: a verifier hardcoded to
return true would pass every positive test.

## Making a zero-knowledge consent proof

```bash
python demo/zkp_prove.py --token "mlwe1:…" --challenge <challenge> \
    --context "consent:<patient_id>" --commitment "mlwe1:…" > proof.json
```

The doctor-side prover for the post-quantum consent proof. The token comes from
`GET /api/doctor/consent-token/{patient_id}` (delivered once); the challenge and
context from `POST /api/doctor/zkp/challenge`. The printed JSON is the body for
`POST /api/doctor/zkp/verify`. With `--commitment` the proof is checked locally
first and nothing is printed if it would fail. Needs no database, no liboqs and
no network; set `QUANTUMCARE_CONSENT_TOKEN` instead of `--token` to keep the
token out of shell history.

## Prerequisites for the blockchain demo

Anvil is ephemeral — restarting it wipes the deployed contract, after which new
anchors fall back to `local-simulated`. Redeploy after every anvil restart:

```bash
anvil                                   # terminal 1
forge create contracts/PHR.sol:PHR_Security \
  --rpc-url http://127.0.0.1:8545 \
  --private-key <anvil account 0 key> --broadcast
```

The address is deterministic for that account's first deployment, so it matches
`BLOCKCHAIN_CONTRACT_ADDRESS` in `.env` without editing anything.

## Full hosted demonstration

See [WORKING_DEMO.md](WORKING_DEMO.md) for the five-role deployed workflow,
captioned-video submission requirements and the command to regenerate measured
results and a sample PDF. `run_hosted_demo.py` uses only Python's standard
library, requests the administrator password privately, and saves generated
account credentials outside the public evidence bundle.
