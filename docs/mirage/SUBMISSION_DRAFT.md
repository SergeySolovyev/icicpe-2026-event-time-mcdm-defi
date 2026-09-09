# MIRAGE — submission draft

Prepared on 9 September 2026 from the implemented route-comparison demo and the subsequently verified MCP integration. These are ready-to-paste drafts; preparing them does not save or submit an ETHGlobal form. The current observed form state is recorded in [SUBMISSION_FORM_STATE.md](SUBMISSION_FORM_STATE.md).

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

### How it is made

MIRAGE extends our existing open-source USDC allocator and reuses the MIT-licensed EVM bytecode extractor from our second project, revert.pro. The original T1 decision policy still proposes an allocation. A new admission wrapper evaluates the market evidence and can veto that proposal when checks fail, are incomplete, or do not cover the proposed amount.

A deployed Subgraph Studio subgraph indexes Morpho Blue CreateMarket events. Python discovers USDC markets at a pinned block hash, then makes individual RPC reads of market state, oracle contracts and interest-rate models. Supported oracle templates use factory membership, configuration getters and sampled historical prices. Unsupported bytecode goes through the existing 70-feature extractor for structural diagnostics.

Uniswap v3 supplies a geometric TWAP and QuoterV2 sale simulations. MIRAGE compares direct and WETH routes with exactly the same collateral input, preserving both results and their raw calls. Offline replay rebuilds derived values from those calls. A Python server exposes the interactive workbench, evidence inspection and original-policy comparison. For the frozen four-market demo, we independently reread 185 distinct contract calls and eight runtime-code reads through each of two RPC providers; all matched.

An optional stdio MCP server uses the official Python SDK to expose three reusable tools: get_saved_report, inspect_market, and preview_saved_allocation. An official SDK client successfully called all three, including a live Graph-to-RPC inspection of PAXG at block 25938274. AI agents can consume the same structured evidence and allocation comparison as the workbench. Findings are computed by explicit rules; no LLM or ML safety score decides admission.

### Public GitHub repositories

Primary implementation and Continuity history:

https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi

Existing revert.pro bytecode-extraction project:

https://github.com/SergeySolovyev/icicpe-2026-defi-vuln-detection

### Demonstration URL

https://mirage-workbench.onrender.com

The Render release, public four-market saved-evidence interface, and a fresh WETH inspection were verified on 9 September 2026. That live browser check discovered 697 Graph market IDs, inspected one market for 10000 USDC, and returned PASS at Ethereum block `25938497`. Both the original T1 and gated preview allowed entry. This new capture has not received the frozen demo's separate two-provider verification. Release details and free-instance behavior are documented in [HOSTING.md](HOSTING.md). The free service may sleep when idle; allow time for it to wake before recording or judging.

## Continuity disclosure

Before ETHOnline, the primary repository already contained the USDC allocator, its T1/T2/T3 policies, six protocol adapters, and an event-time replay framework. The documented baseline is commit `520b676ce59ae0a10ff098554fee7800ba6ca91a`. The original T1 policy ranks rate and cost inputs; it does not rank markets by TVL. In this demo, an explicit market ID is supplied as a destination for the original policy's cold-start decision.

The hackathon extension adds the MIRAGE package, deployed Graph discovery, block-bound RPC evidence, accounting and oracle checks, Uniswap reference and route comparisons, deterministic replay, the admission gate, the interactive workbench, and the MCP server. The first hackathon commit is `e56cd7f` on 9 September. See [README — BEFORE / AFTER](../../README.md) and the public commit history for the boundary between existing and new work.

The second repository contributes its exact EVM feature extractor, preserved with its MIT license and provenance. MIRAGE actually invokes that extractor and records 70 features; it does not reuse or claim a vulnerability classifier. New PUSH-operand inspection identifies candidates for further investigation, not proven immutable values or contract dependencies. Source commit: `324431a514c5ebebbdbe620cb789f83ea78a231a`. See [vendored provenance](../../mirage/vendor/revert_pro/PROVENANCE.md).

The demo is a present-state decision comparison at a recorded block. It makes no claim about historical profit, recovered funds or losses prevented. The accounting report distinguishes recorded accounting assets, free liquidity, and a share-normalized quantity; it does not label supply shares as recovered principal.

## The Graph — sponsor answer

**Prize:** Best AI Tooling or AI Use Case with The Graph (Continuity).

