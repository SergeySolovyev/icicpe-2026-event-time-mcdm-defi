# First-money playbook — fastest realistic path to the first dollar

**Date:** 2026-06-10. Goal: first revenue ASAP, no consulting treadmill.
Honest truth from the scale workflow: the bottleneck is **demand**, not
building — so the first dollar comes from an *ask*, not more code. Two tracks,
run in parallel this week. Track A fits the founder's psychology best (work
once → lump check, no buyer trust-gate); Track B is faster if a warm buyer
exists.

---

## TRACK A — Grant (best fit: work-once, lump, no treadmill, no adviser-risk)

Why first: it doesn't require a treasury to trust a solo unaudited researcher
with funds. It requires ONE strong application, and the assets already exist
(reproducible paper + per-block 6-protocol panel + the honest negative result
+ a live rate dashboard). It's the "launch once, get a check" the founder
wants, just framed as a public good.

**Lead program — Ethereum Foundation ESP (Ecosystem Support Program).**
Rolling (no deadline wait), solo-friendly, funds open-source tools + research +
public goods. Decision in weeks. Ask $15–40k.
**Alternates (apply in parallel):** Gitcoin Grants (round-based quadratic —
community donations can land within a round); Optimism RetroPGF (rewards
*already-shipped* public goods — the open panel/dashboard/paper qualify);
Arbitrum / Uniswap Foundation; Morpho/Euler ecosystem tooling grants.

### Draft application (paste-ready, EF ESP form: "Project description")

> **Project:** *Open Per-Block DeFi Lending-Rate Panel + Honest Yield Benchmark*
>
> **One-line:** A free, reproducible, per-block dataset and benchmark of USDC
> supply rates across the six largest Ethereum lending protocols (Aave V3,
> Compound V3, Spark, Morpho Blue, Euler V2, Fluid), with an open
> net-of-real-gas event-time methodology — so anyone can reproduce "what idle
> stablecoins actually earn," instead of trusting opaque vault dashboards.
>
> **Problem:** Cross-protocol lending rates are reported inconsistently and
> only as raw APY. There is no open, correctly-decoded, per-block, net-of-gas
> reference an Ethereum treasury, researcher, or agent can reproduce. Each of
> the six venues exposes rates differently (Aave RAY-annualized; Compound only
> via Comet view-calls; Spark `getReserveData`; Fluid via the fToken layer;
> plus real `eth_feeHistory` gas and the Maker DSR lead) — a real, error-prone
> integration most reuse a vendor for or get wrong.
>
> **What the grant funds (all open-sourced, MIT/CC-BY):**
> 1. Release the per-block 6-protocol panel (~98% coverage, Nov 2024–present)
>    + the decoders, as a public good others can re-run.
> 2. A live "honest rate dashboard": current + historical net-of-gas supply
>    rates across the six venues, with the size-haircut (slippage) and
>    gas-sensitivity disclosed — not a single misleading APY.
> 3. The open methodology paper (event-time evaluation, leakage-free
>    walk-forward) including a *pre-registered negative result*: a Cox-hazard
>    ML tier does **not** beat a 50-line rule — published openly to counter
>    yield-optimization overclaiming in the ecosystem.
> 4. 6 months of coverage maintenance + extension to 1–2 L2s (Base/Arbitrum).
>
> **Why this benefits Ethereum:** treasuries (DAOs, on-chain orgs), builders,
> agents, and researchers get a neutral, reproducible yield reference; it
> raises the honesty bar against incentive-juiced/opaque yield products; and
> it is a public good no single protocol has an incentive to maintain neutrally.
>
> **Why us:** solo quant researcher (WorldQuant University / HSE), author of a
> reproducible SCOPUS-track paper on exactly this; the panel, decoders, and
> benchmark already exist and are committed — the grant funds opening,
> hosting, maintenance, and L2 extension, not greenfield research.
>
> **Budget ask:** $15–40k for 6 months (hosting + data infra + maintenance +
> L2 coverage). **Deliverables:** public repo, live dashboard, the paper, a
> reproducibility guide. **Timeline:** dashboard + open panel in 4 weeks;
> L2 coverage by month 3.

---

## TRACK B — Warm paid pilot (fastest cash if a warm buyer exists)

The hardened Yield-Drag Report exists. A warm contact who controls/advises
$0.5–10M idle USDC can pay for a bespoke backward-looking audit in days. Keep
it strictly backward-looking + flat-fee + research-framed to stay on the safe
side of the adviser line.

### The offer (3 flat-fee SKUs — no performance fee, no custody)

| SKU | What | Price |
|---|---|---|
| **Yield-Drag Audit** | one-time bespoke backward-looking report on your real address: net-of-gas drag vs event-time routing, size-haircut at your size, gas-sensitivity, per-venue time-share | **$2,500** |
| **Audit + 90-day monitoring** | the audit + monthly drag report + rate-cross alerts | **$5,000** |
| **Validated data/panel access** (for quant/fund buyers) | the per-block 6-protocol panel + the walk-forward validation harness | **$2,000/mo** |

> **ToS one-liner (put on the invoice + a 1-paragraph terms page):** "Treasury
> Yield Analytics — backward-looking research, not personalized investment
> advice; non-custodial, we never touch funds." Form a $0–300 LLC and have a
> crypto-literate lawyer bless this one paragraph before the first invoice.

### Warm-outreach message (send AFTER running the free report on their address)

> Subject: you left ~$X on the table on [treasury] last quarter (net of gas)
>
> Hi [name] — I'm a quant researcher (WorldQuant/HSE); I published a
> reproducible paper on event-time DeFi lending allocation (incl. the honest
> result that an ML tier *lost* to a 50-line rule). I ran my free Yield-Drag
> analysis on [their public address]: held passively, your idle USDC earned
> ~A%; event-time routing across the 6 biggest lenders — net of real gas —
> would have earned ~B%, i.e. **~$X left on the table** last [period]
> (size-adjusted, gross of MEV/slippage — I show the haircut).
>
> 2-min animation of the real routing + the 1-page report attached. If useful,
> I do a full bespoke audit on your live position for $2,500 (backward-looking
> research, non-custodial, I never touch funds). Worth a 15-min call?

### Target profile (who to send to — you supply the names)
Someone you can reach in **one hop** who controls or advises **$0.5–10M idle
USDC**: a small crypto-fund GP/CIO, a DAO treasury/ops lead, a crypto-fintech
CFO, or a quant peer with an on-chain book. **Disqualify** anyone below ~$250k
(gas kills the edge) or who needs a security audit before paying for a *report*.

**⚠ The gating unknown only you can resolve:** write down, by name, every
1-hop contact who fits. If that list is **< 8 names**, that — not the product —
is your real constraint, and Track A (grants) is the higher-probability first
dollar.

---

## This-week checklist
1. **Track A:** submit the EF ESP inquiry (draft above) + start a Gitcoin grant
   page. ~half a day, reuses existing assets, no buyer needed.
2. **Track B:** write the named 1-hop list. Run the free report on the top 5–8
   real addresses. Send the message + animation. Make the $2,500 ask.
3. **Proof-point / go-no-go:** first grant approved OR first $2,500 invoice
   cleared = demand is real → build the funnel (public dashboard + MCP).
   Zero of both after the asks = demand thesis is the blocker, not the code.
