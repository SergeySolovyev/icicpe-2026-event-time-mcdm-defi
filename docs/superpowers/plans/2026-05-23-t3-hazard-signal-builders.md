# T3 Hazard Model + Signal Builders F1/F3/F4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Cox / Weibull hazard model T3 that predicts "time-until-cross-protocol-rate-flip" conditioned on three signal-class feature families (F1 lead, F3 fragmentation, F4 related), trains on the per-block panel, exports to ONNX for live-agent reuse, and slots into the same `DecisionPolicy` interface as B1-T2 from Plan B.

**Architecture:** Three independent feature builders read the per-block panel and emit one `<feature_name>.parquet` per family. A training pipeline joins all feature parquets with rate-flip labels (next protocol-flip arrival time), fits a Cox proportional-hazards model (lifelines), exports the linear coefficient vector + baseline-hazard table to ONNX, and a `T3HazardPolicy(DecisionPolicy)` consumes the ONNX in `decide()` to compute `E[remaining_dwell] · spread > gas_cost` switching gate.

**Tech Stack:** Python 3.11 (existing `.venv`), pandas 2.x, numpy, lifelines (Cox/Weibull regression), onnx, onnxruntime, pytest. F2 (mempool order-book dynamics from MacKenzie Table 3.2) is **explicitly deferred** to future work — historic Flashbots mempool snapshots have gaps in 2024 per design-spec risk R1, and we don't want a single dependency to block the paper.

**Source-of-truth grounding:**
- Design spec: `C:\Users\1\.claude\plans\enumerated-scribbling-barto.md`
- Literature: `docs/research/literature-foundation.md` §5 (MacKenzie Table 3.2 signal classes)
- Plan A output: `data/cached/per_block_panel.parquet` (3.93M rows × 10+ cols; full panel pending Kaggle secret-bind)
- Plan B locked interface: `decision/base.py` (`BlockState`, `Action`, `DecisionPolicy`, `BLOCKS_PER_YEAR=2_628_000`)

---

## File map

```
decision/
└── features/
    ├── __init__.py
    ├── base.py                     # NEW: SignalFeatureBuilder ABC + label helpers
    ├── f1_lead.py                  # NEW: DSR + sDAI proxy + Curve 3pool rate lag
    ├── f3_fragmentation.py         # NEW: pairwise cross-protocol spreads (15 pairs for 6-way)
    └── f4_related.py               # NEW: gas regime + stablecoin peg deviations

decision/
├── t3_hazard.py                    # NEW: T3HazardPolicy + ONNX inference loader
└── t3_train.py                     # NEW: training pipeline (lifelines Cox)

backtest/
└── run_signal_ablation.py          # NEW: LOO ablation over F1/F3/F4

results/
├── tables/
│   ├── signal_feature_stats.csv    # one row per feature: mean, std, IC vs label
│   ├── t3_hazard_coefs.csv         # Cox model fitted coefficients with p-values
│   └── signal_ablation.csv         # LOO contribution: T3-with-F_i-only vs full T3
└── models/
    └── t3_cox.onnx                 # serialised T3 model

tests/
├── test_signal_features_base.py    # ABC contract + label helpers
├── test_f1_lead.py                 # DSR & lag-feature correctness
├── test_f3_fragmentation.py        # spread math + sign convention
├── test_f4_related.py              # peg-deviation math + gas-regime quantiles
├── test_t3_train.py                # Cox fit on synthetic, verify HR signs
├── test_t3_hazard_policy.py        # T3HazardPolicy ABC compliance + decide()
└── test_signal_ablation.py         # LOO runner exit-code + CSV shape
```

---

## Canonical feature-frame schema

Every feature builder emits a DataFrame indexed by `block_number` (int64) with the per-block panel's `block_timestamp` (datetime64[ns, UTC]) preserved. **One column per derived feature**, all float64. Examples:

| Builder | Column patterns (example) |
|---|---|
| F1 | `f1_dsr_apr`, `f1_dsr_lag_3600`, `f1_sdai_proxy_apr`, `f1_curve_3pool_apr`, `f1_lead_spread_dsr_vs_aave` |
| F3 | `f3_spread_aave_vs_compound`, `f3_spread_aave_vs_morpho`, …, `f3_spread_max_minus_min`, `f3_dispersion_std` |
| F4 | `f4_gas_gwei`, `f4_gas_log10`, `f4_gas_quantile_30d`, `f4_eth_usd`, `f4_usdc_peg_dev_bps`, `f4_usdt_peg_dev_bps` |

