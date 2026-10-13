"""Replacing an outdated PHR.sol on a real chain (migrate_contract.py).

CI deploys test/legacy/PHR_V1.sol — the contract as it was before consentStatus
— to anvil, records three consent decisions on it, then migrates:

    D1  granted on-chain,   database Authorized   → carried as granted
    D2  withdrawn on-chain, database Revoked      → carried as withdrawn
    D3  withdrawn on-chain, database Authorized   → carried as WITHDRAWN, and listed:
        the row was edited in SQL, and the chain's answer is the one that survives

then reads every decision back from the newly deployed contract. Opt-in:

    RUN_E2E=1 BLOCKCHAIN_ENABLED=true DATABASE_URL=… (anvil at BLOCKCHAIN_RPC_URL)
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_E2E") != "1" or os.getenv("BLOCKCHAIN_ENABLED", "false").lower() != "true",
    reason="contract migration needs RUN_E2E=1 and a running chain")


def _legacy_artifact():
    import json
    from app import chain_client
    path = chain_client._ARTIFACT_PATH.parent.parent / "PHR_V1.sol" / "PHR_Security_V1.json"
    if not path.exists():
        pytest.skip(f"legacy contract not built ({path}); run forge build")
    return json.loads(path.read_text())


def _send(web3, account, settings, call):
    tx = call.build_transaction({"from": account.address,
                                 "nonce": web3.eth.get_transaction_count(account.address),
                                 "chainId": settings.BLOCKCHAIN_CHAIN_ID, "gas": 3_000_000,
                                 "gasPrice": web3.eth.gas_price})
    receipt = web3.eth.wait_for_transaction_receipt(
        web3.eth.send_raw_transaction(account.sign_transaction(tx).raw_transaction), timeout=60)
    assert receipt["status"] == 1
    return receipt


def test_consent_moves_from_an_outdated_contract_and_the_chain_wins():
    import psycopg
    from eth_account import Account
    from web3 import Web3
    from app.config import get_settings
    from app.consent_ledger import party_ref
    from app.chain_client import load_contract_artifact
    from app.security import encrypt_data, hash_password
    from migrate_contract import migrate

    settings = get_settings()
    web3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL))
    account = Account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
    legacy_artifact = _legacy_artifact()

    # The outdated contract, deployed as an old installation would have it.
    factory = web3.eth.contract(abi=legacy_artifact["abi"], bytecode=legacy_artifact["bytecode"]["object"])
    legacy_address = _send(web3, account, settings, factory.constructor())["contractAddress"]
    legacy = web3.eth.contract(address=legacy_address, abi=legacy_artifact["abi"])

    # A patient and three doctors, with consent rows the application would have written.
    tag = uuid.uuid4().hex[:6]
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as db:
        ids = {}
        for name, role in (("P", "Patient"), ("D1", "Doctor"), ("D2", "Doctor"), ("D3", "Doctor")):
            ids[name] = db.execute(
                """INSERT INTO Users (user_id, full_name, email, password_hash, role, gender,
                                      date_of_birth_encrypted, status)
                   VALUES (%s, %s, %s, %s, %s, 'Other', %s, 'Approved') RETURNING id""",
                (f"MIG-{name}-{tag}", f"Migration {name}", f"mig-{name.lower()}-{tag}@e2e.example.com",
                 hash_password("unused-Pass-1!"), role, encrypt_data("1980-01-01"))).fetchone()[0]
        consent = {}
        for doctor, db_status, on_chain in (("D1", "Authorized", True), ("D2", "Revoked", False),
                                            ("D3", "Authorized", False)):
            consent[doctor] = str(db.execute(
                """INSERT INTO Consent (patient_id, subject_user_id, subject_role, status, onchain_tx_hash)
                   VALUES (%s, %s, 'Doctor', %s, '0xlegacy') RETURNING consent_id""",
                (ids["P"], ids[doctor], db_status)).fetchone()[0])
            _send(web3, account, settings, legacy.functions.updateConsent(
                party_ref(str(ids["P"])), party_ref(str(ids[doctor])), on_chain))

    # Dry run: nothing deployed, the plan says what the chain says.
    plan = migrate(legacy_address, apply=False, say=lambda *_: None)
    assert plan["status"] == "dry_run"
    carried = dict(plan["carry"])
    assert (carried[consent["D1"]], carried[consent["D2"]], carried[consent["D3"]]) == (True, False, False)
    assert consent["D3"] in plan["disagree"] and consent["D1"] not in plan["disagree"]

    done = migrate(legacy_address, apply=True, say=lambda *_: None)
    assert done["status"] == "migrated" and legacy_address in done["previous"]
    new = web3.eth.contract(address=done["new_address"], abi=load_contract_artifact()["abi"])
    states = [new.functions.consentStatus(party_ref(str(ids["P"])), party_ref(str(ids[d]))).call()
              for d in ("D1", "D2", "D3")]
    assert states == [1, 2, 2]                  # granted, withdrawn, withdrawn — the chain's answers

    # The new contract is current: running again finds nothing to do.
    assert migrate(done["new_address"], apply=False, say=lambda *_: None)["status"] == "current"