MIRAGE is reusable MCP tooling for allocation agents, demonstrated with our existing automated USDC allocator. Its three tools replay evidence, inspect a market live, and compare the original allocation with the admission gate. The Graph is required: a live inspection must discover the market in the deployed subgraph before reading its contracts. The report can veto an allocation and explains the evidence behind that decision. We verified the complete stdio workflow through the official MCP SDK. In the live PAXG run at block 25938274, Graph discovered 697 USDC market IDs, one market was inspected, and the result blocked entry. Saved tools separately replay the four-market demonstration. Other agents can reuse these typed tools and structured results without a custom adapter.

Relevant implementation: [MCP setup and verified run](MCP.md), [MCP server](../../mirage/mcp_server.py), [subgraph](../../subgraph/), [discovery](../../mirage/discovery/subgraph.py), [admission gate](../../mirage/gate.py), and [architecture](ARCHITECTURE.md). Live query endpoint: https://api.studio.thegraph.com/query/1759002/mirage-morpho-markets/v0.0.1

The [official Graph criteria](https://ethglobal.com/events/ethonline2026/prizes/the-graph) require a meaningful agent/application workflow using live Graph data, public documentation, and a two-to-four-minute demonstration. This entry supplies reusable MCP tools and demonstrates their decision effect in the existing allocator. It does not claim an integrated LLM or eligibility for the separate composable-products prize on the strength of this one subgraph.

## Uniswap Foundation — sponsor answer

**Prize:** Best Uniswap Stack Contribution.

MIRAGE uses the Uniswap v3 factory, pool observations and QuoterV2 as a reusable lending-market admission check. A geometric TWAP provides an independent price reference. Exact-input quotes then test a declared collateral sale. The integration compares a direct route and a route through WETH with the same input and records both. In our verified wstETH example, the direct route returns 5,927.556111 USDC while the WETH route returns 10,007.772538 USDC. That comparison changes the exit finding from rejection to acceptance; the separate unsupported-oracle finding remains. Every result can be replayed from the saved calls.

Relevant source: [collector and replay](../../mirage/chain/uniswap.py), [reference-price check](../../mirage/detectors/reference_price.py), [exit check](../../mirage/detectors/exit_depth.py). Contract addresses, reproduction commands and source references are in [UNISWAP.md](UNISWAP.md). Developer feedback is in [FEEDBACK.md](../../FEEDBACK.md).

The [official sponsor criteria](https://ethglobal.com/events/ethonline2026/prizes) require an open-source repository, repository feedback, and the external developer feedback form. Sergey must submit that external form and record its completion before the final prize submission. A prepared feedback file alone does not complete that requirement.

## Evidence for reviewers

- [Frozen demo manifest](../../mirage/snapshots/demo.json): four inspected markets at Ethereum block `25938082`, with a hash of the compressed evidence file.
- [Verification record](VERIFICATION_2026-09-09.json): repeated reads through two independent provider configurations.
- [Architecture and trust boundaries](ARCHITECTURE.md): data path, replay, decision wrapper and supported coverage.
- [MCP verification](MCP.md): official SDK stdio calls, saved decision replay and a dated live Graph-to-RPC inspection.
- [Public deployment](HOSTING.md): stable Render URL, exact deployed commit, release status and hosting limits.
- [Demo script](DEMO_SCRIPT.md): three-minute walkthrough with a fresh Graph check and clearly labeled historical evidence.

The [ETHGlobal rules](https://ethglobal.com/rules) make the disclosure of existing work and credible development history material to Continuity eligibility. Keep the README's BEFORE/AFTER sections and the actual commit history accessible to reviewers.

## Sergey — final actions

1. Review the MIRAGE project fields, use `https://mirage-workbench.onrender.com` as the demo URL, connect GitHub in ETHGlobal and select the public repository. Sergey makes the final form save; Continuity is already selected.
2. Record and upload the human-narrated demo using [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Confirm that a signed-out viewer can open the video and application.
3. Complete the Uniswap developer feedback form linked from `FEEDBACK.md`; record completion without exposing private account data.
4. Review sponsor selections and the later form steps, then make the final project and prize submissions yourself. No submission is performed by this document.
5. Connect the event Discord if still required for event participation or organizer questions.

Working deadline provided by Sergey: **13 September 2026, 19:00 Moscow / 12:00 EDT**. Confirm the dashboard countdown before the final submission; do not plan around midnight.
