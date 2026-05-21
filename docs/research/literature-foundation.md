# Literature Foundation for the Event-Time DeFi Lending Allocator

**Status:** 4 of 5 source-book extracts complete (O'Hara, Krause, Kissell,
López de Prado AFML). MacKenzie deep-read pending. This file is the
research-notes substrate for the paper's §II Background and §III
Methodology and for the design spec at
`C:\Users\1\.claude\plans\enumerated-scribbling-barto.md`.

**Created:** 2026-05-21 by 5 parallel research subagents reading targeted
~120 pages each.

**Cross-reference:** map between book extracts → paper sections is at
the end of this file.

---

## 1. O'Hara (1995) — *Market Microstructure Theory*

PDF: `D:\DeFi\_OceanofPDF.com_Market_Microstructure_Theory_-_Maureen_OHara.pdf`

### 1.1 Adverse selection in DeFi lending

* **Glosten-Milgrom (Ch 3, §3.3, pp 58-65)** ports directly: informed
  traders trade on private signals about future V; the dealer's spread
  compensates for expected losses to them, scaled by probability of
  informed trade μ (Fig 3.1, p 63).

* **DeFi analogs of the informed trader:**
  * Whales front-running governance proposals (Aave / Compound rate-model
    upgrades, IRM parameter changes).
  * MEV searchers observing pending oracle updates or large liquidations
    in the mempool.
  * Institutional rebalancers (Ethena, MakerDAO allocators) whose flows
    are large enough to swing pool utilization.

* The mempool is the "ticker tape" — anyone watching pending txs has a
  Glosten-Milgrom-style signal about next-block rates. μ (informed
  fraction) maps to share of block-level deposit / withdraw value
  originating from informed actors. **Higher μ ⇒ higher posterior
  variance of next-block rate ⇒ shorter expected dwell time ⇒ higher
  rate-flip frequency.** Easley-O'Hara (1987a; Ch 3, §3.4, pp 66-71):
  expected dwell ≈ 1/(αμ).

### 1.2 Kyle's λ in DeFi lending

* **Kyle (1985), Ch 4, §4.1, pp 91-99, eqs. 4.4-4.5 (p 93)** — λ is the
  slope of price in aggregate net order flow x+μ.

* **DeFi mapping (key insight):** the IRM curve `r(U)` is a
  **deterministic** Kyle's λ. The slope `dr/dU` evaluated at current
  utilization U is observable. Near the kink point u\* (typically
  u\* ∈ [0.8, 0.9]), `dr/dU` jumps by **1-2 orders of magnitude**.
  Compare to traditional finance where λ must be econometrically inferred.

* **1/λ = market depth** (O'Hara footnote 9, p 109). In DeFi:
  1/λ ∝ TVL · (distance from kink). Protocols near kink ⇒ shallow ⇒
  flippy. This justifies **tracking utilization across all 6 protocols**,
  not just rate.

### 1.3 Sequential vs strategic models

* **Strategic Kyle fits better.** Each Ethereum block is a batch auction
  (Ch 4, pp 91-92): proposer sees aggregate net order flow (sum of
  deposits − withdrawals across the block) and the IRM sets a single
  clearing rate at block close. **Structurally identical to Kyle's
  single-auction setting, NOT trade-by-trade Glosten-Milgrom.**

* Multi-period Kyle (§4.1.2, pp 101-103) with auctions Δt = 12s maps
  directly to Ethereum block sequence; difference-equation system
  (eqs. 4.28-4.31) describes how λ_n evolves block-to-block.

* Glosten-Milgrom still applies *within* a block for ordering inside
  the proposer's bundle, but rate update at block close is Kyle-batch.

### 1.4 Spread decomposition — the Demsetz inversion

* **O'Hara Ch 2 + Ch 3, pp 53-65:** three components of spread —
  adverse selection, inventory, order processing.

* **DeFi inversion** of Demsetz price-of-immediacy (Ch 1, pp 5-6):
  in traditional markets, the dealer *charges* the spread; in DeFi
  cross-protocol allocation, **the spread is OUR prize** and our
  gas+slippage is OUR private "spread" eaten on each round-trip.
  Our switch rule `E[dwell] · spread > gas` is **literally the Demsetz
  condition inverted**.

* DeFi spread components:
  * *Adverse-selection*: expected APY decay after we deposit because our
    move signals to other allocators.
  * *Inventory*: utilization shift our deposit causes
    (`Δr = -∂r/∂U · our_size/TVL`) — mechanical, not strategic; closest
    to Ho-Stoll inventory cost.
  * *Order-processing*: gas + bridging + smart-contract risk premium.

### 1.5 Citations for §II Background

1. **O'Hara (1995), Ch 3, §3.3, pp 58-65** — Glosten-Milgrom sequential
   trade and regret-free conditional expectation pricing.
2. **O'Hara (1995), Ch 4, §4.1, pp 91-99, eqs. 4.4-4.5 (p 93)** — Kyle's
   λ as linear price impact; for our `dr/dU` analog and depth 1/λ.
3. **O'Hara (1995), Ch 3, §3.4, pp 66-71 (Easley-O'Hara 1987a)** —
   information-event uncertainty (α) and trade-size separating equilibria
   for our expected-dwell-time formulation as inverse of event-arrival
   rate.

