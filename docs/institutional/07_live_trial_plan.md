# Live Trial Plan

Five-phase ramp from Sepolia testnet to fund-LP allocation. **No
phase >$25M without 12 months of mainnet track record at lower sizes.**

| Phase | Network | Size | Duration | Success criteria | Abort conditions |
|---|---|---|---|---|---|
| 0 | Sepolia | $10K notional | 1 week | ≥10 switches, no agent crashes, Flashbots dry-run path verified | Unhandled exception, history.parquet corruption |
| 1 | Mainnet shadow | $0 (paper trade) | 4 weeks | Allocations match backtest predictions ±5%; gas within 2× model | Systematic deviation > 10% |
| 2 | Mainnet live | $10K | 4 weeks | Net APY > Aave by 20 bp; zero kill-switch events | Net APY < Aave −50 bp; any safety event |
| 3 | Mainnet scale | $100K | 8 weeks | Net APY > Aave + 30 bp; max DD < 50 bp; uptime > 99% | Net APY < Aave; DD > 100 bp |
| 4 | Fund LP allocation | $1M+ | Ongoing | Track record on public Dune dashboard | Per investor mandate |

## Public PnL transparency

Dune Analytics dashboard with on-chain-attestable PnL series, updated
daily, comparable to publicly-verifiable Aave APY benchmark.

## Hard rules

- **Phase 5 ($5M+)**: requires 6 months of Phase 3-4 track record +
  risk register sign-off.
- **No phase >$25M without 12 months mainnet track record**
  (per Risk Register ch 05 G2).