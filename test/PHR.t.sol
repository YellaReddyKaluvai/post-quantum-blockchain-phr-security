// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../contracts/PHR.sol";

// Foundry cheatcodes, declared directly so the test needs no forge-std checkout.
interface Vm {
    function prank(address) external;
    function expectRevert(bytes calldata) external;
}

contract PHRSecurityTest {
    Vm constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    PHR_Security phr;
    address constant OUTSIDER = address(0xBEEF);

    function setUp() public {
        phr = new PHR_Security();      // this test contract is the admin
    }

    function test_onlyTheBackendKeyCanWriteConsent() public {
        vm.prank(OUTSIDER);
        vm.expectRevert(bytes("Admin only"));
        phr.updateConsent("p", "d", true);
    }

    function test_onlyTheBackendKeyCanAppendAuditOrEmergency() public {
        vm.prank(OUTSIDER);
        vm.expectRevert(bytes("Admin only"));
        phr.logDataAccess("u", "READ", "h");
        vm.prank(OUTSIDER);
        vm.expectRevert(bytes("Admin only"));
        phr.emergencyAccess("d", "p", "h");
    }

    function test_revocationIsDistinctFromNoRecord() public {
        require(phr.consentStatus("p", "d") == 0, "fresh pair has no record");
        phr.updateConsent("p", "d", true);
        require(phr.consentStatus("p", "d") == 1 && phr.checkConsent("p", "d"), "granted");
        phr.updateConsent("p", "d", false);
        require(phr.consentStatus("p", "d") == 2 && !phr.checkConsent("p", "d"), "revoked");
        require(phr.getAuditTrailCount() == 2, "each decision is audited");
    }
}