---

## 2. Krause — *An Introduction to Market Microstructure Theory* (Bath)

PDF: `D:\DeFi\An Introduction to Market Microstructure Theory.pdf`

### 2.1 LOB vs AMM/kink-IRM price discovery

* In LOB, marginal price = best limit; big trades walk the book (Krause
  Ch 2.1, eq. 2.16, p 34): `p = p₀ + λ(x+u)`.
* **Kink-IRM is the LOB's *cumulative depth schedule made explicit and
  infinite*** — depth at every utilization level is pre-committed by
  the smart contract. There is no walking the book.

* Below kink: `dRate/dDeposit ≈ slope1/TVL`. Above kink: `slope2/TVL`.
  Typically slope1/slope2 differ by ~10-50×.

* **What transfers from Kyle (1985):** λ as a unified depth metric.
  DeFi λ = ∂rate/∂(supply) = (slopeᵢ/TVL)·(1/(1−u)²) for borrow rates.
  Adverse-selection logic transfers when whale deposits leak
  information about future demand.

* **What does NOT transfer:** queue-position races, hidden depth,
  spread-formation models (Cohen et al. 1981, p 130), strategic LP
  signaling in Parlour/Foucault. IRM is deterministic given (u, TVL).

### 2.2 Queue priority — block-builder ordering

* Krause Ch 1.5, pp 20-21: primary = price priority; secondary = time
  priority, size priority, "public before dealer."
* **DeFi analog:** priority gas auction / MEV-Boost top-of-block. Time
  priority replaced by **gas-bid priority**; size priority handled by
  builder profit-maximization.
* **Strategy implication:** a switch tx that ranks low in builder
  ordering can see u, rates, and even pool TVL change within the same
  block. Treat the rate you targeted as *stale by mean Δu of intra-block
  flow*; size gas like you'd size a limit-order aggression (pay up only
  when rate edge > expected slippage from re-ordering).

### 2.3 Market depth — explicit DeFi formula

* LOB depth (Kyle, p 34): 1/λ = √(σ²_u/Σ₀).
* DeFi depth: D_pool = (dRate/dTVL)⁻¹. Below kink with utilization u:
  D = TVL·(1−u)/slope1 (USD per bp).
* **Conversion (closed form):**
  * 1/λ_DeFi = **TVL·(1−u)/slope1** sub-kink
  * 1/λ_DeFi = **TVL·(1−u)²/slope2** above kink — depth collapses
    by factor (1−u)²
* Near kink (u ≈ 0.92), depth is **~150× worse** than sub-kink in
  Aave V3 USDC. Amihud's |r|/V and Kyle's λ port directly with units
  bp/$ instead of $/share.

### 2.4 Resilience / mean reversion — empirical anchor

* Parlour 1998 (Ch 4.2, eq. 4.20, p 137): Cov(Δp_{t+1}, Δp_t) ≥ −s²/4.
* Foucault-Kadan-Kandel 2005 (Ch 4.3, pp 137-140): spread mean-reverts
  geometrically with rate θ/(1−θ), θ = patient-trader fraction.

