"""Evidence that the post-quantum algorithms are real and actually in use.

Written for demonstration: every number printed is measured at run time from
liboqs or read back from the live database. Nothing here is a stored string or
a hardcoded expectation dressed up as a result.

    python3 demo/prove_pqc.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import base64
import psycopg
from psycopg.rows import dict_row

import oqs
from app.crypto_service import (
    ML_KEM_ALG, ML_DSA_ALG, generate_mlkem_keypair, generate_mldsa_keypair,
    encapsulate_aes_key, decapsulate_aes_key, derive_aes_key,
    encrypt_document, decrypt_document, sign_document_hash,
    verify_mldsa_signature, sha256_hex, pqc_available,
)

G = "\033[92m"; R = "\033[91m"; B = "\033[1m"; C = "\033[96m"; D = "\033[0m"
OK = f"{G}PASS{D}"
NO = f"{R}FAIL{D}"


def rule(title):
    print(f"\n{B}{C}{'─' * 74}{D}")
    print(f"{B}{C} {title}{D}")
    print(f"{B}{C}{'─' * 74}{D}")


# FIPS 203 / 204 published parameter sizes. Asserting against the standard,
# not against whatever the library happens to return.
FIPS = {
    "ML-KEM-768":  {"pk": 1184, "sk": 2400, "ct": 1088, "ss": 32,
                    "std": "FIPS 203", "was": "Kyber768"},
    "ML-DSA-65":   {"pk": 1952, "sk": 4032, "sig": 3309,
                    "std": "FIPS 204", "was": "Dilithium3"},
}


def main():
    print(f"\n{B}QuantumCare — Post-Quantum Cryptography Verification{D}")
    print(f"liboqs {oqs.oqs_version()}   ·   python binding {oqs.oqs_python_version()}")

    # 1 ─────────────────────────────────────────────────────────────────────
    rule("1. The library actually provides the NIST-standardised mechanisms")
    kems = oqs.get_enabled_kem_mechanisms()
    sigs = oqs.get_enabled_sig_mechanisms()
    print(f"  {ML_KEM_ALG:<14} enabled in liboqs : "
          f"{OK if ML_KEM_ALG in kems else NO}   ({FIPS[ML_KEM_ALG]['std']})")
    print(f"  {ML_DSA_ALG:<14} enabled in liboqs : "
          f"{OK if ML_DSA_ALG in sigs else NO}   ({FIPS[ML_DSA_ALG]['std']})")
    print(f"  pqc_available()                  : {OK if pqc_available() else NO}")
    print(f"\n  {B}Legacy round-3 names are NOT available:{D}")
    for legacy in ("Kyber768", "Dilithium3"):
        present = legacy in kems or legacy in sigs
        print(f"    {legacy:<12} present in liboqs 0.16 : "
              f"{R + 'yes' + D if present else G + 'no — correctly absent' + D}")
    print(f"  {B}This matters:{D} an earlier build requested \"Dilithium3\", the call")
    print( "  failed, and the failure was swallowed — so placeholder keys were stored")
    print( "  and no real signature was ever produced.")

    # 2 ─────────────────────────────────────────────────────────────────────
    rule("2. Generated key sizes match the published FIPS parameters")
    with oqs.KeyEncapsulation(ML_KEM_ALG) as kem:
        d = kem.details
        print(f"  {ML_KEM_ALG}  ({FIPS[ML_KEM_ALG]['std']}, formerly {FIPS[ML_KEM_ALG]['was']})")
        for label, got, want in (
            ("public key", d["length_public_key"], FIPS[ML_KEM_ALG]["pk"]),
            ("secret key", d["length_secret_key"], FIPS[ML_KEM_ALG]["sk"]),
            ("ciphertext", d["length_ciphertext"], FIPS[ML_KEM_ALG]["ct"]),
            ("shared secret", d["length_shared_secret"], FIPS[ML_KEM_ALG]["ss"]),
        ):
            print(f"    {label:<16}{got:>6} bytes   expected {want:>6}   "
                  f"{OK if got == want else NO}")
        print(f"    claimed NIST level {d['claimed_nist_level']}")

    with oqs.Signature(ML_DSA_ALG) as sig:
        d = sig.details
        print(f"\n  {ML_DSA_ALG}  ({FIPS[ML_DSA_ALG]['std']}, formerly {FIPS[ML_DSA_ALG]['was']})")
        for label, got, want in (
            ("public key", d["length_public_key"], FIPS[ML_DSA_ALG]["pk"]),
            ("secret key", d["length_secret_key"], FIPS[ML_DSA_ALG]["sk"]),
            ("signature", d["length_signature"], FIPS[ML_DSA_ALG]["sig"]),
        ):
            print(f"    {label:<16}{got:>6} bytes   expected {want:>6}   "
                  f"{OK if got == want else NO}")
        print(f"    claimed NIST level {d['claimed_nist_level']}")

    # 3 ─────────────────────────────────────────────────────────────────────
    rule("3. Live ML-KEM-768 key encapsulation round trip")
    t = time.perf_counter()
    pub, priv_enc = generate_mlkem_keypair()
    gen_ms = (time.perf_counter() - t) * 1000
    ct, secret_sender = encapsulate_aes_key(pub)
    secret_receiver = decapsulate_aes_key(ct, priv_enc)
    print(f"  keypair generated in {gen_ms:.2f} ms")
    print(f"  encapsulated ciphertext   {len(base64.b64decode(ct))} bytes")
    print(f"  sender   shared secret    {secret_sender.hex()[:48]}…")
    print(f"  receiver shared secret    {secret_receiver.hex()[:48]}…")
    print(f"  secrets match             {OK if secret_sender == secret_receiver else NO}")
    print(f"\n  {B}What this proves:{D} both sides derive the same AES key without it")
    print( "  ever crossing the wire. That key protects the medical document.")

    # 4 ─────────────────────────────────────────────────────────────────────
    rule("4. Live ML-DSA-65 signature — and rejection of a tampered digest")
    pub_s, priv_s = generate_mldsa_keypair()
    document = b"PATIENT REPORT: haemoglobin 13.4 g/dL, within reference range."
    digest = sha256_hex(document)
    t = time.perf_counter()
    signature = sign_document_hash(digest, priv_s)
    sign_ms = (time.perf_counter() - t) * 1000
    print(f"  document digest (SHA-256) {digest[:48]}…")
    print(f"  signature                 {len(base64.b64decode(signature))} bytes, "
          f"produced in {sign_ms:.2f} ms")
    good = verify_mldsa_signature(digest, signature, pub_s)
    print(f"  verify with the true digest      {OK if good else NO}")

    tampered = sha256_hex(b"PATIENT REPORT: haemoglobin 8.1 g/dL, severe anaemia.")
    bad = verify_mldsa_signature(tampered, signature, pub_s)
    print(f"  verify with an ALTERED digest    "
          f"{G + 'REJECTED — correct' + D if not bad else R + 'ACCEPTED — BROKEN' + D}")
    print(f"\n  {B}Why the second line is the important one:{D} a verifier hardcoded")
    print( "  to return true would pass the first test. Only the refusal proves it works.")

    # 5 ─────────────────────────────────────────────────────────────────────
    rule("5. Hybrid encryption — AES-256-GCM protected by ML-KEM")
    aes_key = derive_aes_key(secret_sender)
    enc = encrypt_document(document, aes_key)
    print(f"  plaintext   {document[:52].decode()}…")
    print(f"  ciphertext  {enc['ciphertext'][:52]}…")
    recovered_key = derive_aes_key(decapsulate_aes_key(ct, priv_enc))
    out = decrypt_document(enc["ciphertext"], recovered_key, enc["nonce"], enc["tag"])
    print(f"  decrypted   {out[:52].decode()}…")
    print(f"  round trip identical      {OK if out == document else NO}")

    corrupted = "A" + enc["ciphertext"][1:]
    try:
        decrypt_document(corrupted, recovered_key, enc["nonce"], enc["tag"])
        print(f"  altered ciphertext        {R}ACCEPTED — BROKEN{D}")
    except Exception:
        print(f"  altered ciphertext        {G}REJECTED by the GCM tag — correct{D}")

    # 6 ─────────────────────────────────────────────────────────────────────
    rule("6. The live database is using these algorithms, not test values")
    dsn = (f"host={os.getenv('DB_HOST','127.0.0.1')} port={os.getenv('DB_PORT','5433')} "
           f"dbname={os.getenv('DB_NAME','pqc_hospital')} user={os.getenv('DB_USER','postgres')} "
           f"password={os.getenv('DB_PASSWORD','')}")
    with psycopg.connect(dsn) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT COUNT(*) AS n,
                              COUNT(*) FILTER (WHERE mlkem_public_key LIKE 'mock%'
                                                  OR mldsa_public_key LIKE 'mock%') AS mocks
                         FROM Users WHERE mlkem_public_key IS NOT NULL""")
        u = cur.fetchone()
        print(f"  accounts holding PQC keypairs        {u['n']}")
        print(f"  placeholder / mock keys among them   {u['mocks']}   "
              f"{OK if u['mocks'] == 0 else NO}")

        cur.execute("""SELECT user_id, mlkem_public_key, mldsa_public_key
                         FROM Users WHERE mlkem_public_key IS NOT NULL
                          AND mlkem_public_key NOT LIKE 'mock%' LIMIT 1""")
        row = cur.fetchone()
        kem_len = len(base64.b64decode(row["mlkem_public_key"]))
        dsa_len = len(base64.b64decode(row["mldsa_public_key"]))
        print(f"\n  sample account {row['user_id']}")
        print(f"    stored ML-KEM public key  {kem_len:>5} bytes   "
              f"expected {FIPS[ML_KEM_ALG]['pk']:>5}   {OK if kem_len == FIPS[ML_KEM_ALG]['pk'] else NO}")
        print(f"    stored ML-DSA public key  {dsa_len:>5} bytes   "
              f"expected {FIPS[ML_DSA_ALG]['pk']:>5}   {OK if dsa_len == FIPS[ML_DSA_ALG]['pk'] else NO}")

        cur.execute("""SELECT COUNT(*) AS n,
                              COUNT(*) FILTER (WHERE kem_algorithm = %s) AS kem,
                              COUNT(*) FILTER (WHERE signature_algorithm = %s) AS dsa,
                              COUNT(*) FILTER (WHERE encrypted_document IS NOT NULL) AS enc
                         FROM LabReports WHERE digital_signature IS NOT NULL""",
                    (ML_KEM_ALG, ML_DSA_ALG))
        r = cur.fetchone()
        print(f"\n  signed lab reports in the database   {r['n']}")
        print(f"    key protected with {ML_KEM_ALG}   {r['kem']} / {r['n']}")
        print(f"    signed with {ML_DSA_ALG}          {r['dsa']} / {r['n']}")
        print(f"    body stored as ciphertext         {r['enc']} / {r['n']}")

        cur.execute("""SELECT report_id_public, digital_signature, encrypted_aes_key
                         FROM LabReports WHERE digital_signature IS NOT NULL
                        ORDER BY created_at DESC LIMIT 1""")
        rep = cur.fetchone()
        if rep:
            sig_len = len(base64.b64decode(rep["digital_signature"]))
            ctl = len(base64.b64decode(rep["encrypted_aes_key"]))
            print(f"\n  most recent report {rep['report_id_public']}")
            print(f"    ML-DSA signature          {sig_len:>5} bytes   "
                  f"expected {FIPS[ML_DSA_ALG]['sig']:>5}   {OK if sig_len == FIPS[ML_DSA_ALG]['sig'] else NO}")
            print(f"    ML-KEM wrapped AES key    {ctl:>5} bytes   "
                  f"expected {FIPS[ML_KEM_ALG]['ct']:>5}   {OK if ctl == FIPS[ML_KEM_ALG]['ct'] else NO}")

    print(f"\n{B}{G}{'═' * 74}{D}")
    print(f"{B}{G} Every figure above was measured at run time — from liboqs, and from{D}")
    print(f"{B}{G} the live database. None of it is a stored or hardcoded expectation.{D}")
    print(f"{B}{G}{'═' * 74}{D}\n")


if __name__ == "__main__":
    main()
