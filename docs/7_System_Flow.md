# 7. System Flows

The four sequences the system has to get right.

## 1. Registration → approval → usable account

```mermaid
sequenceDiagram
    participant U as New user
    participant API as FastAPI
    participant A as Administrator
    participant C as Crypto Service
    participant M as SMTP

    U->>API: POST /api/signup
    API->>API: Argon2id hash, encrypt DOB + blood group
    API-->>A: status Pending
    A->>API: approve
    API->>API: issue permanent ID (PAT-2026-000001)
    API->>C: generate ML-KEM-768 + ML-DSA-65 keypairs
    C-->>API: public keys + AES-encrypted private keys
    API->>M: approval email
    Note over API: Keys exist only after approval.<br/>A pending or rejected account<br/>never holds usable key material.
```

## 2. Doctor requests access → patient decides → backend enforces

```mermaid
sequenceDiagram
    participant D as Doctor
    participant API as FastAPI
    participant P as Patient
    participant B as Blockchain

    D->>API: POST /api/doctor/access-requests (purpose required)
    API-->>P: ACCESS_REQUEST notification
    Note over API: read attempt now → 403
    P->>API: POST .../approve
    API->>B: anchor the consent decision
    API-->>D: ACCESS_GRANTED notification
    D->>API: GET /api/doctor/patients/{id}
    API-->>D: 200 — record released
```

**Verified end to end:** no request `403` · pending `403` · rejected `403` ·
approved `200`. A different patient approving by substituted request id gets
`404`.

## 3. Doctor → laboratory → patient (the main clinical workflow)

```mermaid
flowchart LR
    A[Doctor orders<br/>investigation] --> B[Lab queue<br/>priority ordered]
    B --> C[Structured form<br/>1 of 9 panels]
    C --> D[Hospital PDF]
    D --> E[SHA-256]
    E --> F[AES-256-GCM]
    F --> G[ML-KEM-768<br/>wraps AES key]
    G --> H[ML-DSA-65<br/>signs digest]
    H --> I[(DB + S3 + IPFS)]
    I --> J[Chain anchor]
    J --> K[Notify patient<br/>and doctor]
    K --> L[Verified read<br/>digest re-checked]
```

## 4. Emergency break-glass

```mermaid
sequenceDiagram
    participant D as Doctor
    participant API as FastAPI
    participant P as Patient
    participant B as Blockchain
    participant A as Administrator

    Note over D,API: Patient has withdrawn consent — reads return 404
    D->>API: POST /api/doctor/emergency-access (clinical reason, ≤24h)
    API->>API: validate reason is substantive
    API-->>P: EMERGENCY_ACCESS notification, immediately
    API->>B: anchor the declaration
    API-->>A: appears in Emergency Access review
    D->>API: record now readable until expiry
```

Break-glass is deliberately **not** gated on approval — waiting for a second
party in an emergency defeats the purpose. The control is accountability, not
prevention: the reason must be substantive, the override is time-boxed, the
patient is told at once, and the declaration is anchored so it cannot be quietly
removed.

## 5. Security event → risk → alert → incident

```mermaid
flowchart LR
    A[Authentication] --> B[RBAC]
    B --> C[Relationship<br/>or consent]
    C --> D{Access<br/>decision}
    D -->|refused| X[403]
    D -->|allowed| E[Record released]
    E -.->|behavioural<br/>metadata only| F[Security event]
    F --> G[Peer baseline<br/>median ± MAD]
    G --> H[Risk score<br/>+ attribution]
    H --> I{Level}
    I -->|LOW| J[Monitor]
    I -->|MEDIUM| K[Verify]
    I -->|HIGH| L[Escalate → Incident]
```

Nothing produced by the AI layer feeds back into the access decision. It can
raise an alarm about a read; it cannot authorise or prevent one.