* **DeFi empirical claim (verify in Week 1):**
  * USDC pool u half-life on Aave V3 / Compound V3 sub-kink:
    **6-18 hours** (≈ 1800-5400 blocks).
  * Above-kink excursions revert faster: **1-3 hours** (slope2 generates
    strong supplier flow).
  * **This pins T2 OU κ ≈ ln(2)/9h ≈ 0.077 hr⁻¹ ≈ 2.1e-5 block⁻¹** as a
    prior; calibration on training window can refine.

### 2.5 Citations for §II Background

1. **Kyle (1985)**, *Continuous Auctions and Insider Trading*,
   Econometrica 53, 1315-1335 — λ price-impact (via Krause Ch 2.1,
   eq. 2.15, p 34).
2. **Cohen, Maier, Schwartz, Whitcomb (1981)**, *Transactions Costs,
   Order Placement Strategy, and Existence of the Bid-Ask Spread*,
   JPE 89, 287-305 (via Krause Ch 4.1, pp 127-130).
3. **Foucault, Kadan, Kandel (2005)**, *Limit Order Book as a Market
   for Liquidity*, RFS 18 (via Krause Ch 4.3, pp 137-140) —
   patient/impatient resilience, geometric waiting time
   t(sᵢ) = Δt(1 + 2Σ(θ/(1−θ))^k) (eq. 4.27).

---

## 3. Kissell (2014) — *The Science of Algorithmic Trading and Portfolio Management*

PDF: `D:\DeFi\The Science of Algorithmic Trading and Portfolio Management, Robert Kissell.pdf`

### 3.1 Implementation Shortfall adapted

* Kissell (p 97, eq. 3.1): `IS = Paper Return − Actual Return`. Wagner
  expansion (eq. 3.7, p 102):
  ```
  IS = S(P₀ − P_d)_delay
     + Σ sⱼ(P_avg − P₀)_trading
     + (S − Σ sⱼ)(Pₙ − P₀)_opportunity
     + fees
  ```

* **DeFi adaptation** — paper return = supplying to the ex-post best
  protocol every block. For block window [t₀, tₙ]:
  ```
  IS_defi = ∫ [r*(t) − r_held(t)] · V dt
          + Σ_k (gas_k + slip_k + mev_k)
  ```
  where r*(t) = max_i r_i(t) is the paper-optimal protocol.
  Structurally Wagner's "Market Activity IS" (p 104, eq. 3.8) with
  arrival-price → arrival-rate and benchmark-price → paper-best-rate.

### 3.2 I-Star / Almgren-Chriss decomposition

* Kissell's I-Star (p 146, eq. 4.7; p 149, eqs. 4.8-4.9):
  ```
  MI = b₁ · I* · POV^{a₄}  +  (1 − b₁) · I*
       └─ temporary (b₁ share) ┘   └─ permanent (1−b₁) share ┘
  I* = a₁ · (Q/ADV)^{a₂} · σ^{a₃}  (eq. 4.13)
  ```

* **DeFi mapping:**
  * **I*** ↔ instantaneous rate-shift if we dumped V into protocol i in
    one block: I*_defi = a₁ · (V/TVL_i)^{a₂} · σ_r^{a₃}.
  * **Permanent (1−b₁)·I***: new utilization-driven rate kink every other
    supplier now sees. Does NOT decay.
  * **Temporary b₁·I*·POV^{a₄}**: MEV / front-running premium. Decays
    after our tx is mined (γ ≈ 1/block for sandwich; multi-block for
    JIT-liquidity races). POV ↔ our V / total per-block supply flow.
  * **Trader's dilemma** (P3, p 140): fast → less rate-drift risk, more
    MEV; slow → less MEV, more dwell on wrong protocol. Identical
    structure to our gas-vs-spread-risk tradeoff.

### 3.3 Three-component cost under Kissell

`E[total_cost] = E[explicit] + E[market_impact] + E[opportunity]`

* **gas** = Kissell "commission + fees" (fixed-visible, Table 3.1, p 95).
* **slippage** (own deposit moving utilization) = permanent impact
  (1 − b₁) · I*.
