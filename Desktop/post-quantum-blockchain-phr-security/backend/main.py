from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
import uuid
import os

# Internal Modules
from crypto_utils import crypto_manager

app = FastAPI(title="PQC-Blockchain PHR API", version="1.0.0")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict this!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Pydantic Models ===
class RegisterRequest(BaseModel):
    role: str
    credentials: str

class UploadDataRequest(BaseModel):
    patient_id: str
    ipfs_hash: str
    payload_base64: str

class ConsentRequest(BaseModel):
    patient_id: str
    doctor_id: str
    status: str

# Mock Database connection string
def get_db():
    pass

# === Endpoints ===

@app.post("/api/register")
async def register_user(request: RegisterRequest):
    """
    Registers a user in the PostgreSQL database.
    (In a real implementation, 'credentials' would be hashed natively, 
     and a Kyber Public Key might be generated and linked to their profile).
    """
    new_uuid = str(uuid.uuid4())
    # TODO: Insert into Users table
    return {"status": "success", "uuid": new_uuid, "role": request.role}


@app.post("/api/data/upload")
async def upload_health_record(request: UploadDataRequest):
    """
    Simulates storing a health record encrypted with AES, wrapped in Kyber.
    """
    try:
        # Step 1: In a real system, we'd fetch the public key of the Patient or Dr.
        receiver_public_key, _ = crypto_manager.generate_keypair()
    
        # Step 2: KEM - Encapsulate an AES key with Kyber
        ciphertext_kyber, aes_shareable_key = crypto_manager.encapsulate_key(receiver_public_key)
    
        # Step 3: Use AES key to encrypt the payload data locally (simulated here)
        # payload = base64.b64decode(request.payload_base64)
        # encrypted_payload_dict = crypto_manager.encrypt_payload_aes(aes_shareable_key, payload)
    
        # Step 4: Insert record into PostgreSQL mapping Patient -> IPFS Hash -> Kyber Ciphertext
        # TODO: db_insert(patient_id, request.ipfs_hash, ciphertext_kyber)
    
        return {
            "status": "success", 
            "message": "File wrapped in Kyber AES and metadata committed.",
            "ipfs": request.ipfs_hash,
            # "kyber_ciphertext_snippet": ciphertext_kyber[:20].hex() # Just for debugging
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/record/access")
async def access_record(record_id: str, requester_id: str):
    """
    Verifies Consent + Audit logs it to Blockchain.
    Returns the Decapsulated AES Key if authorized.
    """
    # Step 1: Check Consent Table (Postgres)
    # is_authorized = check_consent(record_id, requester_id)
    is_authorized = True # Mock
    if not is_authorized:
        raise HTTPException(status_code=403, detail="Unauthorized access attempt.")

    # Step 2: Trigger Blockchain Audit Log Smart Contract via Web3.py
    # trigger_audit(requester_id, "Read_Record", timestamp, ipfs_hash)
    
    # Step 3: Decapsulate key (User provides secret_key to their local client ideally)
    
    return {
        "status": "success",
        "message": "Access granted. Authorized.",
        "blockchain_tx": "0xabc123mocktxhash..."
    }


@app.post("/api/consent/update")
async def update_consent(request: ConsentRequest):
    """
    Updates the consent status in PostgreSQL.
    """
    # TODO: Upsert into Consents table
    return {"status": "success", "message": f"Consent updated to {request.status} for Dr. {request.doctor_id}"}


@app.post("/api/federated-update")
async def federated_update(hospital_node_id: str, weights_payload: dict):
    """
    Phase 4: AI Security Layer.
    Receives encrypted local AI model weights for global Anomaly Detection aggregation.
    """
    return {"status": "success", "message": "Federated weights securely received for aggregation."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