Validator (`decision.features.base.validate_feature_frame`):
1. Index name == `"block_number"`, dtype `int64`, monotonic.
2. `block_timestamp` column present, tz-aware UTC.
3. All other columns float64.
4. Column-prefix matches builder family (e.g. `f1_*` for F1 builder).
5. NaN allowed per cell, but warn if any column is 100% NaN (likely a fetcher gap).

---

## Task 1: Feature schema + ABC + label helper

**Files:**
- Create: `decision/features/__init__.py`
- Create: `decision/features/base.py`
- Create: `tests/test_signal_features_base.py`

The shared contract: every feature builder is a callable `build(panel: pd.DataFrame) -> pd.DataFrame` returning the canonical feature-frame shape above. Plus a label helper `build_flip_labels(panel, *, horizon_blocks)` that emits the supervised target for T3 training (next-protocol-flip block lag).

- [ ] **Step 1: Write failing test** (`tests/test_signal_features_base.py`)

```python
import pandas as pd
import pytest
from decision.features.base import (
    SignalFeatureBuilder, validate_feature_frame, build_flip_labels,
)


def _mini_panel(n=300):
    """3-protocol toy panel with rate-flips at known blocks."""
    block = list(range(1_000_000, 1_000_000 + n))
    ts = pd.date_range("2025-01-01", periods=n, freq="12s", tz="UTC")
    a = [0.04] * 100 + [0.06] * 100 + [0.04] * 100
    b = [0.05] * n
    c = [0.045] * n
    return pd.DataFrame({
        "block_number": block,
        "block_timestamp": ts,
        "aave_v3_lending_apr": a,
        "compound_v3_lending_apr": b,
        "morpho_blue_lending_apr": c,
    })


class _DummyF1(SignalFeatureBuilder):
    family = "f1"
    def build(self, panel):
        return pd.DataFrame(
            {"f1_dummy": [1.0] * len(panel)},
            index=pd.Index(panel["block_number"], name="block_number"),
        ).assign(block_timestamp=panel["block_timestamp"].values)


def test_builder_must_set_family():
    class NoFamily(SignalFeatureBuilder):
        def build(self, panel):
            return pd.DataFrame()
    with pytest.raises(NotImplementedError, match="family"):
        NoFamily()


def test_validate_passes_canonical_frame():
    df = _DummyF1().build(_mini_panel())
    validate_feature_frame(df, expected_family="f1")


def test_validate_rejects_wrong_prefix():
    df = _DummyF1().build(_mini_panel()).rename(columns={"f1_dummy": "f3_oops"})
    with pytest.raises(ValueError, match="prefix"):
        validate_feature_frame(df, expected_family="f1")


def test_validate_rejects_non_float64_value_column():
    df = _DummyF1().build(_mini_panel())
    df["f1_dummy"] = df["f1_dummy"].astype("int32")
    with pytest.raises(ValueError, match="float64"):
        validate_feature_frame(df, expected_family="f1")


def test_build_flip_labels_basic_shape():
    """Flip label = blocks until the top-APR protocol changes. With
    aave going 4 -> 6 -> 4, top protocol flips from compound to aave
    at block 100, then aave back to compound at block 200."""
    panel = _mini_panel()
    labels = build_flip_labels(panel, horizon_blocks=500)
    assert "blocks_to_flip" in labels.columns
    assert "event_observed" in labels.columns
    # Right before the 100->aave flip, blocks_to_flip should be small.
    pre_flip = labels.iloc[99]
    assert 0 <= pre_flip["blocks_to_flip"] <= 1
    assert pre_flip["event_observed"] == 1
    # Last 100 blocks: no future flip within horizon -> censored.
    last = labels.iloc[-1]
    assert last["event_observed"] == 0
```

- [ ] **Step 2: Run test (expect ImportError)**

```
.venv\Scripts\pytest tests/test_signal_features_base.py -v
```

- [ ] **Step 3: Implement**

`decision/features/__init__.py`:
```python
"""Signal feature builders for T3 hazard model.

Three families per MacKenzie (2021) Table 3.2 mapped to DeFi:
    f1 (lead)         -- DSR / sDAI / Curve 3pool rate-lead features
    f3 (fragmentation) -- pairwise cross-protocol spreads (dominant signal)
    f4 (related)      -- gas regime + stablecoin peg deviations

F2 (order-book dynamics from mempool) is DEFERRED to future work per
design spec risk R1: historic Flashbots mempool snapshots have gaps
in 2024 and we don't want a single dependency to block the paper.
"""
```

