# MIRAGE — pre-deposit checks for Morpho Blue

MIRAGE adds evidence-backed market checks to this repository's existing USDC
allocator. Intended submission: **ETHOnline 2026, Continuity Track**.

**Current release:** block-pinned accounting checks, live Graph discovery, an
allocator entry gate and reproducible offline evidence. Oracle reference prices,
collateral exit depth and bytecode interpretation are still being implemented.
Reports explicitly mark those missing checks `insufficient`; an accounting pass
does not admit a market.

## BEFORE — existing work

This repository already contained an event-time USDC allocator for Aave V3,
Compound V3, Spark, Morpho Blue, Euler V2 and Fluid. The last baseline commit is
[`520b676`](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/commit/520b676).

- [T1](decision/t1_threshold.py) uses APR, estimated time until the leader changes,
  capital and switching costs.
- [T2](decision/t2_optimal_stopping.py) uses optimal stopping; [T3](decision/t3_hazard.py)
  uses a survival model, with fallback to T1.
- [EventReplayEngine](backtest/replay_per_block.py) accrues yield and charges gas
  around the existing [DecisionPolicy interface](decision/base.py).
- [The reproduction notebook](notebooks/reproduce_predictive_mcdm_defi.ipynb)
  and research results predate MIRAGE. They are not new hackathon results.

The event-time policies do **not** rank by TVL. Their existing `morpho_blue` venue
is one selected wstETH/USDC market, not all permissionless Morpho markets.
MIRAGE's contribution is an explicit check of a proposed destination, rather
than replacing TVL and claiming that this changes T1's historical decisions.

