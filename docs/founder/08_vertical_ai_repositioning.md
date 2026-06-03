# Repositioning — from "AI-powered DeFi allocator" to a vertical AI-native treasury service

**Date:** 2026-06-03. Supersedes the YC-centric framing in `05_gtm_pitch.md`
and `06_moat.md` where they conflict. Grounded in the mature VC consensus
(a16z, Bessemer, Menlo, Sequoia, Emergence, NFX, First Round, Greylock) on
vertical AI / AI-native services / outcome pricing — not the "solo-founder
romance" version of the thesis.

---

## 0. The one idea that reframes everything

Every serious fund agrees: **the moat is NOT the model.** It is the
workflow, the data, the trust, the distribution, and the domain context
(a16z *Context is King*; First Round *AI-powered isn't a position*; NFX
*Verticalization of Everything*; Bessemer *Building Vertical AI*).

We did not assert this — **we proved it on our own product.** The honest
research result is that the ML tier (Cox hazard) adds **nothing**
out-of-sample (−5.97 bp vs the 50-line T1 rule, 0/5 windows, robust across
gas regimes). For a typical AI startup that would be a crisis. For *this*
positioning it is the unlock: we are forced — and now free — to build the
*real* moat instead of hiding behind "we use ML."

> The algorithm is a commodity. The **vertical workflow around it** —
> event-time execution, non-custodial trust, zero-drift research↔production,
> reproducibility, and the treasurer relationship — is the company.

This is exactly what a16z, Bessemer and NFX say a durable AI company is.

---

## 1. What we are (corrected positioning)

**Not:** "an AI-powered multi-protocol DeFi yield optimizer." ("AI-powered
isn't a position" — First Round. Treasurers don't buy "AI"; they buy a
solved job.)

**Yes:** **an AI-native treasury service that earns better-than-passive,
risk-controlled yield on idle stablecoin balances — non-custodially,
net-of-cost, with a published track record.** The buyer purchases an
*outcome* (basis points of validated outperformance over leaving USDC
parked), not access to a dashboard.

The job-to-be-done it eats: the **labor** a treasury spends (or fails to
spend) manually watching cross-protocol rates, deciding when a switch
clears gas, and executing it safely. That is **labor budget**, not software
budget (NFX *Bigger than SaaS*; Bessemer — vertical AI competes with labor).

---

## 2. Why the honest research makes the pitch *stronger* (a16z "Demos to Deals")

a16z's core warning: a flashy demo is easy; a production AI product is hard
(non-determinism, trust, evals, cost/latency, orchestration). Our honesty
is the antidote, and it is already production-grade where it counts:

| a16z "real product" requirement | What we have (verified) |
|---|---|
| Trust / no overclaim | Retracted our own +7.03 bp; publish the ML-negative openly |
| Evals / measured ROI | Net-of-**real**-gas edge **+2.11 pp** (test) / **+4.05 pp** (walk-forward), 6/6 windows, p<0.001 — leakage-free |
| Cost discipline | Real `eth_feeHistory` gas modelled; 322 rebalances for **$68**; gas-aware throttling proven across 10–200 gwei |
| Determinism / "system of action" | The agent *executes* (Flashbots private mempool), not just advises — Bessemer "systems of action" |
| Zero research↔prod drift | The same `decision/` package runs backtest and live agent — a defensibility most "AI" startups can't claim |