`decision/features/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np


class SignalFeatureBuilder(ABC):
    """Each subclass MUST set class attribute `family` to one of
    {"f1","f3","f4"} -- enforced at __init__ time."""
    family: str = ""

    def __init__(self) -> None:
        if not self.family:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set `family` class attr "
                f"(one of 'f1', 'f3', 'f4')"
            )

    @abstractmethod
    def build(self, panel: pd.DataFrame) -> pd.DataFrame:
        """Return feature-frame indexed by block_number with
        block_timestamp column + one float64 column per derived feature.
        All value-column names MUST start with `self.family + '_'`.
        """


def validate_feature_frame(df: pd.DataFrame, *, expected_family: str) -> None:
    if df.index.name != "block_number":
        raise ValueError(
            f"feature frame index must be named 'block_number', "
            f"got {df.index.name!r}"
        )
    if df.index.dtype != "int64":
        raise ValueError(f"index dtype must be int64, got {df.index.dtype}")
    if "block_timestamp" not in df.columns:
        raise ValueError("feature frame must have 'block_timestamp' column")
    ts = df["block_timestamp"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        raise ValueError("block_timestamp must be datetime")
    if getattr(ts.dt, "tz", None) is None:
        raise ValueError("block_timestamp must be tz-aware UTC")

    value_cols = [c for c in df.columns if c != "block_timestamp"]
    expected_prefix = expected_family + "_"
    for col in value_cols:
        if not col.startswith(expected_prefix):
            raise ValueError(
                f"feature column {col!r} missing prefix {expected_prefix!r}"
            )
        if df[col].dtype != "float64":
            raise ValueError(
                f"feature column {col!r} must be float64, "
                f"got {df[col].dtype}"
            )


def build_flip_labels(
    panel: pd.DataFrame,
    *,
    horizon_blocks: int,
) -> pd.DataFrame:
    """Survival labels for T3: at each block, blocks until the next
    top-APR-protocol change OR horizon_blocks (censored).

    Returns a DataFrame indexed by block_number with two columns:
        blocks_to_flip   int64   blocks until next flip (or horizon)
        event_observed   int8    1 = real flip seen, 0 = censored
    """
    proto_cols = [c for c in panel.columns if c.endswith("_lending_apr")]
    if len(proto_cols) < 2:
        raise ValueError("need >=2 protocol APR columns to compute flips")

    # Argmax over protocol APRs per block -> "current top protocol".
    apr = panel[proto_cols].to_numpy()
    # Treat NaN as -inf so it's never argmax winner.
    apr_safe = np.where(np.isnan(apr), -np.inf, apr)
    top_idx = np.argmax(apr_safe, axis=1)

    # Flip = top_idx[t] != top_idx[t-1].
    flips = np.diff(top_idx) != 0
    flip_positions = np.where(flips)[0] + 1  # block-relative positions of flips

    n = len(panel)
    blocks_to_flip = np.full(n, horizon_blocks, dtype=np.int64)
    event = np.zeros(n, dtype=np.int8)

    j = 0  # pointer into flip_positions
    for i in range(n):
        while j < len(flip_positions) and flip_positions[j] <= i:
            j += 1
        if j < len(flip_positions):
            delta = int(flip_positions[j] - i)
            if delta <= horizon_blocks:
                blocks_to_flip[i] = delta
                event[i] = 1
            # else: stays at horizon_blocks censor value

    return pd.DataFrame(
        {"blocks_to_flip": blocks_to_flip, "event_observed": event},
        index=pd.Index(panel["block_number"], name="block_number"),
    )
```

- [ ] **Step 4: Run test, expect 5/5 pass**

- [ ] **Step 5: Commit**

```bash
git add decision/features/__init__.py decision/features/base.py tests/test_signal_features_base.py
git commit -m "T3 signal feature ABC + flip-label helper (Plan C Task 1)

Locks the contract for the 3 parallel feature builders (F1 lead, F3
fragmentation, F4 related). Same lock-then-fork pattern as Plan A's
event_schema.py and Plan B's decision/base.py: shared interface
committed BEFORE the parallel subagents fork.

build_flip_labels: emits supervised survival targets (blocks_to_flip,
event_observed) computed by argmax over <proto>_lending_apr columns
per block, with horizon_blocks censoring. This is the y for the Cox
regression in Task 5."
```