The second foundation is
[revert.pro's bytecode feature-extraction repository](https://github.com/SergeySolovyev/icicpe-2026-defi-vuln-detection).
Its extractor normalizes and disassembles runtime bytecode and counts features.
It does not recover immutable values. Planned reuse is the input normalization,
disassembly and program-counter indexing patterns, with attribution. New oracle
interpretation must handle known templates, proxies and storage explicitly;
listing PUSH constants is not proof of their meaning. This integration is pending.

## AFTER — work added during ETHOnline 2026

The first hackathon commit, `e56cd7f` on 9 September, added the MIT license and
Morpho discovery subgraph. This release adds:

| Component | Implemented behavior |
|---|---|
| [Subgraph](subgraph/) | Indexes only tuple `CreateMarket`, with no contract calls in the mapping |
| [Discovery client](mirage/discovery/subgraph.py) | Reads live Graph market IDs at one block; validates pagination, deployment, indexing status and block hash |
| [Chain reader](mirage/chain/morpho.py) | Reads raw Morpho params and state with single RPC calls at a numeric block |
| [RPC transport](mirage/chain/rpc.py) | Rotates endpoints; validates Multicall3 count and byte boundaries; recovers by single calls |
| [Accounting detector](mirage/detectors/phantom_volume.py) | Computes free liquidity, utilization and normalized share exchange rate |
| [Report and snapshots](mirage/scan.py) | Preserves target, calldata, raw return, block number and hash; refuses overwriting a frozen snapshot |
| [Allocator gate](mirage/gate.py) | Vetoes new entries into explicitly mapped markets with blocked, missing, stale or incomplete evidence |

The gate calls the original policy once with the complete state. It neither
forces an exit from a held position nor changes T1/T2/T3's candidate observations.
Unmapped venues are outside MIRAGE coverage. Existing baselines remain unchanged.

## Live Graph deployment

Version `v0.0.1` was deployed to
[Subgraph Studio](https://thegraph.com/studio/subgraph/mirage-morpho-markets/) on
9 September. Deployment ID:
`QmYkbwLirDouGqfRapedCcQ8YCbM8dzKA13agskDwGzJ6K`.

The query endpoint returned real market entities with
`_meta.hasIndexingErrors = false` at block `19972938`. **Deployment and entity
indexing succeeded; full synchronization and an end-to-end live scan are not
yet verified.** See
[the deployment guide](subgraph/README.md) for setup and verification.

The Graph supplies market discovery; raw on-chain calls supply monetary inputs.
`scan --source=subgraph` fails if Graph data is missing or inconsistent; it does
not silently substitute a local snapshot or Morpho API.

## Quick start

Python 3.10+ is sufficient for the accounting CLI; it uses the standard library.
Run from a clean clone's repository root:

```console
python -m mirage demo --offline
python -m mirage verify 0x8eaf7b29f02ba8d8c1d7aeb587403dcb16e2e943e4e2f5f94b0963c2386406c9 --block 25937912
```

For a live scan after synchronization, set the query URL and choose a block
which the subgraph has indexed. This is the **query URL**, not the deploy key:

```powershell
$env:MIRAGE_SUBGRAPH_URL = 'https://api.studio.thegraph.com/query/1759002/mirage-morpho-markets/v0.0.1'
python -m mirage scan --source=subgraph
```

The default block is resolved from Ethereum's `finalized` tag. During initial
sync, wait until the subgraph has caught up. The existing `prune: auto` setting
can make old indexed blocks unavailable; the frozen chain snapshot's block is
not guaranteed to remain queryable through Graph.

The generated feed is `mirage/feed/latest.json` (ignored by Git). Monetary raw
integers are strings to preserve precision in JavaScript consumers. RPC URLs
can be configured with comma-separated `MIRAGE_RPC_URLS`.

The gate uses the existing allocator dependencies, including pandas; install
the repository's [requirements](requirements.txt) for allocator/replay work.
There is no `mirage backtest` command or deployed transaction executor yet.

## Verified snapshot, not a reconstructed principal

The committed [snapshot](mirage/snapshots/mainnet-25937912.json.gz) contains two
markets independently read through PublicNode and dRPC with **single** calls
at block **25,937,912**. Both providers returned identical bytes and block hash.

| Market | Stored supply claims, USDC | Free liquidity, USDC | Share rate / initial rate |
|---|---:|---:|---:|
| PAXG/USDC `0x8eaf7b29…` | 6,212,914,536.395500 | **0** | 66,215.818314× |
| deUSD/USDC `0xbd1ad3b9…` | 348,282.184849 | **0.010000** | 109.652016× |

Amounts are USDC units, not independent USD valuations. These are stored values
at the cited block; `lastUpdate` is retained. The snapshot does not validate
historical totals across all 697 markets and is not evidence of live Graph use.

`totalSupplyShares / 1e6` is **not** recovered principal. New deposits buy shares
at the current exchange rate. The exact normalized rate is
`1e6 * (totalSupplyAssets + 1) / (totalSupplyShares + 1e6)`.
A high rate prompts investigation; it does not prove phantom debt or insolvency.
See [the accounting corrections and primary sources](docs/mirage/CORRECTIONS_2026-09-09.md).

Free liquidity is `totalSupplyAssets - totalBorrowAssets`. Blocking entry when
this is zero is an explicit MIRAGE policy choice, not a claim that Morpho
prohibits deposits. It does not by itself establish a user's withdrawal rights.

Every finding includes reproducible `eth_call` evidence. To independently
recapture at a new numeric block:

```console
python -m scripts.mirage_capture_demo --block NEW_BLOCK_NUMBER
```

The command saves a new snapshot only after two independent provider captures
agree. It refuses to replace an existing file.

## Validation

```console
python -m unittest discover -s tests -p test_mirage_core.py -q
python -m pytest -q tests/test_mirage_core.py tests/test_mirage_gate.py tests/test_t1_threshold.py
```

On 9 September: **60 tests passed**, including ABI truncation, pagination,
share accounting, snapshot consistency, entry veto and a regression proving
that changing TVL alone does not change T1's action. Core tests also run with
`python -S`, skipping two optional `eth_abi` comparisons. These are offline
tests; the separate two-provider snapshot capture is the live chain check.

## Remaining work and submission limits

- Complete the oracle, independent Uniswap reference and collateral exit checks.
- Implement and attribute the revert.pro bytecode path; unknown cases stay insufficient.
- Verify Graph synchronization and show its live data driving the allocator gate.
- Build an explicitly labelled market-level decision demo and historical replay.
  Historical loss prevention has not been demonstrated.
- Add actual Uniswap integration, `FEEDBACK.md`, the feedback form and the demo video.
  No Uniswap prize requirement is claimed complete yet.

The [Graph Continuity prize](https://ethglobal.com/events/ethonline2026/prizes/the-graph)
has a **$5,000 pool**, with awards of $2,500, $1,500 and $1,000. Eligibility requires
live Graph data and meaningful application/agent use; a local build or an offline
snapshot is insufficient. The separate composability prize is not established
by one custom discovery subgraph. Clarify eligibility for unlabelled prizes
with the organizers rather than assuming access.

## License

[MIT](LICENSE). Sergei Solovev.
