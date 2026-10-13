// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title PHR_Security as it was before consentStatus — a TEST FIXTURE only.
 * @dev Never deployed by the application. CI deploys it to a local chain to
 * prove backend/migrate_contract.py carries consent from such a contract to the
 * current one (backend/tests/test_contract_migration_live.py). Same writes and
 * events as contracts/PHR.sol; only the three-state consent record is missing,
 * so "withdrawn" and "never decided" both read as false here.
 */
contract PHR_Security_V1 {
    address public admin;

    struct AuditLog {
        string userUUID;
        string actionType;
        string resourceHash;
        uint256 timestamp;
    }

    mapping(string => mapping(string => bool)) private consentRegistry;
    AuditLog[] public globalAuditTrail;

    event ConsentUpdated(string indexed patientUUID, string indexed doctorUUID, bool isAuthorized, uint256 timestamp);
    event AuditLogged(string indexed userUUID, string actionType, string resourceHash, uint256 timestamp);
    event EmergencyAccessTriggered(string indexed doctorUUID, string indexed patientUUID, uint256 timestamp);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Admin only");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    function updateConsent(string memory patientUUID, string memory doctorUUID, bool _isAuthorized) public onlyAdmin {
        consentRegistry[patientUUID][doctorUUID] = _isAuthorized;
        emit ConsentUpdated(patientUUID, doctorUUID, _isAuthorized, block.timestamp);
        _logAudit(patientUUID, _isAuthorized ? "Grant_Consent" : "Revoke_Consent", doctorUUID);
    }

    function checkConsent(string memory patientUUID, string memory doctorUUID) public view returns (bool) {
        return consentRegistry[patientUUID][doctorUUID];
    }

    function logDataAccess(string memory userUUID, string memory actionType, string memory resourceHash) public onlyAdmin {
        _logAudit(userUUID, actionType, resourceHash);
    }

    function emergencyAccess(string memory emergencyDoctorUUID, string memory patientUUID, string memory resourceHash) public onlyAdmin {
        emit EmergencyAccessTriggered(emergencyDoctorUUID, patientUUID, block.timestamp);
        _logAudit(emergencyDoctorUUID, "EMERGENCY_ACCESS", resourceHash);
    }

    function _logAudit(string memory userUUID, string memory actionType, string memory resourceHash) internal {
        globalAuditTrail.push(AuditLog(userUUID, actionType, resourceHash, block.timestamp));
        emit AuditLogged(userUUID, actionType, resourceHash, block.timestamp);
    }

    function getAuditTrailCount() public view returns (uint256) {
        return globalAuditTrail.length;
    }
}
