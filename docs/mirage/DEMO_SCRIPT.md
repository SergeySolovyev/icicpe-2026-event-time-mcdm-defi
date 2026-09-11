# MIRAGE — three-minute demo

Target: about three minutes and forty seconds of human narration with normal-speed screen recording. Record at 1080p so the block, amount and evidence remain legible. The [Graph prize](https://ethglobal.com/events/ethonline2026/prizes/the-graph) asks for two to four minutes; the [observed project form](SUBMISSION_FORM_STATE.md) caps the video at four minutes and rejects accelerated video.

For the follow-up discussion, use [the judging questions and evidence links](JUDGE_QA.md).

For questions about scale, open the separate [697-market capture and audit report](UNIVERSE_FULL_2026-09-09.md). It records all three check groups at block `25938815`, with 32 PASS, 3 WARN, 95 BLOCK and 567 INSUFFICIENT. This is additional published evidence; the timed walkthrough below uses four selected cases at block `25938082`. Do not attribute the demo's two-provider verification to the full universe or describe complete collection as complete admission coverage.

## Prepare before recording

Run the application from the repository root:

```console
python -m pip install -r requirements-mirage.txt
python -m mirage serve
```

Open `http://127.0.0.1:8765`, or the verified public Python application URL. Keep the public README, `mirage/bytecode.py`, and `mirage/vendor/revert_pro/PROVENANCE.md` in nearby tabs. Close account or deploy-key pages before recording.

The **Load demo** control restores the frozen four-market evidence selected by `mirage/snapshots/demo.json`. The current repository default is `mainnet-full-25938082-diagnostics-v2.json.gz`: an offline diagnostic derivation of the same recorded block `25938082`, not a new capture. See [diagnostic replay and parent provenance](DIAGNOSTIC_REPLAY.md). Verify the deployed release in [HOSTING.md](HOSTING.md) before recording. Expected final verdicts: PAXG `BLOCK`; deUSD `INSUFFICIENT`; wstETH `INSUFFICIENT` because of its unsupported oracle, with its exit check `PASS`; WETH `PASS`. The saved amount is `10000` USDC.

Rehearse a fresh WETH check once to establish realistic RPC latency. During recording, show its live source and new block only after it finishes. The later numerical comparison deliberately uses **Load demo**, so those exact historical values remain reproducible. The [event's video rules](https://ethglobal.com/events/ethonline2026/info/details) allow editing out unnecessary waiting. If the real request is slow, cut only the waiting interval, retain the request and completed result for the same market/amount, and label the cut as waiting removed. Do not speed up footage, alter the result, or describe an unfinished request as a result. Human narration, 720p or higher, and a final duration of 2–4 minutes remain required; AI voiceover and filming the screen with a phone are prohibited.

MCP preparation for the Graph entry: install `requirements-mirage-mcp.txt` and rehearse the actual SDK client example below. A configured MCP client can also use the portable launcher in [MCP.md](MCP.md). Rehearse `get_saved_report` and `preview_saved_allocation` with the PAXG market ID and `amount_usdc: "10000"`. The former returns four saved markets; the latter shows original T1 `switch` and gated `hold`. These tools run without a new network capture. The separate verified live `inspect_market` call took 54.36 seconds at block `25938274`; allow real latency for any new live call. Do not paste ordinary text into the server's JSON-RPC stdin.

For a ready-to-run terminal demonstration, use `python scripts/mirage_mcp_demo.py`.
It launches the official SDK client and prints actual saved PAXG/WETH decisions,
including the amount mismatch. It does not run an LLM or collect live observations.

**Run this once before the recorder starts, not after.** The stdio child imports the
scientific stack before it answers `initialize`, so the first run is slow and a screen
recorder adds to that. On a fully loaded Windows host on 11 September 2026, importing
`mirage.mcp_server` alone took 48.9 seconds, a completed handshake took 178.8 seconds,
and the whole demo finished in 164 seconds. Wait for the closing line:

```text
MCP session closed. Evidence-block replay complete; no funds moved.
```

If the command prints `MCP demo failed.` instead, this segment is not recordable yet.
The message now names the likely cause and prints the tail of the stdio server's own
error log, which distinguishes a server-side exception from a slow or killed start.
Close other applications and rerun; on a slower machine raise the wait with
`--timeout 600` or `MIRAGE_MCP_TIMEOUT=600`. Do not open the recorder on the strength
of a transcript from an earlier day.

## 0:00–0:35 — live Graph discovery

**Screen:** Select WETH and `10000` USDC. Click **Check market**. Show progress, then the successful source label and block. Keep the application's status visible while speaking.

**Say:**

> MIRAGE checks the evidence before an allocator enters a lending market. We built it on our existing USDC allocator. This WETH check starts with live market discovery through The Graph, then reads contracts at one Ethereum block. When it finishes, the source label and block show exactly which evidence supports the decision.

## 0:35–1:05 — three checks, explicit scope

**Screen:** Click **Load demo**. Show the saved label and block `25938082`. Inspect PAXG and its three check sections; briefly show deUSD's oracle finding.

**Say:**

> Now I am loading our reproducible example: six hundred and ninety-seven Graph-discovered USDC market IDs, with four markets inspected. We check available liquidity, oracle credibility, and a specified collateral sale. PAXG has zero available USDC, and its oracle price also diverges from our independent reference. deUSD has a constant oracle configuration; a constant alone is a warning, not proof of mispricing.

## 1:05–1:50 — the same-size route counterexample

**Screen:** Inspect wstETH → **Collateral exit depth**. Show the **Recorded route comparison** table: the exact common collateral input, Direct and Via WETH outputs, and **Selected in report**. Then open **Inspect measurements** once: the basis-point figures are metrics, not table columns, and the direct candidate's values sit inside the `candidate routes` JSON there. Keep the exit `PASS` and overall `INSUFFICIENT` distinguishable.

**Say:**

> One bad route can give the wrong answer. Using QuoterV2, we sell the same three point two two wstETH on two routes, at the same block. Direct returns about five thousand nine hundred and twenty-eight USDC. Through WETH, about ten thousand and eight. The direct hop crossed nine initialized ticks. Each WETH leg crossed one. That is concentrated liquidity running out, and the winning route even pays higher fees. Our exit check blocks above five hundred basis points. Direct is over four thousand. The better route passes. The oracle template is still unsupported, so the market stays insufficient.

Visible in the **Recorded route comparison** table itself, without reading every
digit aloud. The table has three columns, Route, Collateral input and USDC output,
and the workbench groups thousands, so the screen reads `5,927.556111` where this
document writes `5927.556111`:

| Item | Value on screen |
|---|---:|
| Common collateral input | 3.220832145173417247 wstETH |
| Direct output | 5,927.556111 USDC |
| WETH-route output | 10,007.772538 USDC |
| Selected route | marked `Selected in report` |

The basis-point figures are **not** columns in that table. They are recorded
metrics, so open **Inspect measurements** once to show them. The selected route's
own values appear as named rows there; the direct candidate's appear inside the
`candidate routes` JSON on the same panel:

| Item | Value | On-screen label |
|---|---:|---|
| Selected route's fee-inclusive impact against its spot | 6.39 bps | `price impact bps vs spot` |
| WETH route's execution shortfall against the primary TWAP | -7.77 bps | `execution shortfall bps vs twap` |
| Exit policy's configured threshold | 500 bps | `max price impact bps` |
| Direct route's execution shortfall against the primary TWAP | 4072.44 bps | inside `candidate routes` |
| Direct route | 1 hop, fee 500, 9 initialized ticks crossed | inside `candidate routes` |
| WETH route | 2 hops, fees 100 and 500, 1 tick per leg | inside `candidate routes` |

The labels render with spaces, not underscores. The exit-depth finding's panel is the
one that opens as **Inspect measurements (17)**; `candidate routes` is the last entry
in it and prints both candidates as pretty JSON.

The metrics panel prints these at full precision, for example
`4072.4438889999999985662...`, not rounded. Say the rounded value and let the
screen show the exact one; do not claim the screen displays a rounded number.

The primary reference is the same direct-pool TWAP, approximately 3104.787691 USDC/wstETH, for both candidate sizes and for both route candidates. Both shortfalls are stored per candidate as `execution_shortfall_bps_vs_twap`, and [`exit_depth.detect`](../../mirage/detectors/exit_depth.py) recomputes them from the raw amounts at replay instead of trusting the stored display value.

If a judge asks why the direct quote should be believed, the answer is in the quoter's own output rather than in the reference price: the direct hop crossed nine initialized ticks while each WETH leg crossed one, the winning route pays more in total fees (6 bps against 5), and neither quote's `sqrtPriceX96After` approaches the QuoterV2 boundary, so both accepted the whole input instead of returning a partial fill. State the scope honestly too: the scenario size is derived from the direct pool's own TWAP, so that TWAP valuing this input near 10,000 USDC is true by construction and is not independent confirmation. The load-bearing comparison is quote against quote at an identical raw input. This compares the implemented direct and WETH candidates; it does not establish the best route across every venue.

## 1:50–2:15 — original allocator versus admission gate

**Screen:** Select PAXG in the allocation panel, amount `10000`, and click **Preview allocation**. Show **Original allocator** and **With MIRAGE**; open **Response details** if needed to make the original T1 policy visible.

**Say:**

> Here the original T1 policy evaluates the selected destination and proposes entry. MIRAGE receives that proposal and holds because the evidence fails admission. The policy is unchanged. Its rate input is an annualized accrual-rate indication. We are comparing decisions at this recorded block, without claiming historical profits or money saved.

## 2:15–2:35 — a positive control and amount sensitivity

**Screen:** Select WETH, keep `10000`, and preview. Both decisions enter. Change the amount to `20000` and preview again to show that the saved quote does not cover the new amount. Restore `10000` afterward.

**Say:**

> WETH passes the implemented checks for this amount, so the original entry stands. Changing the amount changes the question: the saved sale quote no longer covers the proposal. A fresh check is required.

## 2:35–3:00 — real reuse of revert.pro

**Screen:** Inspect wstETH → **Oracle credibility** → **Inspect measurements**. Show the bytecode diagnostics: `features_extracted`, `feature_count: 70`, and the upstream commit. Briefly open `mirage/bytecode.py` at the `_extract_features_single` call, then the vendored provenance and MIT attribution.

**Say:**

> Our second existing project is revert.pro. MIRAGE calls its actual open-source bytecode extractor: seventy features, with the source commit and license preserved. These are structural diagnostics. Address-shaped constants remain investigation candidates, and unsupported behavior stays explicit. The extractor does not certify an oracle as safe.

## 3:00–3:30 — reusable MCP tools

**Screen:** Briefly show one call in **Reproduce the evidence**, including its block and raw return. Then show the real terminal command `python scripts/mirage_mcp_demo.py` and its completed output: all three discovered tools, saved block `25938082`, PAXG original `switch` versus gated `hold`, and WETH's amount-sensitive previews. This MCP segment is required for the Graph version of the video. Use actual command output, not a fabricated terminal transcript. If startup is slow, cut only the waiting interval and label it, preserving the command and its own completed result. End with the workbench and the README's BEFORE/AFTER link visible.

**Say:**

> Agents can reuse this evidence through three verified MCP tools: saved reports, live inspection, and allocation previews. Exact calls explain the decisions. MIRAGE gives an existing allocator a clear boundary: evidence first, allocation second.

## 3:30–3:40 — published coverage beyond the demo

**Screen:** Open the public [697-market report](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/blob/master/docs/mirage/UNIVERSE_FULL_2026-09-09.md). Show block `25938815` and the aggregate table, including `INSUFFICIENT`. This is a separate saved capture, not the four-market workbench report or a fresh browser scan.

**Say:**

> Beyond these four examples, we published observations for all six hundred and ninety-seven markets. Missing evidence stays visible.

## Presenter checks

- The first successful check is live; the later exact figures belong to the explicitly loaded block `25938082`. A failed refresh leaves saved evidence visible and must be described that way.
- The four inspected markets at block `25938082` are a selected demo subset of 697 discovered IDs. The later full capture at block `25938815` records all three check groups for all 697, including missing observations; collection is not evidence sufficiency or admission. Keep the two artifacts distinct.
- The comparison invokes the real T1 policy for the selected explicit market ID at cold start. Do not say the original allocator ranked PAXG by TVL, confuse that ID with its former wstETH adapter, or imply a historical backtest result.
- Free liquidity is recorded supply assets minus borrow assets. Do not call supply assets TVL or label supply shares as recovered principal. A proposed new deposit does not prove pre-existing withdrawal liquidity.
- For AdaptiveCurve IRMs, the annualized displayed rate uses the accrual-rate indication averaged since the stored last update, rather than an instantaneous rate or a future return.
- The wstETH exit passes; its unsupported oracle is the remaining admission limitation. Preserve both findings on screen.
- The completed independent verification covers 185 distinct calls plus eight code reads through each of two providers. It verifies this frozen evidence, not every discovered market or future execution.
- The MCP integration is verified through the official SDK, including saved tools and a dated live inspection. Present it as reusable AI tooling; do not imply that an LLM or ML safety score makes the admission decision.
- Omit claims about Chainlink CRE, Arc deployment, prevented losses or universal market safety. The working workflow itself is the demonstration.

After recording, check sound and small text, confirm the total duration is at most four minutes, and test the uploaded video's access while signed out. Sergey performs the final upload/form submission. The public application URL must also be tested separately from this local rehearsal address.
