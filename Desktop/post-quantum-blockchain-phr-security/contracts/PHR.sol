// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title PHR Security - Consent & Audit Log Contract
 * @dev Immutable ledger for Personal Health Record access control and auditing.
 */
contract PHR_Security {
    
    address public admin;

    // --- Structures ---
    
    struct AuditLog {
        string userUUID;      // Who performed the action (Patient/Doctor UUID)
        string actionType;    // E.g., "Read_Record", "Upload_Record", "Emergency_Access"
        string resourceHash;  // Decentralized Identifer (e.g., IPFS CID)
        uint256 timestamp;    // When
    }
    
    // --- State Variables ---

    // patientUUID => mapping(doctorUUID => isAuthorized)
    mapping(string => mapping(string => bool)) private consentRegistry;
    
    // Ordered list of all immutable audit events
    AuditLog[] public globalAuditTrail;

    // --- Events ---
    event ConsentUpdated(string indexed patientUUID, string indexed doctorUUID, bool isAuthorized, uint256 timestamp);
    event AuditLogged(string indexed userUUID, string actionType, string resourceHash, uint256 timestamp);
    event EmergencyAccessTriggered(string indexed doctorUUID, string indexed patientUUID, uint256 timestamp);

    // --- Modifiers ---
    modifier onlyAdmin() {
        require(msg.sender == admin, "Admin only");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    // --- Core Functions ---

    /**
     * @dev Patients can grant or revoke access to a specific doctor.
     * @param patientUUID The UUID of the patient granting consent.
     * @param doctorUUID The UUID of the doctor receiving consent.
     * @param _isAuthorized True to grant, False to revoke.
     */
    function updateConsent(string memory patientUUID, string memory doctorUUID, bool _isAuthorized) public {
        // In a real dApp, msg.sender would be verified against a mapping of patient wallets.
        // For API abstraction, we assume the backend validates JWTs before calling this script.
        consentRegistry[patientUUID][doctorUUID] = _isAuthorized;
        
        emit ConsentUpdated(patientUUID, doctorUUID, _isAuthorized, block.timestamp);
        
        // Implicitly log the consent change
        _logAudit(patientUUID, _isAuthorized ? "Grant_Consent" : "Revoke_Consent", doctorUUID);
    }

    /**
     * @dev Checks if a doctor has access to a patient's records.
     */
    function checkConsent(string memory patientUUID, string memory doctorUUID) public view returns (bool) {
        return consentRegistry[patientUUID][doctorUUID];
    }

    /**
     * @dev Adds an immutable record to the blockchain. Called by the backend whenever a record is accessed.
     */
    function logDataAccess(string memory userUUID, string memory actionType, string memory resourceHash) public {
        _logAudit(userUUID, actionType, resourceHash);
    }

    /**
     * @dev "Break-Glass" Emergency Access Protocol.
     * Logs a high-priority, immutable event alerting the patient and admins of emergency data access.
     */
    function emergencyAccess(string memory emergencyDoctorUUID, string memory patientUUID, string memory resourceHash) public {
        // Trigger high-priority event
        emit EmergencyAccessTriggered(emergencyDoctorUUID, patientUUID, block.timestamp);
        
        // Log the forced access
        _logAudit(emergencyDoctorUUID, "EMERGENCY_ACCESS", resourceHash);
    }

    // --- Internal Helpers ---
    
    function _logAudit(string memory userUUID, string memory actionType, string memory resourceHash) internal {
        AuditLog memory newLog = AuditLog({
            userUUID: userUUID,
            actionType: actionType,
            resourceHash: resourceHash,
            timestamp: block.timestamp
        });
        
        globalAuditTrail.push(newLog);
        emit AuditLogged(userUUID, actionType, resourceHash, block.timestamp);
    }
    
    /**
     * @dev Returns the total number of audit logs.
     */
    function getAuditTrailCount() public view returns (uint256) {
        return globalAuditTrail.length;
    }
}
