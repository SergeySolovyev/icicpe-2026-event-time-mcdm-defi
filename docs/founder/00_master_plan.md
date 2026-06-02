# Master Plan — Event-Time DeFi Treasury Allocator
### Solo-founder, AI-first execution plan (YC canon)

**Owner:** Sergei Solovev (solo founder). **Operating model:** 1 human +
an AI multi-agent network. **Date:** 2026-06-01. **Status:** living doc.

> YC north stars applied throughout: *make something people want;
> narrow ICP; talk to users; do things that don't scale; stay
> default-alive; ship the thinnest valuable slice; be honest about what
> works.*

---

## 0. One-liner

**Per-block, gas-aware automation that earns idle stablecoin treasuries
more than parking in any single lending protocol — non-custodial, fully
auditable, agent-run.**

---

## 1. The honest asset inventory (post-audit)

We only build on what survived the research-integrity audit
(`docs/research/honest_limitations_audit.md`):

- **REAL & defensible (the product foundation):** a closed-form,
  gas-aware, *event-time* threshold rule (T1) that reallocates USDC
  across the six largest Ethereum-L1 lending venues every block and beats
  passive single-protocol holds by **+1.5 to +2.8 pp annualized** on a
  6-window walk-forward (p<1e-4 on 5/6 contrasts). Leakage-free; T1 is
  online and training-free.
- **Honest negatives (do NOT build the pitch on these):** the Cox ML tier
  adds ≈0 out-of-sample over T1 (leakage + a feature-wiring fallback bug,
  both now found); gas is a flat-25-gwei placeholder; backtest omits
  MEV/slippage (production must use Flashbots private mempool).
- **Engineering already in hand:** production agent (per-block loop,
  Flashbots path, Prometheus, append-only audit, 128/128 tests),
  bit-identical research↔prod decision module, reproducibility envelope,
  Institutional Dossier + LP deck.

**Strategic consequence:** the product is the *simple, transparent,
event-time gas-aware allocator*, not "AI alpha." Honesty is the moat with
institutional buyers, not a liability.

---

## 2. Three phases (sequenced; A→B unblock C's credibility, but C's
##    founder work runs in parallel because it rests on T1, not T3)

### Phase A — Research integrity to completion *(in flight)*
Goal: every headline number honest and reproducible.
- A1 fix #1/#1b: expanding-window OOS with T3 actually evaluating *(running)*.
- A2 fix #2: gas-sensitivity sweep (T1/T2 at 10–200 gwei).
- A3: disclose W6-dominance + N=6 CI on any residual T3 increment.
- A4: document RPC-gated data gaps (Compound TVL, Fluid util, real gas) as next-extension.
- A5: consolidate the honest verdict → research-complete gate.

### Phase B — Paper (SCOPUS Vol-2) honest sync
- B1: propagate the leakage-free numbers into the paper; reframe T3 as an
  honest negative ("F3 spread is the decision variable; the gas-gated
  threshold captures it; the ML layer does not beat it OOS"). Rebuild,
  verify, push.

### Phase C — Product for DeFi treasurers *(the venture)*
- C0: founder package (market/ICP/MVP/risk/GTM/moat) — *multi-agent, running*.
- C1: MVP = **non-custodial advisory-first** allocator. The product never
  takes custody; it computes the optimal per-block allocation and either
  (a) shows it (dashboard + alerts), (b) proposes a one-click signed
  rebalance through the treasury's own Safe{Wallet} module, or (c) runs as
  a guarded keeper the treasury authorizes — funds never leave the
  treasury's control. This is the regulatory wedge: advisory/non-custodial
  ships without a money-transmitter/custody license.
- C2: design partners — hand-run allocations for 3–5 real treasuries
  ("do things that don't scale").
- C3: productize the winning motion; pricing (lean perf-fee on
  outperformance-vs-passive, or flat SaaS).

---

## 3. Operating model — solo founder + AI multi-agent network

The human is the only bottleneck. Everything delegable runs on agents:

| Function | How it's run |
|---|---|
| Research / backtests / data | local compute + agent-authored scripts |
| Founder artifacts (market, ICP, GTM, risk) | multi-agent Workflow fan-out |
| Paper writing / LaTeX | agent + verify loop |
| Product build (MVP) | agent-driven TDD on the existing agent repo |
| Competitive / market intel | web-research agents |
| Ops / monitoring | the production agent's own observability |

Human-only (the real bottlenecks): user interviews, legal sign-off,
custody/key decisions, capital deployment, account creation, anything
irreversible or financial.

---

## 4. Default-alive milestone ladder (6 months)

1. **M1 (wk 1–2):** research honest + paper synced + founder package + 1
   design-partner conversation booked.
2. **M2 (wk 3–6):** non-custodial advisory MVP live on testnet + mainnet
   read-only; 3 design-partner treasuries running paper allocations.
3. **M3 (wk 7–12):** first treasury executes real signed rebalances via
   Safe module; real gas + MEV-protected path live; track-record begins.
4. **M4 (wk 13–26):** ≥3 paying/committed treasuries; verifiable
   outperformance-vs-passive track record; YC application / pre-seed
   narrative ready.

---

## 5. Risk posture

Non-custodial-first; advisory before discretionary; Flashbots-private
execution; depeg/oracle/smart-contract risk register
(see `02_risk_compliance.md`). A lawyer reviews the advisory-vs-discretionary
line and jurisdiction before any discretionary keeper handles real funds.

---

## 6. Where the human is needed

Maintained as a live list; consolidated at the end of each work cycle
(see the "FOUNDER ACTIONS REQUIRED" section produced by the founder-package
synthesis and surfaced in chat). Categories: API keys (Etherscan/RPC/The
Graph), accounts (HF write token done; Safe, hosting), legal review,
design-partner intros, and the go/no-go on real-capital execution.
