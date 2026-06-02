I have all the data I need across market sizing, 11 competitors, regulatory context, and the positioning gap. Writing the deliverable now.

# Market & Competitor Landscape — Event-Time MCDM Allocation across DeFi Lending Protocols

*Prepared June 2026. All figures sourced inline; where a number is a directional estimate from secondary aggregators it is flagged as such. This is a market map, not a results claim — the product's edge figures (+1.5–2.8pp annualized vs passive holds) come from the project's own walk-forward backtest, not from any source below.*

---

## 1. Market sizing — idle stablecoin treasury yield (TAM / SAM / SOM)

The product sells one thing: **better-than-passive, risk-controlled yield on idle stablecoin balances, delivered non-custodially**. The funnel below sizes that opportunity from the total stablecoin float down to a realistic 3-year capture for a solo, non-custodial, advisory-first operator.

### TAM — total addressable: all stablecoins that *could* be earning optimized cross-protocol yield

- Total stablecoin circulating supply crossed **~$320B** in Q2 2026 (USDT ~$190B, USDC ~$78B), up sharply through 2026 ([KuCoin, May 2026](https://www.kucoin.com/blog/Stablecoin-Liquidity-Hits-$320B-Milestone-in-May-2026); [DefiLlama Stablecoins](https://defillama.com/stablecoins)).
- **~$170B (≈60%)** sits on Ethereum L1 — the chain set this product targets ([KuCoin, May 2026](https://www.kucoin.com/blog/Stablecoin-Liquidity-Hits-$320B-Milestone-in-May-2026)).
- CoinDesk Research frames **~$305B of stablecoins as "lazy" / idle** — earning the issuer (via reserve T-bill income) but not the holder. This is the "$300B efficiency gap" and is the cleanest articulation of the TAM ([CoinDesk Research, 2026](https://www.coindesk.com/research/productive-stablecoins-closing-the-usd300b-efficiency-gap)).

> **TAM ≈ $150–305B** of idle stablecoin value that could be optimized. The narrow, honestly-defensible cut (idle USDC/USDS on Ethereum L1, the protocols this product actually routes across) is **~$100–170B**.

### SAM — serviceable: idle stablecoins in *treasuries* that want managed, institutional-grade yield

This is the product's stated ICP (DAOs, protocol treasuries, crypto-native funds/family offices) — not retail wallets.

- **DAO treasuries: ~$26–28B** across 13,000+ DAOs, but heavily concentrated — only **~220 DAOs hold >$1M**, and **<80 are truly active** ([Eco, 2026](https://eco.com/support/en/articles/14799687-dao-treasury-management-onchain-governance-spend)).
- Of aggregate DAO crypto treasury value, **only ~10% (~$1.1B) is currently held in stablecoins** — and most of *that* is "dead weight" earning nothing ([CoinDesk Research, 2026](https://www.coindesk.com/research/productive-stablecoins-closing-the-usd300b-efficiency-gap)). The largest treasuries (Uniswap ~$4.8B, Sky/MakerDAO ~$3.9B, Optimism ~$2.1B, Arbitrum ~$1.7B, Lido ~$1.4B) skew toward native tokens, but each runs an operational-reserve stablecoin sleeve that is exactly the target ([Eco, 2026](https://eco.com/support/en/articles/14799687-dao-treasury-management-onchain-governance-spend)).
- Add crypto-native funds, market makers, and family-office stablecoin operating cash. Institutional treasury writeups put conservative on-chain stablecoin yield targets at **4–8% APY**, and explicitly cite idle-USDC examples (e.g. one DAO forfeiting **~$105k/month** on ~$26M idle at a 5% target) ([Alphapoint, 2026](https://alphapoint.com/blog/stablecoin-treasury-management-for-institutions-the-definitive-2026-guide); [Eco, 2026](https://eco.com/support/en/articles/14799687-dao-treasury-management-onchain-governance-spend)).

> **SAM ≈ $3–8B** of treasury-held stablecoins that are addressable today — the union of DAO stablecoin reserves (~$1–2B and growing as treasuries "productize" idle cash), crypto-fund operating stablecoins, and the institutional-capital pools the product is explicitly designed for (edge grows with size as gas amortizes). The directional ceiling, as treasuries shift idle cash into yield, trends toward the **$10B+** "productive stablecoin treasury" pool implied by the efficiency-gap research.

### SOM — serviceable obtainable: realistic 3-year capture for a solo, non-custodial, advisory-first operator

Constraints that bound SOM hard: (a) non-custodial advisory means the product *recommends/executes-with-client-keys* rather than pooling AUM, so "AUM" is really "assets-under-advisement / assets-routed"; (b) solo founder, capital-light, no custody license initially; (c) the competitive set below already holds the easy capital.

Reference points for what a focused new vault/advisor captures:
- ether.fi **Liquid** (Veda-powered) reached **$750M TVL / 26,000 users** as a focused vault product ([Veda, 2026](https://veda.tech/blog/partnership-announcement-etherfi)).
- Notional V3 (a credible but second-tier lending protocol) sits at **~$843M** ([DefiLlama via search, 2026](https://defillama.com/protocol/notional-v3)).
- Maple grew syrupUSD to **~$1.9B** by serving the institutional-credit niche tightly ([Maple/AInvest, 2026](https://www.ainvest.com/news/maple-finance-path-100m-arr-5b-aum-high-growth-play-defi-lending-2512/)).

> **SOM (3-yr, realistic for this structure): ~$50M–300M assets-routed/advised.** A defensible base case is landing **5–20 treasury clients** at $2–25M each. Revenue at a ~10–15% performance fee on a +1.5–2.8pp *outperformance* (not gross yield) is modest per dollar — which is exactly why the product's own thesis (edge grows with position size; institutional capital is the natural ICP) matters: SOM is unlocked by a *few large* mandates, not many small ones. A single $100M institutional mandate moves SOM more than 50 DAO sleeves.

**Sizing caveat (honest):** because the product is advisory/non-custodial and fees attach to *outperformance over passive*, not gross AUM, the revenue-relevant market is materially smaller than the headline $/TVL figures of the custodial vaults below. The moat is regulatory-light reach, not fee-per-dollar.

---

## 2. Competitor matrix (12 players + passive baselines)

Columns: **Custody model · Strategy type · Fees · Chains · Who it serves · Key weakness (vs this product)**. All TVL/fee figures are 2026 unless noted; several are from secondary aggregators (DefiLlama, Eco, vaults.fyi) and should be treated as directional.

| # | Player | Custody | Strategy type | Fees | Chains | Who it serves | Key weakness vs. this product |
|---|--------|---------|---------------|------|--------|---------------|-------------------------------|
| 1 | **Yearn V3** ([defiprime](https://defiprime.com/yvusd-yearn-stablecoin-vault); [Eco](https://eco.com/support/en/articles/14745618-best-stablecoin-vaults-in-2026)) | Custodial (ERC-4626 vault holds funds) | Multi-strategy stablecoin aggregation; yvUSDC/yvUSDT/yvUSD; APY ~4–6.5% | yvUSD **0/0**; legacy vaults up to **10% perf + 2% mgmt** | Multi-chain | Retail + DeFi-native | Aggregator category shrank to **~$1.6B** as capital fled to curated vaults; rebalances on keeper cadence, **not per-block/event-time**; not gas-aware at the block level |
| 2 | **Morpho Vaults (ex-MetaMorpho)** ([DefiLlama](https://defillama.com/protocol/morpho); [Eco](https://eco.com/support/en/articles/13064566-morpho-protocol-explained-2026)) | Custodial (curator-managed vault) | Curated allocation across isolated Morpho Blue markets; conservative USDC 4–5% | Curator-set, typ. **~15% of yield** | Ethereum, Base + | DAOs, institutions, fintechs | **Single-protocol (Morpho only)** — cannot arbitrage Aave↔Compound↔Spark↔Fluid; allocation is curator-discretionary, not a transparent closed-form rule |
| 3 | **Gauntlet** (as Morpho curator) ([Eco](https://eco.com/support/en/articles/13064566-morpho-protocol-explained-2026); [arxiv 2512.11976](https://arxiv.org/html/2512.11976v1)) | Non-custodial *advisory* + curated vaults | Quant risk-curation; **~$2B / 27.6%** of Morpho vault TVL | **15% of yield** | Ethereum, Base + | Institutions, protocols | Closed/proprietary risk models; intra-Morpho focus; large-org service model — won't serve a $2–25M DAO sleeve cheaply; not event-time/per-block |
| 4 | **Aera (by Gauntlet)** ([Aera](https://www.aera.finance/); [docs](https://docs.aera.finance/aera-for-treasury-management)) | **Non-custodial** ("designated accounts"; only owner withdraws) | Autonomous DAO treasury mgmt — TWAP stables, levered ETH, LP mining | Negotiated mandate | Ethereum, Polygon | **DAOs / treasuries** (closest ICP overlap) | Broad treasury mandate (multi-asset, levered strategies), **not** a focused gas-aware cross-lending-protocol stablecoin optimizer; heavyweight, relationship-sold; rebalance cadence is strategy-level, not per-block |
| 5 | **Veda / ether.fi (BoringVault)** ([PRNewswire](https://www.prnewswire.com/news-releases/veda-raises-18m-led-by-coinfund-to-bring-institutional-grade-defi-yield-to-consumer-apps-through-3-7b-vault-platform-302488185.html); [Veda](https://veda.tech/blog/partnership-announcement-etherfi)) | Custodial vault primitive (non-custodial *infra*, funds in vault) | "DeFi engine" — powers Kraken DeFi Earn, ether.fi Liquid; **$3.5–3.8B TVL**; stables 3–8% | Embedded / partner-set | **B2B2C** — wallets, fintechs, exchanges | Distribution play, not a transparent allocator; opaque strategy selection; targets app-embedded retail float, not direct treasury advisory; not event-time |
| 6 | **Sommelier / Somm** ([DefiLlama](https://defillama.com/protocol/sommelier); [Somm](https://app.somm.finance/)) | Non-custodial (ERC-4626 + Cosmos appchain for off-chain compute) | Off-chain-computed active vault rebalancing | Vault-set | Ethereum, Optimism, Arbitrum | DeFi-native | Architecturally closest (off-chain compute, non-custodial) but **ETH/LST-centric**, small TVL, momentum stalled; not focused on stablecoin cross-lending or per-block gas-aware routing |
| 7 | **Maple Finance (syrupUSDC)** ([Maple](https://maple.finance/); [DefiLlama](https://defillama.com/protocol/maple-finance)) | Custodial (pooled institutional credit) | Real-loan-interest yield, not allocation; **~$2.1B TVL**; HY pool ~9.2% | Spread on loans | Ethereum, Solana | **Institutional credit** lenders/borrowers | Different product — *credit risk* yield, not protocol-rate arbitrage; counterparty/default risk; not a passive-lending optimizer |
| 8 | **Index Coop** ([DefiLlama](https://defillama.com/protocol/index-coop); [Index Coop](https://www.indexcoop.com/)) | Custodial (tokenized index/structured product) | Structured yield tokens (hyETH on Gauntlet-curated Morpho, icETH); **~$15M TVL** | Streaming/mgmt fee | Ethereum, Arbitrum, Base | Retail / passive holders | ETH-yield/leverage focus; tiny TVL; tokenized-index wrapper, not active stablecoin allocation |
| 9 | **Idle Finance** ([Idle](https://idle.finance/); [docs](https://docs.idle.finance/products/perpetual-yield-tranches/guide)) | Custodial (tranche vaults) | Algo allocation across lending protocols + **senior/junior risk tranches** | Perf/mgmt fee | Ethereum + L2s | Risk-segmented yield seekers | **Conceptual closest** (algorithmically allocates across lending protocols) but small/quiet post-2023; rebalances slowly, **not per-block, not gas-aware**; tranching ≠ event-time threshold rule |
| 10 | **Notional V3** ([DefiLlama](https://defillama.com/protocol/notional-v3)) | Custodial (fixed-rate lending pools) | **Fixed-rate** stablecoin lending; **~$843M TVL** (mostly Arbitrum) | Protocol fee | Ethereum, Arbitrum | Fixed-income-style users | Fixed-rate ≠ dynamic best-rate routing; can't capture transient cross-protocol APY spreads; single-venue |
| 11 | **Steakhouse Financial** (Morpho curator) ([DefiLlama](https://defillama.com/protocol/steakhouse-financial); [Eco](https://eco.com/support/en/articles/13064566-morpho-protocol-explained-2026)) | Non-custodial advisory + curated vaults | Risk-curation; **~$1.29B / 17.8%** of Morpho vault TVL | **15% of yield** | Ethereum, Base + | DAOs, RWA, institutions | Intra-Morpho curation; discretionary; high-touch service model; not cross-protocol event-time |
| 12 | **Kraken DeFi Earn / CEX-routed vaults** ([The Block](https://www.theblock.co/amp/post/403277/veda-brings-the-vault-stack-behind-kraken-defi-earn-to-privys-2000-plus-developer-teams)) | **Custodial** (CEX holds keys, routes to vaults) | Routes exchange deposits into curated lending vaults; up to ~8% | Spread + vault fee | CEX-abstracted | **Retail CEX users** | Fully custodial; opaque; serves retail float not sophisticated treasuries that want self-custody + auditability |
| — | **Passive baseline: hold in single protocol** (Aave V3 / Compound V3 / Spark / Fluid) ([Eco](https://eco.com/support/en/articles/14800882-best-defi-lending-protocols-2026-tvl-rates-risk)) | Self-custody (user supplies directly) | Buy-and-hold single-protocol lending; stables 3–8% | **None** (gas only) | Per protocol | Everyone (the default) | **This is the benchmark the product beats by +1.5–2.8pp** — passive leaves cross-protocol rate spreads on the table; never rebalances |
| — | **Passive baseline: yield-bearing stablecoin** (sUSDS / yield-bearing wallets) ([CoinDesk](https://www.coindesk.com/research/productive-stablecoins-closing-the-usd300b-efficiency-gap)) | Token-level (hold the token) | Hold a yield-bearing stable; sUSDS alone added **>$2.5B** net | Embedded | Multi | Passive holders, treasuries | One rate, one issuer's risk; no cross-protocol optimization; GENIUS Act yield-prohibition pressure on *payment* stablecoins (see §3) |

### What the matrix shows

1. **Two structural camps, and a hole between them.** Custodial vaults (Yearn, Morpho Vaults, Veda, Maple, Idle, Notional, Index Coop, Kraken) hold the easy capital but require trusting a vault/curator with funds. Non-custodial advisors (Aera, Gauntlet, Steakhouse, Sommelier) preserve self-custody but are either *broad* treasury mandates or *single-venue* (intra-Morpho) curation. **Nobody is a focused, non-custodial, transparent, cross-protocol, gas-aware, event-time stablecoin allocator.**
2. **The curated-vault wave is the real incumbent.** Capital migrated *away* from classic aggregators (~$1.6B total) *into* curated Morpho vaults (~$5.8–10B), with Gauntlet + Steakhouse alone running ~45% of that ([defiprime](https://defiprime.com/defi-vaults-guide); [Eco](https://eco.com/support/en/articles/13064566-morpho-protocol-explained-2026)). But those vaults are **single-protocol (Morpho-only)** and **discretionary** — they don't arbitrage across the 6 lending venues, and they charge 15% of *gross yield*.
3. **Closest analogs are weak exactly where this product is strong.** Idle (cross-protocol algo allocation) is dormant and slow-rebalancing; Sommelier (non-custodial off-chain compute) is ETH-centric and small. Neither does **per-block event-time** reallocation or **block-level gas-aware** netting.

---

## 3. The positioning gap this product fills

Plotting the field on two axes makes the white space explicit:

```
                 CROSS-PROTOCOL (Aave/Comp/Spark/Morpho/Euler/Fluid)
                                    ▲
                                    │
        Idle (slow, dormant) ●      │      ◄── ★ THIS PRODUCT ★
        Yearn (keeper cadence) ●    │          event-time per-block,
                                    │          gas-aware, transparent
                                    │          closed-form rule, non-custodial
   ─────────────────────────────────┼─────────────────────────────────►
   CUSTODIAL                         │                      NON-CUSTODIAL
                                    │
        Morpho Vaults ●             │   Aera ● (broad multi-asset mandate)
        Kraken DeFi Earn ●          │   Gauntlet / Steakhouse ● (intra-Morpho)
        Veda/ether.fi ●             │   Sommelier ● (ETH-centric)
                                    ▼
                          SINGLE-PROTOCOL / DISCRETIONARY
```

**The unoccupied quadrant — and the product's exact positioning — is:**

> **Non-custodial advisory + transparent closed-form rule + cross-protocol + gas-aware + event-time (per-block) reallocation.**

No competitor combines all five. Concretely, the differentiators:

- **Event-time, per-block reallocation.** Every other player rebalances on a keeper schedule, a curator's discretion, or epoch boundaries. This product re-evaluates allocation **per block** against live rates — capturing transient cross-protocol APY spreads that slow rebalancers structurally miss. *(Honest caveat: production must route through a Flashbots private mempool to avoid MEV/slippage, which the backtest does not yet deduct.)*
- **Cross-protocol breadth (6 venues, ~67% of ~$54B lending TVL).** Aave V3, Compound V3, Spark, Morpho Blue, Euler V2, Fluid — vs incumbents locked to one venue (Morpho Vaults, Notional) or one risk-curator's market set. Total DeFi lending sits at **~$54B** with **84% of debt stablecoin-denominated** ([Eco, 2026](https://eco.com/support/en/articles/14800882-defi-lending-protocols-2026-tvl-rates-risk)), so the venues this product spans are the bulk of the addressable rate surface.
- **Gas-aware threshold rule (the actual product).** A ~50-line closed-form rule with **no trained parameters** — auditable, leakage-free, and (per the project's own honesty caveat) the part that actually beats passive. The ML tier adds ~0 OOS once leakage/wiring bugs are fixed. *This transparency is itself a wedge against opaque curator vaults.* **Honest caveat: backtest gas is a flat 25 gwei placeholder; real gas is not yet wired, and net edge at $1M is ~+1.75bp/rebalance and gas-bounded — so the edge is small at retail size and grows with position size.**
- **Non-custodial-first → regulatory-light go-to-market.** This is the decisive structural advantage for a solo founder. The product *advises/executes-with-client-keys*; the client never surrenders custody. That dodges the money-transmitter/custody burden, and aligns with the 2026 regulatory wind: the SEC's Sept-2025 no-action letter and the CFTC's self-custodial-wallet no-action letter both signal that **self-custody is the favored compliance path** ([IQ-EQ, 2026](https://iqeq.com/insights/the-secs-no-action-letter-on-crypto-custody-what-advisers-and-funds-need-to-know/); [Jenner & Block, 2026](https://www.jenner.com/en/news-insights/client-alerts/cftc-no-action-letter-for-self-custodial-crypto-wallet-reflects-shift-in-regulatory-approach)). Critically, the **GENIUS Act prohibits *payment* stablecoin issuers from paying yield** ([Congress.gov S.1582](https://www.congress.gov/bill/119th-congress/senate-bill/1582/text); [OCC Bulletin 2026-3](https://occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-3.html)) — which *pushes* treasuries away from "just hold a yield-bearing stablecoin" and toward **external optimized allocation** like this product. The regulatory tide is a tailwind, not a headwind, for non-custodial advisory yield.
- **Bit-identical backtest/production decision modules + full reproducibility envelope (128/128 tests, GitHub + HuggingFace dataset, Prometheus observability, append-only audit).** Against discretionary curators whose models are closed, the product can *prove* its rule did what it claims — a credible-neutrality pitch to risk-averse DAO governance and institutional allocators.

### Honest competitive risks (do not paper over)

- **Aera is the most dangerous neighbor.** It is already non-custodial, already targets DAO treasuries, and is backed by Gauntlet + Bain Capital Crypto. If Aera ships a focused gas-aware cross-lending stablecoin strategy, the gap narrows fast. The product's defensibility is *narrowness + transparency + per-block event-time*, not the non-custodial model alone.
- **Curated Morpho vaults could go cross-protocol.** Gauntlet/Steakhouse have the capital and credibility; nothing stops a "cross-venue" curated vault. First-mover on the transparent closed-form rule + reproducibility envelope is the defense.
- **Fee-per-dollar is thin.** Charging on *outperformance over passive* (+1.5–2.8pp), not gross AUM, means the business needs **size** (institutional mandates) to be meaningful — which the product's own thesis already acknowledges (edge grows as gas amortizes over larger positions). The ICP must skew institutional, not long-tail DAO.
- **Gas/MEV not yet wired in the backtest.** Until real gas and Flashbots routing are in production, the live net edge at small size is unproven and gas-bounded. This is the single biggest "show-me" for any user conversation.

---

## Sources

- [KuCoin — Stablecoin liquidity hits $320.6B, May 2026](https://www.kucoin.com/blog/Stablecoin-Liquidity-Hits-$320B-Milestone-in-May-2026)
- [DefiLlama — Stablecoins](https://defillama.com/stablecoins) · [DefiLlama — Lending protocols](https://defillama.com/protocols/lending)
- [CoinDesk Research — Productive Stablecoins: Closing the $300B Efficiency Gap, 2026](https://www.coindesk.com/research/productive-stablecoins-closing-the-usd300b-efficiency-gap)
- [Eco — DAO Treasury Management 2026](https://eco.com/support/en/articles/14799687-dao-treasury-management-onchain-governance-spend) · [Eco — Best DeFi Lending Protocols 2026](https://eco.com/support/en/articles/14800882-best-defi-lending-protocols-2026-tvl-rates-risk) · [Eco — Best Stablecoin Vaults 2026](https://eco.com/support/en/articles/14745618-best-stablecoin-vaults-in-2026) · [Eco — Morpho Explained 2026](https://eco.com/support/en/articles/13064566-morpho-protocol-explained-2026)
- [Alphapoint — Stablecoin Treasury Management for Institutions 2026](https://alphapoint.com/blog/stablecoin-treasury-management-for-institutions-the-definitive-2026-guide)
- [defiprime — Complete Guide to DeFi Vaults 2026](https://defiprime.com/defi-vaults-guide) · [defiprime — yvUSD](https://defiprime.com/yvusd-yearn-stablecoin-vault)
- [Aera Finance](https://www.aera.finance/) · [Aera docs — Treasury Management](https://docs.aera.finance/aera-for-treasury-management)
- [Veda — ether.fi Liquid partnership](https://veda.tech/blog/partnership-announcement-etherfi) · [PRNewswire — Veda $18M raise / $3.7B platform](https://www.prnewswire.com/news-releases/veda-raises-18m-led-by-coinfund-to-bring-institutional-grade-defi-yield-to-consumer-apps-through-3-7b-vault-platform-302488185.html) · [The Block — Veda/Kraken/Privy](https://www.theblock.co/amp/post/403277/veda-brings-the-vault-stack-behind-kraken-defi-earn-to-privys-2000-plus-developer-teams)
- [DefiLlama — Sommelier](https://defillama.com/protocol/sommelier) · [Somm Finance app](https://app.somm.finance/)
- [Maple Finance](https://maple.finance/) · [DefiLlama — Maple](https://defillama.com/protocol/maple-finance) · [AInvest — Maple path to $5B AUM](https://www.ainvest.com/news/maple-finance-path-100m-arr-5b-aum-high-growth-play-defi-lending-2512/)
- [DefiLlama — Index Coop](https://defillama.com/protocol/index-coop) · [Index Coop](https://www.indexcoop.com/)
- [Idle Finance](https://idle.finance/) · [Idle docs — Perpetual Yield Tranches](https://docs.idle.finance/products/perpetual-yield-tranches/guide)
- [DefiLlama — Notional V3](https://defillama.com/protocol/notional-v3)
- [DefiLlama — Steakhouse Financial](https://defillama.com/protocol/steakhouse-financial) · [DefiLlama — Gauntlet](https://defillama.com/protocol/gauntlet)
- [arXiv 2512.11976 — Institutionalizing risk curation in decentralized credit](https://arxiv.org/html/2512.11976v1)
- [vaults.fyi — Complete list of DeFi vaults, May 2026](https://blog.vaults.fyi/complete-list-of-defi-vaults-yields-updated-daily/)
- [Congress.gov — GENIUS Act S.1582](https://www.congress.gov/bill/119th-congress/senate-bill/1582/text) · [OCC Bulletin 2026-3 — GENIUS Act NPRM](https://occ.treas.gov/news-issuances/bulletins/2026/bulletin-2026-3.html)
- [IQ-EQ — SEC no-action letter on crypto custody](https://iqeq.com/insights/the-secs-no-action-letter-on-crypto-custody-what-advisers-and-funds-need-to-know/) · [Jenner & Block — CFTC self-custodial wallet no-action letter](https://www.jenner.com/en/news-insights/client-alerts/cftc-no-action-letter-for-self-custodial-crypto-wallet-reflects-shift-in-regulatory-approach)