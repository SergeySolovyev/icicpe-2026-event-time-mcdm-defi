# MIRAGE — submission draft

**10 September:** The first application step is now saved with the primary GitHub
repository. The owner will write the application's AI-use wording himself; do not
automatically insert or overwrite that text from this historical draft.
See [current form state](SUBMISSION_FORM_STATE.md) for the remaining steps.

Prepared on 9 September 2026 from the implemented route-comparison demo, verified MCP integration and published 697-market capture. These are ready-to-paste drafts; preparing them does not save or submit an ETHGlobal form. The current observed form state is recorded in [SUBMISSION_FORM_STATE.md](SUBMISSION_FORM_STATE.md). The [submission readiness checklist](SUBMISSION_READINESS.md) separates implemented evidence from pending human and dashboard steps, including the corrected prize-pool amounts.

## First form fields

### Project name

MIRAGE

### Category

DeFi

### Short description

Evidence-based admission checks for Morpho markets, built into an existing USDC allocator.

### Description

An attractive lending rate does not tell an allocator whether its next market deserves a deposit. MIRAGE adds that missing decision step. Before USDC enters a Morpho Blue market, it checks available liquidity, the configured oracle, and a specified collateral sale against independent Uniswap prices and quotes.

The Graph supplies live market discovery. MIRAGE turns those market IDs into a report with exact Ethereum calls, then applies the report to our existing allocation policy. Users can inspect the evidence, change the proposed amount, check another market, and compare the original decision with the admission gate.

The demo includes a refusal and a positive control. PAXG has no pre-existing free USDC at the recorded block, so the gate vetoes entry. WETH passes the implemented checks. A wstETH example shows why route selection matters: the same input quotes about 5,928 USDC directly and 10,008 USDC through WETH. Its exit check passes after comparison; its unsupported oracle remains visible. Every result names its block, amount and coverage.

Beyond the four-case demo, we published all three check groups for all 697 Graph-discovered USDC markets at block 25938815, for a 10000 USDC scenario. The aggregate reports are 32 PASS, 3 WARN, 95 BLOCK and 567 INSUFFICIENT. Complete collection includes unavailable evidence; it is not a claim that every market can be assessed or admitted. The original snapshot, corrected diagnostics and audit records are public and can be replayed offline.

### How it is made

MIRAGE extends our existing open-source USDC allocator and reuses the MIT-licensed EVM bytecode extractor from our second project, revert.pro. The original T1 decision policy still proposes an allocation. A new admission wrapper evaluates the market evidence and can veto that proposal when checks fail, are incomplete, or do not cover the proposed amount.

A deployed Subgraph Studio subgraph indexes Morpho Blue CreateMarket events. Python discovers USDC markets at a pinned block hash, then makes individual RPC reads of market state, oracle contracts and interest-rate models. Supported oracle templates use factory membership, configuration getters and sampled historical prices. Unsupported bytecode goes through the existing 70-feature extractor for structural diagnostics.

Uniswap v3 supplies a geometric TWAP and QuoterV2 sale simulations. MIRAGE compares direct and WETH routes with exactly the same collateral input, preserving both results and their raw calls. Offline replay rebuilds derived values from those calls. A Python server exposes the interactive workbench, evidence inspection and original-policy comparison. For the frozen four-market demo, we independently reread 185 distinct contract calls and eight runtime-code reads through each of two RPC providers; all matched.

The separate full-universe capture covers all 697 discovered markets at block 25938815. Independent accounting and Uniswap calculations checked the saved raw observations, and expected exit outcomes matched production for every market. Both original and derived snapshots replayed successfully; the diagnostic migration preserved raw evidence, finding codes, severities and rates. These are offline checks, not a second-provider verification of the full universe.

An optional stdio MCP server uses the official Python SDK to expose three reusable tools: get_saved_report, inspect_market, and preview_saved_allocation. An official SDK client successfully called all three, including a live Graph-to-RPC inspection of PAXG at block 25938274. AI agents can consume the same structured evidence and allocation comparison as the workbench. Findings are computed by explicit rules; no LLM or ML safety score decides admission.

AI use: Sergey supplied the existing repositories, product direction and initial research context. OpenAI Codex agents generated and revised most new MIRAGE code, tests, interface and documentation; earlier Claude Code assistance is reported for preparation and the initial subgraph. The repository's docs/mirage/AI_USE.md provides file-level attribution and links to the corrected specification and selected prompt provenance. Historical attribution and completeness of the original planning archive remain under review.

