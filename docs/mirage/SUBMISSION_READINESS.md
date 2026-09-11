# MIRAGE submission readiness — updated 11 September 2026

**11 September, pre-recording pass.** Four things were found and fixed before the
video was recorded, none of them cosmetic:

- The MCP client example could not complete on a loaded machine. Its client read
  timeout was 60 seconds while a cold import of the stdio child measured 48.9 seconds
  alone and 178.8 seconds to a finished handshake, and the child's stderr went to
  `os.devnull`, so a dying server was indistinguishable from a timeout. The default is
  now 300 seconds with a `--timeout` / `MIRAGE_MCP_TIMEOUT` override, the child's error
  output goes to a log whose tail is printed on failure, and the fresh-process stdio
  test's 40-second budget was raised above the stall it exists to catch. Verified on
  this host under full load: the demo completed in 164 seconds, exit code 0.
- The deployed subgraph has pruned both documented evidence blocks. A pinned query for
  25938082 or 25938815 now returns a retention error while the deployment itself is
  healthy. This is disclosed in [the subgraph README](../../subgraph/README.md),
  [ARCHITECTURE](ARCHITECTURE.md) and the Graph sponsor answer, together with an
  unpinned query a reviewer can run today.
- The vendored source repository had been renamed. Links now use the canonical
  `smart-contract-vuln-detection-from-bytecode` path instead of relying on GitHub's
  rename redirect.
- `LLM_TRANSCRIPT.md` and `CLAUDE.md` at the repository root are pre-event coursework
  artifacts that never mention MIRAGE. Both now carry a scope note, and
  [AI_USE](AI_USE.md) states what they are, so neither reads as an incomplete AI
  disclosure for this submission.

The Uniswap answer, demo script and judge notes now carry the recorded tick and fee
evidence behind the route gap, and state plainly that the scenario size is derived from
the same TWAP, so the load-bearing comparison is quote against quote.

**10 September:** Check-in #2 is submitted. GitHub is connected; Project details,
Images (logo, cover, three screenshots) and Tech stack are saved. Showcase:
https://ethglobal.com/showcase/mirage-vbqty. Top 10 + Partner Prizes and the two
partner entries are saved with owner ratings (Graph 8, Uniswap 7).
Video, external Uniswap feedback, owner wording
and final submission remain open. Final still uses from-scratch wording despite
Continuity and was left unchecked pending clarification.
[Current form state](SUBMISSION_FORM_STATE.md) supersedes older dashboard notes below.

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
| Live provider evidence | [Subgraph deployment](../../subgraph/DEPLOYMENT.json) and [dated live MCP call](MCP.md) at block 25938274. [Current release verification](QUOTE_REASON_V2_VERIFICATION_2026-09-09.json) includes one fresh public inspection at block 25939677: exit reason `zero_token_address`, overall `INSUFFICIENT`, then restoration of the saved demo. |
| Reusable AI tooling and decisions | [MCP setup/client example](MCP.md); three typed tools, compact/full reports, actual original/gated previews. [Exact-release CI](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/actions/runs/34349726175) passed 221 tests, the actual SDK stdio example and Docker offline replay. No LLM integration is claimed. |
| Uniswap implementation | [Contract addresses](../../mirage/chain/uniswap.py#L14), [QuoterV2 call](../../mirage/chain/uniswap.py#L344), [integration guide](UNISWAP.md). Specified-size simulation, not a submitted swap. |
| Inspectable routing effect | [Public route comparison and previews](ROUTE_UI_VERIFICATION_2026-09-09.json): exact common wstETH input, both quotes, separate exit and market verdicts. |
| Public application | [Hosting proof](HOSTING.md): deployed commit, CI and actual browser observations. A free instance may sleep; wake it before judging. |
| Repository feedback | [FEEDBACK.md](../../FEEDBACK.md) describes actual integration experience. This is distinct from sending the external feedback form. |
| Full discovery universe | [697-market capture and audits](UNIVERSE_FULL_2026-09-09.md): all three check groups recorded and replayed at block 25938815, with independent accounting and exit checks. Overall 32 PASS, 3 WARN, 95 BLOCK and 567 INSUFFICIENT; these are report verdicts, not allocation admissions. |

The Graph's AI Tooling route accommodates reusable MCP infrastructure; an integrated
LLM is not a prerequisite. Uniswap's nomination permits v3 integrations and tooling;
this entry does not require an invented transaction, v4 hook or Trading API usage.
The applicable requirements are on the two linked sponsor pages above.

## Submission steps still open

| Item | Current evidence / next required result |
|---|---|
| Human demo video | [Script](DEMO_SCRIPT.md) is prepared, including the actual MCP client segment. No completed upload or accessible video URL has been verified. |
| External Uniswap feedback | [Prepared answers](UNISWAP_FORM_DRAFT.md), the feedback URL and technical selections are now filled in the external browser form. Personal ratings, integration duration, future plans and consent remain unresolved. The form has not been submitted. |
| Owner attribution wording and human contribution | The owner explicitly reserved the application's AI-use wording. That field remains untouched. [AI_USE.md](AI_USE.md) and the historical contribution record still require his review; no human authorship or review is inferred from commit dates. |
| Original planning archive | [Specification](planning/BUILD_SPEC.md) and [selected provenance](planning/PROMPT_PROVENANCE.md) are explicitly partial/reconstructed. Archive completeness remains unresolved. |
| Continuity declaration | Final uses from-scratch wording and flags the pre-event first commit, despite Continuity being selected. It permits flagged repositories to be submitted for manual review. The declaration remains unchecked pending clarification; preserve original history. |
| Final submission | Both sponsor entries are already saved. The project still requires its final submission and an acceptance confirmation. Partner judging is asynchronous; the separate Uniswap feedback requirement remains applicable. |

The [event's submission and AI rules](https://ethglobal.com/events/ethonline2026/info/details)
require a 2–4 minute video, transparent reuse/AI attribution and meaningful team
contribution. A spec-driven build must disclose its specs, prompts and planning.
The deadline is **13 September 2026, 12:00 EDT / 19:00 Moscow**. The script follows
the human-voice, normal-speed, minimum-720p rules; writing it does not complete them.

## Full-universe capture and default demo

The [completed 697-market capture](UNIVERSE_FULL_2026-09-09.md) publishes the
original snapshot, derived diagnostics and verification records. No rows remain
missing or accounting-only. Missing oracle and exit evidence remains explicit:
625 markets have at least one insufficient finding, including 58 whose aggregate
verdict is BLOCK. The default demonstration still contains four inspected markets
at its earlier block; its separate two-provider verification is not attributed to
the full-universe capture.