---

## Task 2: F1 lead features (DSR + sDAI + Curve 3pool)

**Files:**
- Create: `decision/features/f1_lead.py`
- Create: `tests/test_f1_lead.py`

F1 = MacKenzie's "futures lead" class. In DeFi: the Maker DSR (already in Plan A's `events_dsr.parquet`) leads Aave/Compound USDC supply rates by ~1-6 hours per Gudgeon (2020). sDAI exchange rate is a proxy for DSR. Curve 3pool's swap rate proxies the marginal stablecoin holder's expected return.

This builder reads the per-block panel + the `events_dsr.parquet` and produces these features:

| Column | Meaning |
|---|---|
| `f1_dsr_apr` | Current DSR rate (forward-filled onto block grid) |
| `f1_dsr_lag_300` | DSR rate 300 blocks (~1 hour) ago |
| `f1_dsr_lag_1800` | DSR rate 1800 blocks (~6 hours) ago |
| `f1_dsr_delta_300` | `f1_dsr_apr - f1_dsr_lag_300` |
| `f1_lead_spread_dsr_vs_top` | DSR minus the max protocol APR (positive = DSR is a better rate) |

`f1_sdai_proxy_apr` and `f1_curve_3pool_apr` are stubbed for Plan C; full implementation in a follow-up since they require additional fetchers (also subgraph-based, low risk).

- [ ] **Step 1: Write failing test** (~6 tests covering shape + lag correctness + DSR injection)
- [ ] **Step 2: Confirm fail**
- [ ] **Step 3: Implement** following the pattern in `decision/features/base.py`
- [ ] **Step 4: Confirm pass**
- [ ] **Step 5: Commit per the message in the plan-doc**

(Full TDD code body identical-pattern to Task 1; see line-counts assumption ~250 LOC + 150 LOC tests.)

---

## Task 3: F3 fragmentation features (dominant signal)

**Files:**
- Create: `decision/features/f3_fragmentation.py`
- Create: `tests/test_f3_fragmentation.py`

F3 = same instrument on multiple venues. Cross-protocol spread is the **single most important signal** per design spec (it IS our decision variable). 6 protocols → 15 unordered pairs.

| Column | Meaning |
|---|---|
| `f3_spread_<i>_vs_<j>` | one column per pair, lending_apr difference |
| `f3_spread_max_minus_min` | top APR − bottom APR (universe dispersion) |
| `f3_spread_top2` | top APR − runner-up APR (immediate switching signal) |
| `f3_dispersion_std` | std of all available protocol APRs at this block |
| `f3_top_protocol_id` | int8 index into the sorted protocol list (categorical encoding) |

Crucial: handle NaN — if only Morpho + Euler columns are present (partial panel), only 1 pair (`f3_spread_morpho_blue_vs_euler_v2`) is produced. The builder reads available protocols from the panel and adapts dynamically — same pattern as the replay engine in Plan B.

5 tests: dynamic-protocol-discovery / spread-sign-convention / top2-equals-max-minus-runner-up / dispersion-zero-with-1-protocol / int8-top-protocol-encoding.

---

## Task 4: F4 related features (gas + peg deviations)

**Files:**
- Create: `decision/features/f4_related.py`
- Create: `tests/test_f4_related.py`

F4 = correlated instruments. For DeFi-lending switching: ETH price (drives gas), gas regime (peg-30day-quantile), stablecoin pegs (USDC/USDT/DAI deviations signal stress).

| Column | Meaning |
|---|---|
| `f4_gas_gwei` | per-block gas price (from panel) |
| `f4_gas_log10` | log10 transform (gas is right-skewed) |
| `f4_gas_quantile_30d` | rank of current gas vs trailing 30 days [0,1] |
| `f4_eth_usd` | ETH/USD price (Chainlink) |
| `f4_usdc_peg_dev_bps` | (USDC mid-price − 1.0) × 10_000 |

**Top-LP wallet activity** mentioned in the design spec is DEFERRED (requires per-pool subgraph queries that risk cost overruns). Note in `__doc__`.

5 tests: gas-log-transform / 30day-quantile-trailing / peg-dev-zero-at-1.0 / nan-safety / column-prefix.

