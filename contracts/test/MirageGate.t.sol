// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {MirageGate, AggregatorV3Interface} from "../src/MirageGate.sol";
import {ExecutionGuard} from "../src/ExecutionGuard.sol";

/// @dev Minimal controllable stand-in for a Chainlink aggregator.
contract MockAggregator is AggregatorV3Interface {
    uint8 private _decimals;
    int256 private _answer;
    uint256 private _updatedAt;
    uint80 private _roundId;

    constructor(uint8 decimals_, int256 answer_, uint256 updatedAt_) {
        _decimals = decimals_;
        _answer = answer_;
        _updatedAt = updatedAt_;
        _roundId = 1;
    }

    function set(int256 answer_, uint256 updatedAt_) external {
        _answer = answer_;
        _updatedAt = updatedAt_;
        _roundId += 1;
    }

    function decimals() external view returns (uint8) {
        return _decimals;
    }

    function description() external pure returns (string memory) {
        return "MOCK / USD";
    }

    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80) {
        return (_roundId, _answer, _updatedAt, _updatedAt, _roundId);
    }
}

contract MirageGateTest is Test {
    MirageGate internal gate;
    ExecutionGuard internal guard;
    MockAggregator internal feed;

    address internal publisher = address(0xA11CE);
    address internal stranger = address(0xB0B);

    // wstETH/USDC market id from the recorded MIRAGE demonstration.
    bytes32 internal constant MARKET = 0xb323495f7e4148be5643a4ea4a8221eef163e4bccfdedc2a6f4696baacbc86cc;
    uint128 internal constant AMOUNT = 10_000_000_000; // 10,000 USDC, 6 decimals
    uint64 internal constant EVIDENCE_BLOCK = 25_938_082;

    uint32 internal constant MAX_DEVIATION_BPS = 500; // same bound the offchain exit policy uses
    uint64 internal constant MAX_FEED_AGE = 3 hours;
    uint64 internal constant MAX_DECISION_AGE = 1 hours;

    // 3104.787691 USDC per unit, expressed with the feed's 8 decimals.
    uint256 internal constant REFERENCE_PRICE = 310_478_769_100;

    function setUp() public {
        vm.warp(1_700_000_000);
        feed = new MockAggregator(8, int256(REFERENCE_PRICE), block.timestamp);
        gate = new MirageGate(address(feed), publisher, MAX_DEVIATION_BPS, MAX_FEED_AGE);
        guard = new ExecutionGuard(address(gate), MAX_DECISION_AGE);
    }

    // ------------------------------------------------------------------ construction

    function test_constructor_storesFeedMetadata() public view {
        assertEq(address(gate.feed()), address(feed));
        assertEq(gate.feedDecimals(), 8);
        assertEq(gate.publisher(), publisher);
        assertEq(gate.maxDeviationBps(), MAX_DEVIATION_BPS);
    }

    function test_constructor_rejectsZeroAddresses() public {
        vm.expectRevert(MirageGate.ZeroAddress.selector);
        new MirageGate(address(0), publisher, MAX_DEVIATION_BPS, MAX_FEED_AGE);

        vm.expectRevert(MirageGate.ZeroAddress.selector);
        new MirageGate(address(feed), address(0), MAX_DEVIATION_BPS, MAX_FEED_AGE);
    }

    function test_constructor_rejectsOutOfRangeBounds() public {
        vm.expectRevert(MirageGate.BoundOutOfRange.selector);
        new MirageGate(address(feed), publisher, 0, MAX_FEED_AGE);

        vm.expectRevert(MirageGate.BoundOutOfRange.selector);
        new MirageGate(address(feed), publisher, 10_001, MAX_FEED_AGE);

        vm.expectRevert(MirageGate.BoundOutOfRange.selector);
        new MirageGate(address(feed), publisher, MAX_DEVIATION_BPS, 0);
    }

    // ------------------------------------------------------------------ access control

    function test_submit_onlyPublisher() public {
        vm.prank(stranger);
        vm.expectRevert(MirageGate.NotPublisher.selector);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);
    }

    // ------------------------------------------------------------------ the core behaviour

    function test_allow_isRecordedWhenFeedAgrees() public {
        vm.prank(publisher);
        MirageGate.Verdict stored =
            gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        assertEq(uint8(stored), uint8(MirageGate.Verdict.Allow));

        MirageGate.Decision memory d = gate.decisionFor(MARKET, AMOUNT);
        assertEq(uint8(d.verdict), uint8(MirageGate.Verdict.Allow));
        assertEq(d.amountUsdc, AMOUNT);
        assertEq(d.evidenceBlock, EVIDENCE_BLOCK);
        assertEq(d.deviationBps, 0);
        assertFalse(d.vetoedByFeed);
        assertTrue(gate.isAllowed(MARKET, AMOUNT, MAX_DECISION_AGE));
    }

    /// @dev This is the reason the contract exists: Chainlink can only make it stricter.
    function test_allow_isDowngradedWhenFeedDisagreesBeyondBound() public {
        // Feed 10 % below the reference price MIRAGE used. 1000 bps > 500 bps bound.
        feed.set(int256(REFERENCE_PRICE * 90 / 100), block.timestamp);

        vm.prank(publisher);
        MirageGate.Verdict stored =
            gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        assertEq(uint8(stored), uint8(MirageGate.Verdict.Blocked));

        MirageGate.Decision memory d = gate.decisionFor(MARKET, AMOUNT);
        assertTrue(d.vetoedByFeed);
        assertApproxEqAbs(uint256(d.deviationBps), 1111, 2); // diff/chainlink, not diff/reference
        assertFalse(gate.isAllowed(MARKET, AMOUNT, MAX_DECISION_AGE));
    }

    function test_allow_survivesDeviationInsideBound() public {
        // 2 % below: inside the 500 bps bound once expressed against the feed answer.
        feed.set(int256(REFERENCE_PRICE * 98 / 100), block.timestamp);

        vm.prank(publisher);
        MirageGate.Verdict stored =
            gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        assertEq(uint8(stored), uint8(MirageGate.Verdict.Allow));
        assertFalse(gate.decisionFor(MARKET, AMOUNT).vetoedByFeed);
    }

    /// @dev Chainlink never upgrades a decision. A Blocked verdict stays Blocked even when
    ///      the feed agrees perfectly with the reference price.
    function test_blocked_isNeverUpgradedByAgreeingFeed() public {
        vm.prank(publisher);
        MirageGate.Verdict stored =
            gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Blocked);

        assertEq(uint8(stored), uint8(MirageGate.Verdict.Blocked));
        assertFalse(gate.decisionFor(MARKET, AMOUNT).vetoedByFeed);
        assertFalse(gate.isAllowed(MARKET, AMOUNT, MAX_DECISION_AGE));
    }

    function test_submit_rejectsNoneVerdict() public {
        vm.prank(publisher);
        vm.expectRevert(MirageGate.InvalidVerdict.selector);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.None);
    }

    function test_submit_rejectsZeroAmountAndZeroReference() public {
        vm.startPrank(publisher);
        vm.expectRevert(MirageGate.InvalidAmount.selector);
        gate.submitDecision(MARKET, 0, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        vm.expectRevert(MirageGate.InvalidReferencePrice.selector);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, 0, MirageGate.Verdict.Allow);
        vm.stopPrank();
    }

    // ------------------------------------------------------------------ feed health

    function test_submit_revertsOnStaleFeed() public {
        feed.set(int256(REFERENCE_PRICE), block.timestamp);
        vm.warp(block.timestamp + MAX_FEED_AGE + 1);

        vm.prank(publisher);
        vm.expectRevert();
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);
    }

    function test_submit_revertsOnNonPositiveAnswer() public {
        feed.set(0, block.timestamp);

        vm.prank(publisher);
        vm.expectRevert(MirageGate.FeedAnswerNotPositive.selector);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);
    }

    // ------------------------------------------------------------------ size binding

    /// @dev The same property the offchain gate enforces: a decision taken for one sale
    ///      size never authorises a larger one.
    function test_decision_doesNotCarryToADifferentAmount() public {
        vm.prank(publisher);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        assertTrue(gate.isAllowed(MARKET, AMOUNT, MAX_DECISION_AGE));
        assertFalse(gate.isAllowed(MARKET, AMOUNT * 2, MAX_DECISION_AGE));
    }

    function test_decision_agesOut() public {
        vm.prank(publisher);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        vm.warp(block.timestamp + MAX_DECISION_AGE + 1);
        assertFalse(gate.isAllowed(MARKET, AMOUNT, MAX_DECISION_AGE));
    }

    function test_unknownMarketIsNotAllowed() public view {
        assertFalse(gate.isAllowed(bytes32(uint256(1)), AMOUNT, MAX_DECISION_AGE));
        assertEq(uint8(gate.decisionFor(bytes32(uint256(1)), AMOUNT).verdict), uint8(MirageGate.Verdict.None));
    }

    // ------------------------------------------------------------------ the guard

    function test_guard_allowsEntryOnlyAfterAllow() public {
        vm.expectRevert(abi.encodeWithSelector(ExecutionGuard.EntryNotAllowed.selector, MARKET, AMOUNT));
        guard.enter(MARKET, AMOUNT);

        vm.prank(publisher);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        assertTrue(guard.wouldAllow(MARKET, AMOUNT));
        assertEq(guard.enter(MARKET, AMOUNT), 1);
        assertEq(guard.entryCount(), 1);
    }

    function test_guard_revertsWhenGateBlocked() public {
        vm.prank(publisher);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Blocked);

        assertFalse(guard.wouldAllow(MARKET, AMOUNT));
        vm.expectRevert(abi.encodeWithSelector(ExecutionGuard.EntryNotAllowed.selector, MARKET, AMOUNT));
        guard.enter(MARKET, AMOUNT);
        assertEq(guard.entryCount(), 0);
    }

    /// @dev End to end: the feed alone turns an otherwise passing entry into a revert.
    function test_guard_revertsWhenFeedVetoedTheAllow() public {
        feed.set(int256(REFERENCE_PRICE * 90 / 100), block.timestamp);

        vm.prank(publisher);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        vm.expectRevert(abi.encodeWithSelector(ExecutionGuard.EntryNotAllowed.selector, MARKET, AMOUNT));
        guard.enter(MARKET, AMOUNT);
    }

    function test_guard_revertsForADifferentAmount() public {
        vm.prank(publisher);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        vm.expectRevert(abi.encodeWithSelector(ExecutionGuard.EntryNotAllowed.selector, MARKET, AMOUNT * 2));
        guard.enter(MARKET, AMOUNT * 2);
    }

    // ------------------------------------------------------------------ admin

    function test_setPublisherAndBounds() public {
        vm.startPrank(publisher);
        gate.setPublisher(stranger);
        assertEq(gate.publisher(), stranger);
        vm.stopPrank();

        vm.prank(stranger);
        gate.setBounds(250, 1 hours);
        assertEq(gate.maxDeviationBps(), 250);
        assertEq(gate.maxFeedAge(), 1 hours);
    }

    function testFuzz_deviationNeverAllowsBeyondBound(uint256 chainlinkAnswer) public {
        chainlinkAnswer = bound(chainlinkAnswer, 1, type(uint128).max);
        feed.set(int256(chainlinkAnswer), block.timestamp);

        vm.prank(publisher);
        gate.submitDecision(MARKET, AMOUNT, EVIDENCE_BLOCK, REFERENCE_PRICE, MirageGate.Verdict.Allow);

        MirageGate.Decision memory d = gate.decisionFor(MARKET, AMOUNT);
        if (d.deviationBps > MAX_DEVIATION_BPS) {
            assertEq(uint8(d.verdict), uint8(MirageGate.Verdict.Blocked));
        } else {
            assertEq(uint8(d.verdict), uint8(MirageGate.Verdict.Allow));
        }
    }
}
