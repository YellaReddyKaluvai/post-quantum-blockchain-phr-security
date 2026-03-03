-- Database: phr_db

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table: Users
CREATE TABLE IF NOT EXISTS Users (
    UUID UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    Role VARCHAR(50) NOT NULL CHECK (Role IN ('Patient', 'Doctor', 'Admin', 'Emergency')),
    Credentials VARCHAR(255) NOT NULL, -- Hashed password
    Created_At TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: Health_Records
CREATE TABLE IF NOT EXISTS Health_Records (
    Record_ID UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    Patient_ID UUID NOT NULL REFERENCES Users(UUID) ON DELETE CASCADE,
    IPFS_Hash VARCHAR(255) NOT NULL, -- The Decentralized Hash 
    Kyber_Encrypted_Key TEXT NOT NULL, -- The AES key encapsulated by Kyber
    Created_At TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: Consents
CREATE TABLE IF NOT EXISTS Consents (
    Consent_ID UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    Patient_ID UUID NOT NULL REFERENCES Users(UUID) ON DELETE CASCADE,
    Doctor_ID UUID NOT NULL REFERENCES Users(UUID) ON DELETE CASCADE,
    Status VARCHAR(20) NOT NULL CHECK (Status IN ('Authorized', 'Revoked')),
    Updated_At TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(Patient_ID, Doctor_ID)
);

-- Table: Audit_Logs
CREATE TABLE IF NOT EXISTS Audit_Logs (
    Log_ID UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    User_ID UUID NOT NULL REFERENCES Users(UUID),
    Action VARCHAR(100) NOT NULL,
    Blockchain_TX_Hash VARCHAR(100), -- Nullable initially until synced
    Resource_Hash VARCHAR(255), -- IPFS_Hash or Record_ID accessed
    Timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Table: Emergency_Access
CREATE TABLE IF NOT EXISTS Emergency_Access (
    ID UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    Requestor_ID UUID NOT NULL REFERENCES Users(UUID),
    Patient_ID UUID NOT NULL REFERENCES Users(UUID),
    Expiry_Time TIMESTAMP WITH TIME ZONE NOT NULL,
    Status VARCHAR(20) NOT NULL CHECK (Status IN ('Active', 'Expired', 'Revoked')),
    Created_At TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
