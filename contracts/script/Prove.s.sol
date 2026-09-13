// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {MirageGate} from "../src/MirageGate.sol";
import {ExecutionGuard} from "../src/ExecutionGuard.sol";

/// @notice One-shot operator script: deploy, record both decisions, and take the entry
///         the evidence actually covers — in a single broadcast, so the operator supplies
///         their key once instead of four times.
///
/// @dev Every value below is a constant of the recorded evidence, not a parameter:
///      the market, the mainnet block the evidence was read at, and the reference price
///      MIRAGE derived there. They match `mirage/snapshots/mainnet-full-25938082-diagnostics-v2.json.gz`
///      and the output of `scripts/mirage_chainlink_publish.py`, which remains the readable
///      path and prints the same numbers.
///
///      The deliberate failure is NOT here. `ExecutionGuard.enter` for 20,000 USDC must
///      revert, and a script aborts when a broadcast call reverts in simulation, so that
///      one is sent separately with an explicit gas limit — see the runbook, step 3.
///
///      Run with the operator's own key. Nothing in this repository stores or reads one.
///
///        forge script script/Prove.s.sol:Prove \
///          --rpc-url $SEPOLIA_RPC_URL --broadcast --interactive 1
///
///      Environment:
///        CHAINLINK_FEED     aggregator address (Sepolia ETH/USD: 0x694AA1769357215DE4FAC081bf1f309aDC325306)
///        MAX_DEVIATION_BPS  optional, defaults to 500, matching the offchain exit policy
///        MAX_FEED_AGE       optional, defaults to 10800 seconds
///        MAX_DECISION_AGE   optional, defaults to 3600 seconds
contract Prove is Script {
    /// @dev The WETH/USDC Morpho Blue market MIRAGE inspected.
    bytes32 internal constant MARKET = 0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd;

    /// @dev Mainnet block the offchain evidence was read at.
    uint64 internal constant EVIDENCE_BLOCK = 25_938_082;

    /// @dev MIRAGE's reference price, 2500.66364819905... USDC per WETH, scaled to the
    ///      feed's eight decimals.
    uint256 internal constant REFERENCE_SCALED = 250_066_364_819;

    /// @dev The size the saved sale quote covers, and the size it does not.
    uint128 internal constant AMOUNT_ALLOW = 10_000_000_000; // 10,000 USDC, 6 decimals
    uint128 internal constant AMOUNT_BLOCK = 20_000_000_000; // 20,000 USDC, 6 decimals

    function run() external returns (MirageGate gate, ExecutionGuard guard) {
        address feed = vm.envAddress("CHAINLINK_FEED");
        uint32 maxDeviationBps = uint32(vm.envOr("MAX_DEVIATION_BPS", uint256(500)));
        uint64 maxFeedAge = uint64(vm.envOr("MAX_FEED_AGE", uint256(10_800)));
        uint64 maxDecisionAge = uint64(vm.envOr("MAX_DECISION_AGE", uint256(3_600)));

        vm.startBroadcast();

        address publisher = msg.sender;
        gate = new MirageGate(feed, publisher, maxDeviationBps, maxFeedAge);
        guard = new ExecutionGuard(address(gate), maxDecisionAge);

        gate.submitDecision(MARKET, AMOUNT_ALLOW, EVIDENCE_BLOCK, REFERENCE_SCALED, MirageGate.Verdict.Allow);
        gate.submitDecision(MARKET, AMOUNT_BLOCK, EVIDENCE_BLOCK, REFERENCE_SCALED, MirageGate.Verdict.Blocked);

        guard.enter(MARKET, AMOUNT_ALLOW);

        vm.stopBroadcast();

        MirageGate.Decision memory allowed = gate.decisionFor(MARKET, AMOUNT_ALLOW);
        MirageGate.Decision memory blocked = gate.decisionFor(MARKET, AMOUNT_BLOCK);

        console2.log("");
        console2.log("=== send these to Claude ===");
        console2.log("MirageGate     ", address(gate));
        console2.log("ExecutionGuard ", address(guard));
        console2.log("");
        console2.log("=== what was recorded ===");
        console2.log("publisher      ", publisher);
        console2.log("feed           ", feed);
        console2.log("chainlinkAnswer", allowed.chainlinkAnswer);
        console2.log("deviationBps   ", allowed.deviationBps);
        console2.log("10000 verdict  ", uint8(allowed.verdict)); // 1 = Allow
        console2.log("10000 vetoed   ", allowed.vetoedByFeed); // false = the feed agreed
        console2.log("20000 verdict  ", uint8(blocked.verdict)); // 2 = Blocked
        console2.log("isAllowed 10000", gate.isAllowed(MARKET, AMOUNT_ALLOW, maxDecisionAge));
        console2.log("isAllowed 20000", gate.isAllowed(MARKET, AMOUNT_BLOCK, maxDecisionAge));
        console2.log("entryCount     ", guard.entryCount());
        console2.log("");
        console2.log("Now send the deliberate failure, which cannot live in a script:");
        console2.log("  cast send <ExecutionGuard above> \"enter(bytes32,uint128)\" \\");
        console2.log("    0x94b823e6bd8ea533b4e33fbc307faea0b307301bc48763acc4d4aa4def7636cd 20000000000 \\");
        console2.log("    --rpc-url $SEPOLIA_RPC_URL --interactive --gas-limit 120000");
    }
}
