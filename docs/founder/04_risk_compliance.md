# Risk, Compliance & Regulatory Register

**Product:** Event-Time MCDM Allocation across DeFi Lending Protocols (working name "Revert")
**Entity:** Solo founder (Sergei Solovev) — non-custodial yield-routing agent for idle stablecoin treasuries
**Version:** 1.0 — 2026-06-02
**Status:** Pre-launch / living document. Review quarterly and on any change to custody, jurisdiction, fee model, or venue set.

> ⚠️ **NOT LEGAL ADVICE.** This register is an engineering/product-risk artifact written by the founder to *structure* the legal questions and de-risk the build. Every item tagged **`[LAWYER]`** is a binding gate that must be cleared by a licensed attorney in the relevant jurisdiction **before** the corresponding action ships. Do not treat any regulatory characterization below as settled.

---

## 0. Executive posture (the one-paragraph version)

The cheapest path to default-alive for a solo, capital-light founder is to **never touch client funds, never hold keys, and never take discretion** — i.e. ship **non-custodial software + execution tooling**, not a managed service. Funds stay in a client-controlled Safe (Gnosis Safe) multisig; Revert is added as a *constrained, allowlisted Safe module* that can only move USDC **between a fixed set of six audited lending protocols on behalf of the Safe**, and **cannot withdraw to any external address**. Whether the agent runs in **advisory mode** (Revert proposes, client signs) or **delegated-execution mode** (Revert's module executes within hard on-chain limits) is the single most important regulatory fork in this document. Advisory-only is the safest launch posture. Any move toward discretion, pooling, or custody is a step-change in licensing burden and must be lawyer-gated.

---

## 1. Regulatory & licensing risk

### 1.1 The three triggers we are organizing the whole company to avoid

| Trigger | What activates it | Why we can plausibly avoid it | Confidence |
|---|---|---|---|
| **Money transmission / VASP / MSB** (US state MTLs + FinCEN MSB; EU MiCA CASP; offshore VASP) | Accepting, holding, or controlling the transmission of client value; custody of crypto | Funds never leave the client's own Safe; Revert never has unilateral withdrawal power; no pooling | Medium-High **`[LAWYER]`** |
| **Investment adviser (RIA / IAR)** (US Advisers Act; EU MiFID II portfolio mgmt under MiCA art. for portfolio mgmt of crypto-assets) | Being "in the business of" advising others on securities/crypto **for compensation**, esp. with **discretion** | (a) USDC lending positions are likely **not securities**; (b) advisory-only (non-discretionary) + careful framing; (c) software/"publisher" framing | **Low-Medium — most contested item** **`[LAWYER]`** |
| **Commodity pool / CTA / collective investment scheme** | Pooling client funds into a common vehicle that the founder trades | We do **not pool**. Each client = own Safe, own funds, own positions. Separately-managed-account (SMA) topology only | Medium-High **`[LAWYER]`** |

**Design rule that kills two of three triggers: NO POOLING, EVER, at launch.** One Safe per client. The moment funds are commingled into a Revert-controlled vault (like the existing `DeFi-Vega` ERC-4626 vault), you are arguably operating a custodial collective investment vehicle and the licensing analysis flips hard negative. Keep the ERC-4626 vault as a *future, licensed* product line — not the launch vehicle.

### 1.2 The advisory ↔ discretionary line (the core of the whole compliance strategy)

This is a spectrum, not a binary. Position the launch product as far **left** as is commercially viable.

```
SAFEST ◄─────────────────────────────────────────────────────────────► HIGHEST BURDEN
 (1) Pure          (2) Signal/         (3) Non-custodial    (4) Delegated      (5) Discretionary    (6) Custodial
 software/         alert service       advisory             execution w/        managed account     pooled fund
 dashboard         ("here's the        ("we propose,        hard on-chain       (client grants       (we hold keys/
 (client does      better venue")      client clicks        limits (Safe        broad discretion;    funds; ERC-4626
 everything)                           sign)                module, scoped)     we sign freely)      vault)
        └── publisher's exemption candidate ──┘   └─ contested middle ─┘   └──── RIA / CASP / MTL territory ────┘
```

- **Launch here → (3) Non-custodial advisory.** The agent computes the T1 threshold decision per block, but a **human/client signature is required to execute**. Revert holds **no key with spending authority**. This is the thinnest valuable slice and the strongest "we are a software publisher, not a fiduciary" posture.
- **(4) Delegated execution** is the product clients will actually *want* (the value prop is "without active management"). It is reachable **non-custodially** via a tightly-scoped Safe module (see §4). But delegated execution + compensation is where the **RIA/CASP discretion question becomes live**. Do not cross from (3)→(4) for paying clients until **`[LAWYER]`** signs off, per jurisdiction.
- **(5) and (6) are out of scope for a solo unlicensed founder.** They require RIA registration (US), MiCA CASP authorization (EU), and/or custody licensing.

**Concrete framing levers that push us leftward (all `[LAWYER]`-reviewable):**
- Market as a **"non-custodial yield-routing tool / execution infrastructure,"** never "investment management," "advice," "fund," "returns," or "we manage your money."
- **No performance fees at launch.** Performance/AUM fees are a classic indicator of acting as an adviser/manager. Prefer a **flat SaaS subscription** or **per-rebalance infrastructure fee** decoupled from performance. ("For compensation" + "advice" + "discretion" is the RIA triad — break at least one, ideally two.)
- Provide the rule as **general, non-personalized logic** (the T1 threshold is a published, deterministic, parameter-free rule — lean into that; it is *not* personalized advice tailored to a client's financial situation).
- **Client onboards their own Safe**; Revert never creates wallets for clients or holds recovery material.

### 1.3 Jurisdiction-by-jurisdiction posture

#### United States (federal + state)

| Regime | Risk to us | Posture / what it allows a solo founder to ship unlicensed |
|---|---|---|
| **FinCEN MSB / money transmitter** | Money transmission requires *control* of funds. FinCEN's longstanding guidance (2019 CVC guidance) distinguishes hosted/custodial actors from **anonymizing/non-custodial software providers and those who never take control of value** — the latter generally are **not** money transmitters. | **Non-custodial = strong "not an MSB" argument.** Never custody, never take unilateral control. **`[LAWYER]`** to confirm the Safe-module topology preserves "no control." |
| **State MTLs (50-state)** | Same control test, state by state; NY BitLicense is the harshest. | Non-custodial avoids most. **Consider geofencing NY** at launch to sidestep BitLicense ambiguity. **`[LAWYER]`** |
| **SEC — Investment Advisers Act** | "Adviser" = in the business of advising others **as to securities** for compensation. Two escape hatches: **(a) USDC supply positions on Aave/Compound etc. are very likely not "securities,"** and **(b) we provide software/general logic, not personalized advice.** Discretion + comp + securities = registration. | If lending positions aren't securities, the Advisers Act may not bite **at the federal level** regardless of discretion. **But this is the single most lawyer-dependent assumption in the doc.** Do not rely on it unwritten. **`[LAWYER]` — highest priority.** |
| **State investment-adviser laws** | Some states define "adviser" more broadly than the SEC and may not require a "security." | Geofence / `[LAWYER]` per target state. |
| **CFTC (CTA / commodity pool)** | If a venue token or strategy implicates commodities/derivatives, or if we pool. | We don't pool and we don't trade derivatives (spot lending only). Lower risk. **`[LAWYER]`** if venue set expands beyond spot lending. |
| **OFAC sanctions** | **Applies regardless of license status.** Screening counterparties/wallets; the Tornado Cash precedent shows DeFi-adjacent tooling is squarely in OFAC's sights. | **Mandatory wallet screening at onboarding + ongoing** (e.g., Chainalysis/TRM); block sanctioned addresses; document the program. Non-negotiable. See §1.4. |

**US bottom line:** A non-custodial, non-discretionary, no-performance-fee, US-stablecoin-lending **software tool** has a *credible* path to ship without federal MSB or RIA registration — but the RIA "is it a security / are we advising" question and state-by-state MTL/IA patchwork **must** be cleared by counsel. Default to **advisory-only + geofence NY (and likely the whole US until counsel clears it)** if budget is thin.

#### EU / MiCA

| Regime | Risk to us | Posture |
|---|---|---|
| **MiCA CASP authorization** | MiCA regulates a defined list of **crypto-asset services**, including **"portfolio management of crypto-assets"** and **"providing advice on crypto-assets,"** plus custody/transfer services. Performing these *for third parties, professionally, in the EU* triggers CASP authorization. | **Two shields:** (1) **"fully decentralised / no intermediary" carve-out** — MiCA's recitals exclude services provided in a fully decentralised manner with no intermediary. A pure non-custodial software tool *may* fall outside CASP scope; (2) avoid the two trigger services by staying **non-discretionary** (no "portfolio management") and **non-personalized** (avoid "advice"). **`[LAWYER]`** — the decentralisation carve-out is narrow and actively being interpreted; do not over-rely on it. |
| **MiCA "advice on crypto-assets"** | Personalized recommendations → CASP advice service. | Keep the T1 rule **general and published**, not personalized → argue it's not "advice" in the MiCA sense. `[LAWYER]`. |
| **Stablecoin (ART/EMT) rules** | MiCA's Title III/IV constrain *issuers* of stablecoins (USDC's EU availability/compliance), not routers of them. Indirect risk: a venue's stablecoin could become EU-restricted. | Monitor USDC's EU (MiCA EMT) compliance status; have a venue/asset kill-switch. |

**EU bottom line:** **Do not actively solicit EU clients at launch.** Reverse-solicitation is fragile. If/when targeting the EU, the path is either (a) lean hard on the non-custodial/decentralised + non-discretionary posture with counsel, or (b) get CASP authorization (heavy for a solo founder). **`[LAWYER]`** before any EU go-to-market.

#### Offshore (where many DeFi-native products domicile)

| Jurisdiction | Why considered | Caveat |
|---|---|---|
| **Cayman Islands** | Common for DeFi; foundation company structures; VASP Act regime exists. Non-custodial software can sometimes sit outside the VASP perimeter. | VASP registration may still bite "virtual asset services." `[LAWYER]` + local counsel + ongoing economic-substance/registration costs. |
| **BVI** | Light-touch, popular for token/DeFi entities. | Similar VASP analysis; needs local counsel. |
| **UAE / VARA (Dubai)** | Comprehensive, *clear* crypto regime; advisory & management activities are licensable but the rulebook is explicit. | Licensing is real and not free; better when funded, not at $0. |
| **Singapore / MAS (PSA, FSMA)** | Mature regime; "dealing in / advising on" digital payment tokens is regulated. | MAS is rigorous; advisory on DPTs can require a CMS licence. `[LAWYER]`. |

**Offshore bottom line:** Offshore domicile does **not** create a free pass — every serious jurisdiction now has a VASP/CASP-equivalent perimeter, and offshore-domiciled does not exempt you from the laws of the *jurisdictions where your clients are* (US/EU clients re-import US/EU rules). Offshore is a tool for *entity domicile + IP holding + neutral governing law*, not a regulatory eraser. Choose domicile **with counsel** as a funded step, not a launch hack.

### 1.4 Cross-cutting compliance obligations (apply at every posture, even pure software)

- **OFAC/sanctions screening** of every client wallet at onboarding and continuously (`[LAWYER]` + a screening vendor). Block + log.
- **KYC/AML:** A pure non-custodial software tool may have *limited* KYB/KYC obligations, but **institutional ICP (DAOs, funds, family offices) will demand it anyway**, and many jurisdictions impose AML on advisers/managers. Implement **KYB onboarding** for institutional clients regardless — it is also a sales asset. `[LAWYER]` for the regulatory floor.
- **Terms of Service / disclaimers:** explicit "non-custodial, non-advisory, no guarantee of returns, client retains full control and responsibility, past backtest ≠ future results, smart-contract risk borne by client" language. `[LAWYER]`-drafted.
- **No misleading performance claims.** The honest backtest caveats (flat-25-gwei gas placeholder; no MEV/slippage deduction; +1.5–2.8pp gross; ML adds ~0 over T1) **must** appear in any client-facing performance material. Overstating net edge is both a securities/consumer-protection risk and a reputational one. **Show net-of-realistic-cost figures, not gross.**
- **Marketing language audit:** ban "guaranteed," "safe," "risk-free," "managed," "fund," "returns you'll earn." `[LAWYER]`-reviewed marketing copy gate.

---

## 2. Smart-contract & protocol risk (the six venues)

**Venue set:** Aave V3, Compound V3, Spark, Morpho Blue, Euler V2, Fluid (~67% of ~$54B lending TVL).

| Risk | Description | Mitigation |
|---|---|---|
| **Protocol smart-contract exploit** | A lending venue is hacked/drained (Euler suffered a major exploit in 2023; recovered funds, but the precedent is real). Client funds in that venue at the time are at risk. | (a) **Per-venue exposure caps** as a hard config (no single venue > N% of a client's capital unless client opts in); (b) **only venues with multiple reputable audits + meaningful battle-tested TVL/age**; (c) **real-time exploit monitoring + automatic exit** — the founder *already operates a 24/7 vulnerability scanner* (`DeFi -/production_scanner.py`); wire its alerts into a venue **kill-switch** that can pull allocation from a venue on credible exploit signal; (d) maintain a per-venue **risk score** feeding the MCDM (the existing scoring already has a 25% Risk weight — make venue-hack risk an explicit input). |
| **Upgrade / governance / admin-key risk** | A venue's admin/governance changes parameters maliciously or by capture (e.g., raises risk params, pauses withdrawals, upgrades a proxy to a malicious impl). Morpho Blue/Euler V2 are highly parameterized/modular → larger surface. | Monitor governance + proxy-admin events per venue (the scanner already detects proxy-init/admin-func patterns); treat an unexpected upgrade/param change as a kill-switch trigger; prefer venues with timelocks on upgrades. |
| **Withdrawal liquidity / utilization risk** | At high utilization a lending pool may not have liquidity to satisfy a withdrawal/reallocation at the moment the agent wants to move; the agent could be stuck or move at a penalty. | Include **available-liquidity / utilization** as a pre-trade check in the decision module; do not signal a move into/out of a venue the move can't actually be executed against; size moves to available liquidity. |
| **Stablecoin depeg risk (USDC and venue-internal stables)** | USDC depeg (cf. March 2023 SVB episode, briefly ~$0.88) hits the entire book; venue-native stablecoins (e.g., Spark's sDAI/DAI line, Fluid/others) add second-order depeg exposure. | (a) **USDC depeg monitor** with a defined threshold → halt rebalancing / alert (do not churn gas chasing yield during a depeg); (b) avoid routing into venue-internal stables without explicit risk budgeting; (c) document depeg as a borne-by-client risk in ToS; (d) **`[future]`** optional client-configurable depeg circuit-breaker. |
| **Oracle risk** | Lending venues price collateral via oracles (Chainlink etc.). A stale/manipulated oracle can cause bad liquidations or mispricing; our *yield* read (supply APY) is less oracle-sensitive than a leveraged position, but venue solvency depends on oracles. | (a) For a **supply-only USDC** strategy, direct oracle exposure is **lower** than for borrowers — state this honestly; (b) still monitor venue oracle health where exposed; (c) avoid venues/markets with thin or exotic oracle setups (a relevant filter for Morpho Blue's permissionless markets — **only whitelist curated/blue-chip Morpho markets**, never permissionless long-tail ones). |
| **Data-source / feed integrity** | The agent's *own* APY/state reads (the data layer feeding T1) could be wrong/stale (bad RPC, reorg, indexer lag) → bad decision. | Reorg-aware reads; sanity bounds on APY inputs (reject implausible values); multi-source/redundant RPC; the decision must be **bit-identical** between backtest and live (already a stated property — preserve it under fault conditions). |
| **Composability / dependency risk** | A venue depends on another protocol (e.g., a stablecoin's PSM, a wrapper, an LST) that fails upstream. | Map each venue's critical dependencies; treat upstream failure as a venue-level risk input. |

**Honest caveat carried from product context:** the **backtest uses flat 25-gwei gas and does not deduct MEV/slippage**. The live net edge at $1M is ~**+1.75 bp/rebalance, gas-bounded**. This means **transaction-cost risk is a first-order economic risk, not a footnote** — see §3. Edge grows with position size as gas amortizes; small accounts may be **net-negative after real gas** → enforce a **minimum viable position size** and a **per-rebalance net-benefit gate** (only rebalance if expected APY pickup × dwell-time-adjusted notional > realistic all-in execution cost).

---

## 3. MEV & execution risk

| Risk | Description | Mitigation |
|---|---|---|
| **Sandwich / front-running of rebalances** | A public-mempool rebalance tx is visible; searchers can front-run/sandwich the venue interaction, extracting value and worsening fill. | **Route all execution through Flashbots Protect / private mempool (or an equivalent private order-flow / MEV-protected RPC).** This is already the designed live path — make it **mandatory and fail-closed**: if the private relay is unavailable, **do not fall back to the public mempool**; skip the rebalance. |
| **Failed/expired txs & gas waste** | A tx reverts (state moved) or is left pending; gas spent for nothing erodes the thin per-rebalance edge. | Pre-trade simulation/`eth_call` dry-run + tight slippage/limit params + nonce management + a **net-benefit gate** that already accounts for failure probability; cap gas price. |
| **Gas-spike / fee-market risk** | A gas spike turns a +1.75 bp move into a net loss. **Backtest's flat 25 gwei masks this.** | **Wire real-time gas into the decision rule before live trading** (explicit open item from product caveats). Hard rule: **rebalance only if net-of-actual-gas benefit > threshold.** No real-gas wiring → no live trading. **`[blocking]`** |
| **Slippage / price impact** | Large reallocations move venue rates / incur slippage not modeled in backtest. | Size-aware execution; split large moves; model expected impact in the net-benefit gate; **do not advertise backtest gross numbers as net.** |
| **Reorg / inclusion risk** | A rebalance lands then gets reorged; or private-relay tx isn't included for several blocks. | Reorg-aware confirmation before considering a move "done"; idempotent decision loop; the per-block (event-time) design should tolerate non-inclusion gracefully (just re-evaluate next block). |
| **MEV in the backtest vs reality gap** | Backtest **does not deduct MEV/slippage** → reported edge is optimistic. | **Production MUST use Flashbots private mempool** (stated). Additionally: run a **shadow/paper-trading period** in production to measure *realized* net edge vs backtest before taking meaningful client capital, and publish the realized-vs-backtest gap honestly. |

---

## 4. Key-management & non-custodial execution (Safe modules)

**Architecture principle: the founder must never hold a key that can move client funds to an address the client doesn't control.** This is the technical fact that underpins the entire "not a money transmitter / not custodial" legal posture in §1. If this property breaks, the regulatory analysis breaks with it.

**Recommended topology (Safe + scoped module):**

- **Client owns a Gnosis Safe** (their multisig, their owner keys, their threshold). Funds live here. Revert never holds Safe owner keys or recovery material.
- **Revert is enabled as a Safe *module* with a narrowly-scoped, allowlisted permission set** (use a guard/allowlist library such as Zodiac Roles or an equivalent permissions module). The module is constrained on-chain to:
  - **Allowlisted target contracts only:** exactly the six lending venues' supply/withdraw entry points. Nothing else is callable.
  - **Allowlisted asset:** USDC (and only the specific tokens the strategy uses).
  - **No external transfers:** the module **cannot** call `transfer`/`withdraw` to any address outside the venue↔Safe loop. Funds can only ever move *Safe → venue → Safe*. **There is no code path by which Revert moves money out to a Revert-controlled or third-party address.** This is the single most important control in the document.
  - **Function-selector allowlist:** only `supply`/`withdraw`-class selectors on each venue; no `borrow`, no `delegate`, no approval to arbitrary spenders.
  - **Optional rate limits / caps:** max notional per tx, max txs per day, per-venue exposure caps enforced on-chain where feasible.
- **The Safe owners (client) retain full unilateral control:** they can **disable the Revert module instantly** and withdraw everything without Revert's cooperation. (Document and demo this as a sales/safety feature: "fire us in one click.")

| Risk | Description | Mitigation |
|---|---|---|
| **Agent signer key compromise** | The hot key Revert uses to call the module is stolen. | (a) The **on-chain allowlist caps the blast radius** — a stolen signer key still can't exfiltrate funds (only shuffle them among the six venues); (b) signer key in **KMS/HSM or hardware-backed signer**, never plaintext on disk; (c) key rotation; (d) per-key spend/rate limits; (e) the existing agent already uses **EIP-712 signed decisions + nonce + timestamp anti-replay** — extend that discipline to the signer. |
| **Module/permission misconfiguration** | An over-broad allowlist accidentally permits an external transfer or a dangerous selector. | **Module config is the crown jewel** → independent **audit of the Safe module + allowlist** (`[blocking]` before any real funds); automated test that asserts "no path to external transfer" (the project already runs 128/128 tests — add explicit *negative* tests: attempt to move funds out, attempt non-allowlisted selector, assert revert); formal review of the Zodiac/Roles config. |
| **Upstream Safe / module dependency risk** | A vulnerability in Gnosis Safe or the Zodiac/Roles modules themselves. | Pin audited versions; monitor Safe/Zodiac advisories; prefer the most battle-tested contracts; have a documented client-side "disable module + migrate Safe" runbook. |
| **Operational availability** | The agent is down → missed rebalances (lost opportunity, not lost funds). | Acceptable failure mode (funds remain safely supplied in the last venue). Supervisor/auto-restart (the codebase already has `monitor_supervisor_v2.py`-style supervision); Prometheus observability (already present); alerting. **Fail-safe = stop, never fail-dangerous.** |
| **Audit-trail / dispute risk** | A client disputes a rebalance decision. | The append-only audit log + EIP-712-signed, reproducible decisions (already built) give a **bit-identical, replayable decision record** — strong dispute defense. Preserve and timestamp it; consider client-readable audit export. |
| **Avoid the custodial trap** | The existing `DeFi-Vega` **ERC-4626 vault** pools funds under contract control — that is a **custodial/collective** pattern. | **Do not use the pooled vault as the launch vehicle.** SMA-per-Safe only. Vault = later, licensed product. (Repeats §1.1 because it matters here too.) |

---

## 5. Prioritized risk register

**Likelihood:** L=Low / M=Medium / H=High. **Impact:** L / M / H / **Critical** (existential). **Owner** is the solo founder (all roles) — named by *function* to clarify the hat being worn and where external help is mandatory.

| # | Risk | Cat. | Likelihood | Impact | Mitigation (control) | Owner / gate |
|---|---|---|---|---|---|---|
| R1 | **Mischaracterized as RIA / investment adviser** (esp. if any discretion or perf-fee) | Reg | M | **Critical** | Launch advisory-only (posture 3); no perf fee; general non-personalized rule; software/publisher framing; **counsel opinion before any paying client** | **`[LAWYER]`** (US securities/IA counsel) — **#1 priority** |
| R2 | **Mischaracterized as money transmitter / VASP / unlicensed custody** | Reg | M | **Critical** | Strict non-custodial Safe-module topology (§4); no pooling; no external-transfer code path; counsel opinion on "no control" | **`[LAWYER]`** + Founder (architecture) |
| R3 | **MiCA CASP / EU portfolio-mgmt or advice trigger** on EU solicitation | Reg | M (if EU GTM) | **Critical** | No active EU solicitation at launch; non-discretionary + non-personalized; decentralisation posture; CASP only as funded step | **`[LAWYER]`** (EU counsel) before EU GTM |
| R4 | **Venue smart-contract exploit** drains client funds in a venue | SC | M | **Critical** | Per-venue caps; multi-audited venues only; live exploit scanner → **kill-switch auto-exit**; risk score in MCDM; whitelist only curated Morpho markets | Founder (Eng/Risk) — **wire scanner→kill-switch `[blocking]`** |
| R5 | **Backtest overstates net edge** (flat 25-gwei gas, no MEV/slippage) → real net negative; also a **misleading-claims** legal risk | Exec + Reg | **H** (as currently built) | H | **Wire real gas into decision rule** `[blocking]`; net-benefit gate per rebalance; min position size; **publish net-of-cost, not gross**; production shadow-trading to measure realized edge | Founder (Quant) — **blocks live trading** |
| R6 | **Safe module / allowlist misconfig** opens an external-transfer or dangerous selector path | Key-mgmt | L–M | **Critical** | Independent module+allowlist **audit `[blocking]`**; negative tests (assert revert on exfil/non-allowlisted selector); pin audited Zodiac/Safe versions | **`[AUDITOR]`** + Founder (Eng) |
| R7 | **Agent signer key compromise** | Key-mgmt | L–M | M (blast-radius capped by allowlist) | KMS/HSM-backed signer; rotation; rate limits; on-chain allowlist caps damage; EIP-712 + nonce anti-replay | Founder (SecOps) |
| R8 | **MEV sandwich / public-mempool leakage** of rebalances | Exec | M (if mempool path used) | M | **Mandatory Flashbots/private relay, fail-closed** (no public fallback); pre-trade simulation; slippage limits | Founder (Eng) — **fail-closed `[blocking]`** |
| R9 | **USDC or venue-stable depeg** | SC/Market | L–M | H | Depeg monitor + halt-rebalance threshold; avoid venue-internal stables w/o budget; ToS disclosure; optional client circuit-breaker | Founder (Risk) |
| R10 | **OFAC/sanctions hit** (sanctioned client wallet; Tornado-Cash-style tooling exposure) | Reg | L | **Critical** | Mandatory wallet screening at onboarding + ongoing; block + log; documented program | **`[LAWYER]`** + screening vendor |
| R11 | **Gas-spike turns rebalance net-negative** | Exec | M | M | Real-time gas in decision; cap gas price; net-benefit gate (same control as R5) | Founder (Quant) |
| R12 | **Venue governance/upgrade capture or malicious param change** | SC | L–M | H | Monitor governance/proxy-admin events (scanner); treat as kill-switch trigger; prefer timelocked venues | Founder (Risk/Eng) |
| R13 | **Withdrawal-liquidity / high-utilization** blocks or penalizes a reallocation | SC | M | M | Pre-trade liquidity/utilization check; size to available liquidity; don't signal infeasible moves | Founder (Eng) |
| R14 | **Oracle staleness/manipulation** at a venue | SC | L | M | Supply-only = lower oracle exposure (state honestly); monitor venue oracle health; avoid exotic-oracle markets | Founder (Risk) |
| R15 | **Data-feed / reorg / RPC error** → bad decision | SC/Exec | M | M | Reorg-aware reads; APY sanity bounds; redundant RPC; bit-identical decision under faults | Founder (Eng) |
| R16 | **Misleading marketing** ("guaranteed," "safe," "managed," gross perf) → consumer-protection / securities-promo risk | Reg | M | H | Banned-words list; `[LAWYER]`-reviewed copy; honest caveats (ML adds ~0 over T1; gross≠net) in all material | **`[LAWYER]`** + Founder (Marketing) |
| R17 | **Pooling / ERC-4626 vault used as launch vehicle** → custodial/collective-investment trigger | Reg | L (if discipline holds) | **Critical** | **SMA-per-Safe only at launch**; vault deferred to licensed product line | Founder (Product) — hard rule |
| R18 | **Key-person / solo-founder concentration** (illness, burnout, single point of failure for ops + keys) | Ops | M | H | Documented runbooks; client one-click module-disable means *funds survive founder absence*; signer recovery plan; consider a co-signer/backup operator | Founder (Ops) |
| R19 | **Tax / reporting obligations** for clients or entity (token rewards, fee income, entity domicile) | Reg | M | M | Entity + tax structuring with advisor; client tax disclaimers in ToS | **`[LAWYER]`/`[TAX]`** |
| R20 | **Reliance on the contested "USDC-lending-isn't-a-security" assumption** | Reg | M | **Critical** | This assumption underpins R1's escape hatch — **get it in writing from counsel**; if it fails, fall back to pure-software/advisory + geofence | **`[LAWYER]`** — explicit written opinion |

### Top-5 blocking gates before taking real client capital
1. **R5/R11 — real gas wired + net-benefit gate** (else the product can lose money you claimed it makes). *Engineering, blocking.*
2. **R1/R20 — written counsel opinion** on adviser status + securities characterization for the launch posture/jurisdiction. *Legal, blocking.*
3. **R6 — independent audit of the Safe module + allowlist**, with negative exfiltration tests passing. *Audit, blocking.*
4. **R8 — Flashbots private relay mandatory and fail-closed.** *Engineering, blocking.*
5. **R4 — exploit-scanner → kill-switch wired** for automatic venue exit. *Engineering, blocking.*

---

## 6. Recommended launch posture (synthesis)

- **Topology:** SMA-per-client Safe + scoped Safe module. **No pooling. No external-transfer path. Client can fire you in one click.**
- **Regulatory posture:** **Non-custodial, non-discretionary advisory software** (posture 3), **flat subscription/infra fee (no performance fee)**, **US: geofence NY at minimum (likely all US until counsel clears); EU: no active solicitation**; offshore entity domicile only as a funded, counsel-led step.
- **Honesty in market:** net-of-realistic-cost performance only; T1 (not the ML) is the product; gas/MEV caveats disclosed.
- **Move to delegated execution (posture 4) and/or EU/US scale only after the `[LAWYER]` gates (R1, R2, R3, R20) and the engineering gates (R4, R5, R6, R8) are cleared.**
- **Keep the ERC-4626 pooled vault out of the launch path** — it is the regulatory cliff edge (R17).

---

*Relevant local assets referenced (absolute paths):*
- `D:\DeFi\predictive-mcdm-defi\` — research / decision-module home (Event-Time MCDM).
- `D:\DeFi\REVERT_pm\`, `D:\DeFi\revert_api\`, `D:\DeFi\revert_site_deploy\`, `D:\DeFi\revert_qa_artifacts\` — the "Revert" commercialization track (PM, API, site, QA) where this register should live.
- `D:\DeFi\DeFi -\production_scanner.py` and `D:\DeFi\DeFi -\160326\monitor_supervisor_v2.py` — existing 24/7 exploit scanner + supervisor to wire into the R4 kill-switch.
- `D:\DeFi\DeFi-Vega Project\` — the ERC-4626 vault + Python agent (EIP-712 signed decisions, MCDM scoring). **Keep the pooled vault out of the launch path (R17); reuse the signing/audit discipline for the Safe-module signer.**

> **Final reminder:** items tagged **`[LAWYER]`**, **`[AUDITOR]`**, **`[TAX]`**, and **`[blocking]`** are gates, not suggestions. The non-custodial architecture is what makes the optimistic regulatory reading *possible*; it does not make it *certain*. Get R1/R2/R20 in writing before a single dollar of client capital moves.