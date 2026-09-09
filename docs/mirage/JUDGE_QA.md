# MIRAGE — answers for the judging conversation

Prepared from the implemented product and verified release on 9 September 2026.
Use the linked evidence on screen. These are preparation notes, not a claim that
the project has been submitted or qualified.

## What is the contribution beyond Morpho's existing warnings?

Morpho already provides warnings and can block deposits in its main interface:
`deposit_disabled` and `oracle_unusable` at RED each gate that form. MIRAGE does
not claim to have invented automated admission. Its contribution to our existing
allocator is an evidence-backed entry veto, a quote bound to the proposed sale
size and block, reproducible observations, and reusable MCP tools.
[Morpho's current warning documentation](https://docs.morpho.org/get-started/resources/app-ecosystem/).

**Show:** WETH at 10000 USDC permits entry; changing to 20000 leaves the original
proposal intact but the MIRAGE preview refuses it until matching evidence exists.
[Recorded public-browser check](RENDER_BROWSER_VERIFICATION_2026-09-09.json).

## Is the BEFORE/AFTER comparison the actual old allocator?

Yes: the scenario adapter calls the existing T1 policy, and the wrapper calls that
same policy once before applying its veto. The scenario supplies an explicit market
ID for a cold-start decision. It does not claim the old six-protocol data pipeline
selected PAXG, that T1 ranked TVL, or that a historical investment was saved.

**Show:** [scenario adapter](../../mirage/allocator.py),
[policy wrapper](../../mirage/gate.py), and [baseline policy](../../decision/t1_threshold.py).
The broader [replay integration test](../../tests/test_mirage_gate.py) separately
checks that a refused entry produces no switch or gas charge in the old replay engine.

## Why does zero free liquidity block a new deposit?

This is MIRAGE's explicit conservative policy for a nonempty market. It is not a
claim that the Morpho contract rejects the deposit: a new deposit can add liquidity.
The policy refuses entry when there is no pre-existing unborrowed liquidity at the
checked block. Other findings are independent. Users can inspect the exact reason
instead of receiving an unexplained safety score.

**Show:** [accounting detector](../../mirage/detectors/phantom_volume.py).
Stored supply assets minus borrow assets describes available liquidity, not
historical principal or a guarantee about a future withdrawal.

## What exactly does the Uniswap check establish?

A geometric TWAP supplies a reference, and QuoterV2 simulates a specified sale.
The current routing policy compares complete direct and WETH candidates for the
same collateral input. The wstETH example changes the exit finding when the better
route is used; its unsupported oracle still keeps the whole market insufficient.

**Show:** [route evidence and reproduction](UNISWAP.md). This is a bounded route
comparison at one block. Fees are included; gas, future price changes and full
liquidator economics are not. It does not prove that every position in the market
can be liquidated or that this is the best route across every venue.

## What happens if an oracle cannot be understood?

It remains insufficient. Supported templates use factory membership, configuration
getters and observed feed/price data. Equal sampled prices alone do not establish
constancy throughout an interval. A constant conversion is not automatically wrong.

**Show:** [oracle reader](../../mirage/chain/oracle.py) and the separate reference
finding in the workbench. Missing code, empty return data, a failed read and a
completed observation have different meanings.

## Why reuse revert.pro if it does not certify the oracle?

We invoke its actual unchanged runtime-bytecode extractor and retain its MIT license
and exact-byte provenance. Its 70 features supply structural diagnostics for further
investigation. New PUSH-operand inspection adds candidates, not proven immutable
values or dependencies. The gate does not use an ML vulnerability score.

**Show:** the `_extract_features_single` call in [the adapter](../../mirage/bytecode.py)
and [upstream provenance](../../mirage/vendor/revert_pro/PROVENANCE.md).

## Is The Graph necessary, or just a label on cached data?

Every live workbench or MCP inspection must discover the selected USDC market in
our deployed creation-event subgraph at the resolved block hash before contract
collection. Failed discovery is reported; cached IDs do not substitute for success.
Saved tools deliberately replay saved Graph-origin evidence and say so.

**Show:** [discovery client](../../mirage/discovery/subgraph.py),
[deployed subgraph](../../subgraph/README.md), and [MCP tools](MCP.md).
The Graph supplies the market set; direct contract observations supply monetary inputs.

## What does the independent verification cover?

For the original four-market capture, 185 distinct contract calls and eight code
reads were repeated individually through each of two RPC providers and matched.
Offline replay then recomputes derived findings. This checks captured responses and
internal consistency; it is not a cryptographic proof of arbitrary supplied data.

The current default is an [offline diagnostic derivation](DIAGNOSTIC_REPLAY.md)
with identical raw inputs; it has a new file hash and records its parent hash.

**Show:** [original verification record](VERIFICATION_2026-09-09.json),
[derivation record](DIAGNOSTIC_REPLAY.md), and the current snapshot hash
in [the demo manifest](../../mirage/snapshots/demo.json). That earlier snapshot
inspects four of its 697 discovered IDs. The separate [full-universe capture](UNIVERSE_FULL_2026-09-09.md)
records all three check groups for all 697 markets at block `25938815`, including
unavailable observations. Its offline audits do not extend the demo's two-provider
rereads to the full universe. Later live checks have their own block and scope.

## Is it an AI agent making an investment decision?

The MCP interface lets agents consume verified evidence and request the actual
allocator comparison. Explicit deterministic rules compute findings and admission;
no LLM supplies a safety score. The verified SDK calls demonstrate working reusable
tooling, not an integrated autonomous trading agent. There is no transaction API.

**Show:** [MCP setup and evidence](MCP.md). Do not describe a terminal SDK client as
an LLM or imply that it executed an investment.

## What was made with AI, and what did the team contribute?

Most new MIRAGE code, tests, UI and documentation were generated or revised by Codex
agents. The supplied preparation history also reports Claude Code assistance.
Sergey supplied the two foundations, problem direction and initial research context.
Additional personal work and historical attribution must be confirmed by him.

**Show:** [file-level attribution](AI_USE.md) and [planning provenance](planning/PROMPT_PROVENANCE.md).
Do not invent human authorship, a manual audit, or completeness of the original
planning archive. Those remaining disclosure questions must be resolved before submission.
