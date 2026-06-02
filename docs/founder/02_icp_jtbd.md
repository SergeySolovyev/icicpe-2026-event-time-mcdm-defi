I have enough context. This is a pure strategy/market deliverable grounded in the product context. I'll write the markdown doc directly.

# ICP, Jobs-to-be-Done & User-Interview Doc
### Event-Time MCDM Allocation across DeFi Lending Protocols

> **Product in one line:** A non-custodial agent that re-allocates idle USDC across the 6 largest Ethereum-L1 lending protocols on a per-block basis using a closed-form, gas-aware threshold rule, beating passive single-protocol holds by **+1.5 to +2.8 pp annualized** (paired-bootstrap p<1e-4 on 5/6 walk-forward contrasts), with institutional-grade risk controls.
>
> **Economic spine that drives ICP selection:** net edge per rebalance is gas-bounded (~+1.75 bp/rebalance at $1M), and **the edge grows with position size** as fixed gas amortizes. Therefore the natural wedge is the *largest* idle-stablecoin treasuries, not the most numerous. This single fact reorders everything below.

---

## 0. Scope & honesty guardrails (carry these into every user conversation)

These are the *true* constraints of the product as it stands today. Do not oversell in interviews — under-claiming builds the trust this ICP requires.

- The **threshold rule (T1)** is the product. The ML tier (T3 Cox hazard) adds ~0 out-of-sample edge once leakage + a feature-wiring bug are fixed. Lead with the simple rule; the "AI" framing is a liability with this skeptical, technical audience.
- Backtest gas is a **flat 25 gwei placeholder** (real gas not yet wired). Net-of-gas numbers are directional, not audited.
- Backtest **does not deduct MEV/slippage**; production routes through a **Flashbots private mempool**. Say this proactively — sophisticated treasuries will ask.
- Net edge at $1M ≈ **+1.75 bp/rebalance gas-bounded**; edge **grows with size**. Below ~$250k–$500k, gas likely eats most of the edge — be honest that small treasuries are *not* the fit yet.
- **Non-custodial-first.** No money-transmitter/custody license at launch; user keys never touch our infra. This is both a regulatory dodge and a *trust feature* for this ICP.

---

## 1. Three candidate ICP segments (ranked)

Ranked by fit to the gas-amortization economics + reachability by a solo, capital-light, AI-first founder + ability to ship non-custodially today.

### Rank #1 — Crypto-native funds & family offices (incl. crypto treasury/yield desks)
*(Quant funds, crypto hedge funds, market-maker treasury desks, DAW/family offices, "on-chain treasury" SMAs.)*

| Dimension | Detail |
|---|---|
| **Who holds the budget** | PM / CIO / Head of Treasury / Head of Trading. Decision is fast (1–2 people), capital is discretionary, mandate explicitly allows DeFi. For SMAs: the GP. |
| **Idle USDC** | $2M–$100M+ in idle stablecoins between trades, in cash buffers, or as a dedicated "low-risk on-chain yield" sleeve. Often 10–40% of book sits idle waiting for setups. |
| **Current behavior** | Manually parks USDC in Aave V3 / a single Morpho vault; some chase points/incentives; a few wrote their own rebalancing scripts that bit-rotted. Many just leave it idle ("opportunity cost is invisible on the P&L"). |
| **Pain** | (a) Idle stablecoin yield drag is a measurable performance leak the LPs/principal *can* see. (b) Manually monitoring 6 protocols' per-block rates is nobody's job. (c) Smart-contract/depeg risk concentration in one protocol. (d) They *understand* the +1.5–2.8pp edge instantly and can size it against their book. |
| **Why now** | Stablecoin lending rates are a live, watched number in 2025–26; "idle treasury optimization" is a recognized line item; non-custodial infra (Flashbots, account abstraction, ERC-4626) is mature; institutional comfort with on-chain treasury is at an all-time high. |

**Why this is the natural #1:** they have the *largest* idle balances (gas amortizes → edge is real and material in bps×size), they're **financially literate** (they price the edge in seconds and don't need hand-holding on what "annualized excess return, paired-bootstrap p<1e-4" means), they're **reachable by one person** (small, networked community), and they're **comfortable non-custodial** (they already self-custody). This is the wedge.

