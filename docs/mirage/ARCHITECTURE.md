# MIRAGE architecture and evidence boundaries

MIRAGE joins the existing event-time allocator to new market admission checks.
The public workbench is backed by Python modules and actual saved or freshly
collected chain evidence. There is no separate set of UI-only verdicts.

## Data path

1. [`discover_markets`](../../mirage/discovery/subgraph.py) queries the deployed
   creation-event subgraph at the resolved Ethereum block hash. The source record
   names its deployment, indexed/query blocks and discovered market count.
2. [`capture`](../../mirage/scan.py) receives an explicit set of selected market
   IDs. The workbench verifies that each selected ID belongs to that Graph result.
   Its inspected count is distinct from the discovery universe.
3. [`read_market`](../../mirage/chain/morpho.py) obtains immutable market parameters
   and the six stored state fields. The oracle, Uniswap and IRM collectors use
   that same numeric block. Historical oracle samples have separate anchors.
4. Pure detectors compute findings from collected observations. Raw uint values
   remain exact decimal strings in JSON; decimal conversion occurs explicitly.
5. [`report_from_snapshot`](../../mirage/scan.py) decodes market ABI and invokes
   `validate_oracle`, `replay_reference` and `replay_rate`. These reconstruct
   derived values from saved calls without a network fallback. Token pairs and
   block anchors must agree before a full report is constructed.
6. [`compare`](../../mirage/allocator.py) creates an explicit market-level
   cold-start state for the existing `T1ThresholdPolicy`. The wrapper
   [`MirageGatedPolicy`](../../mirage/gate.py) either preserves the original action
   or changes a prohibited new entry to hold.

## Reused code and new work

The allocator's `DecisionPolicy`, `BlockState`, T1/T2/T3 and historical replay
engine remain the existing research foundation. MIRAGE's wrapper calls the
original policy once with the complete candidate state. It does not remove
candidates and thereby alter the original policy's internal observations.

The exact upstream revert.pro extractor is in
[`mirage/vendor/revert_pro`](../../mirage/vendor/revert_pro/PROVENANCE.md).
[`inspect_bytecode`](../../mirage/bytecode.py) invokes its single-runtime method
on unsupported oracle bytecode. MIRAGE exposes selected structural features,
the full feature-vector digest and upstream provenance; heuristic vulnerability
labels and security scores are not used. Instruction-boundary walking and PUSH
operand candidates are new code. They do not prove called dependencies or
immutable meanings. Exact EIP-1167 recognition only identifies the embedded
implementation address, not its behavior.

The supported semantic oracle template is official Ethereum
MorphoChainlinkOracleV2 factory membership plus successfully read configuration.
Getter-compatible custom implementations and the legacy oracle used by the old
wstETH allocator venue remain unsupported. Unknown does not become unsafe proof
or a pass.

## Source and state separation

The subgraph indexes only
`CreateMarket(indexed bytes32,(address,address,address,address,uint256))`, beginning
at block 18883124. Its immutable `Market` entity contains identifiers and event
metadata. The mapping makes no contract calls and indexes no supply/borrow state
events. Changing that tuple signature changes the event topic.

The RPC transport uses single calls, bounded retries and numeric blocks. It
keeps a functioning provider and rotates after failure. The request-local cache
reuses the same `(method, address, calldata, block)` reads; failure stays a failure
rather than becoming zero. Multicall3 decoding checks its count and ABI boundaries,
but the observed workbench paths retain directly reproducible single-call results.

The Graph client requests pages by the RPC-resolved block hash. This handles
Graph Node's historical numeric `_meta.hash == null` behavior without weakening
the hash check. Missing data, indexing errors or incompatible metadata abort
discovery. The UI may keep showing its saved report after that failure, with
the saved/live label unchanged.

## Policy scope

| Check | Default consequence |
|---|---|
| Nonempty market with supply equal to borrow | Block new entry because no pre-existing free liquidity is observed |
| Normalized share rate greater than 2 | Warn; principal and the cause of the rate are unknown |
| V2 constant configuration | Warn; equal samples alone never establish interval constancy |
| Oracle/reference deviation above 500 bps | Block under MIRAGE's configured policy |
| Missing oracle template, reference or specified-size quote | Insufficient; gate vetoes entry |
| Quoted execution shortfall above 500 bps against spot or TWAP | Block for this size on the selected route |
| Matching evidence passes the checks | Original policy's action may pass the gate; no universal safety certification |

The quote size is explicit. A hypothetical USDC notional converts to collateral
base units at the recorded primary TWAP. The current `compare-direct-weth/1`
policy compares the direct and WETH routes with that identical input and chooses
the greatest quoted loan-token output. The primary price reference is preserved
even if the better execution route differs. Each route's spot price measures its
own execution impact; shortfall also remains measured against the unchanged
primary TWAP. Quotes include pool fees and exclude gas. Changing the amount
requires matching evidence. There is no inference from active liquidity or
reserves to total market liquidation capacity.

The default frozen evidence is
[`mainnet-full-25938082-routes-v2.json.gz`](../../mirage/snapshots/mainnet-full-25938082-routes-v2.json.gz).
It yields PAXG `block`, deUSD `insufficient`, wstETH `insufficient`, and WETH `pass`.
The wstETH exit passes through WETH; its unsupported oracle is the remaining
admission blocker. The earlier
[`mainnet-full-25938082.json.gz`](../../mirage/snapshots/mainnet-full-25938082.json.gz)
is retained solely as a historical regression artifact for `direct-first/1`.
Replay respects each artifact's recorded routing policy rather than silently
applying the newer route choice to older evidence.

Rate observations preserve the IRM address, calldata, stored `lastUpdate`, block
timestamp and raw return. Their annualization is an indication on stored state.
AdaptiveCurveIrm's `borrowRateView` returns an interval average since `lastUpdate`;
the collector does not simulate a new accrual or claim an instantaneous rate.

## Local API

[`server.py`](../../mirage/server.py) binds to `127.0.0.1` and serves the workbench:

| Endpoint | Purpose |
|---|---|
| `GET /api/report` | Recompute the current saved/live snapshot into findings |
| `GET /api/status` | Read refresh progress and saved/live state |
| `GET /api/allocator?amount=10000&market=0x...` | Compare actual T1 and gated actions at the evidence block |
| `POST /api/scan` | Start read-only Graph discovery and selected-market checks |

The scan JSON body accepts `{"amount_usdc":"10000","market_id":"0x..."}`.
Omitting the market ID uses the documented demo shortlist. Only one refresh is
active at a time. A successful refresh validates and saves a new snapshot before
replacing the report. Local Host/Origin checks limit browser access to this server;
it is not an authenticated public deployment.

The gate performs no network calls, signatures or transactions. Its default
freshness requirement is the exact decision block. Future evidence is always
rejected; a wider age window requires an explicit `max_age_blocks` setting.
The workbench is an evidence-block decision comparison, not a trading executor
or a historical P&L reconstruction.
