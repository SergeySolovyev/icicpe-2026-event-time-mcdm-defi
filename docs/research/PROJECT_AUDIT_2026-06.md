# Project Audit — academic rigor + sellability + token reality

**Date:** 2026-06-09. **Method:** adversarial multi-agent workflow (43 agents,
3.4 M tokens, ~2 h): 1 mapping pass → 7 expert dimensions → independent
skeptic re-check of every critical/high finding → 3 buyer personas
(SCOPUS reviewer, institutional DeFi allocator, crypto/securities operator)
→ integrated verdict → completeness critic. Every finding cites a real
file/result; the completeness critic re-checked the panel and caught one
scoping error (below).

## Headline grades

| Dimension | Grade |
|---|---|
| Statistical methodology (leakage / p-hacking) | **B** |
| Data provenance & reproducibility | **B** |
| Claim ↔ evidence integrity | **D** |
| Internal consistency (paper↔code↔results↔docs) | **D** |
| DeFi microstructure & quant-finance logic | **C** |
| Production-engineering / security maturity | **D\*** |
| Go-to-market readiness & token reality | **C** |
| **Overall** | **C** |

\* The Production-Engineering **D was a scoping error** — see "Corrected picture".

## Bottom line

A **fundable, intellectually honest research kernel** wrapped in (a) a paper
that would **desk-reject in its current built state** over self-contradictions
on its two load-bearing tables, and (b) a product surface whose hardest,
most commercially relevant parts are early/unaudited. The two gates are
independent and should be fixed separately.

- **Academic gate:** MAJOR REVISIONS (not reject). The science is leakage-free
  and the pre-registered ML-negative recomputes to the digit; the blockers are
  *synchronization/significance presentation* defects, all fixable.
- **Selling gate (larger):** sellable **today** as exactly one artifact — the
  free, read-only **O1 Yield-Drag Report** (it works, reconciles to the dollar,
  ships caveats in-band). The execution/keeper service that justifies an
  outcome fee is real but **Sepolia-only, 2/6 adapters, unaudited**, and the
  headline edge is **gross of the MEV/slippage that binds at institutional size**.
- **Token:** **NO token.** Pure securities/regulatory liability + distraction;
  nothing to decentralize, incentives already aligned, funds never pool. The
  architecture is *deliberately* built to avoid one — endorse that explicitly.

## What is genuinely strong (lead with these)

1. **Leakage-free on REAL data.** T1 is an online EWMA crossover on past-only
   block gaps; panel uses backward-only ffill / `merge_asof(direction="backward")`;
   NaN protocols dropped not imputed; the decision variable (per-protocol USDC
   supply APR) is real on-chain data correctly decoded for all six venues. Passes
   the López de Prado leakage checklist.
2. **Exemplary ML honesty.** The pre-registered NEGATIVE recomputes exactly
   (mean of the 5 committed OOS deltas = −5.969 bp, 0/5 windows); the Cox model
   actually executes (C-index 0.64–0.67, not a silent fallback); the earlier
   leaky +7.03 bp is explicitly retracted. A clean reproducible pre-registered
   negative is rare and differentiating.
3. **O1 Yield-Drag Report is a real, low-risk wedge.** Generate-only contract,
   SHA-256 panel provenance, 5 numeric quality gates that raise instead of
   emitting untrusted output, JSON audit sidecar reconciling to the dollar
   ($33,965 drag / 212.6 bp / 378 reb / $98.62 gas / panel SHA `d22df80bb554`).
4. **Correct, securities-aware no-token posture** (SMA-per-Safe, no pooling,
   non-custodial) — the right stance for a post-FTX treasury committee.

## Corrected picture (completeness-critic catch)

The 7-dimension audit walked **only the research repo** and concluded "the
production agent does not exist → grade D". **That is wrong.** The agent lives
in the companion **public** repo `github.com/SergeySolovyev/event-time-mcdm-agent`
(verified: PUBLIC, branch `master`, pushed 2026-05-28): real
`agent/mempool.py` (≈350-line Flashbots private-mempool client, dual-key auth,
`eth_sendPrivateTransaction`, not a stub), `agent/per_block_loop.py` with
stale-snapshot guards, `agent/observability.py`, `src/AIVault.sol` (ERC-4626),
`src/adapters/{AaveV3,CompoundV3}Adapter.sol`, `test/invariant/VaultInvariant.t.sol`.
**Calibrated truth:** the agent exists but is **Sepolia-testnet only, 2 of 6
adapters built, self-reported tests, unaudited** — and the two built adapters
(Aave, Compound) are **not** the edge-carrying venues (Euler 49% + Spark 29%
of time-share are unbuilt).

