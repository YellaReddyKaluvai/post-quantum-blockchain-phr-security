# 4. Architecture Validation

Claims verified by observation against a running system — not inferred from the
code that was supposed to produce them.

## Cryptography

| Check | Method | Result |
|---|---|---|
| ML-KEM key round trip | Encapsulate, decapsulate with the stored private key | 32-byte match |
| ML-DSA signature | Sign a digest, verify with the public key | valid |
| ML-DSA tamper detection | Verify against an altered digest | rejected |
| Mechanism authenticity | Measure stored key sizes | 1,184 / 1,952 / 3,309 bytes — exact FIPS 203/204 |
| Placeholder keys | Scan all 515 accounts | 0 found |

## Storage & integrity

| Check | Method | Result |
|---|---|---|
| Clinical text at rest | Search the database for a condition name | 0 rows of 810 |
| Bucket contents | Scan every S3 object for plaintext markers | ciphertext only |
| Object keys resolve | `head_object` on every recorded key | 795 / 795 |
| Disaster recovery | Rebuild a report from the S3 copy alone | valid PDF |
| Database tamper | Rewrite `document_hash`, then verify | integrity alert raised |
| Chain unavailable | Stop the node, then anchor | labelled `local-simulated` |
| IPFS round trip | Pin ciphertext, retrieve by CID | byte-identical |

## Authorization

| Check | Result |
|---|---|
| Cross-role probes across all endpoints | 224 / 224 refused |
| 5xx sweep across 56 endpoints, 5 roles | none |
| Unrelated doctor reads a chart | `403` |
| Access request pending / rejected / approved | `403` / `403` / `200` |
| Another patient decides a request | `404` |
| Consent revocation on an existing report | `200` → `404` |
| Break-glass after revocation | access restored, anchored |

## AI security

| Check | Result |
|---|---|
| Insider pattern — 140 charts at 03:00, 11 failed sign-ins | 85.42 **HIGH** |
| Nineteen ordinary clinicians in the same run | all **LOW** |
| Alert and escalation | `ESCALATE`, incident `INC-2026-00001` |
| Forged peer signature | rejected `401` |
| Poisoned peer parameters | rejected `400` |

## Why the refusals are the important results

Confirming that a valid report verifies proves very little on its own — a
function that always returned *true* would pass that test. The meaningful
results above are the ones where the system correctly **refused**: the tampered
digest, the missing object, the wrong role, the stopped chain, the forged
signature.

## A note on method

The cloud module was declared finished once before it actually was. Re-checking
it rather than trusting that conclusion is what surfaced unencrypted imaging
uploads, plaintext doctor documents, and an IPFS link that had never resolved.
Each was found by reading back what was actually stored, not by reading the code
that stored it. Where this document says a thing is verified, that is the
standard applied.
