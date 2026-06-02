I'll ground this in the product context provided — no invented results. Let me produce the GTM, positioning, pitch, and YC application package.

---

# Event-Time MCDM Allocation — GTM, Positioning, Pitch & YC Application

> Working name suggestion: **Yieldbench** (or **Optimal Yield Router / OYR**). Pick one and use consistently. Below I use **Yieldbench**.

---

## 1. One-Line Positioning + the "Make Something People Want" Wedge

**One-liner (external, buyer-facing):**
> *Yieldbench is non-custodial yield routing for stablecoin treasuries — it watches the 6 largest Ethereum lending markets every block and moves your USDC to the best risk-adjusted rate, beating any single-protocol park by 1.5–2.8 points a year. You keep your keys.*

**One-liner (investor-facing):**
> *We're the BlackRock-grade allocation layer for the $50B+ of idle stablecoins sitting in DeFi lending — a closed-form, leakage-free routing rule that institutional treasuries can run without trusting us with custody.*

**The wedge ("make something people want"):**
The painful, unglamorous truth for any DAO/fund treasurer: **idle USDC parked in one protocol (usually Aave, by default) is leaving 150–280 bps/yr on the table**, and nobody has time to babysit per-block rate divergence across 6 venues. They *know* this. They don't act because (a) manual re-allocation is operationally annoying and gas-expensive at the wrong size, and (b) every "yield optimizer" they've seen either took custody (Celsius/BlockFi trauma) or chased mercenary farm APYs that blew up.

So the wedge is the **narrowest, most defensible slice**: a **read-only "you're leaving money on the table" report** for one treasury, on real on-chain balances, with a provable backtest behind it — then graduate to non-custodial execution they authorize. We are not a vault. We are not a custodian. We are a *router with a proof*.

**Why this specific thing is wanted (not just useful):**
- It's **measurable and adversarial-proof**: +1.5–2.8 pp annualized, walk-forward, paired-bootstrap p<1e-4 on 5/6 contrasts. A treasurer can show this to their risk committee.
- It's **boring on purpose**: only the 6 bluest-chip lending markets (~67% of ~$54B TVL), only stablecoins, no leverage, no exotic farms. "Better-than-passive, not degen."
- It's **honest about its ceiling**: the threshold rule (T1) *is* the product. We don't oversell an ML black box that adds ~0 OOS. Treasurers trust vendors who tell them where the alpha *isn't*.

---

## 2. Launch Sequence — Do Things That Don't Scale

The whole early game is **3–5 hand-run design-partner treasuries**, fully manual, fully white-glove. No self-serve product until the motion is proven.

**Phase 0 — Weaponize the proof (Weeks 0–2).**
- Turn the Institutional Dossier + reproducibility envelope into a **2-page "Treasury Yield Audit"** template: "Here is your current USDC allocation, here is what event-time routing would have earned over the last 6 windows, here is the net-of-gas delta at your size."
- Build a **read-only scanner**: point it at a treasury's public address, pull current balances across the 6 protocols, compute the live spread and the historical counterfactual. This is the cold-open artifact.

**Phase 1 — Hand-run allocations for 3–5 design partners (Weeks 2–12).**
- Recruit 3–5 treasuries (see ICP below). Target ones with **$2M–$25M idle USDC** — large enough that gas amortizes and the edge is real, small enough that the founder can hand-hold.
- **You personally run the allocation loop.** The agent already exists (per-block loop, Flashbots path, audit log). But the *decision to move* is co-signed with the partner each time at first — you send a signed transaction proposal, they approve from their own multisig/Safe. **Non-custodial from day one.** You never hold keys.
- Cadence: weekly "here's what we'd move and why" call + a shared dashboard (Prometheus already there). Log every rebalance to the append-only audit so the partner has a clean record.
- **Goal of this phase is not revenue — it's evidence and trust.** You want: (1) live, real-money track record (even on small size); (2) 3–5 reference customers who'll do a quote; (3) the precise list of operational frictions (Safe module UX, gas timing, accounting/export needs) that the self-serve product must kill.

**Phase 2 — Productize the Safe module (Weeks 8–20, overlapping).**
- Replace the co-signing ceremony with a **Gnosis Safe / Safe{Wallet} module** that the treasury installs once, scoped to *only* "move USDC among these 6 whitelisted lending pools, never withdraw to an external address." This is the non-custodial unlock: they delegate *routing authority*, not *custody*. Revocable any block.
- Wire **real gas** (kill the 25 gwei placeholder) and **Flashbots private mempool** for production execution — both are explicitly required before charging on net edge.