### Public GitHub repositories

Primary implementation and Continuity history:

https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi

Existing revert.pro bytecode-extraction project:

https://github.com/SergeySolovyev/smart-contract-vuln-detection-from-bytecode

### Demonstration URL

https://mirage-workbench.onrender.com

The current Render release, `9aeb01c`, was verified on 9 September 2026 with one fresh public inspection at block `25939677`, followed by restoration of the saved four-market demo. The inspected zero-token case returned `INSUFFICIENT` with the specific exit reason `zero_token_address`; see the [release verification](QUOTE_REASON_V2_VERIFICATION_2026-09-09.json). An earlier release's WETH inspection at block `25938497` returned PASS for 10000 USDC, with both original T1 and gated previews allowing entry. These live captures have not received the frozen demo's separate two-provider verification. Release details and free-instance behavior are documented in [HOSTING.md](HOSTING.md). The free service may sleep when idle; allow time for it to wake before recording or judging.

## Continuity disclosure

Before ETHOnline, the primary repository already contained the USDC allocator, its T1/T2/T3 policies, six protocol adapters, and an event-time replay framework. The documented baseline is commit `520b676ce59ae0a10ff098554fee7800ba6ca91a`. The original T1 policy ranks rate and cost inputs; it does not rank markets by TVL. In this demo, an explicit market ID is supplied as a destination for the original policy's cold-start decision.

The hackathon extension adds the MIRAGE package, deployed Graph discovery, block-bound RPC evidence, accounting and oracle checks, Uniswap reference and route comparisons, deterministic replay, the admission gate, the interactive workbench, and the MCP server. The first hackathon commit is `e56cd7f` on 9 September. See [README — BEFORE / AFTER](../../README.md) and the public commit history for the boundary between existing and new work.

The second repository contributes its exact EVM feature extractor, preserved with its MIT license and provenance. MIRAGE actually invokes that extractor and records 70 features; it does not reuse or claim a vulnerability classifier. New PUSH-operand inspection identifies candidates for further investigation, not proven immutable values or contract dependencies. Source commit: `324431a514c5ebebbdbe620cb789f83ea78a231a`. See [vendored provenance](../../mirage/vendor/revert_pro/PROVENANCE.md).

The demo is a present-state decision comparison at a recorded block. It makes no claim about historical profit, recovered funds or losses prevented. The accounting report distinguishes recorded accounting assets, free liquidity, and a share-normalized quantity; it does not label supply shares as recovered principal.

## The Graph — sponsor answer

**Prize:** Best AI Tooling or AI Use Case with The Graph (Continuity).

MIRAGE is reusable MCP tooling for allocation agents, demonstrated with our existing automated USDC allocator. Its three tools replay evidence, inspect a market live, and compare the original allocation with the admission gate. The Graph is required: a live inspection must discover the market in the deployed subgraph before reading its contracts. The report can veto an allocation and explains the evidence behind that decision. We verified the complete stdio workflow through the official MCP SDK. In the live PAXG run at block 25938274, Graph discovered 697 USDC market IDs, one market was inspected, and the result blocked entry. Saved tools separately replay the four-market demonstration. Other agents can reuse these typed tools and structured results without a custom adapter.

Relevant implementation: [MCP setup and verified run](MCP.md), [MCP server](../../mirage/mcp_server.py), [subgraph](../../subgraph/), [discovery](../../mirage/discovery/subgraph.py), [admission gate](../../mirage/gate.py), and [architecture](ARCHITECTURE.md). Live query endpoint: https://api.studio.thegraph.com/query/1759002/mirage-morpho-markets/v0.0.1

Two commands let a reviewer check this without reading any code. `curl` with the unpinned query in [the subgraph README](../../subgraph/README.md) returns the deployment CID, indexing status and five live USDC markets. `python scripts/mirage_mcp_demo.py --live --timeout 900` runs the official SDK client against the real stdio server and adds one `inspect_market` call, so the Graph-discovery gate, the finalized block hash and the resulting verdict are all visible in one terminal. A market missing from live discovery returns `market_not_discovered` before any contract read. Please do not pin a reviewing query to the historical block numbers named in this document. The deployment uses `prune: auto`, and as of 11 September 2026 both `25938082` and `25938815` have fallen outside the retained range, so a pinned query returns a pruning error while the deployment itself is healthy. Live discovery always resolves the current finalized block, and the historical evidence replays from the committed snapshots rather than from a historical Graph query.

