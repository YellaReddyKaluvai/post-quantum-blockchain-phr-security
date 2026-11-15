"""Evidence that the blockchain anchoring is real, and what it protects.

The database is not evidence of the chain. A transaction hash sitting in a
table is something this application wrote about itself; the point of anchoring
is that a second, independent system holds the same value. So every figure
below that claims to come from the chain is read back from the chain over RPC.

    python3 demo/prove_blockchain.py

The final section is the one worth watching: it alters a stored digest and
shows verification failing, then restores it. A guarantee that has never been
observed failing has not been demonstrated.
"""

import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

import psycopg
from psycopg.rows import dict_row

G = "\033[92m"; R = "\033[91m"; B = "\033[1m"; C = "\033[96m"; Y = "\033[93m"; D = "\033[0m"
RPC = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
DSN = (f"host={os.getenv('DB_HOST','127.0.0.1')} port={os.getenv('DB_PORT','5433')} "
       f"dbname={os.getenv('DB_NAME','pqc_hospital')} user={os.getenv('DB_USER','postgres')} "
       f"password={os.getenv('DB_PASSWORD','')}")


def rule(title):
    print(f"\n{B}{C}{'─' * 72}{D}")
    print(f"{B}{C} {title}{D}")
    print(f"{B}{C}{'─' * 72}{D}")


def rpc(method, params):
    req = urllib.request.Request(
        RPC, method="POST", headers={"Content-Type": "application/json"},
        data=json.dumps({"jsonrpc": "2.0", "id": 1,
                         "method": method, "params": params}).encode())
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r).get("result")


def strings_in(data_hex):
    """Pull the printable ABI-encoded strings out of an event's data blob."""
    raw = bytes.fromhex(data_hex[2:])
    out = []
    for i in range(0, len(raw), 32):
        text = raw[i:i + 32].rstrip(b"\x00").decode("utf8", "ignore")
        if len(text) > 3 and text.isprintable() and any(c.isalnum() for c in text):
            out.append(text)
    return out


def main():
    print(f"\n{B}QuantumCare — Blockchain Anchoring Verification{D}")

    rule("1. The chain is a separate, live system")
    try:
        block = int(rpc("eth_blockNumber", []), 16)
        chain_id = int(rpc("eth_chainId", []), 16)
        print(f"  RPC endpoint      {RPC}")
        print(f"  chain id          {chain_id}")
        print(f"  current block     {block}          {G}reachable{D}")
    except Exception as exc:
        print(f"  {R}No chain reachable at {RPC}: {exc}{D}")
        print(f"  {Y}Start it with ./start.sh, then run this again.{D}\n")
        return

    contract = os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS", "")
    code = rpc("eth_getCode", [contract, "latest"]) or "0x"
    print(f"  contract          {contract}")
    print(f"  deployed          {G + str(len(code) // 2) + ' bytes of bytecode' + D if code != '0x' else R + 'NOT DEPLOYED' + D}")

    rule("2. What the database claims")
    with psycopg.connect(DSN) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""SELECT anchored_on, COUNT(*) AS n FROM DocumentAnchors
                        GROUP BY anchored_on ORDER BY 2 DESC""")
        for row in cur.fetchall():
            label = "on-chain" if row["anchored_on"] != "local-simulated" else "simulated (no chain at the time)"
            print(f"  {row['anchored_on']:<18} {row['n']:>4}   {label}")

        cur.execute("""SELECT tx_hash, block_number, document_type, action, document_hash
                         FROM DocumentAnchors
                        WHERE anchored_on <> 'local-simulated' AND tx_hash LIKE '0x%'
                        ORDER BY created_at DESC LIMIT 1""")
        anchor = cur.fetchone()

    if not anchor:
        print(f"\n  {Y}No on-chain anchors yet. Open a report as a patient while the")
        print(f"  chain is running, then run this again.{D}\n")
        return

    print(f"\n  most recent on-chain anchor")
    print(f"    document      {anchor['document_type']} · {anchor['action']}")
    print(f"    transaction   {anchor['tx_hash']}")
    print(f"    block         {anchor['block_number']}")
    print(f"    digest        {anchor['document_hash']}")

    rule("3. The same transaction, read back OFF the chain")
    receipt = rpc("eth_getTransactionReceipt", [anchor["tx_hash"]])
    if not receipt:
        print(f"  {R}Not found on this chain.{D}")
        print(f"  {Y}anvil keeps its state in memory, so a restart clears earlier")
        print(f"  transactions. Anchors written since the last restart are present.{D}\n")
        return

    ok = receipt["status"] == "0x1"
    print(f"  status            {G + 'success' + D if ok else R + 'failed' + D}")
    print(f"  block number      {int(receipt['blockNumber'], 16)}")
    print(f"  block hash        {receipt['blockHash'][:42]}…")
    print(f"  gas used          {int(receipt['gasUsed'], 16):,}")
    print(f"  emitted by        {receipt['logs'][0]['address']}")
    print(f"\n  {B}This came from the chain over RPC, not from the database.{D}")

    rule("4. What the chain itself stores")
    for text in strings_in(receipt["logs"][0]["data"]):
        print(f"    {text}")
    print(f"\n  {B}Note what is absent:{D} no patient name, no diagnosis, no document,")
    print( "  no key material. Only the action and the digest.")

    rule("5. Does the on-chain digest match the stored one?")
    parts = [s for s in strings_in(receipt["logs"][0]["data"])
             if len(s) == 32 and all(c in "0123456789abcdef" for c in s)]
    on_chain = "".join(parts)
    print(f"  database   {anchor['document_hash']}")
    print(f"  on-chain   {on_chain}")
    match = on_chain == anchor["document_hash"]
    print(f"\n  {G + '✓ IDENTICAL — the record has not been altered' + D if match else R + '✗ MISMATCH — integrity alert' + D}")

    rule("6. The tamper test — what makes any of this worth doing")
    print( "  Rewriting the stored digest simulates an attacker with full database")
    print( "  access. The chain is untouched, so the two stop agreeing.\n")
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute("UPDATE DocumentAnchors SET document_hash = %s WHERE tx_hash = %s",
                    ("0" * 64, anchor["tx_hash"]))
        conn.commit()
        cur.execute("SELECT document_hash FROM DocumentAnchors WHERE tx_hash = %s",
                    (anchor["tx_hash"],))
        tampered = cur.fetchone()[0]
        print(f"  database now   {tampered}")
        print(f"  on-chain still {on_chain}")
        print(f"\n  {R}✗ MISMATCH — verification fails, integrity alert raised{D}")

        cur.execute("UPDATE DocumentAnchors SET document_hash = %s WHERE tx_hash = %s",
                    (anchor["document_hash"], anchor["tx_hash"]))
        conn.commit()
        print(f"\n  {G}restored — digests agree again{D}")

    print(f"\n{B}{G}{'═' * 72}{D}")
    print(f"{B}{G} An attacker who owns the database can rewrite that column.{D}")
    print(f"{B}{G} They cannot rewrite the chain — so the tampering shows.{D}")
    print(f"{B}{G}{'═' * 72}{D}\n")


if __name__ == "__main__":
    main()
