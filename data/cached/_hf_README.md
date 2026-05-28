---
license: cc-by-4.0
language:
- en
tags:
- defi
- ethereum
- lending
- microstructure
- mcdm
- event-time
pretty_name: ICICPE 2026 — Event-Time 6-Way DeFi Lending Panel
size_categories:
- 1M<n<10M
---

# ICICPE 2026 — Event-Time 6-Way DeFi Lending Panel

Per-block (≈12 s grid) panel of USDC supply markets across the six largest
Ethereum-L1 lending protocols (Aave V3, Compound V3, Spark, Morpho Blue,
Euler V2, Fluid; ~67 % of ~$54 B TVL), Nov 2024 → Apr 2026.

This dataset is the headline input table for:

> **"Event-Time MCDM Allocation across DeFi Lending Protocols:
> An HFT-Inspired Methodology with Walk-Forward Validation."**
> Sergei Solovev, WorldQuant University, 2026 (ICICPE SCOPUS Vol-2).

Paper repository (reproducible end-to-end pipeline, T1/T2/T3 training
artefacts, walk-forward equity parquets, Institutional Dossier):
<https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi>

Production live agent (per-block loop, Flashbots private mempool,
Tier 5 observability):
<https://github.com/SergeySolovyev/event-time-mcdm-agent>

## File

`per_block_panel.parquet` (≈72 MB) — one row per Ethereum block, columns:

| Family | Columns | Notes |
|---|---|---|
| Index | `block_number`, `timestamp` | Ethereum L1 mainnet |
| Per-protocol supply APR | `aave_apy`, `compound_apy`, `spark_apy`, `morpho_apy`, `euler_apy`, `fluid_apy` | annualized, decimal |
| Per-protocol utilization | `aave_util`, `compound_util`, … | 0–1 |
| Per-protocol TVL | `aave_tvl`, `compound_tvl`, … | USDC, no decimals |
| F1 lead-rate | `dsr_rate`, `dsr_rate_lag_300`, `dsr_rate_lag_1800` | Maker DSR + lagged |
| F3 fragmentation | `top_apy`, `top_protocol`, `spread_top_runner_up`, pairwise `spread_{i}_{j}` | computed columns |
| F4 related | `eth_usd`, `gas_log10`, `usdc_peg_dev` | gas placeholder `25 gwei` const (see Limitations §VII (ii) in paper) |

## Build

The panel is produced by stitching per-event subgraph/RPC fetches onto a
uniform per-block grid. Source code lives in the paper repo under
`data/build_per_block_panel.py`. Reproduce with:

```bash
git clone https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi
cd icicpe-2026-event-time-mcdm-defi
python -m scripts.finalize_6way_pipeline
```

## Citation

```bibtex
@misc{solovev2026eventtime,
  author = {Sergei Solovev},
  title  = {Event-Time MCDM Allocation across DeFi Lending Protocols},
  year   = {2026},
  note   = {ICICPE 2026 SCOPUS Vol-2 submission; per-block panel and
            walk-forward equity parquets at HuggingFace Datasets
            \texttt{sssolovjov/icicpe-2026-defi-panel}},
}
```

## License

Released under CC-BY-4.0 — free use with attribution.