* **MEV** = temporary impact b₁ · I* · POV^{a₄} + timing risk
  σ_r · √(Δt/250 · V/ADV) (eq. 4.5, p 146).
* **opportunity** = (S − Σ sⱼ)(Pₙ − P_d) analog from eq. 3.7.

### 3.4 Optimal rebalance frequency — closed form

Kissell's cost-risk objective (p 281, eq. 8.22):
```
min  b₁·I*·α + (1−b₁)·I*
   + λ · σ · √(1/(250·3) · X/ADV · α^{-1}) · P₀
```
Closed-form optimal trade rate (eq. 8.23):
```
α* = ( b₁·I / ( λ·σ·P₀ · √(1/3 · 1/250 · X/ADV) ) )^{2/3}
```

* **DeFi mapping:**
  * α ↔ rebalance frequency f (switches per block)
  * b₁·I ↔ per-switch MEV + slippage cost
  * λ ↔ aversion to rate-spread risk
  * σ·P₀·√(X/ADV) ↔ rate-spread volatility × notional

* **Frequency rises with 2/3-power of spread vol; falls with 2/3-power
  of unit switching cost.** Compare numerically to T2's OU-Bellman
  threshold in §III.

* With alpha signal μ (expected spread persistence, eq. 8.14, p 277):
  ```
  α* = √( X · μ / (b₁ · I · ADV) )
  ```
  Directly applicable to our `E[future spread × dwell]` decision rule
  in T1.

### 3.5 Citations for §III Methodology

1. **Kissell (2014), eq. 3.7, p 102** — Wagner's expanded IS
   decomposition. *Parent formalism for our event-time shortfall
   against paper-best-rate.*
2. **Kissell (2014), eqs. 4.7-4.9, pp 146-149 (I-Star model)** —
   `MI = b₁·I*·POV^{a₄} + (1−b₁)·I*`. *Anchors our permanent
   (utilization-shift) vs temporary (MEV) impact split with
   power-function calibration.*
3. **Kissell (2014), eq. 8.23, p 281** — closed-form optimal trade rate
   α*. *Direct map to our optimal rebalance-frequency formula under
   gas-vs-spread-risk tradeoff.*

---

## 4. López de Prado (2018) — *Advances in Financial Machine Learning* (AFML)

PDF: `D:\DeFi\Advances in Financial Machine Learning.pdf`

### 4.1 Triple-Barrier Method (Ch 3.4, pp 45-47; Snippets 3.2-3.5)

AFML labels each seed event with the first of {upper barrier, lower
barrier, vertical barrier h}. **Direct mapping to our switch/hold
decision per seed block t_{i,0}:**

* **Upper barrier**: cross-protocol spread Δr_{ij,t} exceeds switch
  threshold +ptSl[0] · trgt_{i,0} → label +1 (switch to protocol j).
* **Lower barrier**: adverse spread move −ptSl[1] · trgt_{i,0} (or
  borrow-rate spike, utilization-shock) → label −1 (exit / hold
  baseline B4).
* **Vertical barrier** t_{i,1} = t_{i,0} + h: max-holding in blocks
  (h = N blocks ≈ time-decay of stale signal) → label 0.
* **trgt_{i,0}** = rolling EWMA std of per-block spread returns
  (Snippet 3.1, p 44, span0 = 100).

**Meta-labeling for T3 (Ch 3.6, p 50, Snippets 3.6-3.7):** primary T3
sets *side* (which protocol); secondary learns *size* {0, 1} on the
survival / no-switch event. Asymmetric barriers OK with meta-labeling
(p 50): ptSl = [1, 2] for trend, [0, 2] for mean-reversion
(Exercises 3.4-3.5, p 55).

### 4.2 Purged + Embargoed k-fold CV (Ch 7.4, pp 105-108)

* **Purge** (§7.4.1, p 105): drop any train obs i with t_{i,1} ≥ t_{j,0}
  for any test j. Three sufficient overlap conditions on p 106 apply
  directly to block-event spans [t_{i,0}, t_{i,1}].

