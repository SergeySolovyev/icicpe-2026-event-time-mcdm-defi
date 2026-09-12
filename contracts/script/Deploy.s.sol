// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {MirageGate} from "../src/MirageGate.sol";
import {ExecutionGuard} from "../src/ExecutionGuard.sol";

/// @notice Deploys MirageGate against a Chainlink feed, plus the reference consumer.
///
/// @dev Run with the operator's own key. Nothing in this repository stores or reads a
///      private key; the deployer supplies it to forge at the command line.
///
///      forge script script/Deploy.s.sol:Deploy \
///        --rpc-url $SEPOLIA_RPC_URL --broadcast --verify
///
///      Environment:
///        CHAINLINK_FEED     aggregator address (Sepolia ETH/USD: 0x694AA1769357215DE4FAC081bf1f309aDC325306)
///        MIRAGE_PUBLISHER   address allowed to submit decisions; defaults to the deployer
///        MAX_DEVIATION_BPS  optional, defaults to 500, matching the offchain exit policy
///        MAX_FEED_AGE       optional, defaults to 10800 seconds
///        MAX_DECISION_AGE   optional, defaults to 3600 seconds
contract Deploy is Script {
    function run() external returns (MirageGate gate, ExecutionGuard guard) {
        address feed = vm.envAddress("CHAINLINK_FEED");
        address publisher = vm.envOr("MIRAGE_PUBLISHER", msg.sender);
        uint32 maxDeviationBps = uint32(vm.envOr("MAX_DEVIATION_BPS", uint256(500)));
        uint64 maxFeedAge = uint64(vm.envOr("MAX_FEED_AGE", uint256(10_800)));
        uint64 maxDecisionAge = uint64(vm.envOr("MAX_DECISION_AGE", uint256(3_600)));

        vm.startBroadcast();
        gate = new MirageGate(feed, publisher, maxDeviationBps, maxFeedAge);
        guard = new ExecutionGuard(address(gate), maxDecisionAge);
        vm.stopBroadcast();

        console2.log("MirageGate     ", address(gate));
        console2.log("ExecutionGuard ", address(guard));
        console2.log("feed           ", feed);
        console2.log("publisher      ", publisher);
        console2.log("maxDeviationBps", maxDeviationBps);
        console2.log("maxFeedAge     ", maxFeedAge);
        console2.log("maxDecisionAge ", maxDecisionAge);
    }
}