The same discovery-and-evidence pipeline also completed a separate capture of all 697 USDC markets at block 25938815. The [published universe report](UNIVERSE_FULL_2026-09-09.md) includes original observations, offline replay and actual coverage: 32 PASS, 3 WARN, 95 BLOCK and 567 INSUFFICIENT. The default saved MCP demonstration remains four markets at its earlier block; discovery, collection, evidence sufficiency and allocation admission are distinct.

The [official Graph criteria](https://ethglobal.com/events/ethonline2026/prizes/the-graph) require a meaningful agent/application workflow using live Graph data, public documentation, and a two-to-four-minute demonstration. This entry supplies reusable MCP tools and demonstrates their decision effect in the existing allocator. It does not claim an integrated LLM or eligibility for the separate composable-products prize on the strength of this one subgraph.

## Chainlink — sponsor answer

**Prize:** Best Chainlink-Powered Upgrade (Continuity Track).

MIRAGE decides offchain and stays read-only. The upgrade takes one finished verdict for one market at one exact sale size and records it in [`MirageGate`](../../contracts/src/MirageGate.sol) on Sepolia, where a Chainlink price feed checks it before it is stored. `submitDecision` calls `latestRoundData()` inside contract logic, measures the deviation between the reference price MIRAGE used and the live answer, and writes the verdict to storage. This is a state change driven by Chainlink data, not a feed value rendered in a frontend.

The feed can only make the outcome stricter. A proposed `Allow` that disagrees beyond the configured bound is stored as `Blocked` and flagged `vetoedByFeed`; a proposed `Blocked` is always stored as `Blocked`. No feed answer converts a `Blocked` into an `Allow`. A stale feed reverts the call instead of recording a decision on a price of unknown age.

[`ExecutionGuard`](../../contracts/src/ExecutionGuard.sol) makes the recorded flag load-bearing rather than decorative: `enter` reverts with `EntryNotAllowed` unless the gate holds a fresh `Allow` for that exact market and that exact amount. Published from the same recorded evidence, an entry for 10,000 USDC succeeds and the same entry for 20,000 reverts, because the saved sale quote does not cover the larger size. That is the offchain product's central property, carried into the contract and observable on a block explorer.

How it improves the existing project: before this, the verdict lived only inside our process, and the price our reasoning rested on was never checked by anything independent. Now the decision is durable, readable by whatever executes next, and subject to a second opinion from a source we do not control.

Relevant source: [MirageGate](../../contracts/src/MirageGate.sol), [ExecutionGuard](../../contracts/src/ExecutionGuard.sol), [tests](../../contracts/test/MirageGate.t.sol), [publisher](../../scripts/mirage_chainlink_publish.py), [deployment runbook and limits](CHAINLINK.md). 21 Foundry tests cover both veto directions, stale and non-positive answers, access control, the amount binding, decision ageing and each guard path, including a fuzz test asserting that a stored `Allow` implies the deviation stayed within the bound.

Scope stated plainly: the contracts are on Sepolia, not mainnet; MIRAGE's evidence is read from mainnet while the consulted feed is on Sepolia, so the measured deviation includes ordinary movement between those two contexts; the guard holds no funds and this prototype never transfers or swaps value; and the publisher refuses any market whose collateral the feed does not describe, because an ETH/USD feed says nothing about wstETH.

## Uniswap Foundation — sponsor answer

**Prize:** Best Uniswap Stack Contribution.

MIRAGE uses the Uniswap v3 factory, pool observations and QuoterV2 as a reusable lending-market admission check. A geometric TWAP provides an independent price reference. Exact-input quotes then test a declared collateral sale. The integration compares a direct route and a route through WETH with the same input and records both. In our verified wstETH example, one identical raw input of 3220832145173417247 base units, quoted at the same block, returns 5,927.556111 USDC on the direct route and 10,007.772538 USDC through WETH. Three recorded details make that gap mechanical rather than anecdotal. The direct quote crossed nine initialized ticks in a single hop, while each WETH leg crossed one, which is what running out of concentrated liquidity looks like in the quoter's own output. The winning route is also the more expensive one: two hops at 100 and 500 costing 6 basis points in fees against the direct pool's 5. And neither quote's `sqrtPriceX96After` approaches the QuoterV2 boundary, so both accepted the entire input rather than returning a truncated fill. Against the same primary TWAP the policy uses, the direct route's execution shortfall is 4,072.44 basis points and the WETH route's is -7.77, while the exit check blocks at a configured 500. A direct-only check therefore rejects an exit the stack can support at this size.

Two scope statements belong with that result. The load-bearing comparison is quote against quote at an identical raw input, not TWAP against quote: the scenario size is itself derived from the direct pool's TWAP, so the TWAP valuing this input near 10,000 USDC is true by construction and is not independent confirmation. And this describes supported route execution at one block, not overall market safety. Both shortfalls are stored per candidate as `execution_shortfall_bps_vs_twap` and recomputed from the raw amounts at replay rather than trusted as display values. The separate unsupported-oracle finding still stands, so the market's overall verdict remains insufficient. Every result can be replayed from the saved calls.

Relevant source: [collector and replay](../../mirage/chain/uniswap.py), [reference-price check](../../mirage/detectors/reference_price.py), [exit check](../../mirage/detectors/exit_depth.py). Contract addresses, reproduction commands and source references are in [UNISWAP.md](UNISWAP.md). Developer feedback is in [FEEDBACK.md](../../FEEDBACK.md).

The [full-universe evidence](UNIVERSE_FULL_2026-09-09.md) also records exit checks for 697 markets at block 25938815: 79 PASS, 34 BLOCK and 584 INSUFFICIENT. Separate ABI and numerical calculations over the saved observations matched production exit outcomes for every market. Missing reference or quote evidence stays insufficient; bounded Uniswap route search does not establish liquidity across all venues or future execution.

The [official sponsor criteria](https://ethglobal.com/events/ethonline2026/prizes) require an open-source repository, repository feedback, and the external developer feedback form. Sergey must submit that external form and record its completion before the final prize submission. A prepared feedback file alone does not complete that requirement.

## Evidence for reviewers

- [Frozen demo manifest](../../mirage/snapshots/demo.json): four inspected markets at Ethereum block `25938082`, with a hash of the compressed evidence file.
- [Verification record](VERIFICATION_2026-09-09.json): repeated reads through two independent provider configurations.
- [Full 697-market capture](UNIVERSE_FULL_2026-09-09.md): separate block `25938815`, original and derived snapshots, exact coverage and independent offline accounting/exit audits.
- [Architecture and trust boundaries](ARCHITECTURE.md): data path, replay, decision wrapper and supported coverage.
- [MCP verification](MCP.md): official SDK stdio calls, saved decision replay and a dated live Graph-to-RPC inspection.
- [Public deployment](HOSTING.md): stable Render URL, exact deployed commit, release status and hosting limits.
- [Demo script](DEMO_SCRIPT.md): three-minute walkthrough with a fresh Graph check and clearly labeled historical evidence.

The [ETHGlobal rules](https://ethglobal.com/rules) make the disclosure of existing work and credible development history material to Continuity eligibility. Keep the README's BEFORE/AFTER sections and the actual commit history accessible to reviewers.

## Sergey — final actions

1. Connect GitHub in ETHGlobal so the prepared MIRAGE draft can select the public repository and be saved. The verified demo URL is `https://mirage-workbench.onrender.com`; Continuity is already selected. Saving these editable fields is distinct from Sergey's final submission.
2. Record and upload the human-narrated demo using [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Confirm that a signed-out viewer can open the video and application.
3. Complete the Uniswap developer feedback form linked from `FEEDBACK.md`; record completion without exposing private account data.
4. Review sponsor selections and the later form steps, then make the final project and prize submissions yourself. No submission is performed by this document.
5. Connect the event Discord if still required for event participation or organizer questions.
6. Confirm the personal research/design/validation contributions and historical AI attribution in [AI_USE.md](AI_USE.md). Resolve the incomplete original planning archive against the event's specification-disclosure rule before final submission; the corrected public specification is not represented as the complete original archive.

Working deadline provided by Sergey: **13 September 2026, 19:00 Moscow / 12:00 EDT**. Confirm the dashboard countdown before the final submission; do not plan around midnight.