* **Embargo** (§7.4.2, p 107): `h ≈ 0.01 · T` "often suffices."
  * For 18 months ≈ 540 days: **embargo ≈ 5.4 days** (≈ 37,800 blocks
    at 12-s Ethereum cadence).
  * Tighten if features have longer autocorrelation: embargo =
    max(5.4 d, feature_window).

* For triple-barrier holding h_blocks:
  * **purge_window = h_blocks** (the label span itself)
  * **embargo_window = pctEmbargo · T with pctEmbargo = 0.01** (p 107)

* Use **k = 5-10, NO shuffling** (Exercise 7.1, p 110).

### 4.3 Deflated Sharpe Ratio (Ch 14.7.3, p 204)

```
SR* = √V[{ŜR_n}] · ( (1−γ)·Z⁻¹[1−1/N] + γ·Z⁻¹[1−1/(N·e)] )

where γ = Euler-Mascheroni ≈ 0.5772
      N = number of independent trials
      V[{ŜR_n}] = variance across trials' Sharpe ratios
```

Then DSR = P̂SR[SR*] (Ch 14.7.2, p 203):
```
P̂SR[SR*] = Z[ (ŜR − SR*)·√(T−1)
            / √(1 − γ̂₃·ŜR + (γ̂₄−1)/4 · ŜR²) ]
```

**For our N = 3 trials (H₁ᵃ, H₁ᵇ, H₁ᶜ):**
* Z⁻¹[1 − 1/3] = 0.4307
* Z⁻¹[1 − 1/(3e)] = 0.8896
* SR* ≈ √V · (0.4233 · 0.4307 + 0.5772 · 0.8896) ≈ √V · 0.6957

**Target DSR > 0.95**, not nominal p < 0.05 (Snippet 14.5, p 205:
"Marcos' Third Law").

**WARNING:** if we run T1 / T2 / T3 across **6 protocols × 3 baselines**
the effective N ≈ 54 trials — DSR threshold becomes much stricter.
**Stay focused on the 3-test H₁ matrix.**

### 4.4 Sample weighting (Ch 4)

**Do not drop non-event blocks** — use AFML's average-uniqueness
weighting (Ch 4.4, p 61):
```
ū_i = (Σ u_{t,i}) / (Σ 1_{t,i})
where u_{t,i} = 1_{t,i} · c_t⁻¹
and c_t = concurrent labels at t
```

Combine with return-attribution weights (Ch 4.6, p 68):
`w_i ∝ |Σ r_{t,i} / c_t|`.

For RF use BaggingClassifier with `max_samples = avgU` and sequential
bootstrap (Snippets 4.5, 6.2, pp 65 / 99). Add **time-decay** (Ch 4.7,
p 70) so recent 18-month tail is upweighted.

### 4.5 Hawkes processes — NOT in AFML

AFML Ch 19 only uses **Poisson** arrivals for informed / uninformed
traders (PIN, p 291: λ = μ, ε; VPIN, §19.5.2, p 292). No self-exciting
kernel.

For **T3 hazard with cross-protocol contagion**, cite externally:
* **Hawkes, A. G. (1971)**, *Spectra of some self-exciting and mutually
  exciting point processes*, Biometrika 58 (1), 83-90.
* **Bacry, Mastromatteo, Muzy (2015)**, *Hawkes processes in finance*,
  Market Microstructure and Liquidity 1 (1), 1550005.

Use AFML for labeling + CV scaffolding only.

### 4.6 Citations for §III / §V

1. **López de Prado (2018), Ch 3.4, pp 45-47, Snippet 3.2** —
   triple-barrier labeling for switch / no-switch events.
2. **López de Prado (2018), Ch 4.4-4.5, pp 61-67, Snippets 4.2-4.5** —
   average uniqueness + sequential bootstrap for overlapping per-block
   labels.
3. **López de Prado (2018), Ch 7.4.1-7.4.2, pp 105-107, Snippets
   7.1-7.3** — Purged k-fold with embargo h ≈ 0.01·T against
   hourly-resolution leakage of Solovev (2026c).
4. **López de Prado (2018), Ch 14.7.3, p 204** — Deflated Sharpe
   formula for SR* with N trials and variance V[{ŜR_n}].
