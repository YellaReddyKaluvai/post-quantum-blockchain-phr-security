"""Deploy the PHR_Security audit contract and report its address.

Usage:
    # 1. compile (from the repository root)
    forge build

    # 2. start a local chain, if not using a testnet
    anvil --port 8545 --chain-id 31337

    # 3. deploy
    python3 deploy_contract.py

Then copy the printed BLOCKCHAIN_CONTRACT_ADDRESS into backend/.env.

Targets whatever BLOCKCHAIN_RPC_URL / BLOCKCHAIN_PRIVATE_KEY point at, so the
same script deploys to a local dev chain or a public testnet.
"""

import sys

from web3 import Web3
from eth_account import Account

from app.config import get_settings
from app.chain_client import load_contract_artifact


def with_margin(estimate: int) -> int:
    """Gas for a transaction: the node's estimate plus a quarter. A fixed figure
    either wastes nothing or runs out — and storage-heavy calls run out."""
    return int(estimate * 1.25) + 10_000


def deploy(web3, account, settings, artifact) -> str:
    """Deploy PHR_Security; return its address. Raises RuntimeError on a revert."""
    contract = web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"]["object"])
    constructor = contract.constructor()
    tx = constructor.build_transaction({
        "from": account.address,
        "nonce": web3.eth.get_transaction_count(account.address),
        "chainId": settings.BLOCKCHAIN_CHAIN_ID,
        "gas": with_margin(constructor.estimate_gas({"from": account.address})),
        "gasPrice": web3.eth.gas_price,
    })
    signed = account.sign_transaction(tx)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  tx: {tx_hash.hex()}")
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        raise RuntimeError("deployment transaction reverted")
    print(f"  deployed in block {receipt['blockNumber']}, gas used {receipt['gasUsed']}")
    return receipt["contractAddress"]


def main() -> int:
    settings = get_settings()

    print(f"RPC      : {settings.BLOCKCHAIN_RPC_URL}")
    print(f"Chain ID : {settings.BLOCKCHAIN_CHAIN_ID}")
    print(f"Network  : {settings.BLOCKCHAIN_NETWORK_NAME}")

    web3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL, request_kwargs={"timeout": 20}))
    if not web3.is_connected():
        print(f"\nERROR: no Ethereum node reachable at {settings.BLOCKCHAIN_RPC_URL}")
        print("Start one with:  anvil --port 8545 --chain-id 31337")
        return 1

    try:
        artifact = load_contract_artifact()
    except FileNotFoundError as exc:
        print(f"\nERROR: {exc}")
        return 1

    account = Account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
    balance = web3.eth.get_balance(account.address)
    print(f"Deployer : {account.address}")
    print(f"Balance  : {web3.from_wei(balance, 'ether')} ETH")

    if balance == 0:
        print("\nERROR: deployer has no funds — it cannot pay gas.")
        print("On a testnet, fund this address from a faucet first.")
        return 1

    print("\nDeploying PHR_Security...")
    try:
        address = deploy(web3, account, settings, artifact)
    except RuntimeError as exc:
        print(f"\nERROR: {exc}.")
        return 1
    print("\n" + "=" * 68)
    print("Add this line to backend/.env:")
    print(f"\n    BLOCKCHAIN_CONTRACT_ADDRESS={address}\n")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
