I have everything I need. The agent is real and well-architected: pure-function decision policies (`decision/`), 6 protocol readers, Flashbots private-tx client with dual-key auth, hand-rolled Prometheus + structured logging + fsync'd append-only audit trail, and an atomic-write history store. The vault project also has Solidity adapters (`AaveV3Adapter.sol`, `CompoundV3Adapter.sol`) and an EIP-712 signed-decision path I can reuse for the Safe module.

I now have enough grounding to write the MVP product spec. Returning markdown only.

---

# Event-Time MCDM Allocator — MVP Product Spec

**Product working name:** REVERT Allocate (non-custodial stablecoin yield router)
**Owner:** Sergei Solovev (solo founder + AI agents)
**Status:** MVP scoping
**Grounded in:** the existing per-block agent (`DeFi-Vega Project/agent/` + `predictive-mcdm-defi/decision/`) — bit-identical decision modules shared with the validated backtest.

---

## 0. The one-sentence product

> A **non-custodial** service that watches USDC supply rates across the 6 largest Ethereum-L1 lending protocols every block and tells your treasury (or, with your permission, executes through *your own* Safe) exactly when moving funds is worth more than the gas to move them — using a closed-form, no-trained-params rule that beat passive single-protocol holds by **+1.5 to +2.8 pp annualized** in a leakage-free 6-window walk-forward.

The product is the **gas-aware threshold rule (T1)**, not the ML. T1 is ~50 lines, zero trained parameters, and is the thing that actually beats the benchmark. The ML tier (T3 Cox hazard) is explicitly **out of scope for the MVP** because it added ~0 out-of-sample edge once leakage and a feature-wiring bug were fixed. Shipping the simple rule is the honest, defensible move.

---

## 1. The thinnest valuable slice (what a real treasury pays for)

**Recommendation: a NON-CUSTODIAL, ADVISORY-FIRST MVP.**

The product **computes** the optimal allocation and **signals** it. It never takes custody, never holds keys that can move treasury funds unilaterally, and in its first paid form executes only through a transaction the treasury's *own* multisig signers approve. This is the YC-canonical move here for three reasons:

1. **Regulatory dodge (default-alive).** Non-custodial advisory + signing-through-the-customer's-own-Safe avoids money-transmitter / custody licensing that would kill a solo founder. We touch information and unsigned calldata, never customer funds.
2. **Trust gating.** No DAO treasurer hands a brand-new solo product withdrawal rights on day one. "We compute, you sign" is the only thing that closes a first paying customer in weeks rather than after a year-long audit relationship.
3. **It's already 80% built.** The existing agent's `decide(state) -> Action` loop, Flashbots path, and audit trail are exactly the advisory engine. The only genuinely new surface is (a) reading a customer's *existing* position instead of a vault we control, and (b) emitting unsigned Safe calldata instead of self-signing.

**The thinnest sliver that someone pays for:** a treasury parks idle USDC in *one* protocol today (e.g. Aave V3) because rebalancing by hand isn't worth a person's time. They pay us a small monthly fee + performance share to (1) continuously tell them when a better protocol clears the gas hurdle, and (2) hand them a one-click, pre-built, MEV-protected rebalance transaction their Safe signers approve. We capture the +1.5–2.8 pp they're leaving on the table, minus our cut, with **zero custody risk to them**.

**ICP for the MVP (narrow it hard):** crypto-native funds, family offices, and small protocol/DAO treasuries holding **$1M–$25M idle USDC in a Safe{Wallet} multisig**, who already use Aave/Compound but rebalance manually or not at all. Position size matters: net edge at $1M is ~+1.75 bp/rebalance (gas-bounded), and **edge grows with size as gas amortizes** — so the qualified lead is "large idle stablecoin balance in a Safe," and institutional capital is the natural ICP.