5. **López de Prado (2018), Ch 12.4, pp 163-166** — Combinatorial
   Purged CV (CPCV) backtest paths for robust ΔSharpe distributions
   under H₁ᵃ⁻ᶜ.

---

## 5. MacKenzie (2021) — *Trading at the Speed of Light*

PDF: `D:\DeFi\Trading_at_the_Speed_of_Light_-_Donald_MacKenzie.pdf`

Already captured from first pass (chapter 3, chapter 6):
* **Table 3.2** — 4 HFT signal classes (futures-lead, order-book
  dynamics, fragmentation, related instruments).
* **Making vs taking specialization** (Ch 6) — we are pure takers;
  quantitative-analysis-first.
* **ATD's "Goldman leaves its bid" pattern** (Ch 3) — order-book
  dynamics from dealer-action; DeFi analog is mempool tx watching.

### 5.1 XTX Markets — regression-based signal-quality firm (p 176)

**Direct quote (p 176):**
> "One market-making HFT firm, London-based XTX Markets, even advertises
> the salience of regression as a way of making that prediction. I had
> assumed its name was one of the quasi-acronyms common in business, but
> when I read it etched in glass I realized that it was **X^T X**, a
> pervasive operation in regression analysis (the multiplication of a
> data matrix by its 'transpose')."

* **Implication:** "Gerko methodology" = combining many noisy signals
  through linear regression `(X^T X)⁻¹ X^T y` and acting on the
  projection. MacKenzie calls this **"squashing"** — squashing multiple
  signals into a single "microprice" / "theoretical value" / "fair
  price" (pp 175-176).
* **Direct theoretical ancestor** of our 4-signal MCDM aggregation
  (APY / Risk / Cost / Stability or, in our event-time pivot, the 4
  MacKenzie-Table-3.2 signal classes F1-F4).
* **Use in paper §I Introduction** as the explicit XTX citation
  motivating the "signal-quality not latency" framing.

### 5.2 Latency arms race decline → signal-driven equilibrium

No single sentence "latency arbs are dying" but the argument is built
across Ch 3 epilogue and Ch 6. Two anchor quotes:

* **ATD's collapse parable (pp 102-103):**
  > "The more profound cause of ATD's difficulties was that HFT's
  > speed race had begun... ATD survived not by winning the speed race
  > but by finding a new niche."

* **Post-last-look FX equilibrium (p 196, interviewee FW):**
  > "A lot of them [HFT firms] ... morphed into market-makers now
  > [with] less predatory behavior."

* **Use in paper §I and §VI** to justify pivot away from speed-based
  HFT thinking. Especially relevant for DeFi: Ethereum L1's 12-s block
  cadence makes speed-only competition structurally unwinnable
  (MEV-Boost top-of-block is the ceiling).

### 5.3 Treasurys triangle ↔ DeFi institutional / retail asymmetry

* **Direct dealer-client information asymmetry** (Ch 4, pp 107-117):
  primary dealers had infrastructural power (Braun 2018, p 119) by being
  part of state debt issuance.

* **DeFi mapping:**
  * Primary dealers ↔ protocol-native actors (whitelisted vaults,
    institutional borrowers, MEV searchers).
  * Retail clients ↔ retail LPs.
  * "HFT firms are careful not to exploit the greater speed of their
    systems" (p 117, interviewee CA on Goldman) ↔ reputation-managed
    off-chain quoting (RFQ systems, CowSwap, 1inch Fusion) in DeFi.

* **Direct Match episode (pp 114-116):** Island-style all-to-all
  Treasurys platform killed by being denied clearing access. **DeFi
  analog:** a permissioned-or-blocked front-end is structurally similar.
  Reinforces why **on-chain shared clearing (L1 settlement) is the
  structural pre-condition** for cross-protocol allocator alpha.

### 5.4 Speed-bump asymmetry → Flashbots private mempool

* **IEX 350μs coil is SYMMETRIC** — *"slows down both categories
  equally"* (p 203). MacKenzie says this is **NOT primarily
  protection of slow takers.**

