from functools import lru_cache
from pathlib import Path
from pydantic import BaseModel
import logging
import os
import secrets
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pqc_hospital")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    # 32 bytes for AES. NOTE: this default only applies when the variable is
    # absent entirely. A ".env" line written as documented — "ENCRYPTION_KEY="
    # with nothing after the "=" — sets it to "", which os.getenv returns as-is
    # rather than falling through to this default; see get_settings(), which
    # corrects that case the same way it already does for SECRET_KEY.
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")
    # Keys the pseudonymous party references written to the consent contract.
    # Separate from SECRET_KEY so that rotating the session key cannot make every
    # on-chain consent look tampered with. Never change it once consents are on-chain.
    CONSENT_LEDGER_KEY: str = os.getenv("CONSENT_LEDGER_KEY", "")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    # STARTTLS before login. Leave on for any real mail server; only a local
    # test server (e.g. Mailpit in CI) that offers no TLS needs it off.
    SMTP_STARTTLS: bool = os.getenv("SMTP_STARTTLS", "true").lower() != "false"
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@hospital.com")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")
    
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
    refresh_token_days: int = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))

    # ─── Browser sessions ────────────────────────────────────────────────────
    # The session lives only in an HttpOnly cookie that page scripts cannot
    # read. CORS_ORIGINS lists the frontends allowed to call the API with it —
    # never "*", which with credentials would let any site act as the user.
    CORS_ORIGINS: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    # "lax" when the frontend and API share a site (the default); "none" when
    # they are on different sites, which also forces Secure.
    SESSION_COOKIE_SAMESITE: str = os.getenv("SESSION_COOKIE_SAMESITE", "lax").lower()
    # Secure (HTTPS only). Off by default for http://localhost development.
    SESSION_COOKIE_SECURE: bool = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "AKIA_MOCK_QUANTUMCARE_AWS_KEY")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "mock_aws_secret_key_quantumcare_pqc")
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")
    AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "quantumcare-pqc-phr-storage")
    # An S3-compatible endpoint (SeaweedFS, MinIO, Ceph, …) instead of AWS. Blank = AWS.
    AWS_S3_ENDPOINT_URL: str = os.getenv("AWS_S3_ENDPOINT_URL", "")
    # S3's own at-rest encryption, on top of the AES-GCM the app applies first.
    # "AES256" (default) for AWS; "none" for a store without server-side
    # encryption configured (SeaweedFS refuses the header otherwise).
    AWS_S3_SERVER_SIDE_ENCRYPTION: str = os.getenv("AWS_S3_SERVER_SIDE_ENCRYPTION", "AES256")
    # No IPFS gateway or pinning settings: nothing is published to the IPFS
    # network. The system computes an IPFS-style CIDv0 purely as a content
    # address for the encrypted document (see storage_service), which needs no
    # network and no account. Keeping a gateway URL here would imply a
    # retrievable public link that does not exist.

    # ─── Blockchain audit anchoring ──────────────────────────────────────────
    # Defaults target a local dev chain (anvil) so every developer gets real
    # on-chain writes with no accounts, no funds and no internet. Point these at
    # a public testnet (e.g. Sepolia) to share one ledger across the team:
    #   BLOCKCHAIN_RPC_URL=https://sepolia.infura.io/v3/<key>
    #   BLOCKCHAIN_CHAIN_ID=11155111
    #   BLOCKCHAIN_PRIVATE_KEY=<testnet-only key, never a real-funds key>
    #   BLOCKCHAIN_EXPLORER_URL=https://sepolia.etherscan.io/tx/
    BLOCKCHAIN_ENABLED: bool = os.getenv("BLOCKCHAIN_ENABLED", "true").lower() == "true"
    BLOCKCHAIN_RPC_URL: str = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    BLOCKCHAIN_CHAIN_ID: int = int(os.getenv("BLOCKCHAIN_CHAIN_ID", "31337"))
    BLOCKCHAIN_CONTRACT_ADDRESS: str = os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS", "")
    # Contracts this deployment used before (comma-separated), e.g. after
    # migrate_contract.py. Anchors written to them still verify; events from any
    # other contract never count as this hospital's anchors.
    BLOCKCHAIN_PREVIOUS_CONTRACT_ADDRESSES: str = os.getenv("BLOCKCHAIN_PREVIOUS_CONTRACT_ADDRESSES", "")
    # anvil's first well-known dev account. Public, unfunded outside local dev,
    # and safe to commit as a default — never use it on a real network.
    BLOCKCHAIN_PRIVATE_KEY: str = os.getenv(
        "BLOCKCHAIN_PRIVATE_KEY",
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    )
    BLOCKCHAIN_EXPLORER_URL: str = os.getenv("BLOCKCHAIN_EXPLORER_URL", "")
    BLOCKCHAIN_NETWORK_NAME: str = os.getenv("BLOCKCHAIN_NETWORK_NAME", "anvil-local")

logger = logging.getLogger(__name__)

# Values that ship in this repository. A key anyone can read is not a secret:
# with the session-signing key, any visitor could mint an Administrator token.
_PLACEHOLDER_SECRET_KEYS = {"change-me-in-production", "replace-with-a-long-random-string", ""}
_PUBLIC_ENCRYPTION_KEYS = {"0123456789abcdef0123456789abcdef"}
_PUBLIC_ADMIN_PASSWORDS = {"Admin@1234", ""}
MIN_SECRET_KEY_LENGTH = 32

