// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @notice Minimal Chainlink aggregator interface, vendored so this project pulls no
///         external Solidity dependency. Matches AggregatorV3Interface exactly.
interface AggregatorV3Interface {
    function decimals() external view returns (uint8);

    function description() external view returns (string memory);

    function latestRoundData()
        external
        view
        returns (uint80 roundId, int256 answer, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound);
}

/// @title MirageGate
/// @notice Records the MIRAGE admission decision for one Morpho Blue market and one
///         sale size, onchain, and lets a Chainlink price feed veto it.
///
/// @dev Division of labour, deliberately kept narrow.
///
///      MIRAGE itself stays offchain and read-only. It discovers the market through The
///      Graph, reads Morpho, the oracle and Uniswap directly, and produces a verdict for
///      an exact (market, amount, evidence block) triple. Only that finished verdict is
///      submitted here.
///
///      This contract is not a mirror of that work. It performs an independent check that
///      the offchain pipeline cannot perform on its own: it reads a Chainlink feed at
///      submission time and compares the price MIRAGE used against it. The comparison can
///      only ever make the outcome stricter. A proposed ALLOW whose reference price
///      disagrees with Chainlink beyond the configured bound is stored as BLOCK; a
///      proposed BLOCK is always stored as BLOCK. Chainlink can veto an entry here. It can
///      never authorise one.
///
///      The stored decision is meant to be read by whatever executes next. `ExecutionGuard`
///      in this repository is the reference consumer: it reverts unless this contract holds
///      a fresh ALLOW for the exact market and amount being entered.
contract MirageGate {
    // --------------------------------------------------------------------- types

    enum Verdict {
        None, // no decision recorded for this key
        Allow, // offchain checks passed and Chainlink agreed with the reference price
        Blocked // offchain checks failed, or Chainlink disagreed beyond the bound
    }

    struct Decision {
        Verdict verdict;
        uint128 amountUsdc; // exact sale size the verdict covers, 6 decimals
        uint64 evidenceBlock; // Ethereum mainnet block the offchain evidence was read at
        uint64 recordedAt; // block.timestamp of this submission
        int256 chainlinkAnswer; // raw feed answer observed at submission
        uint80 chainlinkRound; // feed round the answer came from
        uint32 deviationBps; // |reference - chainlink| / chainlink, in basis points
        bool vetoedByFeed; // true when Chainlink downgraded a proposed Allow
    }

    // --------------------------------------------------------------------- errors

    error NotPublisher();
    error ZeroAddress();
    error InvalidVerdict();
    error InvalidAmount();
    error InvalidReferencePrice();
    error FeedAnswerNotPositive();
    error FeedRoundIncomplete();
    error FeedStale(uint256 updatedAt, uint256 nowTs, uint256 maxAge);
    error BoundOutOfRange();

    // --------------------------------------------------------------------- events

    event DecisionRecorded(
        bytes32 indexed marketId,
        uint128 indexed amountUsdc,
        Verdict verdict,
        Verdict proposedVerdict,
        uint64 evidenceBlock,
        int256 chainlinkAnswer,
        uint80 chainlinkRound,
        uint32 deviationBps,
        bool vetoedByFeed
    );
    event PublisherChanged(address indexed previous, address indexed current);
    event BoundsChanged(uint32 maxDeviationBps, uint64 maxFeedAge);

    // --------------------------------------------------------------------- storage

    /// @notice Chainlink aggregator consulted on every submission. Immutable by design:
    ///         a decision history is only meaningful against one fixed price source.
    AggregatorV3Interface public immutable feed;

    /// @notice Decimals reported by the feed, cached at construction.
    uint8 public immutable feedDecimals;

    /// @notice Address allowed to submit decisions. The MIRAGE operator.
    address public publisher;

    /// @notice Largest tolerated disagreement between the reference price MIRAGE used and
    ///         the Chainlink answer, in basis points. Above this, an Allow becomes Blocked.
    uint32 public maxDeviationBps;

    /// @notice Oldest tolerated feed update, in seconds. Beyond this a submission reverts
    ///         rather than recording a decision on a stale price.
    uint64 public maxFeedAge;

    /// @dev keccak256(marketId, amountUsdc) => decision.
    mapping(bytes32 => Decision) private _decisions;

    // --------------------------------------------------------------------- modifiers

    modifier onlyPublisher() {
        if (msg.sender != publisher) revert NotPublisher();
        _;
    }

    // --------------------------------------------------------------------- construction

    constructor(address feed_, address publisher_, uint32 maxDeviationBps_, uint64 maxFeedAge_) {
        if (feed_ == address(0) || publisher_ == address(0)) revert ZeroAddress();
        if (maxDeviationBps_ == 0 || maxDeviationBps_ > 10_000) revert BoundOutOfRange();
        if (maxFeedAge_ == 0) revert BoundOutOfRange();

        feed = AggregatorV3Interface(feed_);
        feedDecimals = AggregatorV3Interface(feed_).decimals();
        publisher = publisher_;
        maxDeviationBps = maxDeviationBps_;
        maxFeedAge = maxFeedAge_;

        emit PublisherChanged(address(0), publisher_);
        emit BoundsChanged(maxDeviationBps_, maxFeedAge_);
    }

    // --------------------------------------------------------------------- admin

    function setPublisher(address publisher_) external onlyPublisher {
        if (publisher_ == address(0)) revert ZeroAddress();
        emit PublisherChanged(publisher, publisher_);
        publisher = publisher_;
    }

    function setBounds(uint32 maxDeviationBps_, uint64 maxFeedAge_) external onlyPublisher {
        if (maxDeviationBps_ == 0 || maxDeviationBps_ > 10_000) revert BoundOutOfRange();
        if (maxFeedAge_ == 0) revert BoundOutOfRange();
        maxDeviationBps = maxDeviationBps_;
        maxFeedAge = maxFeedAge_;
        emit BoundsChanged(maxDeviationBps_, maxFeedAge_);
    }

    // --------------------------------------------------------------------- submission

    /// @notice Record one MIRAGE admission decision, subject to a live Chainlink check.
    /// @param marketId        Morpho Blue market id the decision covers.
    /// @param amountUsdc      Exact sale size the offchain evidence covers, 6 decimals.
    ///                        A decision never applies to a different amount.
    /// @param evidenceBlock   Mainnet block the offchain evidence was read at.
    /// @param referencePrice  Collateral price MIRAGE used, scaled to the feed's decimals.
    /// @param proposed        Verdict the offchain pipeline produced. Allow or Blocked.
    /// @return stored         Verdict actually recorded after the Chainlink check.
    function submitDecision(
        bytes32 marketId,
        uint128 amountUsdc,
        uint64 evidenceBlock,
        uint256 referencePrice,
        Verdict proposed
    ) external onlyPublisher returns (Verdict stored) {
        if (proposed != Verdict.Allow && proposed != Verdict.Blocked) revert InvalidVerdict();
        if (amountUsdc == 0) revert InvalidAmount();
        if (referencePrice == 0) revert InvalidReferencePrice();

        (uint80 roundId, int256 answer,, uint80 answeredInRound) = _readFeed();
        // casting to uint256 is safe: _readFeed reverts unless answer is strictly
        // positive, so the sign bit is never set here.
        // forge-lint: disable-next-line(unsafe-typecast)
        uint32 deviationBps = _deviationBps(referencePrice, uint256(answer));

        bool veto = proposed == Verdict.Allow && deviationBps > maxDeviationBps;
        stored = veto ? Verdict.Blocked : proposed;

        _decisions[_key(marketId, amountUsdc)] = Decision({
            verdict: stored,
            amountUsdc: amountUsdc,
            evidenceBlock: evidenceBlock,
            // casting to uint64 is safe: block.timestamp exceeds 2**64 only far beyond
            // any plausible lifetime of this contract.
            // forge-lint: disable-next-line(unsafe-typecast)
            recordedAt: uint64(block.timestamp),
            chainlinkAnswer: answer,
            chainlinkRound: roundId,
            deviationBps: deviationBps,
            vetoedByFeed: veto
        });

        // answeredInRound is read and surfaced through the event's round field only; the
        // staleness guard above is what protects the decision.
        answeredInRound;

        emit DecisionRecorded(
            marketId, amountUsdc, stored, proposed, evidenceBlock, answer, roundId, deviationBps, veto
        );
    }

    // --------------------------------------------------------------------- reads

    /// @notice Full decision record for a market and amount. `verdict == None` means no
    ///         decision was ever recorded for this exact pair.
    function decisionFor(bytes32 marketId, uint128 amountUsdc) external view returns (Decision memory) {
        return _decisions[_key(marketId, amountUsdc)];
    }

    /// @notice True only when a decision exists for this exact market and amount, it is
    ///         Allow, and it was recorded no longer than `maxAge` seconds ago.
    /// @dev    The amount is part of the key on purpose. A decision taken for one sale
    ///         size says nothing about a larger one, which moves the price further.
    function isAllowed(bytes32 marketId, uint128 amountUsdc, uint64 maxAge) public view returns (bool) {
        Decision storage d = _decisions[_key(marketId, amountUsdc)];
        if (d.verdict != Verdict.Allow) return false;
        if (block.timestamp > uint256(d.recordedAt) + uint256(maxAge)) return false;
        return true;
    }

    function key(bytes32 marketId, uint128 amountUsdc) external pure returns (bytes32) {
        return _key(marketId, amountUsdc);
    }

    // --------------------------------------------------------------------- internals

    function _key(bytes32 marketId, uint128 amountUsdc) private pure returns (bytes32) {
        return keccak256(abi.encodePacked(marketId, amountUsdc));
    }

    function _readFeed()
        private
        view
        returns (uint80 roundId, int256 answer, uint256 updatedAt, uint80 answeredInRound)
    {
        uint256 startedAt;
        (roundId, answer, startedAt, updatedAt, answeredInRound) = feed.latestRoundData();
        startedAt;

        if (answer <= 0) revert FeedAnswerNotPositive();
        if (updatedAt == 0) revert FeedRoundIncomplete();
        if (block.timestamp > updatedAt + uint256(maxFeedAge)) {
            revert FeedStale(updatedAt, block.timestamp, uint256(maxFeedAge));
        }
    }

    /// @dev Symmetric relative difference against the Chainlink answer, in basis points,
    ///      saturating at 10000 so an absurd reference price cannot overflow the field.
    function _deviationBps(uint256 refPrice, uint256 feedPrice) private pure returns (uint32) {
        uint256 diff = refPrice > feedPrice ? refPrice - feedPrice : feedPrice - refPrice;
        uint256 bps = (diff * 10_000) / feedPrice;
        // casting to uint32 is safe: the ternary above returns before the cast whenever
        // bps reaches 10_000, so the cast only ever sees a value below that.
        // forge-lint: disable-next-line(unsafe-typecast)
        return bps >= 10_000 ? uint32(10_000) : uint32(bps);
    }
}
