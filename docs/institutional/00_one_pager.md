# DeFi Lending Allocator — One-Pager

**Strategy**: Event-time gas-aware multi-protocol allocator across
Ethereum L1 USDC lending pools (Aave V3 + Morpho Blue + Euler V2).
**Test window**: January – April 2026 (4 months, 864,000 blocks).

## Headline numbers (on $1M position)

| Metric | T1 (this strategy) | B1 (Aave hold) |
|---|---:|---:|
| **Net APY** | 4.56% | 3.23% |
| **Sharpe (annualized, daily)** | 36.09 | 29.34 |
| **Sortino** | ∞ | ∞ |
| **Calmar** | ∞ | ∞ |
| **Max DD** | 0.0% | 0.0% |
| **Information Ratio vs B1** | 9.94 | — |

## Walk-forward N×M verdict (binding metric: net APY, 6 windows)

**Scope**: 3 of 6 designed protocols in panel (Aave V3 + Morpho Blue
+ Euler V2; Compound/Spark/Fluid + DSR signal queued for extension).
Paired bootstrap across 6 non-overlapping 3-month windows
(Nov 2024 – Apr 2026), B=10,000 resamples, seed=42.

| Policy | vs Aave hold | vs Morpho hold | vs Euler hold |
|---|---:|---:|---:|
| **T1** threshold | **+1.83pp** (6/6, p=0.00) | **+1.60pp** (6/6, p=0.00) | +0.48pp (2/6, p=0.20) |
| **T2** OU stopping | **+1.62pp** (6/6, p=0.00) | **+1.39pp** (6/6, p=0.00) | +0.27pp (2/6, p=0.27) |
| B4 MCDM-EMA (hourly) | **+0.92pp** (6/6, p=0.00) | +0.68pp (5/6, p=0.05) | −0.44pp (2/6, p=0.76) |

Event-time policies (T1, T2) strongly outperform passive Aave V3 and
Morpho Blue holds in 6/6 windows (~$25B addressable TVL of in-scope
universe). No policy outperforms passive Euler V2 hold without F1
lead-rate signal (journal-extension scope, Vol-2 §VII). T3 hazard
collapses to T1 on F3-only features by analytical reduction; full
ladder requires F1+F4 panel extension.

## Capacity

Edge stable up to **\$5M**; degrades meaningfully at **\$25M**;
analytical ceiling **\$50M** per Krause (2005) market-depth bound on
Morpho/Euler pool depths.

## Risk one-liner

Smart-contract risk (Aave V3 + Morpho Blue + Euler V2 audited),
USDC peg risk (Circle issuer), MEV exposure (mitigated via Flashbots
private mempool). Full risk register: ch 05.

**Contact**: Sergei S. Solovev, HSE FCS, sssolovjov@gmail.com