* **Asymmetric speed bumps protect makers** (Reuters FX module, CBOE
  EDGA proposal, IEX Dec 2019 proposal): delay *taking* messages but
  not *cancels*. Quote (p 200):
  > "Delaying taking while not delaying 'cancels' gives substantial
  > protection to market-making algorithms. If the market moves, they
  > have three milliseconds (a long time, by HFT standards) to cancel
  > their stale quotes before they get picked off."

* **Reframing**: **Flashbots private mempool is an asymmetric speed
  bump** — our switch tx is invisible until inclusion (delayed
  *visibility* to MEV bots) but cancellation / re-pricing of our own
  intent remains fast. **Closer to "last look" in FX than to IEX's
  symmetric coil.**

* **Use in paper §III.E MEV-protection subsection** with explicit
  citation to MacKenzie p 200-203.

### 5.5 The "hinge" concept (Andrew Abbott via MacKenzie, pp 93-94)

* **Definition:** *"a process that creates rewards in more than one
  sphere of activity."*

* **Original example:** Island's profits funded HFT firms; HFT firms'
  liquidity made Island win share — mutual reinforcement across the
  firm-sphere and the venue-sphere.

* **DeFi analog (key paper §VI framing):**
  > A multi-protocol allocator's fragmentation-rent (arb across
  > Aave / Morpho / Euler rate quotes) **simultaneously**
  > (a) earns the allocator alpha and
  > (b) makes it rational for new lending protocols to launch, because
  > differentiated-rate venues now attract sophisticated flow that
  > bootstraps TVL.

* **Structural pre-condition** (MacKenzie p 95): hinge depends on
  **unified clearing**. **DeFi has this for free** — Ethereum L1 is
  the shared settlement layer equivalent to the DTCC for shares.
  Without it (e.g., cross-chain allocation between Solana and
  Ethereum), the hinge does not close.

### 5.6 Canonical HFT academic papers (Appendix, pp 239-242)

MacKenzie's named canon for §II Related Work:

1. **Budish, Lee, Shim (2019)**, *Will the market fix the market?*
   Quarterly Journal of Economics — economic model of the
   exchange/HFT "hinge"; complementary to Budish et al. (2015) QJE.
2. **Aquilina, Budish, O'Neill (2020)**, BIS Working Paper 955 —
   empirical quantification of latency-arbitrage rent.
3. **Menkveld, A. J. (2013)**, *High frequency trading and the new
   market makers*, Journal of Financial Markets 16 (4), 712-740 —
   Chi-X market-making study.
4. **Menkveld, A. J. (2016)**, *The economics of high-frequency
   trading: Taking stock*, Annual Review of Financial Economics 8 (1),
   1-24 — review article.
5. **Brogaard, Hendershott, Riordan (2014)**, *High-frequency trading
   and price discovery*, Review of Financial Studies 27 (8), 2267-2306.
6. **Biais, Bisière, Spatt (2003)**, *Imperfect competition in
   financial markets: ISLAND vs NASDAQ*, ECN microstructure.
7. **Hendershott, Jones, Menkveld (2011)**, *Does algorithmic trading
   improve liquidity?*, Journal of Finance 66 (1), 1-33.
8. **UK Foresight Programme (2012)** — *The Future of Computer Trading
   in Financial Markets*, government meta-review.

Social-studies-of-finance complement (for §VI sociological framing):
* Pardo-Guerra (2019), *Automating Finance*
* Lewis (2014), *Flash Boys*
* Knorr Cetina & Bruegger (2002), *Global microstructures*

### 5.7 Citations for §I / §II / §III / §VI

1. **MacKenzie (2021), p 176 (XTX = X^T X)** — for §I motivating
   regression-based signal-quality framing.
2. **MacKenzie (2021), pp 200-203 (asymmetric speed bumps)** — for
   §III.E reframing Flashbots private mempool as asymmetric speed
   bump / FX-style last-look protection.
3. **MacKenzie (2021), pp 93-94 (hinge concept)** — for §VI
   discussion of allocator-protocol mutual reinforcement.
4. **MacKenzie (2021), Table 3.2, p 97 (4 HFT signal classes)** —
   for §II.B signal taxonomy (F1-F4 mapping).