**Phase 3 — Repeatable onboarding (Weeks 16–26).**
- Standardize the audit → trial → Safe-module → monthly-report funnel so a new treasury can go live in <2 weeks without the founder on every call.

**Do-things-that-don't-scale principles applied:** founder runs ops manually; recruit customers one-by-one via warm intros; over-serve the first 5 absurdly; treat each rebalance as a chance to learn the friction; don't build self-serve until you've hand-delivered the value 5 times.

---

## 3. Distribution Channels (Crypto-Native Buyers)

Buyers here don't come from Google Ads. They come from **trust signals inside the crypto-native social graph.** Ranked by leverage for a solo founder:

1. **Warm intros to DAO treasury / governance contributors.** The highest-intent path. Names to work: large DAO treasuries with big stablecoin reserves, protocol treasuries, and the delegate/working-group people who run them. Get introduced by a mutual founder/angel.
2. **DAO governance forums (Commonwealth / Discourse).** Post a *neutral, data-rich* "Treasury yield analysis for [DAO]" thread — not a pitch, a public good. This is how credibility compounds in DAO-land. One good forum post → inbound from 3 other treasuries.
3. **Crypto-native fund / family-office networks.** Crypto VC scout networks, angel syndicates, "crypto treasurer" Telegram/Signal groups. These are the institutional-capital ICP where the edge grows with size.
4. **DeFi research credibility (your existing moat).** You already have figshare preprints + a GitHub/HuggingFace reproducibility envelope. Publish the methodology (leakage-free walk-forward, paired-bootstrap) as a research note. Researchers-who-ship are *highly* trusted by crypto-native allocators. Cross-post to relevant DeFi research collectives.
5. **Twitter/X "build in public" + the honest-caveats angle.** The differentiated content: *"I built an ML tier and it added ~zero over a 50-line threshold rule. Here's why the simple thing wins."* That kind of intellectually honest post travels in DeFi-quant circles and sorts for exactly your buyer.
6. **Safe ecosystem distribution.** Once the Safe module exists, the Safe app marketplace / module directory is a native discovery surface for exactly the multisig-treasury audience.
7. **Targeted events:** DeFi-focused side events at the big conferences (devconnect-style), treasury-management roundtables. One founder, a laptop, the live scanner, and a "let me run your address right now" demo.