# Chain IDs a local dev chain actually uses (anvil, hardhat). Anything else is
# a real network, where anvil's well-known dev private key must never sign.
_LOCAL_DEV_CHAIN_IDS = {31337, 1337}
_WELL_KNOWN_DEV_PRIVATE_KEYS = {
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
}

_KEY_DIR = Path(os.getenv("GENERATED_KEY_DIR") or Path(__file__).resolve().parent.parent)
_SECRET_KEY_FILE = _KEY_DIR / ".secret_key"
_LEDGER_KEY_FILE = _KEY_DIR / ".ledger_key"
_GENERATED: set[str] = set()      # settings whose configured value was replaced


def _generated_secret_key(path: Path = _SECRET_KEY_FILE) -> str:
    """A random key, created once and kept beside the app.

    Used when a key is unset, a shipped placeholder or too short. Kept in a
    file rather than in memory so every worker and every restart agree on it;
    created exclusively, so two workers starting together cannot write two.
    """
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except PermissionError:
        # A read-only filesystem: still never fall back to a published key.
        logger.warning("Cannot write %s; using a per-process random key. Sessions and "
                       "consent references will not survive a restart — set the key "
                       "explicitly.", path)
        return secrets.token_urlsafe(48)
    except FileExistsError:
        key = path.read_text(encoding="utf-8").strip()
        if len(key) >= MIN_SECRET_KEY_LENGTH:
            return key
        raise RuntimeError(f"{path} exists but does not hold a usable key; delete it to regenerate.")
    key = secrets.token_urlsafe(48)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key)
    logger.warning("Generated a key at %s because none was configured.", path)
    return key


def configuration_warnings(settings: "Settings") -> list[str]:
    """Insecure settings an administrator must know about, including any replaced
    with a generated key at startup."""
    warnings = []
    if settings.ENCRYPTION_KEY in _PUBLIC_ENCRYPTION_KEYS:
        warnings.append(
            "ENCRYPTION_KEY is the public example key from this repository, so the "
            "personal fields it protects are readable by anyone with the database. "
            "Move existing data to a new key with backend/rotate_encryption_key.py "
            "(server stopped), then set the new key.")
    elif len(settings.ENCRYPTION_KEY) != 32:
        warnings.append("ENCRYPTION_KEY is not exactly 32 characters; it is padded or truncated.")
    if "SECRET_KEY" in _GENERATED:
        warnings.append(
            f"SECRET_KEY is unset, a placeholder or shorter than {MIN_SECRET_KEY_LENGTH} "
            f"characters; a generated key ({_SECRET_KEY_FILE.name}) is in use. Set it "
            "explicitly when running more than one server.")
    if "BLOCKCHAIN_PRIVATE_KEY" in _GENERATED:
        warnings.append(
            "BLOCKCHAIN_PRIVATE_KEY was anvil's well-known public dev key while "
            f"BLOCKCHAIN_CHAIN_ID ({settings.BLOCKCHAIN_CHAIN_ID}) is not a local dev chain "
            f"({sorted(_LOCAL_DEV_CHAIN_IDS)}); on-chain anchoring has been disabled rather "
            "than sign transactions on a real network with a key anyone can look up. Set a "
            "funded, testnet/mainnet-only private key to enable it.")
    return warnings


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.SECRET_KEY in _PLACEHOLDER_SECRET_KEYS or len(settings.SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
        settings.SECRET_KEY = _generated_secret_key(_SECRET_KEY_FILE)
        _GENERATED.add("SECRET_KEY")
    if len(settings.CONSENT_LEDGER_KEY) < MIN_SECRET_KEY_LENGTH:
        settings.CONSENT_LEDGER_KEY = _generated_secret_key(_LEDGER_KEY_FILE)
        _GENERATED.add("CONSENT_LEDGER_KEY")
    if not settings.ENCRYPTION_KEY:
        # An absent variable already defaults to this via the field above; this
        # covers "ENCRYPTION_KEY=" present-but-empty, which os.getenv returns
        # as "" rather than falling through to that default. Without this, an
        # empty string is padded to 32 zero-bytes by get_encryption_key() — a
        # key that matches no data ever encrypted under the documented default,
        # silently making every existing encrypted column unreadable rather
        # than failing loudly. configuration_warnings() still reports this as
        # the public example key, same as if it had been set explicitly.
        settings.ENCRYPTION_KEY = next(iter(_PUBLIC_ENCRYPTION_KEYS))
    if (
        settings.BLOCKCHAIN_ENABLED
        and settings.BLOCKCHAIN_CHAIN_ID not in _LOCAL_DEV_CHAIN_IDS
        and settings.BLOCKCHAIN_PRIVATE_KEY.lower() in _WELL_KNOWN_DEV_PRIVATE_KEYS
    ):
        # Refuse to anchor rather than sign real-network transactions with a
        # key every wallet and tutorial on earth already has memorized.
        logger.critical(
            "BLOCKCHAIN_CHAIN_ID=%s is not a local dev chain but BLOCKCHAIN_PRIVATE_KEY is "
            "anvil's published dev key. Disabling on-chain anchoring (falling back to "
            "local-simulated) rather than using it on a real network.",
            settings.BLOCKCHAIN_CHAIN_ID,
        )
        settings.BLOCKCHAIN_ENABLED = False
        _GENERATED.add("BLOCKCHAIN_PRIVATE_KEY")
    return settings
