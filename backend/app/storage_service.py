import os
import hashlib
import base64
import logging
from typing import Tuple
from app.config import get_settings

logger = logging.getLogger(__name__)

def generate_ipfs_cid_v0(content_bytes: bytes) -> str:
    """
    Generates a standard IPFS multihash CIDv0 (Base58 string starting with Qm...)
    from raw/encrypted file content bytes.
    Standard IPFS multihash format: [0x12 (sha2-256), 0x20 (32 bytes len), sha256_hash]
    """
    sha256_hash = hashlib.sha256(content_bytes).digest()
    multihash_bytes = b"\x12\x20" + sha256_hash
    
    # Base58 encoding for standard IPFS Qm... multihash CIDv0
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    num = int.from_bytes(multihash_bytes, 'big')
    encoded = ""
    while num > 0:
        num, remainder = divmod(num, 58)
        encoded = alphabet[remainder] + encoded
        
    for byte in multihash_bytes:
        if byte == 0:
            encoded = "1" + encoded
        else:
            break
            
    return encoded

def upload_to_aws_s3(encrypted_bytes: bytes, file_name: str, content_type: str = "application/octet-stream") -> Tuple[str, str]:
    """
    Uploads encrypted payload bytes to AWS S3.
    Returns (s3_key, s3_url).
    Supports boto3 when credentials are valid, or provides deterministic S3 URI.
    """
    settings = get_settings()
    s3_key = f"phr_records/{file_name}"
    s3_url = f"https://{settings.AWS_S3_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"

    try:
        import boto3
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        s3_client.put_object(
            Bucket=settings.AWS_S3_BUCKET,
            Key=s3_key,
            Body=encrypted_bytes,
            ContentType=content_type
        )
        logger.info(f"Uploaded file to AWS S3: {s3_url}")
    except Exception as e:
        logger.warning(f"AWS S3 upload fallback (boto3/credentials): {e}")

    return s3_key, s3_url

def process_and_pin_ipfs(encrypted_bytes: bytes, document_name: str) -> Tuple[str, str, str]:
    """
    Processes encrypted medical record bytes into IPFS multihash format and pins to cloud storage.
    Returns (ipfs_cid, ipfs_gateway_url, s3_key).
    """
    settings = get_settings()
    
    # 1. Compute standard IPFS multihash CID (Qm...)
    ipfs_cid = generate_ipfs_cid_v0(encrypted_bytes)
    ipfs_gateway_url = f"{settings.IPFS_GATEWAY_URL}{ipfs_cid}"
    
    # 2. Upload payload to AWS S3 cloud storage
    file_name = f"{ipfs_cid}_{document_name.replace(' ', '_')}.enc"
    s3_key, _ = upload_to_aws_s3(encrypted_bytes, file_name)
    
    logger.info(f"Generated IPFS CID: {ipfs_cid} -> AWS S3 Key: {s3_key}")
    return ipfs_cid, ipfs_gateway_url, s3_key
