I now have the ground truth, and it materially changes the review. The single most important finding: there is a **discrepancy between the headline claims and the actual data state** that a YC partner must flag, because it's the difference between "binding finding" and "aspirational."

Key verified facts:
1. **T3≡T1 is true at source level** — `t3_hazard.py:199` and `t1_threshold.py:95` are byte-identical (`yield_gain > gas_cost`). The honesty is real and code-backed.
2. **The "6-protocol +1.5–2.8pp" headline is NOT what the backtest actually ran on.** `PROJECT_OVERVIEW.md` §10 (the "Current data state" section, the most operationally honest part) says the panel that was *actually built* has **3 protocols (Aave, Morpho, Euler) ≈ 47% TVL**; Spark/Compound/Fluid/DSR fetchers returned **0 events**. The §0 header and the walk-forward table claim 6-way, but §10 contradicts it: "Submission proceeds as a 3-way." The 6-protocol readers exist in the agent (live code), but the *historical panel feeding the bootstrap* is 3-way. **The product context's "6 protocols" headline is partly aspirational.**
3. **Only 2 of 6 Solidity adapters exist** (Aave, Compound) — confirms execution is far from the 6-protocol claim.
4. **128 agent test functions** confirmed (the "128/128" claim is real; the overview's older "120" is stale).
5. **Compound — a named core protocol — has 0 historical data** and is also one of only 2 protocols with a built Solidity adapter. The protocol the product can *execute* on is the protocol it has *no backtest for*.

This is the crux. The package is internally inconsistent on its single most important number. I have enough to write the review.

I'll write the final review now.

---

# YC Partner Review — Event-Time MCDM Allocator ("Revert")

*Brutally honest. I read the code, not just the deck. The package is genuinely strong on craft and intellectual honesty — rare and valuable. But there is one inconsistency at the center of it that has to be fixed before you talk to a single user, and the whole package is one layer of polish on top of zero customer contact. Below is what I'd say across the table.*

---

## 0. The thing I have to say first (it reframes everything)

**Your headline claim and your actual backtest disagree, and you wrote both.** Every artifact leads with *"6 protocols, +1.5–2.8pp, paired-bootstrap p<1e-4."* But your own `PROJECT_OVERVIEW.md` §10 ("Current data state") says the panel that was actually built and bootstrapped has **3 protocols — Aave, Morpho, Euler (~47% TVL)** — and that **Spark, Compound, Fluid, and the DSR feed all returned 0 events.** The §0 header of the same doc claims "full 6-protocol design universe... switch among all six on every block." Those cannot both be true. The honest read, from your own most-operational section, is: **the binding finding is 3-way, and "6-way" is the design target, not the measured result.**

This matters more than any other point in this review for three reasons:

1. **Compound is the worst-case instance of it.** Compound V3 is (a) one of your two named anchor protocols, (b) one of only **two of six** Solidity adapters that actually exist (`AaveV3Adapter.sol`, `CompoundV3Adapter.sol`), and (c) has **zero historical panel data** per §10. So the protocol you are closest to being able to *execute* on is a protocol you have *no backtest for*. A quant doing diligence will find this in ten minutes and you lose the room — including on the claims that *are* real.
2. **Your moat artifact's credibility rests on "we don't overclaim."** That is your single best asset (more below). Shipping a 6-protocol headline on a 3-protocol backtest *is* the overclaim, and it's the one that detonates the trust you've spent the whole package building.
3. **The good news: the honest version is still a fundable finding.** "A 50-line gas-aware rule beats passive holds of Aave, Morpho, and Euler by +1.46 to +2.81pp, leakage-free, 6-window walk-forward, with the simplest contrast (vs Euler) failing 1/6 windows" is a *real, defensible, interesting* result. You do not need the inflated version. Drop to what you can prove and you're stronger, not weaker.

**Founder action before anything else: reconcile this number across all six artifacts.** Pick one true claim — I'd use *"3-protocol live-validated (+1.46–2.81pp), 6-protocol architected"* — and propagate it everywhere. This is a 1-hour edit that determines whether the rest of the package reads as rigorous or as marketing.

---

## 1. The 5 biggest risks / gaps across the package

### Risk 1 — The package has zero customer contact, and every document silently assumes the demand it's supposed to test.
This is the YC-canonical failure mode. You have a market map, a beautifully-reasoned ICP doc, an MVP spec, a risk register, a GTM plan, and a moat analysis — **six artifacts of strategy, zero artifacts of "I talked to a treasurer and here's what they said."** The ICP doc even contains a 12-question interview script; there's no evidence it's been run once. Everything downstream (pricing, tiering, the "they respect the honest caveats" assumption, the "manual rebalance isn't worth their time" JTBD) is a *hypothesis you wrote down*, not a finding. The market doc's own SOM math quietly admits the problem: fees attach to *outperformance over passive* (+1.5–2.8pp), not AUM, so at a 10–15% performance fee on a $5M sleeve you're earning ~$7.5k–$21k/yr per client. **The entire revenue thesis depends on landing a few very large mandates, and you have not validated that even one exists.**

### Risk 2 — The economics may be net-negative at the bottom of your own stated ICP, and you haven't measured the real number.
You are admirably upfront that backtest gas is a **flat 25 gwei placeholder** and MEV/slippage is not deducted. But trace the consequences: net edge at $1M is ~+1.75bp/rebalance *gas-bounded*, and your MVP/ICP docs target *$1M–$25M*. At the low end, in a 60–120 gwei regime, with un-modeled supply-curve slippage on a multi-million-dollar reallocation into a single pool, **the real net edge could be at or below zero for your smaller customers.** You've correctly identified this as a "show-me" — but until real gas + slippage are wired into the *replay engine* (not just live reporting), your binding finding's *net-of-cost* version doesn't exist. The +1.5–2.8pp is a *gross* number wearing a net number's clothes. This is the gap between "interesting backtest" and "product that makes money."

### Risk 3 — Execution reality is ~33% of the claimed surface, and the hard 67% is unbuilt and unaudited.
Six protocol *readers* exist (good — verified). But only **two of six Solidity adapters** exist, and the four missing ones (Spark, Morpho Blue, Euler V2, Fluid) are the *heterogeneous, high-surface-area* integrations — Morpho Blue's per-market structure, Euler V2 vaults, Fluid's resolver. Your MVP doc honestly stages this ("ship Aave↔Compound first"), but the package elsewhere markets the full six as if shippable. Compounding this: **none of the execution path is audited**, and your own risk register correctly marks the Safe-module audit as a `[blocking]` gate for Tier C. So the commercially-interesting product (hands-off keeper) is gated on an audit you haven't scoped or funded, and the demoable product (Tier B one-click) can only honestly span the two protocols you have adapters for — which, again, includes the one with no backtest (Compound) and excludes most of the ones with backtests (Morpho, Euler).

### Risk 4 — "Solo + AI-first" is sold as a pure asset; for the institutional ICP it is the adoption ceiling.
Your moat doc is honest about this in one paragraph, then the GTM and YC artifacts revert to celebrating it. Be straight: a DAO or fund treasury committee evaluating "who do I let propose transactions against my $10M Safe" sees **bus-factor-1, no SOC2, no insurance, no 24/7 human on-call, no balance sheet, no prior track record.** The non-custodial Safe-module architecture genuinely caps the *blast radius* (you can't steal funds — verified as the design intent), which is your best counter. But "can't steal" ≠ "won't propose a wrong tx that the committee rubber-stamps," and it doesn't answer "who answers the phone at 3am when a venue is being exploited." The speed/cost advantages of solo+AI are real *below* the institutional-trust line and a liability *above* it — and your ICP is explicitly *above* it.

### Risk 5 — The legal posture is a well-structured set of open questions, not a cleared path, and the whole company is bet on its answer.
The risk register is the best-reasoned artifact in the package and correctly tags R1/R2/R20 as `[LAWYER]`-blocking. But strip the structure away and the situation is: **you have not retained a lawyer, and your default-alive thesis depends entirely on a securities/MSB characterization no lawyer has blessed.** The single load-bearing assumption — "USDC supply positions aren't securities, so the Advisers Act doesn't bite" — is flagged by you as "the single most lawyer-dependent assumption in the doc," and it's unwritten. If it's wrong, advisory-with-a-performance-fee becomes RIA territory and the capital-light solo model is dead. You've done the right *analysis*; you have not *de-risked* anything, because the only thing that de-risks it is a written opinion you don't have.

---

## 2. The single riskiest assumption to validate first

> **That a specific, named, reachable treasury with a large idle USDC balance will actually pay for better-than-passive lending yield delivered as a non-custodial signal/proposal — given that the honest, real (net-of-gas, net-of-slippage) edge is small at anything below institutional size.**

Everything else is downstream of this. Not the tech (it works and you've over-built it). Not the regulatory path (real, but moot if no one wants the product). Not the moat (you can't defend revenue you don't have). The riskiest assumption is the conjunction of **demand × willingness-to-pay × at a size where the edge survives real costs.** Your own analysis quietly concedes all three legs are unproven: demand is asserted, WTP is "performance fee on a thin outperformance," and the size-where-it-works ($25M+ single-decision-maker idle USDC) is exactly the segment your risk register admits a solo unknown founder "will struggle to clear the trust bar cold."

**How to test it cheaply, this week, without building anything new:** run the read-only "Yield-Drag Report" — your Tier A — by hand for **10 named treasuries**, using your *existing* backtest envelope on *their public on-chain balance*. The report says: "Over the last 6 months, your idle USDC in [Aave] left $X on the table vs event-time routing across the protocols we can prove, net of realistic gas at your size." Then watch two things: **(a) do they reply, and (b) does anyone say "how do I get this" vs "interesting, thanks."** That single signal — measured on real addresses, with the honest 3-protocol number — validates or kills the core assumption for ~$0 and two weeks of your time. It is also the literal first step of your own GTM plan; you've just never run it.

---

## 3. Prioritized 2-week action list

**The theme: stop polishing artifacts, reconcile the one broken number, and get the honest report in front of 10 real humans. Do not build new product surface.**

**Days 1–2 — Make the package internally honest (founder, solo, ~1 day).**
1. Reconcile the protocol-count claim across all six artifacts to the *verifiable* version: 3-protocol live-validated (Aave, Morpho, Euler; +1.46–2.81pp), 6-protocol architected. Every "6 protocols, +1.5–2.8pp" headline gets corrected or explicitly labeled "design target."
2. Add one line to every external-facing artifact: "Net-of-real-gas, net-of-slippage edge not yet measured; backtest uses 25 gwei flat, gross of MEV." You already say this internally — surface it consistently so a diligence reader finds it from *you*, not on their own.
3. Fix the stale `120` vs real `128` test count (minor, but it's the kind of thing that erodes trust when found).

**Days 2–4 — Weaponize the honest proof into a cold-open artifact (founder + AI agents).**
4. Build the read-only **Yield-Drag Report** generator: input = a public Safe/wallet address; output = a 1-page, reproducible "here's what passive cost you vs. what we can prove" on the 3 protocols you have real data for, with a *real-gas* counterfactual (pull historical base-fee — this also starts closing Risk 2 with zero new infra). Reuse `per_block_loop` readers + the replay engine. This is the only thing worth *building* in two weeks.
5. Hand-curate a list of **20 named treasury decision-makers** (not orgs — people) from the Aave/Morpho/Euler/Spark governance forums and the treasury-management shop client lists. Names, roles, why-them.

**Days 5–10 — Talk to users (founder; this is the whole point).**
6. Run the Yield-Drag Report unprompted for the **top 10**, and send it cold with one question, not a pitch: *"Did this match your read of your idle-yield drag? Worth a 15-min call?"*
7. Book and run **≥5 interviews** using your existing 12-question script. **Ask about past behavior** (what they did with idle USDC last quarter, who looked at the number, whether anyone complained), not hypotheticals. Specifically pressure-test: (a) is idle-yield drag a *felt* pain or an invisible one; (b) would they sign a non-custodial proposal; (c) what's the minimum balance where they'd bother; (d) what would they need to trust a solo operator.
8. Log every answer verbatim in a `customer_discovery/` doc. The deliverable for week 2 is **interview notes, not code.**

**Days 8–12 — Start the two blocking gates that need a human + money (parallel).**
9. Send a tight scoping email to **2–3 crypto-fluent securities lawyers** for a fixed-fee written opinion on R1/R20 (adviser status + USDC-lending-as-security) for a non-custodial, advisory, performance-fee posture. You need a *quote and a path*, not the full opinion, in two weeks.
10. Wire **real gas into the replay engine** (not just live reporting) and re-run the 3-protocol walk-forward. Produce the *first honest net-of-gas edge number*. This is the number your whole business case actually rests on, and you've never computed it.

**Days 12–14 — Synthesize and decide.**
11. Write a one-pager: did ≥2 of 10 treasuries lean in? Does the net-of-gas edge survive at the size they'd actually commit? Is there a lawyer path under $X? **Go/no-go on building Tier B**, gated on those three answers — not on more strategy docs.

**Explicitly NOT in the two weeks:** the 4 missing Solidity adapters, the Safe module, Tier C, multi-tenant infra, the YC application polish, any "6-protocol" work. None of it matters until the report lands with a real human.

---

## 4. FOUNDER ACTIONS REQUIRED (only the human can do these)

These are the things no agent, and no amount of code, can do for you. Ranked by how badly they block.

**Capital / spend you must authorize:**
- **Retain a crypto-securities lawyer** for a fixed-fee written opinion on (1) RIA/adviser status of a non-custodial advisory product with a performance fee, and (2) whether USDC lending positions are securities in your launch jurisdiction. This is the R1/R20 blocking gate. *Budget ~$5–15k; it gates the entire default-alive thesis.* Nothing ships to a paying client without it.
- **Decide your launch jurisdiction and entity** (US-geofenced-ex-NY vs offshore vs wait). This is a capital + legal decision only you can make; it changes the lawyer you hire.
- **Fund (later, post-validation) a smart-contract audit** of the Safe module + 4 new adapters before Tier B/C touches real money. *Budget likely $30k+.* Don't spend it until users say yes — but know it's coming and scope it now.
- **Pay for production infra keys**: a real archive RPC (Alchemy/own node — your CLAUDE.md shows you've been fighting free-tier 100-call caps), Flashbots relay access, monitoring. Small but real, and the free tiers won't carry production.

**Identity / keys / accounts only you control:**
- **Provide the `THE_GRAPH_API_KEY` and a paid `ETHEREUM_RPC_URL`** and re-run the 4 failed fetchers (Spark, Compound, Fluid, DSR). *Until you do this, your "6-protocol" claim has no data behind it and Compound — a core protocol — has zero backtest.* This is the single highest-leverage hour of your time for closing the credibility gap.
- **Set up the company's public identity**: a real name (pick one — "Revert"/"Yieldbench"/"OYR" are scattered across the artifacts; the inconsistency itself reads as pre-product), domain, a one-page site with the *honest* numbers, and a professional point of contact. Treasuries Google you before replying.
- **Hardware/KMS for the keeper signer** (Tier C) — provisioning a hardware-backed signer is a human, physical-custody-of-secrets task.

**Conversations only you can have (the most important category):**
- **Talk to 5+ real treasurers.** No agent can do this. You — a credible HSE/WQU finance-engineering researcher — are the asset that gets the meeting. Use the warm-intro graph; you have the academic credibility to open doors a typical solo founder can't.
- **Get warm intros** from any founder/angel/researcher in your network into DAO treasury working groups and crypto-fund treasury desks. Cold DMs convert at a fraction of warm intros for this trust-gated buyer.
- **Find your first design partner and commit to over-serving them by hand.** This is a relationship only the founder can carry.
- **Decide your honesty stance publicly.** Your reputational edge (the "When Retrieval Hurts" / "GRU loses to LightGBM, published anyway" track record in your prior work) is real and rare. Decide to publish the *3-protocol, net-of-gas, ML-adds-nothing* result openly. That's a founder values-call, and it's also your best distribution.

**Strategic decisions only you can make:**
- **Resolve solo-founder vs. the institutional ICP.** Either (a) accept a longer trust-building runway and target the smaller/faster crypto-native funds first (where solo+AI is an asset), or (b) recruit a credible co-signer/advisor with an institutional name to clear the trust bar for protocol treasuries. You can't have institutional capital *and* pretend bus-factor-1 isn't a blocker. Pick.
- **Decide whether to pursue YC now or after the 10 conversations.** My honest counsel: the application is strong on tech and honesty, *fatally thin on traction and demand evidence*. Run the two-week validation first; an application that says "I sent honest yield-drag reports to 10 treasuries, 3 want to pilot, here's the net-of-gas edge" is in a completely different league than the current "tech is done, GTM is at zero by design."

---

## Bottom line

You have built, solo, something most seed-stage teams can't: a rigorous, leakage-free, code-honest research result with a production-grade agent behind it, and a moat analysis brave enough to say "the algorithm isn't the moat and the ML adds nothing." That intellectual honesty is your single most valuable, least-copyable asset — **so protect it by not letting your own headline (6 protocols / +1.5–2.8pp) outrun your own data (3 protocols, gross-of-cost).** Fix that one number, compute the first real net-of-gas edge, and put the honest report in front of ten named treasurers. If two of them lean in at a size where the edge survives, you have a company. If none do, you've saved yourself a year of building adapters and audits for a product nobody asked for — which is exactly what the next two weeks are for.