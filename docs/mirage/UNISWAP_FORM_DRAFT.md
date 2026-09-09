# Uniswap feedback form — MIRAGE draft

Inspected read-only on 9 September 2026. The [actual form](https://developers.uniswap.org/hackathon-feedback?utm_campaign=20260904-ethglobal_online&utm_content=callout&utm_medium=eco&utm_source=platform&utm_term=self-serve) was readable through the official ETHGlobal resource link without logging in. No field was filled and nothing was submitted.

The table follows the observed form order, using abbreviated labels. Required markers were visible. Dropdown choices were not exposed by the web reader: select the matching real option in the browser, rather than treating the semantic answers below as exact option labels.

## Field map

| # | Field, abbreviated | Required | Answer or owner action |
|---|---|---|---|
| 1 | Given name | Yes | Sergey enters his preferred spelling. |
| 2 | Family name | No | Sergey enters his preferred spelling. |
| 3 | Email address | Yes | Sergey enters the contact address he wants to share. |
| 4 | Telegram username | Yes | Sergey supplies his actual handle. |
| 5 | Event | Yes | ETHOnline 2026. |
| 6 | Finished a project | Yes | Yes; select the matching available option. |
| 7 | Project explanation | Yes | Paste A below. |
| 8 | AI/agentic classification | Yes | Agentic tooling; select the matching option, using B if free text is available. |
| 9 | Successful Uniswap integration | Yes | Yes; select the matching available option. |
| 10 | Time until first success | Yes | Sergey chooses from the actual options; elapsed integration time was not reliably measured. |
| 11 | Main obstacle | No | Paste C. |
| 12 | Agentic-specific challenge | No | Paste D. |
| 13 | Documentation helpfulness | Yes | Sergey chooses an honest score from 1–5. |
| 14 | Overall support rating | Yes | Sergey chooses an honest score from 1–5. |
| 15 | Plans to continue | Yes | Sergey chooses his actual intention. |
| 16 | Support channels used | Yes | Technical documentation is confirmed; Sergey adds any other channels he personally used. |
| 17 | Missing support | No | Paste E. |
| 18 | Additional comments | No | Paste F, including the public FEEDBACK.md link. |
| 19 | Permission for follow-up | No | Sergey chooses whether to allow contact. |
| 20 | Acceptance of terms/privacy | Yes | Sergey reviews the linked policies and decides himself. |

## Paste-ready technical answers

### A — Project explanation

MIRAGE adds evidence-based admission checks to our existing open-source USDC allocator. Before it enters a Morpho Blue market, MIRAGE checks available liquidity, oracle credibility and a specified collateral sale. The Graph discovers eligible markets. Uniswap v3 supplies an independent geometric TWAP and QuoterV2 exact-input simulations. We compare direct and WETH routes with the same collateral input, preserve the raw Ethereum calls, and let the resulting findings permit or veto the original allocation proposal. The Python workbench exposes the evidence and decision comparison; an MCP server makes the same pipeline reusable by agents. This is a working read-only integration on Ethereum mainnet. We independently verified the frozen four-market demo through two RPC providers. No swap or deposit is executed by the prototype.

### B — Agentic classification, if explanation is possible

MIRAGE extends an automated allocation agent and exposes three tools through the official MCP Python SDK: saved evidence replay, live market inspection, and allocation preview. The stdio workflow was verified with an official SDK client, including a live Graph-to-RPC inspection. Admission uses explicit evidence rules. We have not integrated an LLM into the decision policy or used a machine-learning safety score.

### C — Main obstacle

Distinguishing an inadequate route from inadequate market-wide exit capacity. In our wstETH example at Ethereum block 25938082, exactly 3.220832145173417247 wstETH quoted 5927.556111 USDC through the selected direct pool, but 10007.772538 USDC through WETH. A direct-only check would have refused that exit scenario. We fixed this by comparing both routes at the same block with the same input and unchanged primary reference price, retaining each quote as evidence. The selected route then passed the exit check, while the separate unsupported-oracle finding remained explicit.

### D — Agentic-specific challenge

Giving a caller a result whose scope is clear enough to change an allocation decision. A quote for one amount cannot qualify another amount, unavailable observation history cannot silently become a spot-price estimate, and a saved result cannot be presented as a fresh capture. MIRAGE returns structured findings with block hashes, scenario amounts, raw calls and explicit insufficient-coverage states. Its MCP tools separate saved replay from live inspection, and the admission wrapper can hold the original allocator's proposal when the evidence does not cover it.

### E — Missing support or improvements

A compact Python-oriented guide combining OracleLibrary semantics with QuoterV2 would have helped. Please include a v1/v2 tuple-order comparison, negative-tick rounding, signed cumulative wrap handling, mixed token decimals, and missing observation history. A lending-risk example should distinguish concentrated-liquidity values from executable sale size and compare routes with identical inputs. It would also help to document that exact-input quote output does not itself expose the amount consumed; an explicit completion indicator or consumed-input result in a future interface would simplify conservative consumers.

### F — Additional comments and required feedback link

Our detailed developer feedback, including concrete documentation suggestions and verified mainnet examples, is public here:
https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/blob/master/FEEDBACK.md

Integration guide, contract addresses and reproduction instructions:
https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/blob/master/docs/mirage/UNISWAP.md

Implementation and deterministic replay:
https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/blob/master/mirage/chain/uniswap.py

We used canonical Ethereum Uniswap v3 contracts through individual RPC calls. We did not integrate the hosted Trading API, deploy a v4 hook, or execute a swap. The examples are dated simulations with declared input sizes and retained evidence.

## What still needs Sergey

Contact details, dropdown selections, personal ratings, future plans and consent remain owner decisions. Do not infer an integration duration from commit timestamps, time spent on the entire project, or the live MCP call's 54.36-second runtime. The latter is a tool execution measurement, not development time.

The form exposes no separate URL field for the repository feedback file. Include its public URL in answer F: the [official Uniswap prize requirement](https://ethglobal.com/events/ethonline2026/prizes) requires the completed external response to contain that link. After Sergey submits, confirm the form's success state and record only the submission status or non-sensitive receipt. A local draft and a repository FEEDBACK.md do not establish completion.

## Source record

- Form: public Uniswap page linked above, observed 9 September 2026. The web reader returned all question prompts and required markers, but not dropdown choices.
- Technical answers: [FEEDBACK.md](../../FEEDBACK.md), [UNISWAP.md](UNISWAP.md), [MCP.md](MCP.md), and [verification record](VERIFICATION_2026-09-09.json).
- Repository branch checked locally: `master`, tracking `origin/master`; the public feedback file was last changed in commit `a975436`.

Only this local document was created. No login, external message, checkbox acceptance or form submission was performed.
