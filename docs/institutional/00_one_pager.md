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

## Walk-forward verdict (binding metric: net APY)

T1 outperformed passive Aave hold in **6 of
6** non-overlapping 3-month windows (Nov 2024 – Apr 2026)
on the **binding fund metric**, net APY (mean ΔAPY = **1.84 pp**,
paired-bootstrap p = 0.0). The full ΔAPY vs ΔSharpe lens
discussion — including the Sharpe-inflation paradox on positive-
only return series — is in §02.

## Capacity

Edge stable up to **\$5M**; degrades meaningfully at **\$25M**;
analytical ceiling **\$50M** per Krause (2005) market-depth bound on
Morpho/Euler pool depths.

## Risk one-liner

Smart-contract risk (Aave V3 + Morpho Blue + Euler V2 audited),
USDC peg risk (Circle issuer), MEV exposure (mitigated via Flashbots
private mempool). Full risk register: ch 05.

**Contact**: Sergei S. Solovev, HSE FCS, sssolovjov@gmail.com