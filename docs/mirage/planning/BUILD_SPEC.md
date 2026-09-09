# MIRAGE current corrected engineering specification

Version: `mirage-build-spec/1`, prepared 9 September 2026 against repository revision `e757e91`.

**This is a post-implementation specification of the current product**, not a backdated original prompt. It consolidates the supplied handoff, later corrections and implemented behavior. Historical source identity and limited prompt excerpts are in [PROMPT_PROVENANCE.md](PROMPT_PROVENANCE.md); AI attribution is in [AI_USE.md](../AI_USE.md).

## Objective and scope

Help an allocator or analyst decide whether to admit a proposed USDC allocation to an Ethereum Morpho Blue market using reproducible evidence. Extend the existing allocator and reuse the existing revert.pro extractor for the Continuity submission. Each finding must state its scope and supporting block; uncertainty must remain visible.

This release is a read-only evidence workbench and allocation preview. It has no wallet, custody, automatic trades or onchain allowlist. Its before/after comparison uses the original T1 policy plus an admission veto at the evidence block; it is not a historical loss-avoidance or profitability experiment.

## Implemented requirements and acceptance boundaries

| Requirement | Current implementation / acceptance condition |
| --- | --- |
| Discover actual markets through The Graph | [`subgraph/`](../../../subgraph/) indexes only tuple-form `CreateMarket`. [`discover_markets`](../../../mirage/discovery/subgraph.py) paginates at the resolved block hash and checks deployment/indexing metadata. Selected IDs must belong to that result. Discovery count and inspected count stay separate. |
| Read contract evidence at explicit blocks | [`chain/`](../../../mirage/chain/) uses individual RPC calls, bounded retry/rotation, strict ABI lengths and explicit anchors. Evidence records method/address/calldata/block/hash/raw return. Historical oracle samples retain separate anchors. |
| Keep monetary meanings explicit | [`phantom_volume.py`](../../../mirage/detectors/phantom_volume.py) reports stored supply claims, stored debt, available liquidity `A - B`, utilization and normalized share rate `10^6 * (A + 1) / (S + 10^6)`. USDC base units divide by `10^6`; shares do not reconstruct deposited principal. A high share rate is a diagnostic warning, not proof of fictitious assets. |
| Bound oracle claims to supported evidence | [`oracle.py`](../../../mirage/chain/oracle.py) checks code, official V2 factory membership, configuration getters, samples and feed observations. Equal samples do not establish interval constancy. Unknown templates remain insufficient. |
| Reuse revert.pro honestly | [`bytecode.py`](../../../mirage/bytecode.py) calls the unchanged upstream feature extractor. New PUSH operands are candidates, not proven dependencies or decoded immutables. No learned vulnerability score controls admission. |
| Check a specified exit scenario | [`uniswap.py`](../../../mirage/chain/uniswap.py) collects v3 geometric TWAPs and QuoterV2 evidence for a declared collateral input or USDC-notional scenario. `compare-direct-weth/1` compares complete direct/WETH quotes for the same input. Pool liquidity is not interpreted as dollar liquidation capacity. |
| Apply explicit policies | Nonempty markets with no available liquidity block entry; oracle/reference deviation or specified-exit shortfall above the default 500-bps policy can block. Missing required evidence is insufficient. A pass applies only to the supported checks, block and amount. See [policy boundaries](../ARCHITECTURE.md#policy-scope). |
| Preserve allocator behavior | [`MirageGatedPolicy`](../../../mirage/gate.py) calls the original policy once with the full state, then vetoes prohibited new entries. It does not force liquidation of the current venue. The old `morpho_blue` identity is preserved; [new scenarios](../../../mirage/allocator.py) use explicit market IDs. |
| Reconstruct saved results | [`report_from_snapshot`](../../../mirage/scan.py) validates/replays raw observations before producing findings, without network fallback. Old snapshots retain their recorded route policy. Raw uints remain exact decimal strings in JSON. |
| Expose usable evidence | [`web/`](../../../mirage/web/) distinguishes saved evidence from a completed live capture, supports market-ID inspection and original/gated previews. [`MCP`](../MCP.md) provides three tools; compact `mirage-agent-summary/1` follows full validation, and `include_evidence=true` returns the full `mirage-feed/1`. |
| Support independent operation | [README](../../../README.md), [hosting configuration](../HOSTING.md) and [focused CI](../../../.github/workflows/mirage.yml) support a clean Python 3.12 product environment, Docker build and saved replay without network. Deployment is separate from final hackathon submission. |

## Trace from original handoff to current decisions

Section numbers refer to the hashed `HANDOFF_v2.md` described in [prompt provenance](PROMPT_PROVENANCE.md#source-register). This table is a corrected public mapping; it does not reproduce withdrawn monetary totals.

| Original sections | Retained / changed / superseded |
| --- | --- |
| §§2, 8, 11, 18: product goal, reuse and priorities | Retained: admission checks, two foundations, Graph dependency first. Original prize arithmetic is not a product requirement and is omitted. |
| §§3, 5, 19: accounting and financial assertions | Corrected: claims, debt and available liquidity are distinct. Shares-as-principal, causal claims of fictitious debt and aggregate monetary headlines are withdrawn. [Correction record](../CORRECTIONS_2026-09-09.md). |
| §§4, 15: runtime analysis | Revised: invoke the actual unchanged extractor and label structural diagnostics; do not promise immutable recovery or a security certification. |
| §§6, 7, 19: RPC and decoding traps | Retained strict decoding and individual verification. Corrected empty `price()` semantics: check code separately. Invalid market IDs/selectors are rejected. |
| §§9, 10: demonstration | Revised into the current [demo script](../DEMO_SCRIPT.md) and block-bound policy comparison. No claimed avoided losses; no relabeling the baseline market to manufacture a result. |
| §§11, 14, 16: allocator integration | Implemented the policy wrapper. Superseded the proposed TVL-to-T1 causal chain and principal-based backtest: T1 does not rank TVL. No such backtest command is claimed. |
| §16: package, evidence and cache design | Retained pure detectors, offline gate, explicit provenance and immutable saved artifacts. Current APIs/CLI differ from the proposal; Graph is required for live admission, not silently replaced by cached/API discovery. |
| §§16, 17: subgraph and exit checks | Deployed creation-only subgraph; implemented v3 TWAP and specified-size route quotes. No v4 integration or total-market liquidation-capacity inference. |
| §§11–13: optional sponsor integrations | No Arc deployment, CRE workflow or Chainlink state-changing allowlist implemented. Reading configured Chainlink feeds is not equivalent to those integrations. |

## Evidence and remaining limitations

The default committed evidence at block `25938082` contains four inspected cases, not a full-universe risk assessment: PAXG blocks; deUSD and wstETH remain insufficient; WETH passes the supported scenario. See the [snapshot manifest](../../../mirage/snapshots/demo.json) and [architecture](../ARCHITECTURE.md).

[Linux CI run 34329377252](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/actions/runs/34329377252) recorded 176 focused tests and a Docker build plus replay with `--network=none`. [Public browser verification](../RENDER_BROWSER_VERIFICATION_2026-09-09.json) records a separate live capture. These observations support reproducibility, not an audit, uptime guarantee or future swap execution guarantee.

Unsupported oracle templates, bounded route search, RPC trust, historical data availability and one-block quote validity remain material limits. The historical AI/planning archive and owner contribution confirmation are still open disclosure work; this specification does not certify submission compliance.