---

### Rank #2 — Protocol treasuries (DeFi protocol DAOs/foundations with large stablecoin reserves)
*(Foundations/treasuries of established protocols holding stablecoin runway: e.g. large DeFi protocols, L2 foundations, infra DAOs.)*

| Dimension | Detail |
|---|---|
| **Who holds the budget** | Foundation CFO / treasury committee / a designated multisig signer set. More centralized than a token-voted DAO; often a real legal entity (foundation) with a treasury mandate. |
| **Idle USDC** | $5M–$200M+ stablecoin runway (operating reserve held in USDC/DAI to fund 2–4 years of opex). This is *explicitly* meant to be low-risk and is *explicitly* idle. |
| **Current behavior** | Largest single bucket of idle stablecoins in crypto, but conservative: parked in Aave/Maker DSR/a single blue-chip, or in T-bill RWA products. Diversification + yield is a recurring governance topic. |
| **Pain** | (a) Fiduciary pressure to not let runway sit at 0%, but also not to take protocol-blowup risk. (b) Single-protocol concentration is an embarrassing governance risk (especially holding a *competitor's* token-adjacent risk). (c) Real reporting/audit need → our append-only audit + Prometheus observability is a genuine selling point. |
| **Why now** | Treasury management is now a first-class DAO governance topic; multiple high-profile treasury-yield mandates have passed; foundations are professionalizing. |

**Why #2, not #1:** balances are huge (great for gas amortization) **but** the sales cycle is slow (governance proposal, committee, multisig, sometimes a token vote), risk-aversion is extreme (a backtest with a *placeholder gas number* and *no MEV deduction* will get picked apart in a public forum), and a solo founder with no track record / no audit will struggle to clear the trust bar cold. **Excellent expansion target after 2–3 fund references exist.**

---

### Rank #3 — DAO treasuries (token-governed communities, often heavy in native token + a stablecoin sleeve)
*(Grant DAOs, social/collector DAOs, mid-cap protocol DAOs governed by token holders.)*

| Dimension | Detail |
|---|---|
| **Who holds the budget** | Diffuse: token holders vote; a treasury working group or multisig executes. Slowest, most political buyer. |
| **Idle USDC** | Highly variable. Stablecoin portion is often **smaller** than headline TVL suggests (much of "treasury" is illiquid native token). The *idle USDC* that fits our product may be only $0.5M–$10M. |
| **Current behavior** | Often does nothing with stables, or uses a treasury-management service (Karpatkey/Avantgarde/Llama-style), or parks in Aave. Decisions are public, slow, and contested. |
| **Pain** | (a) "Why is our treasury earning 0%?" is a recurring forum complaint. (b) But governance overhead to *change* anything is enormous. (c) Optics/security fear of "an AI agent moving our money" is highest here. |
| **Why now** | Same macro tailwind, but the buying friction is worst-in-class. |

**Why #3:** smaller relevant idle balances (weakest gas amortization → thinnest edge), slowest and most political buyer, highest "non-custodial AI agent" trust fear, and the founder narrative ("solo + AI agents") plays *worst* to a risk-averse public forum. Good for inbound/PR and long-term TAM, poor as a beachhead.

---

## 2. The #1 beachhead ICP (chosen wedge) + justification

> **Beachhead: Crypto-native quant/trading funds and family offices holding $2M–$50M of idle USDC, where one or two people (PM/CIO/Head of Treasury) control the allocation and the mandate already permits DeFi.**

Even tighter v1 target: **a single-GP quant or crypto fund / family office that self-custodies, parks idle USDC in Aave or one Morpho vault today, and treats idle-stablecoin yield drag as a real (if untracked) line item.**

**Justification — why this beats the bigger treasuries as the *first* customer:**

1. **The economics point straight here.** Net edge is gas-bounded and **grows with position size**. Funds carry the largest *individually-controlled* idle balances ($2M–$50M under one decision-maker), so the per-rebalance gas is amortized to noise and the bps edge × size becomes real dollars they can see. (Protocol treasuries are bigger but the dollars are controlled by a *committee*, not a buyer.)
2. **They can underwrite the honest caveats.** A quant PM reads "placeholder gas, MEV not deducted, edge ~+1.75bp/rebalance gas-bounded, T1 is the product not the ML" and *respects* it instead of being scared off. They can re-run the numbers against their own book. This is the *only* segment where the honesty guardrails are an asset rather than a deal-killer.
3. **One-person, fast sale.** PM/CIO can say yes in one or two calls with discretionary capital — no governance proposal, no public forum, no multisig vote. A solo founder can actually close this.
4. **Non-custodial fits their muscle memory.** They already self-custody and sign transactions; "your keys, our decision module, Flashbots execution" is a feature, not a hurdle. It also keeps the founder license-free (default-alive, capital-light).
5. **They are findable and few.** This community is small, concentrated, and reachable by one human via the channels in §5 — "do things that don't scale" is viable (DM 100 specific people, not "win a DAO vote").
6. **They are the reference engine for Rank #2/#3.** Two or three fund logos + live audited performance is exactly the proof a protocol-treasury governance proposal needs later. Land the funds → expand to treasuries.

**Disqualifiers (say no fast):** treasuries < ~$500k idle (gas eats the edge); anyone needing custody/fiat rails on day one; mandates that forbid DeFi; buyers who require a third-party audit *before* a pilot (revisit post-audit).

**Wedge offer (thinnest valuable slice):** a **read-only "yield drag report"** — point the agent at their wallet/treasury address, show what passive holding cost them vs. the event-time threshold rule over the last N months on *their* balance, fully reproducible from the public GitHub/HuggingFace envelope. Free, non-custodial, zero risk. Convert the believers into a non-custodial signing pilot.

---

## 3. Jobs-to-be-Done statements

**Functional jobs**
- When my fund's USDC sits idle between trades, I want it to automatically earn the best available risk-adjusted lending yield across the major protocols, so I stop leaking basis points I can't justify to my LPs/principal.
- When lending rates shift block-to-block across Aave/Compound/Spark/Morpho/Euler/Fluid, I want a system to reallocate only when the gas-adjusted gain is positive, so I capture the spread without burning it on gas/MEV.
- When I deploy stablecoins on-chain, I want exposure spread across vetted protocols under explicit risk caps, so a single protocol failure or depeg can't take down my whole stablecoin sleeve.

**Emotional / social jobs**
- When my LPs/principal/governance review treasury performance, I want to show idle cash earned a defensible, benchmarked yield, so I look like a competent steward instead of leaving money on the table.
- When I let software move my treasury, I want to *keep my keys and see every decision logged*, so I never have to explain a custody loss or an unaccountable "black-box AI" trade.

**The hire/fire framing (use verbatim in interviews):**
> "I 'hire' this agent to make my idle stablecoins earn more than parking them in one protocol — *without* me babysitting it, *without* giving up custody, and *without* taking on more risk than I'd accept myself."
> Today they "hire" Aave-and-forget, a homegrown script, or a treasury-management service. We must beat all three on yield, effort, and control.

---

## 4. YC-style user-interview script (12 questions — past behavior, not hypotheticals)

> **Rules of engagement (YC canon):** Ask about what they *did*, not what they *would* do. No pitching until the interview is over. Dig for the last specific instance, real dollar amounts, and what they tried. Silence is your friend. Goal: validate the pain and the wedge, not to sell.

1. **Walk me through what happened to your idle USDC over the last quarter** — where did it sit, and how did it get there? *(maps current behavior + balance size)*
2. **The last time you moved stablecoins into a yield venue, what triggered it, and how did you pick the protocol?** *(decision trigger + competitive set)*
3. **How do you decide it's "worth it" to move funds between protocols — walk me through the most recent time you did or chose not to.** *(reveals their implicit gas/effort threshold)*
4. **Roughly what does idle stablecoin yield contribute to your returns, and who looks at that number?** *(quantifies pain + identifies the social/fiduciary audience)*
5. **Has anyone — an LP, your principal, governance — ever asked why idle cash wasn't earning more? What happened?** *(emotional/social job; severity)*
6. **Have you ever built or bought something to manage this — a script, a service, a vault? Tell me about it and whether you still use it.** *(reveals build-vs-buy history + why prior solutions failed)*
7. **What's the most you'd be comfortable allocating on-chain to one protocol, and why that number?** *(risk tolerance + concentration pain, in real dollars)*
8. **Tell me about the last time a DeFi position scared you or went wrong** — depeg, hack, gas spike, stuck tx. *(surfaces the real risk fears the product must answer)*
9. **Who has to sign off before treasury funds move, and how long did that take the last time?** *(buyer / decision unit / sales-cycle length — disqualifies committee-bound prospects)*
10. **When you've evaluated an on-chain yield tool before, what made you trust it or walk away?** *(trust criteria: audits, custody model, track record — tells us what the wedge must show)*
11. **How do you feel about software signing transactions on your treasury — what's your hard line on custody?** *(validates the non-custodial wedge is actually a requirement, not just our assumption)*
12. **If I sent you a report showing exactly what passive holding cost you last quarter vs. an automated reallocation — on *your* actual balance — what would you do with it, and who would you show?** *(tests the free read-only wedge as a real entry point; still grounded in a concrete artifact, not a feature wish-list)*

*Closing ask (after the interview): "Who else doing serious on-chain treasury should I talk to?" → referral chain.*

---

## 5. Where to find these users

**Governance forums & treasury venues** (read the treasury threads → find the working-group members by name → DM them):
- Aave, Compound, Spark, Morpho, Euler, Fluid governance forums (Discourse/Commonwealth) — watch every "treasury management / idle reserve / risk parameter" thread; the people debating these *are* the buyers and the reference accounts.
- Karpatkey, Avantgarde, Llama, Steakhouse Financial public reports/forums — these treasury-management shops sit exactly where our ICP overlaps; study their client lists and the protocols they serve (partner *or* compete).
- Snapshot spaces of mid/large protocols — see which treasuries have live yield/diversification proposals.

**Discords / Telegram** (be a useful participant first, pitch never):
- DeFi protocol Discords' #treasury / #risk / #governance channels (Aave, Morpho, Euler, Spark, Fluid).
- Quant/MM and "DeFi degens with real size" Telegram groups; stablecoin-yield and "where to park USDC" channels.
- Family-office / crypto-allocator private Telegram/Signal groups (warm intros only — these are referral-gated).

**Conferences / IRL** (highest-trust channel for a no-track-record founder):
- **EthCC, Devcon/Devconnect** — the technical DeFi crowd; side-events on treasury & risk.
- **Token2049** (Singapore/Dubai) and **Permissionless** — heavy fund/allocator/family-office presence.
- **DAS (Digital Asset Summit)** and similar institutional-crypto conferences — protocol treasuries + crypto funds.
- Aave/Morpho/Euler community calls and risk-DAO (e.g. Gauntlet/Chaos-style) working sessions — meet the risk people who vet exactly our kind of system.

**Twitter/X circles** (build credibility by publishing the honest backtest + reproducibility envelope, then engage):
- DeFi yield / "stablecoin farmers" and on-chain treasury analysts (the "where's the best USDC yield this week" crowd).
- Protocol risk leads, Gauntlet/Chaos/Llama-Risk researchers, treasury-management firms' founders.
- Quant-DeFi and MEV/Flashbots-adjacent researchers (they'll respect the leakage-free, walk-forward, private-mempool framing — and amplify it).
- Post the read-only **yield-drag report** as a public artifact tied to the GitHub + HuggingFace envelope — it earns inbound from exactly this ICP and doubles as proof for later treasury sales.

**Do-things-that-don't-scale playbook:** build a hand-curated list of ~100 named individuals from the forum threads + conference attendee lists, run the free yield-drag report for the top 20 *before* they ask, and use Q12 + the referral ask to compound. Land 2–3 funds, then take the audited track record into the protocol-treasury governance forums (Rank #2).