---

## Task 5: T3 hazard training pipeline

**Files:**
- Create: `decision/t3_train.py`
- Create: `tests/test_t3_train.py`

Loads the per-block panel + all three feature-frames + flip labels, fits a Cox proportional-hazards model with `lifelines`, exports coefficient vector + baseline-hazard table to a JSON sidecar AND to ONNX (a thin "linear projection + lookup" graph because Cox at inference time = exp(β'x) × baseline survival).

Training-time invariants:
- Purged k-fold (k=5) per López de Prado AFML Ch 7 (Plan A literature foundation §4)
- Embargo = 0.01 × T = ~26 hours of blocks (5.4 days at hourly resolution, scaled)
- Sample-uniqueness weights (overlap-driven, AFML §4.3)
- DSR (Deflated Sharpe Ratio) used in §6 of Plan D, NOT here
- C-index reported, target ≥ 0.55

5 tests: synth-data-recovery-of-known-coefs / censoring-handled / nan-rows-dropped / onnx-export-roundtrip-numerical-parity / c-index-positive-on-synth.

---

## Task 6: T3HazardPolicy + ONNX inference

**Files:**
- Create: `decision/t3_hazard.py`
- Create: `tests/test_t3_hazard_policy.py`

`T3HazardPolicy(DecisionPolicy)` — same `decide(state) -> Action` interface as T1/T2. At each block:
1. Build the live feature vector x_t from the BlockState (mini-reuse of F1/F3/F4 builders, but at single-block granularity).
2. ONNX-infer hazard `λ(t|x_t) = λ₀ · exp(β'x_t)`.
3. Compute `E[remaining_dwell] ≈ 1/λ` (Weibull baseline) or `E[remaining_dwell] = ∫S(τ)dτ` (Cox baseline integration).
4. Switch iff `E[remaining_dwell] · spread > gas_cost_usd / position_usd`.

6 tests: ABC compliance (DecisionPolicy subclass) / cold-start-defers-to-T1 / switch-when-hazard-low / hold-when-hazard-high / ONNX-loaded-from-file-path / decide-is-deterministic.

---

## Task 7: Signal LOO ablation

**Files:**
- Create: `backtest/run_signal_ablation.py`
- Create: `tests/test_signal_ablation.py`

LOO (Leave-One-Out) ablation: retrain T3 with {F1+F3+F4}, {F3+F4}, {F1+F4}, {F1+F3}, report C-index and net-APY contribution per family. **Hypothesis (paper §V): F3 dominates F1 and F4** — the cross-protocol spread itself is the strongest predictor of when it will close.

CSV output `results/tables/signal_ablation.csv`:
```
ablation,c_index,net_apy_pct,delta_apy_vs_full
T3_full        0.612  6.31%   +0.00pp
T3_no_F1       0.609  6.18%   -0.13pp
T3_no_F3       0.541  4.52%   -1.79pp  <- F3 dominant
T3_no_F4       0.605  6.21%   -0.10pp
T3_F3_only     0.598  6.05%   -0.26pp
```

3 tests: ablation-csv-shape / c-index-monotonic-with-features / runner-handles-missing-feature-family.

---

## Plan summary

| Task | Owner | Deps | LOC | Time |
|---|---|---|---|---|
| C1 schema + ABC + label helper | inline | none | ~250 | 30 min |
| C2 F1 lead | subagent | C1 | ~250 | 15 min |
| C3 F3 fragmentation | subagent | C1 | ~250 | 15 min |
| C4 F4 related | subagent | C1 | ~250 | 15 min |
| C5 T3 train | subagent | C2+C3+C4 | ~400 | 25 min |
| C6 T3 policy + ONNX infer | subagent | C5 | ~300 | 20 min |
| C7 signal LOO ablation | inline | C5+C6 | ~200 | 15 min |
| **Total** | mixed | | ~1900 | ~2 h |

**Critical path:** C1 → {C2,C3,C4 parallel} → C5 → C6 → C7.

**Validation gate:** signal ablation must show F3 contributes ≥1 pp APY vs F1+F4 alone (per design spec §III.D); C-index ≥ 0.55 on the validation slice.

**Execution handoff:** Recommend subagent-driven-development with the 3 feature builders dispatched in parallel after C1 lands. C5+C6 are serial deps (C5 trains, C6 consumes). C7 is inline because it requires the live ONNX file + 4 fresh training runs.
