# MIRAGE submission readiness — 9 September 2026

This checklist separates implemented evidence from unfinished submission steps.
It does not claim that a project or prize submission has been accepted.

## Prize amounts and targets

| Continuity nomination | Total nomination pool | Individual awards |
|---|---:|---|
| [The Graph: AI Tooling or AI Use Case](https://ethglobal.com/events/ethonline2026/prizes/the-graph) | $5,000 | $2,500 / $1,500 / $1,000 |
| [Uniswap: Stack Contribution](https://ethglobal.com/events/ethonline2026/prizes/uniswap-foundation) | $2,000 | $1,000 / $1,000 |

Pool totals are not one team's possible award. These are the two prepared sponsor
targets. No third sponsor submission or unmarked Graph category is assumed eligible.

## Implemented evidence

| Item | Evidence and scope |
|---|---|
| Existing open-source work and new extension | [README BEFORE/AFTER](../../README.md), public commit history and [revert.pro provenance](../../mirage/vendor/revert_pro/PROVENANCE.md). T1 and the original extractor are actually invoked. |
| Graph is required for live inspection | [Discovery](../../mirage/discovery/subgraph.py) and [MCP live inspection](../../mirage/mcp_server.py) require the selected market at a pinned block/hash. Graph failure does not silently substitute saved IDs. |
| Live provider evidence | [Subgraph deployment](../../subgraph/DEPLOYMENT.json) and [dated live MCP call](MCP.md) at block 25938274. Current release browser verification used saved evidence. |
| Reusable AI tooling and decisions | [MCP setup/client example](MCP.md); three typed tools, compact/full reports, actual original/gated previews. [Release CI](ROUTE_UI_VERIFICATION_2026-09-09.json) verifies the official SDK. No LLM integration is claimed. |
| Uniswap implementation | [Contract addresses](../../mirage/chain/uniswap.py#L14), [QuoterV2 call](../../mirage/chain/uniswap.py#L344), [integration guide](UNISWAP.md). Specified-size simulation, not a submitted swap. |
| Inspectable routing effect | [Public route comparison and previews](ROUTE_UI_VERIFICATION_2026-09-09.json): exact common wstETH input, both quotes, separate exit and market verdicts. |
| Public application | [Hosting proof](HOSTING.md): deployed commit, CI and actual browser observations. A free instance may sleep; wake it before judging. |
| Repository feedback | [FEEDBACK.md](../../FEEDBACK.md) describes actual integration experience. This is distinct from sending the external feedback form. |

The Graph's AI Tooling route accommodates reusable MCP infrastructure; an integrated
LLM is not a prerequisite. Uniswap's nomination permits v3 integrations and tooling;
this entry does not require an invented transaction, v4 hook or Trading API usage.
The applicable requirements are on the two linked sponsor pages above.

## Submission steps still open

| Item | Current evidence / next required result |
|---|---|
| ETHGlobal repository link | The 9 September browser inspection still offered only Add GitHub Account and disabled repository selection. Owner linking is pending; the prepared form remains unsaved. See [form state](SUBMISSION_FORM_STATE.md). |
| Human demo video | [Script](DEMO_SCRIPT.md) is prepared, including the actual MCP client segment. No completed upload or accessible video URL has been verified. |
| External Uniswap feedback | [Prepared answers](UNISWAP_FORM_DRAFT.md) include the public FEEDBACK.md URL. No successful external submission is recorded. |
| Historical authorship and human contribution | [AI_USE.md](AI_USE.md) records observed direction and AI-generated files. Historical contributions still require owner confirmation. |
| Original planning archive | [Specification](planning/BUILD_SPEC.md) and [selected provenance](planning/PROMPT_PROVENANCE.md) are explicitly partial/reconstructed. Archive completeness remains unresolved. |
| Sponsor selection and final submission | [Submission text](SUBMISSION_DRAFT.md) is ready to paste. Final project/prize submission and any subsequent judging details require actual dashboard confirmation. |

The [event's submission and AI rules](https://ethglobal.com/events/ethonline2026/info/details)
require a 2–4 minute video, transparent reuse/AI attribution and meaningful team
contribution. A spec-driven build must disclose its specs, prompts and planning.
The deadline is **13 September 2026, 12:00 EDT / 19:00 Moscow**. The script follows
the human-voice, normal-speed, minimum-720p rules; writing it does not complete them.

## Full-universe capture remains separate

The published [697-market accounting capture](UNIVERSE_ACCOUNTING_2026-09-09.md)
does not establish complete oracle and exit coverage. The default demonstration
contains four inspected markets. The all-detector universe capture is still in
progress and must be reconciled, replayed and published with its actual coverage.
It is not represented as finished merely because all IDs were discovered.
