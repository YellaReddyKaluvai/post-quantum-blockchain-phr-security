from functools import lru_cache
from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/pqc_hospital")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef") # 32 bytes for AES
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "admin@hospital.com")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "Admin@1234")
    
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "30"))
    refresh_token_days: int = int(os.getenv("REFRESH_TOKEN_DAYS", "14"))

    AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "AKIA_MOCK_QUANTUMCARE_AWS_KEY")
    AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "mock_aws_secret_key_quantumcare_pqc")
    AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")
    AWS_S3_BUCKET: str = os.getenv("AWS_S3_BUCKET", "quantumcare-pqc-phr-storage")
    IPFS_GATEWAY_URL: str = os.getenv("IPFS_GATEWAY_URL", "https://gateway.pinata.cloud/ipfs/")
    IPFS_PINNING_API_KEY: str = os.getenv("IPFS_PINNING_API_KEY", "")

@lru_cache
def get_settings() -> Settings:
    return Settings()