5. **MacKenzie (2021), pp 102-104 (ATD's speed-race loss)** — for §I
   speed-vs-signal-quality argument.

---

## 6. Cross-reference map: book → paper section

| Paper section | Primary sources | Key items |
|---|---|---|
| **§I Introduction motivation** | MacKenzie p 176 (XTX = X^T X); pp 102-104 (ATD parable) | Signal-quality not latency; "squashing" multi-signal regression |
| **§II.A Microstructure foundations** | O'Hara Ch 3-4, Krause Ch 2.1, 4.2-4.3 | Glosten-Milgrom μ ↔ informed-fraction; Kyle's λ ↔ ∂r/∂U; batch-auction model for Ethereum blocks |
| **§II.B HFT signal taxonomy** | MacKenzie Table 3.2, p 97 | 4 signal classes mapped to F1-F4 |
| **§II.C DeFi-specific structural inversion** | O'Hara Ch 1 (Demsetz) | Price-of-immediacy inverted: spread is OUR prize |
| **§II.D Related-work canon** | MacKenzie Appendix pp 239-242 | Budish-Lee-Shim 2019; Menkveld 2013/2016; Brogaard-Hendershott-Riordan 2014; Hendershott-Jones-Menkveld 2011; Aquilina-Budish-O'Neill 2020 |
| **§III.A Decision policy: triple-barrier framing** | AFML Ch 3.4-3.6 | Upper / lower / vertical barriers mapped to switch / adverse / time-decay |
| **§III.B T1 cost model** | Kissell Ch 3, 4 | IS_defi formula + I-Star decomposition |
| **§III.C T2 optimal stopping** | Krause Ch 4 (κ prior), Kissell eq. 8.23 | OU κ ≈ 2.1e-5 block⁻¹; closed-form α* benchmark |
| **§III.D T3 hazard model** | Hawkes 1971 (external) + Bacry et al. 2015 + AFML Ch 4-5 | Self-exciting cross-protocol arrivals + meta-labeling |
| **§III.E MEV protection (Flashbots private mempool)** | MacKenzie pp 200-203 | Asymmetric speed-bump / FX last-look analog (NOT symmetric IEX coil) |
| **§IV Backtest methodology** | AFML Ch 7, 12, 14 | Purged k-fold + embargo 5.4d + DSR > 0.95 |
| **§V Empirical study** | (results) | DSR-adjusted N=3 H₁ matrix |
| **§VI.A Cross-domain discussion** | MacKenzie Ch 6-7, O'Hara Ch 1 | DeFi has MORE info than 1996-HFT; pure-taker specialization |
| **§VI.B "Hinge" framing — allocator + new protocols** | MacKenzie pp 93-94 (Abbott) | Multi-protocol allocator + protocol launches as mutually-reinforcing hinge; L1 shared clearing as pre-condition |
| **§VI.C Dealer-client asymmetry** | MacKenzie Ch 4, pp 107-117 | Treasurys primary-dealer privilege ↔ DeFi institutional vs retail LP info-asymmetry; Direct Match (pp 114-116) ↔ permissioned-DEX-being-blocked analog |

---

## 7. Pre-flight checklist for paper writing

- [ ] Verify Krause (2005, Bath) full citation; need ISBN + publisher.
- [ ] Pull Hawkes (1971) Biometrika 58 from external source and
      Bacry-Mastromatteo-Muzy (2015) Market Microstructure and
      Liquidity 1 (1) 1550005.
- [ ] Empirically verify the 6-18 h sub-kink / 1-3 h above-kink
      half-life claim from Krause-extract §2.4 on our Aave V3 USDC
      data; this is the κ prior for T2.
- [ ] Calibrate Kissell I-Star parameters (a₁, a₂, a₃, a₄, b₁) on our
      Aave V3 + Compound V3 deposit-event panel (Q/ADV → V/TVL,
      σ → σ_r).
- [ ] Decide whether to retain N=3 H₁ matrix or expand to 6×3=18
      protocol-specific tests; DSR cost of expansion is severe.
- [ ] Cross-check that the AFML triple-barrier `applyPtSlOnT1`
      snippet (Ch 3, Snippet 3.2) runs on our per-block event panel
      without modification.

---

*Append MacKenzie deeper-read extract here when subagent returns.*
