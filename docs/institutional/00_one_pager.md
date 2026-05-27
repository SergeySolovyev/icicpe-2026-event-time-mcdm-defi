# DeFi Lending Allocator — One-Pager

**Strategy**: Event-time gas-aware multi-protocol allocator across
the six largest Ethereum L1 USDC lending markets — **Aave V3,
Compound V3, Spark, Morpho Blue, Euler V2, Fluid Finance** (~$36B
of $54B addressable TVL, ~67% coverage of the design universe).
**Test window**: January – April 2026 (4 months, 864,000 blocks).
**Walk-forward**: 6 non-overlapping 3-month windows, Nov 2024 – Apr 2026.

## Headline numbers (on $1M position)

| Metric | T1 (this strategy) | B1 (Aave hold) |
|---|---:|---:|
| **Net APY** | 4.56% | 3.23% |
| **Sharpe (annualized, daily)** | 36.09 | 29.34 |
| **Sortino** | ∞ | ∞ |
| **Calmar** | ∞ | ∞ |
| **Max DD** | 0.0% | 0.0% |
| **Information Ratio vs B1** | 9.94 | — |

## Walk-forward 6-protocol N×M verdict (binding metric: net APY)

Paired bootstrap across 6 non-overlapping 3-month windows, B=10,000
resamples, seed=42. 3 active policies × 6 protocol-holds = 18
contrasts. Cells: mean ΔAPY (pp), one-sided p, wins/6 windows.

| Policy | vs Aave | vs Compound | vs Spark | vs Morpho | vs Fluid | vs Euler |
|---|---:|---:|---:|---:|---:|---:|
| **T1** threshold | **+1.84pp**<br>6/6, p=0.00 | **+1.65pp**<br>6/6, p=0.00 | **+0.80pp**<br>5/6, p=0.03 | **+1.61pp**<br>6/6, p=0.00 | **+1.65pp**<br>6/6, p=0.00 | +0.48pp<br>2/6, p=0.20 |
| **T2** OU stopping | **+1.63pp**<br>6/6, p=0.00 | **+1.45pp**<br>6/6, p=0.00 | +0.60pp<br>5/6, p=0.08 | **+1.40pp**<br>6/6, p=0.00 | **+1.45pp**<br>6/6, p=0.00 | +0.28pp<br>2/6, p=0.26 |
| **T3** Cox hazard | **+1.84pp**<br>6/6, p=0.00 | **+1.65pp**<br>6/6, p=0.00 | **+0.80pp**<br>5/6, p=0.03 | **+1.61pp**<br>6/6, p=0.00 | **+1.65pp**<br>6/6, p=0.00 | +0.48pp<br>2/6, p=0.20 |

Event-time policies (T1, T2) strongly outperform passive holds of
four of six protocols (Aave V3, Compound V3, Morpho Blue, Fluid)
in all 6 windows, and 5/6 windows on Spark. The only gap is
**Euler V2** — top single-protocol yielder from W3 onward; F3-only
allocation cannot preferentially route to Euler without F1 lead-rate
signal (Maker DSR / Euler-specific leads) or F4 related-instruments
(gas regime, peg deviations). T3 ≡ T1 on F3-only features by
analytical collapse — empirically verified to ±0.01 pp on every cell.

## Capacity

Edge stable up to **\$5M**; degrades meaningfully at **\$25M**;
analytical ceiling **\$50M** per Krause (2005) market-depth bound on
Morpho/Euler pool depths.

## Risk one-liner

Smart-contract risk (Aave V3 + Morpho Blue + Euler V2 audited),
USDC peg risk (Circle issuer), MEV exposure (mitigated via Flashbots
private mempool). Full risk register: ch 05.

**Contact**: Sergei S. Solovev, HSE FCS, sssolovjov@gmail.com