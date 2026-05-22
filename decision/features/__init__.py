"""Signal feature builders for the T3 hazard model.

Three families per MacKenzie (2021) *Trading at the Speed of Light*
Table 3.2 mapped to DeFi lending:
    f1 (lead)          -- DSR / sDAI / Curve 3pool rate-lead features
    f3 (fragmentation) -- pairwise cross-protocol spreads (dominant signal)
    f4 (related)       -- gas regime + stablecoin peg deviations

F2 (order-book dynamics / mempool) is DEFERRED to future work per
design spec risk R1 (`C:/Users/1/.claude/plans/enumerated-scribbling-barto.md`):
historic Flashbots mempool snapshots have known gaps in 2024 and we
don't want a single dependency to block the paper. F2 is documented
as an open direction in the paper's §VII.

The mapping rationale lives in
`docs/research/literature-foundation.md` §5 (MacKenzie deep-read
extract). Each feature column is one term in the X matrix of the
Cox proportional-hazards regression that produces the T3 policy.
"""
