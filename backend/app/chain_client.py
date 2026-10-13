"""Web3 client for the PHR audit contract.

Wraps ``contracts/PHR.sol`` so ``anchor_service`` can write real transactions.
The chain target comes entirely from settings, so the same code runs against a
local dev chain (anvil), a shared team testnet, or a private network without
any change here.

What actually goes on-chain: the actor's public ID, the action, and the
document's SHA-256 digest. Never the document, never key material, never
patient-identifying free text — the digest is what makes tampering detectable,
and it reveals nothing on its own.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

# contracts/out/PHR.sol/PHR_Security.json, produced by `forge build`.
_ARTIFACT_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "contracts" / "out" / "PHR.sol" / "PHR_Security.json"
)

_lock = threading.Lock()
_client: Optional["ChainClient"] = None
_init_attempted = False


def load_contract_artifact() -> dict[str, Any]:
    """Read the compiled ABI + bytecode. Raises if the contract isn't built."""
    if not _ARTIFACT_PATH.exists():
        raise FileNotFoundError(
            f"Contract artifact not found at {_ARTIFACT_PATH}. "
            "Run `forge build` from the repository root first."
        )
    with open(_ARTIFACT_PATH) as fh:
        return json.load(fh)


def _hex(value) -> str:
    """0x-prefixed hex. HexBytes.hex() dropped the prefix in newer releases,
    and an unprefixed hash does not round-trip into receipt lookups."""
    text = value.hex() if hasattr(value, "hex") else str(value)
    return text if text.startswith("0x") else "0x" + text


class ChainClient:
    """Minimal wrapper around the deployed PHR_Security contract."""

    def __init__(self):
        from web3 import Web3
        from eth_account import Account

        settings = get_settings()
        self.settings = settings
        self.web3 = Web3(Web3.HTTPProvider(settings.BLOCKCHAIN_RPC_URL, request_kwargs={"timeout": 10}))

        if not self.web3.is_connected():
            raise ConnectionError(f"No Ethereum node at {settings.BLOCKCHAIN_RPC_URL}")

        if not settings.BLOCKCHAIN_CONTRACT_ADDRESS:
            raise ValueError(
                "BLOCKCHAIN_CONTRACT_ADDRESS is not set. Deploy the contract with "
                "`python3 deploy_contract.py` and put the printed address in .env."
            )

        artifact = load_contract_artifact()
        self.account = Account.from_key(settings.BLOCKCHAIN_PRIVATE_KEY)
        self.address = Web3.to_checksum_address(settings.BLOCKCHAIN_CONTRACT_ADDRESS)
        self.contract = self.web3.eth.contract(address=self.address, abi=artifact["abi"])

        if self.web3.eth.get_code(self.address) in (b"", b"0x"):
            raise ValueError(
                f"No contract deployed at {self.address} on chain "
                f"{settings.BLOCKCHAIN_CHAIN_ID}. Re-run deploy_contract.py."
            )

        logger.info(
            "Chain client ready: %s @ %s (chain %s)",
            self.address, settings.BLOCKCHAIN_RPC_URL, settings.BLOCKCHAIN_CHAIN_ID,
        )

    def _transact(self, function_call) -> dict[str, Any]:
        """Sign and send one contract call, then wait for its receipt."""
        # Serialised because nonce selection is read-then-use; two concurrent
        # sends would otherwise pick the same nonce and one would be rejected.
        with _lock:
            nonce = self.web3.eth.get_transaction_count(self.account.address)
            tx = function_call.build_transaction({
                "from": self.account.address,
                "nonce": nonce,
                "chainId": self.settings.BLOCKCHAIN_CHAIN_ID,
                "gas": 500_000,
                "gasPrice": self.web3.eth.gas_price,
            })
            signed = self.account.sign_transaction(tx)
            tx_hash = self.web3.eth.send_raw_transaction(signed.raw_transaction)

        receipt = self.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        if receipt["status"] != 1:
            # Mined but reverted (e.g. the contract's onlyAdmin check): nothing
            # was recorded, and reporting the hash as a success would say it was.
            raise RuntimeError(f"Transaction {_hex(receipt['transactionHash'])} reverted.")
        return {
            "tx_hash": _hex(receipt["transactionHash"]),
            "block_number": receipt["blockNumber"],
            "gas_used": receipt["gasUsed"],
            "status": receipt["status"],
        }

    def log_data_access(self, actor_public_id: str, action: str, document_hash: str) -> dict[str, Any]:
        """Send one audit entry on-chain and wait for its receipt.

        Returns the transaction hash, block number and gas used.
        """
        return self._transact(self.contract.functions.logDataAccess(
            actor_public_id or "SYSTEM", action, document_hash))

    # ─── Consent (PHR.sol updateConsent / checkConsent) ──────────────────────
    #
    # The contract keys consent by two strings. Pseudonymous references are
    # passed (see consent_ledger.party_ref), never names or internal UUIDs, so
    # the public ledger links nothing to a person on its own.

    def update_consent(self, patient_ref: str, doctor_ref: str, authorized: bool) -> dict[str, Any]:
        """Record a grant or withdrawal on-chain (emits ConsentUpdated)."""
        return self._transact(self.contract.functions.updateConsent(
            patient_ref, doctor_ref, bool(authorized)))

    def check_consent(self, patient_ref: str, doctor_ref: str) -> bool:
        """Read the consent state the contract holds. A view call: no transaction."""
        return bool(self.contract.functions.checkConsent(patient_ref, doctor_ref).call())

    def consent_status(self, patient_ref: str, doctor_ref: str) -> str:
        """``none``, ``granted`` or ``revoked`` — a withdrawal is distinguishable
        from the absence of any decision, which ``checkConsent``'s bool is not."""
        code = int(self.contract.functions.consentStatus(patient_ref, doctor_ref).call())
        return {0: "none", 1: "granted", 2: "revoked"}.get(code, "none")

    def declare_emergency(self, doctor_ref: str, patient_ref: str, resource_hash: str) -> dict[str, Any]:
        """Record a break-glass override (emits EmergencyAccessTriggered)."""
        return self._transact(self.contract.functions.emergencyAccess(
            doctor_ref, patient_ref, resource_hash))

    def audit_trail_count(self) -> int:
        """Total audit entries recorded on-chain."""
        return self.contract.functions.getAuditTrailCount().call()


def get_chain_client() -> Optional[ChainClient]:
    """Return the shared client, or None when the chain is unavailable.

    Connection is attempted once. A failure is logged loudly and cached, so a
    down node degrades to local-simulated anchors rather than stalling every
    clinical action on a network timeout.
    """
    global _client, _init_attempted

    settings = get_settings()
    if not settings.BLOCKCHAIN_ENABLED:
        return None

    if _client is not None or _init_attempted:
        return _client

    with _lock:
        if _client is not None or _init_attempted:
            return _client
        _init_attempted = True
        try:
            _client = ChainClient()
        except Exception as exc:
            logger.error(
                "Blockchain anchoring unavailable (%s). Falling back to local-simulated "
                "anchors; anchor rows will record which was used.", exc,
            )
            _client = None
    return _client


def reset_chain_client() -> None:
    """Drop the cached client so the next call reconnects. For tests/redeploys."""
    global _client, _init_attempted
    with _lock:
        _client = None
        _init_attempted = False
