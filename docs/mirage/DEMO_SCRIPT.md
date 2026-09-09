# MIRAGE — three-minute demo

Target: three minutes of human narration with normal-speed screen recording. Record at 1080p so the block, amount and evidence remain legible. The [Graph prize](https://ethglobal.com/events/ethonline2026/prizes/the-graph) asks for two to four minutes; the [observed project form](SUBMISSION_FORM_STATE.md) caps the video at four minutes and rejects accelerated video.

## Prepare before recording

Run the application from the repository root:

```console
python -m pip install -r requirements-mirage.txt
python -m mirage serve
```

Open `http://127.0.0.1:8765`, or the verified public Python application URL. Keep the public README, `mirage/bytecode.py`, and `mirage/vendor/revert_pro/PROVENANCE.md` in nearby tabs. Close account or deploy-key pages before recording.

The **Load demo** control restores the frozen four-market evidence at block `25938082` from `mainnet-full-25938082-routes-v2.json.gz`. Expected final verdicts: PAXG `BLOCK`; deUSD `INSUFFICIENT`; wstETH `INSUFFICIENT` because of its unsupported oracle, with its exit check `PASS`; WETH `PASS`. The saved amount is `10000` USDC.

Rehearse a fresh WETH check once to establish realistic RPC latency. During recording, show its live source and new block only after it finishes. The later numerical comparison deliberately uses **Load demo**, so those exact historical values remain reproducible. If the real request is slow, allow the recording to run up to four minutes or retry with a healthy provider; do not accelerate the video or describe an unfinished request as a result.

Optional MCP preparation: install `requirements-mirage-mcp.txt`, then configure a stdio MCP client to launch `python -m mirage.mcp_server` with this repository as its working directory. Follow [MCP.md](MCP.md). Initialize before recording and rehearse `get_saved_report` and `preview_saved_allocation` with the PAXG market ID and `amount_usdc: "10000"`. The former returns four saved markets; the latter shows original T1 `switch` and gated `hold`. These tools run without a new network capture. The separate verified live `inspect_market` call took 54.36 seconds at block `25938274`; allow real latency for any new live call. Do not paste ordinary text into the server's JSON-RPC stdin.

## 0:00–0:35 — live Graph discovery

**Screen:** Select WETH and `10000` USDC. Click **Check market**. Show progress, then the successful source label and block. Keep the application's status visible while speaking.

**Say:**

> MIRAGE checks the evidence before an allocator enters a lending market. We built it on our existing USDC allocator. This WETH check starts with live market discovery through The Graph, then reads contracts at one Ethereum block. When it finishes, the source label and block show exactly which evidence supports the decision.

## 0:35–1:00 — three checks, explicit scope

**Screen:** Click **Load demo**. Show the saved label and block `25938082`. Inspect PAXG and its three check sections; briefly show deUSD's oracle finding.

**Say:**

> Now I am loading our reproducible example: six hundred and ninety-seven Graph-discovered USDC market IDs, with four markets inspected. We check available liquidity, oracle credibility, and a specified collateral sale. PAXG has zero available USDC. deUSD has a constant oracle configuration; a constant alone is a warning, not proof of mispricing.

## 1:00–1:35 — the same-size route counterexample

**Screen:** Inspect wstETH → **Collateral exit depth** → **Inspect measurements**. Show `candidate routes`, their common `amount_in_raw`, both outputs and the selected WETH path. Keep the exit `PASS` and overall `INSUFFICIENT` distinguishable.

**Say:**

> One bad route can give the wrong answer. We quote the same three point two two wstETH on two routes, at the same block. Direct returns about five thousand nine hundred and twenty-eight USDC. Through WETH, about ten thousand and eight. The input and reference price stay unchanged. The better route passes the exit check. The market remains insufficient because its oracle template is unsupported.

On-screen exact values, without reading every digit aloud:

| Item | Value |
|---|---:|
| Common collateral input | 3.220832145173417247 wstETH |
| Input in base units | 3220832145173417247 |
| Direct output | 5927.556111 USDC |
| WETH-route output | 10007.772538 USDC |
| Selected route's fee-inclusive impact against its spot | 6.39 bps |

The primary reference is the same direct-pool TWAP, approximately 3104.787691 USDC/wstETH, for both candidate sizes. This compares the implemented direct and WETH candidates; it does not establish the best route across every venue.

## 1:35–2:00 — original allocator versus admission gate

**Screen:** Select PAXG in the allocation panel, amount `10000`, and click **Preview allocation**. Show **Original allocator** and **With MIRAGE**; open **Response details** if needed to make the original T1 policy visible.

**Say:**

> Here the original T1 policy evaluates the selected destination and proposes entry. MIRAGE receives that proposal and holds because the evidence fails admission. The policy is unchanged. Its rate input is an annualized accrual-rate indication. We are comparing decisions at this recorded block, without claiming historical profits or money saved.

## 2:00–2:20 — a positive control and amount sensitivity

**Screen:** Select WETH, keep `10000`, and preview. Both decisions enter. Change the amount to `20000` and preview again to show that the saved quote does not cover the new amount. Restore `10000` afterward.

**Say:**

> WETH passes the implemented checks for this amount, so the original entry stands. Changing the amount changes the question: the saved sale quote no longer covers the proposal. A fresh check is required.

## 2:20–2:45 — real reuse of revert.pro

**Screen:** Inspect wstETH → **Oracle credibility** → **Inspect measurements**. Show the bytecode diagnostics: `features_extracted`, `feature_count: 70`, and the upstream commit. Briefly open `mirage/bytecode.py` at the `_extract_features_single` call, then the vendored provenance and MIT attribution.

**Say:**

> Our second existing project is revert.pro. MIRAGE calls its actual open-source bytecode extractor: seventy features, with the source commit and license preserved. These are structural diagnostics. Address-shaped constants remain investigation candidates, and unsupported behavior stays explicit. The extractor does not certify an oracle as safe.

## 2:45–3:00 — inspectable evidence

**Screen:** Open **Reproduce the evidence** and **Copy JSON**. Show target, calldata, numeric block, raw return and block hash. End with the workbench and the README's BEFORE/AFTER link visible. Optional terminal variant within this same 15-second slot: use the already initialized MCP client to call `get_saved_report` and `preview_saved_allocation`, showing the saved block and original/gated decisions in structured results. This replaces the final JSON-click sequence and adds no section or narration.

**Say:**

> Agents can reuse this evidence through three verified MCP tools: saved reports, live inspection, and allocation previews. Exact calls explain the decisions. MIRAGE gives an existing allocator a clear boundary: evidence first, allocation second.

## Presenter checks

- The first successful check is live; the later exact figures belong to the explicitly loaded block `25938082`. A failed refresh leaves saved evidence visible and must be described that way.
- The four inspected markets are a selected demo subset of 697 discovered IDs. Do not describe the discovery count as completed market assessments.
- The comparison invokes the real T1 policy for the selected explicit market ID at cold start. Do not say the original allocator ranked PAXG by TVL, confuse that ID with its former wstETH adapter, or imply a historical backtest result.
- Free liquidity is recorded supply assets minus borrow assets. Do not call supply assets TVL or label supply shares as recovered principal. A proposed new deposit does not prove pre-existing withdrawal liquidity.
- For AdaptiveCurve IRMs, the annualized displayed rate uses the accrual-rate indication averaged since the stored last update, rather than an instantaneous rate or a future return.
- The wstETH exit passes; its unsupported oracle is the remaining admission limitation. Preserve both findings on screen.
- The completed independent verification covers 185 distinct calls plus eight code reads through each of two providers. It verifies this frozen evidence, not every discovered market or future execution.
- The MCP integration is verified through the official SDK, including saved tools and a dated live inspection. Present it as reusable AI tooling; do not imply that an LLM or ML safety score makes the admission decision.
- Omit claims about Chainlink CRE, Arc deployment, prevented losses or universal market safety. The working workflow itself is the demonstration.

After recording, check sound and small text, confirm the total duration is at most four minutes, and test the uploaded video's access while signed out. Sergey performs the final upload/form submission. The public application URL must also be tested separately from this local rehearsal address.
