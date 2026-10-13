"""Move to a freshly deployed PHR.sol without losing on-chain consent.

A contract deployed before ``consentStatus`` existed cannot answer the consent
check, so every consent read reports "unverified" (the backend says so at
startup). Redeploying fixes that, but a new contract starts empty. This script
deploys the current contract and carries every consent decision over from the
OLD CONTRACT — not from the database:

    for each consent that was written on-chain (Consent.onchain_tx_hash set):
        old.checkConsent(patient_ref, doctor_ref)  ──►  new.updateConsent(…, same)

The chain is the witness the database is checked against. Copying state from
the database would launder any row edited in SQL into the new contract and
make the tampering undetectable; copying from the old contract keeps it
detectable. Where the old contract and the database disagree, the old
contract's answer is carried and the row is listed: the backend will report it
as a mismatch, which is what it is.

A consent never written on-chain is left alone (it is "unverified" either way),
and if the old contract has no code (e.g. a restarted local anvil chain) there
is nothing to carry — those consents read "unverified" until the patient's next
decision writes them again. Nothing is invented.

Anchors already written stay valid where they are: add the old address to
BLOCKCHAIN_PREVIOUS_CONTRACT_ADDRESSES so they keep verifying.

Usage (dry run first; --apply deploys and writes):
    python migrate_contract.py
    python migrate_contract.py --apply
"""

import argparse
import sys

from app.consent_ledger import party_ref


def _consents(cur) -> list[dict]:
    cur.execute("""SELECT consent_id, patient_id, subject_user_id, status::text AS status
                     FROM Consent WHERE onchain_tx_hash IS NOT NULL
                    ORDER BY consent_id""")
    return cur.fetchall()


def plan(old, consents: list[dict]) -> tuple[list[tuple[dict, bool]], list[dict]]:
    """(what to write, rows whose database state disagrees with the old contract)."""
    carry, disagree = [], []
    for c in consents:
        on_chain = bool(old.functions.checkConsent(
            party_ref(str(c["patient_id"])), party_ref(str(c["subject_user_id"]))).call())
        carry.append((c, on_chain))
        if on_chain != (c["status"] == "Authorized"):
            disagree.append({**c, "old_contract_says": "granted" if on_chain else "withdrawn"})
    return carry, disagree


def migrate(old_address: str | None, apply: bool, say=print) -> dict:
    """Plan (and with ``apply``, carry out) the migration. Returns what happened:
    ``status`` is one of error / no_code / current / dry_run / migrated."""
    from web3 import Web3
    from eth_account import Account
    from psycopg.rows import dict_row
    from app.config import get_settings
    from app.chain_client import load_contract_artifact
    from app.database import get_db
    from deploy_contract import deploy

    settings = get_settings()
    web3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        say(f"ERROR: no Ethereum node at {settings.BLOCKCHAIN_RPC_URL}")
        return {"status": "error"}
    old_address = old_address or settings.BLOCKCHAIN_CONTRACT_ADDRESS
    if not old_address:
        say("ERROR: no old contract address (BLOCKCHAIN_CONTRACT_ADDRESS or --old).")
        return {"status": "error"}
    artifact = load_contract_artifact()
    old = web3.eth.contract(address=Web3.to_checksum_address(old_address), abi=artifact["abi"])

    if web3.eth.get_code(old.address) in (b"", b"0x"):
        say(f"The old contract {old.address} has no code on this chain (a wiped dev chain?).")
        say("There is no on-chain consent to carry. Deploy with deploy_contract.py; consents")
        say("read 'unverified' until each patient's next decision writes them again.")
        return {"status": "no_code"}
    try:
        old.functions.consentStatus("", "").call()
        say(f"{old.address} already has consentStatus(); nothing to migrate.")
        return {"status": "current"}
    except Exception:  # noqa: BLE001 - absent: this is the contract to migrate from
        pass

    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        consents = _consents(cur)
    carry, disagree = plan(old, consents)
    say(f"Old contract      : {old.address}")
    say(f"Consents on-chain : {len(carry)} to carry over, state read from the old contract")
    for d in disagree:
        say(f"  ! consent {d['consent_id']}: database says {d['status']}, "
            f"old contract says {d['old_contract_says']} — carrying the contract's answer")
    result = {"status": "dry_run", "old_address": old.address,
              "carry": [(str(c["consent_id"]), granted) for c, granted in carry],
              "disagree": [str(d["consent_id"]) for d in disagree]}
    if not apply:
        say("\nDry run. Re-run with --apply to deploy and write.")
        return result

    account = Account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
    say("\nDeploying PHR_Security...")
    new_address = deploy(web3, account, settings, artifact)
    new = web3.eth.contract(address=new_address, abi=artifact["abi"])
    nonce = web3.eth.get_transaction_count(account.address)
    for c, granted in carry:
        tx = new.functions.updateConsent(
            party_ref(str(c["patient_id"])), party_ref(str(c["subject_user_id"])), granted
        ).build_transaction({"from": account.address, "nonce": nonce,
                             "chainId": settings.BLOCKCHAIN_CHAIN_ID, "gas": 200_000,
                             "gasPrice": web3.eth.gas_price})
        receipt = web3.eth.wait_for_transaction_receipt(
            web3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction), timeout=120)
        if receipt["status"] != 1:
            say(f"ERROR: writing consent {c['consent_id']} reverted; the old contract is unchanged.")
            return {**result, "status": "error", "new_address": new_address}
        nonce += 1
    # Read every one back: the migration is done only if the new contract agrees.
    for c, granted in carry:
        state = new.functions.consentStatus(
            party_ref(str(c["patient_id"])), party_ref(str(c["subject_user_id"]))).call()
        if state != (1 if granted else 2):
            say(f"ERROR: consent {c['consent_id']} reads back as {state} on the new contract.")
            return {**result, "status": "error", "new_address": new_address}

    previous = ",".join(a for a in (settings.BLOCKCHAIN_PREVIOUS_CONTRACT_ADDRESSES, old.address) if a)
    say(f"\nCarried {len(carry)} consent(s); each read back from the new contract.")
    say("=" * 68)
    say("Update backend/.env:")
    say(f"\n    BLOCKCHAIN_CONTRACT_ADDRESS={new_address}")
    say(f"    BLOCKCHAIN_PREVIOUS_CONTRACT_ADDRESSES={previous}\n")
    say("=" * 68)
    return {**result, "status": "migrated", "new_address": new_address, "previous": previous}


def main(argv=None) -> int:
    args = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    args.add_argument("--apply", action="store_true", help="deploy and write (default: dry run)")
    args.add_argument("--old", help="old contract address (default: BLOCKCHAIN_CONTRACT_ADDRESS)")
    opts = args.parse_args(argv)
    return 1 if migrate(opts.old, opts.apply)["status"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