## Blocking findings (ranked)

### Academic (fix before any submission OR pitch — a DD team reads the paper)
1. **CRITICAL — `tab:wf-nxm` self-contradiction.** Caption + T3 row claim
   "T3 dominates T1 by +7 bp, p=0.015" with T3>T1 body numbers that exist in
   **no result file** (the cited CSV has T3 byte-identical to T1); the same
   section retracts that exact figure 140 lines later. Delete the T3-dominance
   row/caption claim. Fix in **both** paper dirs **and** purge the
   `submission_packet/` zips where the un-retracted +7.03 bp is still the live
   headline.
2. **CRITICAL — three magnitudes for the same negative.** Abstract "−88 bp",
   `tab:wf-t3-vs-t1` body "−88.3 bp", macro/intro/conclusion "−5.97 bp". Only
   −5.97 (0/5) reproduces from `t3_expanding_walkforward.csv`. Re-key all
   literals to −5.97.
3. **HIGH — non-reproducible N×M effect sizes.** Body prints +1.46…+2.81 pp
   ("5/6, p=0.026 Euler") tracing to a stale **N=2 partial** CSV; the canonical
   `walk_forward_NxM_contrasts.csv` gives **+2.69…+4.05 pp, all 6/6, p=0.0**.
   Re-source to canonical; add Holm/FDR across the 18 contrasts; floor bootstrap
   p (report p<1e-4, not p=0.0); disclose Euler flips non-significant on the
   3-protocol panel.
4. **NEW (critic) — T1 ≈ greedy at near-zero gas (+1.5 bp).** The +210 bp over
   passive is mostly "switching at all"; the gas-aware threshold's value over
   naive greedy only appears as gas rises — **run greedy across the gas sweep**
   to demonstrate it (experiment in progress: `greedy_gas_sensitivity.py`).
5. **NEW (critic) — undisclosed second ML negative.** Committed
   `forecaster/trained_models/metrics.json` (DA-BiGRU-CNN) shows val→test
   collapse (negative test R², dir-acc 0.35 < coin flip). Disclose or remove.

### Selling (independent, larger)
6. **HIGH — net-of-MEV/slippage edge at size is never measured, plausibly ≤0.**
   Replay deducts gas only. Two committed capacity models disagree by **sign and
   10× rebalance count**: `capacity_curve.csv` (38 reb, T1 net **−12.2%** at $5M,
   −163% at $50M) vs `capacity_curve_6way.csv` (383 reb, **+7.16%**). The paper
   cites only the optimistic one and mislabels its T3 rows as T1. Measure net of
   own-trade slippage + MEV at $1M–$25M against the real 49% Euler / 29% Spark
   time-share; cite both capacity models.
7. **HIGH — founder docs assert the agent as already-built in present tense**
   (`03_mvp_spec.md`: "Flashbots client… Solidity adapters… 128/128 tests").
   Reframe as: companion repo, Sepolia-only, 2/6 adapters, unaudited — or build
   the rest. Overclaiming corrodes the "honesty is the moat" position.
8. **MEDIUM — legal + customer validation.** No written legal opinion on the
   load-bearing "USDC-lending ≠ security / advisory-fee avoids RIA-MSB"
   assumption (the docs' own #1 [blocking] item); zero treasurer interviews;
   entity-name drift (Revert/Yieldbench/OYR). One security review + one legal
   opinion + a handful of real interviews gate procurement.

## Reproducibility hygiene (commit/clean before any pitch)
- Uncommitted `equity_walk_forward_6way` parquets → headline not reproducible
  from a clean checkout.
- Panel overwrites (`gas_price_gwei`→real, `fluid_lending_apr`→fToken) present
  in the shipped panel but **no committed script reproduces them**; `make data`
  yields fluid 4.72%, not the 6.18% the headline used.
- `institutional_metrics.csv` has a broken `b2_always_compound=0.0` row; Sharpe
  36 / inf Sortino price tail risk (depeg/exploit/oracle) at zero — repels a
  sophisticated allocator.

## Recommended sequence
1. **(running)** greedy-vs-T1 gas sweep — decides whether the gas-aware
   contribution survives.
2. Fix the two CRITICAL paper contradictions + re-source N×M to canonical CSV
   (verified values in hand). Rebuild PDF, verify 0 broken refs.
3. Measure net-of-MEV/slippage at $1M–$25M; reconcile the two capacity models.
4. Reframe founder-doc present-tense overclaims to the calibrated companion-repo
   truth.
5. Go-to-market: **API/MCP B2B, no token.** Lead with the free O1 report;
   gate the keeper service on a legal opinion + a security audit + the missing
   4 adapters.
