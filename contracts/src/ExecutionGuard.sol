// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {MirageGate} from "./MirageGate.sol";

/// @title ExecutionGuard
/// @notice Reference consumer of MirageGate. Exists to make the recorded verdict
///         load-bearing rather than decorative.
///
/// @dev A gate that only writes a flag nobody reads is logging, not a gate. This contract
///      is the smallest honest demonstration that the flag actually governs execution:
///      `enter` reverts unless MirageGate holds a fresh ALLOW for the exact market and the
///      exact sale size being entered.
///
///      It is deliberately not a vault. It moves no funds and custodies nothing, which
///      keeps the prototype's boundary intact: MIRAGE still never holds or transfers
///      value. What it does prove is the control flow. A BLOCK decision makes the entry
///      transaction fail onchain, which is observable on a block explorer.
contract ExecutionGuard {
    error EntryNotAllowed(bytes32 marketId, uint128 amountUsdc);
    error ZeroAddress();
    error InvalidMaxAge();

    event Entered(bytes32 indexed marketId, uint128 indexed amountUsdc, uint64 evidenceBlock, uint256 entryCount);

    MirageGate public immutable gate;

    /// @notice How old a recorded decision may be and still authorise an entry.
    uint64 public immutable maxDecisionAge;

    /// @notice Number of entries this guard has admitted. The only state it keeps.
    uint256 public entryCount;

    constructor(address gate_, uint64 maxDecisionAge_) {
        if (gate_ == address(0)) revert ZeroAddress();
        if (maxDecisionAge_ == 0) revert InvalidMaxAge();
        gate = MirageGate(gate_);
        maxDecisionAge = maxDecisionAge_;
    }

    /// @notice Attempt an entry for one market at one exact size.
    /// @dev Reverts with `EntryNotAllowed` when the gate holds no decision, a Blocked
    ///      decision, a decision for a different amount, or a decision that has aged out.
    function enter(bytes32 marketId, uint128 amountUsdc) external returns (uint256) {
        if (!gate.isAllowed(marketId, amountUsdc, maxDecisionAge)) {
            revert EntryNotAllowed(marketId, amountUsdc);
        }

        MirageGate.Decision memory d = gate.decisionFor(marketId, amountUsdc);
        unchecked {
            entryCount += 1;
        }
        emit Entered(marketId, amountUsdc, d.evidenceBlock, entryCount);
        return entryCount;
    }

    /// @notice Read-only preview of what `enter` would do, for callers that want to check
    ///         before spending gas.
    function wouldAllow(bytes32 marketId, uint128 amountUsdc) external view returns (bool) {
        return gate.isAllowed(marketId, amountUsdc, maxDecisionAge);
    }
}