**Demo is cheap; trust is expensive.** For a trust-gated buyer (a treasury
committee guarding a multi-million Safe), our non-custodial architecture
(can't move funds, only propose) + the *published honest track record* is
the cheapest trust we can manufacture, and the hardest for a hype competitor
to copy.

---

## 3. Business model — sell the outcome, not the seat (Sequoia / Emergence)

Sequoia/Sierra: shift from "per-seat subscription" to "pay for the job done
well." Emergence *Charging for Intelligence*: price the work, not interface
access.

- **Tier A (wedge, AI-native service):** the **Yield-Drag Report** — we run,
  by hand at first (Emergence: "start as a service, productize the
  repeatable parts"), the analysis on a treasury's *public* address:
  "over the last 6 months your idle USDC left $X on the table vs event-time
  routing, **net of real gas at your size**." Outcome-priced or free wedge.
- **Tier B (productized service):** non-custodial Safe module proposes
  rebalances the committee one-click approves. Price = **performance fee on
  net-of-cost outperformance over passive** — the number we can now quote
  honestly (+2.11 pp net). This is "pay for job well done," aligned with the
  client.
- **Tier C (system of action):** guarded keeper executes within a mandate;
  outcome pricing scales with assets-under-advisement.

Pricing rule (YC *How to Price for B2B* + Emergence): never "$X/mo because
SaaS." Tie price to *measured* outperformance, risk reduction, and the
treasurer-hours saved.

---

## 4. The moat, restated as the five VC-consensus moats

| Moat (the consensus) | Our concrete version |
|---|---|
| **Workflow** (own the end-to-end job) | event-time per-block decision → gas-gated switch → Flashbots execution → audit trail; the whole loop, not a signal |
| **Data / system of record** | the per-block 6-protocol panel + DSR + real gas, all validated on-chain; a proprietary, reproducible dataset competitors must rebuild |
| **Trust** (a16z) | non-custodial (can't steal), published honest results (incl. the ML-negative), Sepolia→ramp track record, deterministic research↔prod parity |
| **Distribution** | the founder's HSE/WQU finance-research credibility + the open, reproducible paper as a credibility flywheel into treasury working groups |
| **Domain context** (Greylock vertical-AI-in-finance) | microstructure-grounded design (MacKenzie taxonomy, López de Prado AFML), real protocol mechanics (IRM curves, fToken vs liquidity-layer), MEV/slippage literacy |

Note what is **deliberately absent**: "our ML model." We removed it as a
claimed moat because it isn't one (proven). That subtraction is the
honesty that makes the rest credible.

---

## 5. What changes vs the earlier founder package

- **05_gtm_pitch / 06_moat:** demote any "AI/ML edge" language; lead with
  *vertical workflow + non-custodial trust + outcome pricing*. The ML tier
  is documented as an honest negative, not a selling point.
- **Pricing:** make outcome-based (performance fee on net outperformance)
  the headline model, not a tier. SaaS-style per-seat is wrong here.
- **Wedge:** the Yield-Drag Report is an **AI-native service** (run it by
  hand, productize later), not a freemium SaaS feature.
- **ICP framing:** "labor budget" not "software budget" — we replace the
  manual treasury yield-management work, sized against staff/BPO cost.

---

## 6. Operating curriculum (the user's reading list, mapped to actions)

**L1 — build/sell mode (YC):** Startup Library · Diana Hu *AI-Native
Company* (AI as the company OS: research, eng, sales, support, evals — we
already run this with the multi-agent network) · Charlie Warren *AI-Native
Services* (start as a service) · Tom Blomfield *Sales Playbook* (founder-led
sales is non-optional — our #1 founder action) + *Price for B2B*.

**L2 — enterprise reality (a16z/Menlo/Bessemer):** *From Demos to Deals* ·
*Context is King* · Menlo *State of Gen AI in the Enterprise* + *Vertical
AI* · **Bessemer *Building Vertical AI*** (most relevant — labor budget,
end-to-end workflow, data/trust moat).

**L3 — business model (Emergence/Sequoia/NFX):** Emergence *AI-Native
Services Playbook* + *Charging for Intelligence* · Sequoia/Bret Taylor
*outcome pricing* · NFX *Bigger than SaaS* + *Verticalization of Everything*.

**L-cross — positioning (First Round/Greylock):** *AI-Powered Isn't a
Position* · Reducto PMF (founder-led enterprise sales) · Greylock
*Vertical AI in finance*.

---

## 7. The one-line thesis

> **Solo is the start mode; vertical AI-native treasury workflow is the
> business.** We sell *validated net-of-cost yield outperformance as a
> non-custodial service*, our moat is the workflow + data + trust + domain
> (never the model — proven), and we price the outcome, not the seat.

This is the "grown-up" version of the theme, and our honest research is the
thing that lets us tell it credibly.