**Anti-channels (don't bother early):** paid ads, generic crypto media PR, retail/influencer reach. Wrong intent, wrong trust model.

---

## 4. Pricing — Options + Recommendation

Three viable models:

| Model | Mechanics | Pros | Cons / Risk |
|---|---|---|---|
| **A. Performance fee** | X% of *excess* yield over a passive benchmark (e.g., over best-single-protocol or over Aave-hold) | Perfectly aligned; only paid when you beat passive; easy "we only win if you win" pitch | Hard to compute trustlessly; "fee on excess" needs an agreed benchmark; lumpy revenue; potential securities/advisory optics if mis-framed |
| **B. Flat AUM bps** | Annualized bps on routed balance (e.g., 5–15 bps/yr), streamed | Predictable revenue; standard asset-mgmt mental model; simple | Charges even in flat-spread regimes; at $1M net edge is ~+1.75bp/rebalance gas-bounded, so high bps can eat the thin edge at small size |
| **C. Flat SaaS** | Fixed $/month per treasury for the routing software + audit + reporting | Clean, non-custodial, *software not advice* (best regulatory posture); recurring; decoupled from performance disputes | Caps upside; doesn't capture the "edge grows with size" economics; feels like a tool not a partner |

**Recommendation: hybrid, staged.**

- **Design-partner phase:** **free** (you're buying evidence and references, not revenue).
- **Launch pricing:** **Performance fee on excess return over an agreed passive benchmark, with a low flat-SaaS floor.** E.g., *"10–20% of yield above your benchmark hold, or $[X]/mo, whichever is greater."*
  - *Why perf-fee as the headline:* it's the most honest expression of the wedge ("we only earn when we beat what you'd have done anyway"), and it's the one number a risk committee can't argue with. It also **scales with position size exactly the way the economics do** — institutional capital pays more because they capture more amortized edge.
  - *Why the SaaS floor:* covers you in flat-spread regimes and frames the relationship as **software, not custody/advice** — critical for the no-money-transmitter-license posture. Lead the contract with "software license + performance bonus," not "asset management fee."
- **Benchmark must be pre-agreed and verifiable** (e.g., "blended best-single-protocol hold" computed from the same on-chain data), and **net of gas/MEV** so you're charging on the *real* delivered edge — not the placeholder-gas backtest number. Be explicit with partners that production net edge is gas-bounded and grows with size.

**Regulatory framing note (respect the constraint):** keep it **non-custodial software + reporting**, not discretionary asset management. The Safe module means the *customer executes*; you provide signed *proposals* and the routing engine. This is the line that keeps you shippable without a money-transmitter/custody license. Get a crypto-fluent lawyer to bless the perf-fee framing before charging.

---

## 5. YC Application — Draft Answers (Solo, AI-First Founder)

> Edit to your voice; YC rewards concrete, concise, founder-obsessed answers. Keep numbers honest — the caveats are a feature.

**What does your company do? (≤50 words)**
> Yieldbench is non-custodial yield routing for stablecoin treasuries. We watch the 6 largest Ethereum lending markets every block and automatically move a treasury's USDC to the best risk-adjusted rate — beating any single-protocol park by 1.5–2.8 points a year. Customers keep custody; we never hold keys.

**Why did you pick this idea to work on? What's your unfair advantage?**
> I'm a finance-engineering researcher (WorldQuant MSc Fin Eng; HSE) who builds reproducible market systems. While studying DeFi lending I found that idle stablecoins lose 150–280 bps/yr by sitting in one protocol, and that a *simple, closed-form, leakage-free* threshold rule captures most of that gap — I have the walk-forward proof (Nov 2024–Apr 2026, paired-bootstrap p<1e-4 on 5/6 contrasts) and a production agent that shares bit-identical decision code with the backtest. My unfair advantage is twofold: (1) the rigor — I caught my own leakage and a feature-wiring bug and can prove the edge is real and not data-mined; (2) AI-first execution — one human plus AI agents already shipped a 128/128-test agent, Flashbots path, observability, and an institutional dossier. I can do the work of a team.

**Why now?**
> Three things converged: (1) DeFi lending consolidated into a handful of credible, audited blue-chip markets (~$54B TVL across these 6), so cross-protocol routing is finally a *safe* operation, not a degen one; (2) post-FTX/Celsius, treasuries demand **non-custodial** solutions — the Safe-module pattern now lets us deliver routing without custody, which wasn't socially acceptable before; (3) AI agents make it possible for a solo founder to run institutional-grade, per-block operations that previously needed a quant desk.

**Who are your competitors, and what do you understand that they don't?**
> Competitors fall into three buckets: (a) **custodial yield optimizers / aggregators** (Yearn-style vaults, exchange "earn" products) — they take custody or pool funds, which is exactly the trauma treasuries are fleeing; (b) **manual treasury management** (a contributor babysitting Aave) — high opex, leaves money on the table; (c) **point-in-time dashboards** that show rates but don't act. What I understand that they don't: the edge is a **per-block, event-time** phenomenon and it's **gas-bounded** — it's small at retail size and *grows with position size as gas amortizes*, which means the right customer is an institutional stablecoin treasury, and the right product is **non-custodial routing with a provable, honest backtest**, not a pooled vault chasing the highest headline APY. I also openly tell customers where the alpha *isn't* (the ML tier adds ~0 over the simple rule) — that honesty is the moat in a space full of overclaiming.

**How far along are you? What's your traction plan?**
> Tech is far along: a closed-form routing rule with a leakage-free walk-forward proof, a production agent (per-block loop, Flashbots private mempool, Prometheus observability, append-only audit, 128/128 tests) sharing bit-identical decision modules with the backtest, full reproducibility envelope (GitHub + HuggingFace), and an 8-chapter institutional dossier + LP deck. **Go-to-market is at zero by design** — next step is to hand-run allocations for 3–5 design-partner treasuries ($2M–$25M idle USDC each), non-custodially, to build a live real-money track record and reference customers. Traction plan: (1) free "treasury yield audits" on real on-chain balances as the cold open; (2) convert 3–5 to hand-run trials; (3) ship a Safe module so they delegate routing authority (never custody); (4) move to perf-fee + SaaS-floor pricing once net-of-gas edge is proven at size.

**What's the size of the market?**
> Immediate beachhead: the ~$54B TVL in these 6 Ethereum lending markets, of which a large share is idle stablecoins parked sub-optimally; we route ~67% of that TVL's protocol set today. Broader: total DeFi-deployed stablecoins across chains and the on-chain treasuries of DAOs, protocols, and crypto-native funds — tens of billions of idle stablecoins that all face the same "leaving 150–280 bps on the table" problem. Revenue scales with routed balance, and our economics improve with size because gas amortizes.

**What's the one thing about your company an investor should remember?**
> A solo, AI-first founder has already built a *provably-real, leakage-free, non-custodial* edge that beats passive stablecoin lending by 1.5–2.8 points a year — and is honest enough to tell you exactly where it stops working.

---

### 2-Minute Demo Script (for YC interview / partner video)

> *Goal: show the proof and the non-custodial execution on a real address. Live scanner + one rebalance.*

- **[0:00–0:20] The problem, concretely.** "This is [DAO]'s treasury — $8M USDC, all parked in Aave. Here's the live rate." *Show scanner pulling real balances + current rates across all 6 protocols.* "Right now Spark and Morpho are paying more. They're leaving money on the table this block."
- **[0:20–0:50] The proof.** "This isn't a guess. Here's a 6-window walk-forward, Nov 2024 to April 2026 — event-time routing beats every single-protocol hold by 1.5 to 2.8 points annualized, paired-bootstrap p under 1e-4 on five of six contrasts. Same code that runs the backtest runs production — bit-identical decision modules." *Show the equity curves + the contrast table.*
- **[0:50–1:25] The non-custodial execution.** "Watch what happens. The agent detects the spread, builds a rebalance, and submits it through Flashbots private mempool to avoid front-running." *Show the agent loop firing, the signed proposal, the Safe approving, the audit log appending.* "Notice: **I never touched their keys.** The Safe module is scoped to only move USDC among these 6 whitelisted pools — it can't withdraw a cent to an outside address. Revocable any block."
- **[1:25–1:50] The honesty + economics.** "I'll tell you what doesn't work: I built an ML hazard model on top, and out-of-sample it added basically nothing over the 50-line rule. The simple thing is the product. And the edge is gas-bounded — at $1M it's about +1.75 bps per rebalance, but it *grows* with size as gas amortizes. That's why our customer is institutional stablecoin treasuries."
- **[1:50–2:00] The ask / close.** "Tech's done and tested. I'm a solo AI-first founder. Next is hand-running this for 3–5 treasuries to build the live track record. That's what I'm here to do."

---

## 6. Six-Month Default-Alive Milestone Plan

"Default-alive" for a capital-light solo founder = **reach a small but real revenue run-rate that covers minimal burn (gas for ops, infra, legal) before any raise is needed**, on the strength of hand-run customers. The asset base is already built; these six months are pure GTM + the non-custodial productization.

| Month | Primary objective | Concrete milestones | Default-alive metric |
|---|---|---|---|
| **M1** | Weaponize proof + open pipeline | Ship read-only **Treasury Yield Audit** scanner (live balances + historical counterfactual on the 6 protocols). Write the methodology research note. Build a target list of 20–30 treasuries; start warm intros + 1 neutral DAO-forum analysis post. | 20+ targeted; 5+ audits delivered |
| **M2** | First design partners, hand-run | Sign **2–3 design partners** ($2M–$25M idle USDC). Begin **co-signed, non-custodial** hand-run allocations (you propose, they approve from their Safe). Start append-only live track record. | 2–3 live partners on real money |
| **M3** | Productize non-custodial execution | Ship **Gnosis Safe module** (scoped: route USDC among 6 whitelisted pools, no external withdrawal, revocable). Wire **real gas** (kill 25 gwei placeholder) + **Flashbots** in production. Get lawyer sign-off on software+perf-fee framing. | 1+ partner live via Safe module (no co-sign) |
| **M4** | Prove net-of-gas edge at size; expand | Reach **5 design partners**. Publish first **monthly net-of-gas performance report** per partner (real delivered edge, honestly net of gas/MEV). Tighten onboarding to <2 weeks. | 5 partners; documented positive net edge on largest partner |
| **M5** | Turn on revenue | Convert 2–3 partners from free to **paid (perf-fee on excess over benchmark + SaaS floor)**. Use track record + references for next-wave inbound. | First paying customers; initial MRR/perf-fee booked |
| **M6** | Default-alive checkpoint + repeatability | Standardized audit→trial→Safe→paid funnel. 3–5 paying treasuries. Decide: keep bootstrapping vs raise on a real track record + revenue. | **Revenue run-rate ≥ minimal burn (default-alive)**, or a clean YC/seed story with live numbers |

**Guardrails baked into the plan (respect the caveats):**
- **Never charge on the placeholder-gas backtest number.** Revenue only turns on (M5) *after* real gas + Flashbots are wired and a real net-of-gas report exists (M3–M4).
- **Non-custodial at every step** — co-sign first (M2), then scoped Safe module (M3). No custody, no money-transmitter exposure, no pooling.
- **Lead with where it works *and* where it doesn't** — the ML-adds-nothing honesty and the gas-bounded/size-dependent edge are stated to every partner. That's the trust engine.
- **Institutional capital is the natural ICP** because net edge grows with size; bias partner selection toward larger idle balances even in the hand-run phase.