**Explicitly NOT in the MVP:**
- Custody of any kind.
- The T3 ML tier (no edge yet — would be selling a feature that doesn't work).
- Non-stablecoin assets, L2s, leverage, borrowing.
- Real-gas wiring and MEV-cost deduction as *backtest* claims — the live product gets real gas and Flashbots for free, but we do not market backtest numbers as net-of-MEV.

---

## 2. Three product tiers

All three share the **same decision core** (`decision/` package, bit-identical to the backtest). The tiers differ only in *how far the signal travels toward execution* and *who holds the pen*.

### Tier A — Read-only Yield Radar (dashboard + alerts) — *non-custodial, zero-permission*
**What it is:** A hosted dashboard + alert feed. Connect a **read-only** Safe address (or paste it — no signature, no connection needed). We run the per-block loop against live mainnet, show the current best protocol, the live spread vs. where the treasury currently sits, and fire an alert (Telegram / email / webhook) the moment a switch *clears the gas hurdle for that specific position size*.
**What the customer does:** Reads. Rebalances manually in their own UI if they want. We are pure information.
**Permissions held:** none. We can never move funds; we only know a public address.
**Why it's valuable alone:** even with zero execution, "you'd earn +X bp right now by moving from Aave to Spark, and it's worth the gas at your size" is a standalone product a treasurer pays for. It's also the trust on-ramp to Tier B.
**Reuses:** `per_block_loop.py`, all 6 `protocols/*` readers, `decision/t1_threshold.py`, `observability.py` (the Prometheus/JSON/audit surfaces become the dashboard's data source), `state/history.py`.

### Tier B — One-Click Signed Rebalance (Safe module) — *non-custodial, customer signs*
**What it is:** Tier A **plus** the product pre-builds the exact rebalance transaction (withdraw from protocol A's adapter, supply to protocol B's adapter) and surfaces it as a **ready-to-sign Safe transaction proposal**. The treasury's existing multisig signers see it in Safe{Wallet}, review the human-readable rationale + simulated outcome, and approve with their own keys. Submission goes out via **Flashbots private mempool** to dodge sandwich attacks on the rebalance.
**What the customer does:** clicks "Approve" in Safe when an alert fires; their own M-of-N quorum signs.
**Permissions held:** none that can move funds unilaterally. The product proposes calldata; the customer's Safe quorum is the sole authority. Worst case if *we* are fully compromised: we propose a bad transaction that the customer's signers must still approve (and which a Safe Guard — see Tier C — would block).
**Why it's the MVP's commercial heart:** it removes the only real friction in Tier A (hand-building a correct multi-protocol rebalance tx) while keeping custody 100% with the customer. This is the tier the first paying customer lands on.
**Reuses:** everything in Tier A, plus the vault project's **Solidity adapters** (`AaveV3Adapter.sol`, `CompoundV3Adapter.sol` — extend to Spark/Morpho/Euler/Fluid), the **EIP-712 signed-decision** pattern already in the vault agent, and the Flashbots client (`mempool.py`, `scripts/flashbots_smoke.py`).

### Tier C — Automated Keeper with Guardrails — *non-custodial via Safe Module, bounded authority*
**What it is:** For customers who want hands-off operation, we deploy an audited **Safe Module** (a smart-contract allowlisted by the customer's Safe) that lets the agent execute *pre-authorized* rebalances **within hard on-chain guardrails** — and nothing else. A keyed keeper bot (the existing per-block agent, `dry_run=False`) submits via Flashbots; a **Safe Guard** contract enforces the invariants on-chain at execution time.
**Guardrails (enforced on-chain by the Module/Guard, not just in our code):**
- **Allowlist:** funds may only ever move *between the 6 approved lending-protocol adapters* — never to an external address. (No withdrawal path to anyone.)
- **Asset lock:** USDC only.
- **Rate-limit:** max N rebalances per day; per-tx and per-day notional caps.
- **Min-edge gate:** on-chain check that the claimed spread × dwell exceeds a stored gas multiple (mirrors T1's rule as a contract guard).
- **Kill switch:** customer can revoke the Module in one Safe transaction, instantly and unilaterally; our agent also has `record_kill_switch` + an auto-halt on anomaly.
**Permissions held:** a *bounded, revocable* execution right that can only shuffle USDC among 6 whitelisted lending pools. Still non-custodial in the meaningful sense: **we can never extract funds to an address we control**, and the customer revokes us at will.
**Why it's a later tier, not the MVP:** it requires a *real* smart-contract audit of the Module + Guard before any treasury enables it. We ship A and B in the 4–6 week window; C is the immediate next milestone, gated on audit. The agent code to drive it already exists (`per_block_loop.run()` live path).

| | Tier A — Radar | Tier B — One-Click | Tier C — Keeper |
|---|---|---|---|
| Custody | None | None | None (bounded module) |
| Who signs | Customer (manual) | Customer Safe quorum | Pre-authorized module + on-chain guard |
| Execution friction | Manual | One click | Hands-off |
| Funds-extraction risk to us | Zero | Zero | Zero (allowlist to 6 pools only) |
| New trust required | Minimal | Low | Medium (needs audit) |
| Ship in MVP window | ✅ | ✅ | ⛔ (audit-gated, next) |
| Pricing | Flat SaaS | SaaS + perf fee | SaaS + higher perf fee |

---

## 3. Concrete feature list for v0 (4–6 weeks, solo + AI)

Scope is **Tiers A and B, mainnet, USDC, Safe{Wallet}**. Tier C is explicitly deferred.

**Week 1–2 — Live read path + decision core hardening**
- [ ] Wire all 6 `protocols/*` readers (`aave, compound, spark, morpho, euler, fluid`) to a production mainnet RPC (Alchemy/your own node) and validate `read_at_block` against known on-chain values. (Backtest used The Graph + RPC; production reads on-chain directly.)
- [ ] **Real gas wiring** — replace the 25 gwei flat placeholder with live `eth_gas_price` / EIP-1559 base-fee + priority-fee estimation in the per-block loop. (This is the single most important fidelity fix; the backtest's flat 25 gwei is a known caveat and must not ship.)
- [ ] **Position-aware T1**: feed the customer's *actual* current protocol + position size into `BlockState.current_protocol` / `position_usd` so the gas-vs-yield threshold is computed for *their* dollars, not a generic notional.
- [ ] Confirm `decision/` import is bit-identical between live agent and backtest (the symlink `agent/decision -> predictive-mcdm-defi/decision` already enforces this — add a CI hash check).

**Week 2–3 — Tier A (Radar) shippable**
- [ ] Multi-tenant config: a customer = {Safe address, current protocol, position size, alert channels}. Stored append-only.
- [ ] Dashboard (read-only) surfacing live per-protocol APY, current best, live spread vs. customer's position, and "switch is/ isn't worth gas right now at your size." Data source = the existing Prometheus `/metrics` + JSONL audit feed; front-end is a thin read layer.
- [ ] Alert engine: fire on `Action.kind == "switch"` for that customer's `BlockState` (Telegram + email + generic webhook). Reuse the JSON-log event schema.
- [ ] `/healthz` + `/metrics` already exist (`observability.py`) — expose uptime/lag SLOs to ops.

**Week 3–5 — Tier B (One-Click) shippable**
- [ ] **Rebalance calldata builder**: turn an `Action(target_protocol=...)` into a concrete `withdraw(A) + supply(B)` call sequence. Extend the existing `AaveV3Adapter.sol` / `CompoundV3Adapter.sol` pattern to Spark/Morpho/Euler/Fluid (these are the missing adapters; the two existing ones are the template).
- [ ] **Safe Transaction Service integration**: propose the built transaction to the customer's Safe via the Safe SDK / Transaction Service API so it shows up in their Safe{Wallet} UI for signing. (Replaces `_build_rebalance_tx`'s current value=0 stub.)
- [ ] **Tenderly/`eth_call` simulation** of the proposed tx, surfaced in the proposal ("post-rebalance you supply X to B at Y% APY, gas ≈ Z").
- [ ] **Flashbots submission on approval**: once the Safe quorum signs, broadcast via the existing `FlashbotsMempool` (`dry_run=False`) so the rebalance isn't sandwiched. Dual-key auth (auth_key ≠ wallet_key) is already implemented and tested.
- [ ] Per-customer append-only audit trail of every proposal + outcome (`AuditTrail` already does daily-rotated, fsync'd JSONL — one dir per tenant).

**Week 5–6 — Productionization + first-customer polish**
- [ ] Auth / accounts (magic-link or wallet-SIWE login), single-operator admin.
- [ ] Reproducibility/credibility page: link the GitHub + HuggingFace dataset + the 6-window walk-forward result and **the honest caveats** (gas now real; MEV protected via Flashbots, not deducted in backtest). Selling the honesty *is* the differentiator to institutions.
- [ ] Billing: flat SaaS + opt-in performance share (computed from the audit trail's realized vs. passive-hold counterfactual).
- [ ] "Do things that don't scale": onboard the first 1–3 customers by hand, sit in their ops channel, build each rebalance proposal with them in the loop.
- [ ] Extend the agent's existing **128/128 test suite** to cover the calldata builder + Safe proposal path + real-gas threshold (target: keep the suite green and growing, not regressing).

**Customer-discovery track (parallel, from day 0):** the repo already has a `customer_discovery/` workspace — run 15–20 treasurer conversations to confirm the "manual rebalance is not worth my time, but I'd sign a one-click proposal" hypothesis before Tier B is fully built.

---

## 4. Architecture sketch (reusing what exists)

```
                          ┌─────────────────────────────────────────────┐
                          │  EXISTING, REUSED AS-IS (the moat)            │
                          │                                               │
  Ethereum L1  ──newHeads──▶  per_block_loop.PerBlockLoop                 │
   (Alchemy/own node)      │    • parallel reads, per-block deadline      │
        │                  │    • assembles BlockState (frozen dataclass) │
        │  6 readers       │                                               │
        ├─▶ protocols/aave │            │ BlockState                       │
        ├─▶ .../compound   │            ▼                                  │
        ├─▶ .../spark      │   decision/  (symlinked, bit-identical to     │
        ├─▶ .../morpho     │              backtest — CI hash-checked)      │
        ├─▶ .../euler      │     t1_threshold.T1ThresholdPolicy            │
        └─▶ .../fluid      │     decide(state) -> Action{hold|switch}      │
                           │     (gas-aware, 0 trained params)            │
                           │            │ Action                           │
                           │            ▼                                  │
                           │   observability.record_decision()            │
                           │     • JSON log  • Prometheus /metrics         │
                           │     • append-only fsync'd audit (per tenant)  │
                           │   state/history.HistoryStore (atomic parquet) │
                           └────────────┬──────────────────┬──────────────┘
                                        │                  │
            ┌───────────────────────────┘                  └───────────────┐
            ▼ (Tier A)                                                      ▼ (Tier B/C: execution)
   ┌──────────────────┐                                      ┌───────────────────────────────┐
   │  NEW: thin web    │                                      │  NEW: Rebalance Builder        │
   │  • multi-tenant   │                                      │   Action -> withdraw(A)+supply(B)│
   │    config store   │                                      │   via adapters (extend existing │
   │  • read-only dash │                                      │   AaveV3Adapter/CompoundV3 .sol │
   │    (reads /metrics │                                      │   to Spark/Morpho/Euler/Fluid)  │
   │    + audit feed)  │                                      └───────────────┬─────────────────┘
   │  • alert engine    │                                                      ▼
   │    (TG/email/hook) │                          ┌──────────────────────────────────────────┐
   └──────────────────┘                          Tier B │ Safe Tx Service (propose) ─▶ Customer │
                                                          │ Safe{Wallet} quorum signs (own keys)  │
                                                          └──────────────────┬───────────────────┘
                                                                             ▼
                                                          ┌──────────────────────────────────────┐
                                                  EXISTING │ mempool.FlashbotsMempool              │
                                                          │  eth_sendPrivateTransaction           │
                                                          │  dual-key (auth_key ≠ wallet_key)     │
                                                          └──────────────────┬───────────────────┘
                                                                             ▼
                            Tier C only (audit-gated):  Safe MODULE + Safe GUARD enforce on-chain:
                              allowlist (6 pools only) · USDC-only · rate/notional caps · min-edge
                              · one-tx revoke (kill switch). Keeper = same loop, dry_run=False.
```

**What is reused verbatim (≈80% of the engine):**
- `agent/per_block_loop.py` — the event-time loop, parallel reads, graceful NaN degradation, per-block deadline.
- `predictive-mcdm-defi/decision/` — `base.py` (BlockState/Action/DecisionPolicy), `t1_threshold.py` (**the product**). Symlinked into the agent so live and backtest run the *same bytes*.
- `agent/protocols/*` — 6 on-chain readers (the abstract `ProtocolReader.read_at_block` contract is already there).
- `agent/mempool.py` — Flashbots private-tx client with correct dual-key auth + `dry_run` safety default.
- `agent/observability.py` — structured JSON logs, hand-rolled Prometheus `/metrics` + `/healthz`, append-only fsync'd per-day audit trail (becomes per-tenant), `record_kill_switch`.
- `agent/state/history.py` — atomic-write rolling parquet (crash-safe).
- `agent/signer.py` + the vault's **EIP-712 signed-decision** path and `AaveV3Adapter.sol` / `CompoundV3Adapter.sol` — templates for the calldata builder and Tier-C module.

**What is genuinely new (the MVP build):**
1. Multi-tenant config + read-only dashboard + alert fan-out (Tier A).
2. `Action → Safe calldata` rebalance builder + 4 new protocol adapters (Spark/Morpho/Euler/Fluid) (Tier B).
3. Safe Transaction Service proposal integration + tx simulation (Tier B).
4. Real-gas estimation replacing the 25 gwei placeholder (cross-cutting fidelity fix).
5. (Deferred) Safe Module + Guard contracts (Tier C, audit-gated).

---

## 5. The three hardest technical risks + mitigations

### Risk 1 — Backtest fidelity gap becomes a *live* loss: flat 25 gwei gas + no MEV/slippage in the validated numbers
The +1.5–2.8 pp edge was measured with a **flat 25 gwei gas placeholder** and **no MEV/slippage deduction**. Live gas spikes (50–200+ gwei) and AMM-less but utilization-curve slippage on large supplies can erase the per-rebalance edge — most acutely at the bottom of the ICP ($1M, where net edge is already only ~+1.75 bp/rebalance and is gas-bounded).
**Mitigations:**
- **Real gas in the threshold, not just in reporting.** T1 already compares `expected_extra_yield_usd > gas_cost_usd`; feed it *live* base-fee + priority-fee so the rule self-throttles in high-gas regimes (it simply holds when a switch isn't worth it — the rule is gas-aware by construction). This converts the caveat into a feature.
- **Slippage-aware supply.** Model the rate impact of supplying the position into the target pool's utilization curve (the readers already fetch `utilization` and `tvl`); deduct expected post-supply rate, not the pre-supply quote, inside the decision.
- **Flashbots-only execution** (already built) eliminates the sandwich/front-run vector that the backtest didn't deduct — production is *structurally* MEV-protected even though the backtest didn't price it.
- **Size-gating in onboarding:** qualify leads at the size where gas amortizes; surface the live net-edge estimate in Tier A so customers self-select. Honest framing: "edge grows with your position size."
- **Shadow period:** run Tier B in propose-only/dry-run against real customers for 2–4 weeks, reconcile *realized* net edge from the audit trail vs. the passive-hold counterfactual before charging a performance fee.

### Risk 2 — Execution correctness across 6 heterogeneous protocols (a wrong rebalance tx loses real money)
Tier B/C must build a *correct* withdraw-from-A + supply-into-B across protocols with very different ABIs (Aave aTokens, Compound V3 Comet, Morpho Blue markets, Euler V2 vaults, Spark, Fluid). A malformed call can revert (wasting gas) or, worse, mis-route funds. Only 2 of 6 adapters (`AaveV3Adapter`, `CompoundV3Adapter`) exist today.
**Mitigations:**
- **Simulate every tx before proposing** (Tenderly / `eth_call` against pinned block) and *block the proposal* if the simulated post-state doesn't match the expected (funds in target adapter, dust within tolerance). Surface the simulation to the signer.
- **Non-custodial structure caps blast radius:** in Tier B the customer's Safe quorum is the last line — a bad proposal still requires M-of-N human approval. In Tier C the **Safe Guard allowlist** makes a funds-to-attacker tx *impossible on-chain* (movement restricted to the 6 pool adapters), so the worst case is a wasteful-but-reversible reshuffle, never theft.
- **Reuse the audited adapter pattern** from the vault (`src/adapters/*.sol`, 67 passing Foundry tests) rather than hand-rolling calldata; extend the existing test harness to each new protocol with fork tests against mainnet state.
- **Stage the protocol rollout:** ship Tier B with only the 2 existing adapters (Aave↔Compound) live; add Spark/Morpho/Euler/Fluid one at a time behind per-protocol feature flags as each gets a fork-test suite. The backtest's biggest contrasts are capturable on a subset.

### Risk 3 — Key & custody-boundary integrity (the thing that, if breached, ends the company)
The whole regulatory and trust thesis is "we never control funds." A breach of that boundary — a leaked keeper `wallet_key`, an over-broad Safe Module, or a compromised proposer that tricks signers — is existential, not a bug.
**Mitigations:**
- **Tier A holds no keys at all** (read-only addresses) — the on-ramp tier is unbreachable by construction.
- **Tier B: the product never holds a key that can move customer funds.** It proposes; the customer's own multisig signs. Our Flashbots `wallet_key` (already separated from `auth_key` in `mempool.py`) signs only *gas-payer* / relay-identity transactions, never a fund-moving tx from the customer's Safe.
- **Tier C bounded authority on-chain:** the Safe Module is allowlisted to *only* call the 6 lending adapters with USDC, under notional/rate caps, with a **one-transaction customer revoke** (kill switch). Even a fully-compromised keeper key cannot send funds to an attacker address — the Guard reverts. This must be **third-party audited before any customer enables it** (the repo's Trail-of-Bits-style audit-prep tooling is already on hand).
- **Operational key hygiene:** keeper keys in a KMS/HSM or hardware-backed signer, never in env files on the box; `dry_run=True` remains the default (as in `mempool.py`) so live broadcast is an explicit, logged opt-in; every signed action is written to the append-only fsync'd audit trail and is independently verifiable by the customer.
- **Anomaly auto-halt:** the existing `record_kill_switch` + metrics (block-lag, gas spike, repeated reverts) trip an automatic pause; resuming requires manual operator action.

---

**Bottom line:** the MVP is Tiers A + B — a non-custodial Yield Radar plus one-click, Flashbots-protected, Safe-signed rebalances — built almost entirely on the existing per-block agent, decision core, Flashbots client, and observability stack. The genuinely new work is multi-tenant glue, the `Action→Safe calldata` builder with 4 additional adapters, real-gas wiring, and Safe Transaction Service integration. Custody never moves to us; that is both the regulatory survival strategy and the reason a treasury says yes in week one. Tier C (bounded keeper) is the immediate, audit-gated next step.

---

*Relevant existing files (absolute paths):*
- `D:\DeFi\DeFi-Vega Project\agent\per_block_loop.py` — event-time loop (reused as-is)
- `D:\DeFi\predictive-mcdm-defi\decision\t1_threshold.py` — the product (gas-aware threshold, 0 trained params)
- `D:\DeFi\predictive-mcdm-defi\decision\base.py` — `BlockState` / `Action` / `DecisionPolicy` contract
- `D:\DeFi\DeFi-Vega Project\agent\mempool.py` — Flashbots private-tx client (dual-key auth, dry-run default)
- `D:\DeFi\DeFi-Vega Project\agent\observability.py` — JSON logs + Prometheus `/metrics` + append-only audit trail
- `D:\DeFi\DeFi-Vega Project\agent\state\history.py` — atomic crash-safe parquet history
- `D:\DeFi\DeFi-Vega Project\agent\protocols\` — 6 protocol readers (`aave, compound, spark, morpho, euler, fluid`)
- `D:\DeFi\DeFi-Vega Project\src\adapters\` — `AaveV3Adapter.sol` / `CompoundV3Adapter.sol` (template for Safe-module calldata + new adapters)