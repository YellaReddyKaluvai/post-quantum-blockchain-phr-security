# Documentation index

Start with [installation](../INSTALL.md) for a new checkout, or
[deployment](../DEPLOY.md) for hosting and migration.

| Document | What it explains |
|---|---|
| [Architecture](1_Architecture_Proof.md) | Layers, technology choices and source map |
| [Modules](2_Module_Breakdown.md) | Backend responsibilities and frontend roles |
| [Development plan](3_Engagement_Plan.md) | Implemented and remaining work |
| [Validation](4_Architecture_Validation.md) | Security properties and refusal tests |
| [Build, tests and CI](5_Process_Audit_CICD_Docker.md) | Containers and checks |
| [Requirements](6_Design_Report_SRS.md) | Requirements and explicit non-goals |
| [System flows](7_System_Flow.md) | Registration, records, consent and audit paths |
| [Identity and access](8_IAM_Architecture.md) | Sessions, roles and emergency access |
| [Database schema](9_Database_Schema.md) | Relationships, encryption and indexes |
| [Federation deployment](10_Federation_Deployment.md) | Hub and independent participants |
| [Repository checklist](11_Repository_Checklist.md) | Evidence for repository requirements |

Reusable resources include [the SQL schema](../backend/db/init.sql),
[backend configuration](../backend/.env.example),
[frontend configuration](../frontend/.env.example),
[cryptography demos](../backend/demo/README.md),
[tests](../backend/tests/), [contract](../contracts/PHR.sol), and
[CI workflow](../.github/workflows/deploy.yml).

The README describes source capabilities. A deployment has only the external
integrations it actually configures; consult [DEPLOY.md](../DEPLOY.md) for the
hosted baseline and verification limits.
