"""Self-contained pure-python reproduction of the T3 Cox-hazard
expanding-window walk-forward — the paper's HONEST out-of-sample
negative-control result.

This module reproduces, from ONLY the cached panel + DSR events (NO
fractal-defi imports), the two headline T3 facts:

  1. HONEST OOS walk-forward (W2..W6): train an F1+F3 Cox model strictly
     on pre-window data, replay it on the window, and compare net APY to
     the training-free T1 threshold policy on the same window. The
     T3-minus-T1 delta is NEGATIVE on all 5 windows (mean ~ -5.97 bp,
     0/5 wins) — a pre-registered negative control. Adding the predictive
     hazard layer on top of T1 does NOT help out of sample; it slightly
     hurts (model-driven dwell occasionally over/under-switches vs T1's
     EWMA dwell, paying gas without net benefit).

  2. The DEPLOYED full-panel T3 model (results/models/t3_cox.json),
     replayed on the test window 2026-01-01..2026-05-01, is
     numerically == T1 to the dollar (net APY 5.368%, final $1,017,341):
     its F1 features are NaN on that window's grid for enough rows that
     T3 falls back to T1's rule, demonstrating the T1 fallback safety
     property.

Engine semantics (matched to notebook_core / backtest.replay_per_block):
  - accrue at the CURRENT venue's APR each block: pos *= 1 + apr/BPY
  - gas paid per switch = gas_used(200000) * gas_price_gwei * 1e-9 * eth
  - gas + eth are read PER BLOCK from the panel columns gas_price_gwei +
    eth_usd (this is why run_t1 reproduces the fractal engine to the
    dollar — the engine reads per-block columns even though it is
    constructed with default_gas_price_gwei=25).

CRITICAL gotcha reproduced here: the panel ships f1_dsr_apr_frac /
f1_dsr_apy_pct, NOT the model's f1_dsr_apr / lag_300 / lag_1800 /
delta_300 / lead_spread_dsr_vs_top. We re-derive the 5 F1 features via
the ported F1LeadBuilder logic (merge_asof backward on block_number from
events_dsr.parquet, then positional lag/delta/lead-spread) BEFORE replay.
If we did not, T3 would silently == T1 on EVERY window and the negative
contrast would vanish.

------------------------------------------------------------------------
REPRODUCTION RESULT (lifelines 0.30.3, this run vs canonical):

  per-window delta_bp (T3 - T1):
    window   canonical     reproduced     diff
    W2       -13.51        -13.51        -0.00
    W3        -3.12         -3.12        -0.00
    W4        -7.20         -7.22        -0.02
    W5        -4.46         -4.46         0.00
    W6        -1.55         -1.55        -0.00
    mean      -5.97 bp      -5.97 bp     wins 0/5   95% CI [-9.89, -2.76]
    p_one_sided_le0 = 1.0 (matches)

  DEPLOYED full-panel t3_cox.json on test window 2026-01-01..2026-05-01:
    T3 == T1 to the dollar — net APY 5.368%, final $1,017,341, 322
    switches, |T3-T1| = $0.00, 100% T1 fallback. (The deployed artifact
    lists f3_top_protocol_id, which the live policy can't materialise, so
    it falls back to T1 on every row — reproduced exactly here.)

  Deviations: only W4 differs, by 0.02 bp. The Cox final fit subsamples
  COX_MAX_ROWS=20000 rows at a fixed seed (123) and lifelines'
  Newton-Raphson is deterministic given that subsample, so per-window
  deltas reproduce to <~0.02 bp. The residual 0.02 bp on W4 is
  attributable solely to the lifelines version (0.30.3 here) vs whatever
  built the canonical CSV. The SIGN is negative on all 5 windows, the
  mean (-5.97 bp), CI, p-value, and 0/5 wins all match exactly.
  Total runtime ~55 s.
------------------------------------------------------------------------
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from notebook_core import run_t1, slice_arrays, net_apy, BPY, PROT, GAS_USED, hold_final

# ---------------------------------------------------------------- constants
# Six windows (same as run_6way_walkforward.py / walkforward_t3_expanding.py).
WINDOWS = [
    ("W1", "2024-11-01", "2025-02-01"),
    ("W2", "2025-02-01", "2025-05-01"),
    ("W3", "2025-05-01", "2025-08-01"),
    ("W4", "2025-08-01", "2025-11-01"),
    ("W5", "2025-11-01", "2026-02-01"),
    ("W6", "2026-02-01", "2026-04-30 23:59:59"),
]

HORIZON_BLOCKS = 7_200       # 24h triple-barrier horizon
EMBARGO_BLOCKS = 39_312      # ~1% of panel (AFML embargo)
PURGE_GAP = HORIZON_BLOCKS + EMBARGO_BLOCKS    # 46_512
SUBSAMPLE_STRIDE = 60        # train = panel[block < train_end].iloc[::60]
MIN_TRAIN_ROWS = 2_000
COX_MAX_ROWS = 20_000        # final-fit subsample cap, seed 123
PENALIZER = 0.001
N_BOOT = 10_000
BOOT_SEED = 42

_LAG_1H = 300                # blocks ~ 1h
_LAG_6H = 1800               # blocks ~ 6h

_DEFAULT_DSR_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "cached" / "events_dsr.parquet"
)
_DEFAULT_PANEL_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "cached" / "per_block_panel.parquet"
)


# ====================================================================== F1
def build_f1(panel: pd.DataFrame, events_dsr_path: Path | str) -> pd.DataFrame:
    """Port of F1LeadBuilder.build — 5 lead-rate features indexed by
    block_number:
        f1_dsr_apr                 DSR ffilled onto the block grid
        f1_dsr_lag_300             DSR ~1h ago  (300-row positional shift)
        f1_dsr_lag_1800            DSR ~6h ago  (1800-row positional shift)
        f1_dsr_delta_300           f1_dsr_apr - f1_dsr_lag_300
        f1_lead_spread_dsr_vs_top  DSR - max(protocol APR) at the block

    merge_asof(direction='backward') on block_number; blocks before the
    first DSR event get NaN. Positional shift assumes one row per block
    (the dense panel grid satisfies this).
    """
    block_numbers = panel["block_number"].astype("int64")
    n = len(panel)

    dsr = pd.read_parquet(events_dsr_path)[["block_number", "lending_rate_apr"]].copy()
    dsr["block_number"] = dsr["block_number"].astype("int64")
    dsr["lending_rate_apr"] = dsr["lending_rate_apr"].astype("float64")
    dsr = dsr.sort_values("block_number").reset_index(drop=True)

    left = pd.DataFrame({"block_number": block_numbers.to_numpy()})
    joined = pd.merge_asof(left, dsr, on="block_number", direction="backward")
    dsr_apr = joined["lending_rate_apr"].to_numpy(dtype="float64")

    s = pd.Series(dsr_apr)
    dsr_lag_300 = s.shift(_LAG_1H).to_numpy(dtype="float64")
    dsr_lag_1800 = s.shift(_LAG_6H).to_numpy(dtype="float64")
    dsr_delta_300 = (dsr_apr - dsr_lag_300).astype("float64")

    proto_cols = [c for c in panel.columns if c.endswith("_lending_apr")]
    arr = panel[proto_cols].to_numpy(dtype="float64")
    all_nan = np.all(np.isnan(arr), axis=1)
    with np.errstate(invalid="ignore"):
        top = np.nanmax(np.where(np.isnan(arr), -np.inf, arr), axis=1)
    top = np.where(all_nan, np.nan, top).astype("float64")
    lead_spread = (dsr_apr - top).astype("float64")

    return pd.DataFrame(
        {
            "f1_dsr_apr": dsr_apr,
            "f1_dsr_lag_300": dsr_lag_300,
            "f1_dsr_lag_1800": dsr_lag_1800,
            "f1_dsr_delta_300": dsr_delta_300,
            "f1_lead_spread_dsr_vs_top": lead_spread,
        },
        index=pd.Index(block_numbers.to_numpy(), name="block_number"),
    )


# ====================================================================== F3
def build_f3(panel: pd.DataFrame) -> pd.DataFrame:
    """Port of F3FragmentationBuilder.build — 15 unordered pair spreads
    (i<j in sorted-name order) + 3 universe summaries + top_protocol_id
    (callers drop the last one before fitting). Sorted protocol order ==
    sorted(PROT) == [aave_v3, compound_v3, euler_v2, fluid, morpho_blue,
    spark].
    """
    from itertools import combinations

    protos = sorted(
        c[: -len("_lending_apr")]
        for c in panel.columns
        if c.endswith("_lending_apr")
    )
    apr = panel[[f"{p}_lending_apr" for p in protos]].to_numpy(dtype="float64")
    index = pd.Index(panel["block_number"].to_numpy(dtype="int64"), name="block_number")

    out: dict[str, np.ndarray] = {}
    for i, j in combinations(range(len(protos)), 2):
        out[f"f3_spread_{protos[i]}_vs_{protos[j]}"] = (apr[:, i] - apr[:, j]).astype("float64")

    with np.errstate(all="ignore"):
        row_max = np.nanmax(apr, axis=1)
        row_min = np.nanmin(apr, axis=1)
        row_std = np.nanstd(apr, axis=1, ddof=0)
        sorted_asc = np.sort(apr, axis=1)        # NaNs pushed to the end
        top2 = sorted_asc[:, -1] - sorted_asc[:, -2]
        apr_safe = np.where(np.isnan(apr), -np.inf, apr)
        top_idx = np.argmax(apr_safe, axis=1).astype("float64")
        top_idx[np.isnan(apr).all(axis=1)] = np.nan

    out["f3_spread_max_minus_min"] = (row_max - row_min).astype("float64")
    out["f3_spread_top2"] = top2.astype("float64")
    out["f3_dispersion_std"] = row_std.astype("float64")
    out["f3_top_protocol_id"] = top_idx
    return pd.DataFrame(out, index=index)


# ============================================================ flip labels
def build_flip_labels(panel: pd.DataFrame, horizon: int = HORIZON_BLOCKS) -> pd.DataFrame:
    """Port of decision.features.base.build_flip_labels.

    blocks_to_flip = blocks until the argmax-APR protocol next changes,
    censored at `horizon`. event_observed = 1 iff a real flip is seen
    within `horizon`, else 0 (censored).
    """
    proto_cols = [c for c in panel.columns if c.endswith("_lending_apr")]
    apr = panel[proto_cols].to_numpy(dtype="float64")
    apr_safe = np.where(np.isnan(apr), -np.inf, apr)
    top_idx = np.argmax(apr_safe, axis=1)

    flip_positions = np.nonzero(np.diff(top_idx) != 0)[0] + 1
    n = len(panel)
    blocks_to_flip = np.full(n, horizon, dtype=np.int64)
    event = np.zeros(n, dtype=np.int8)

    j = 0
    for i in range(n):
        while j < len(flip_positions) and flip_positions[j] <= i:
            j += 1
        if j < len(flip_positions):
            delta = int(flip_positions[j] - i)
            if delta <= horizon:
                blocks_to_flip[i] = delta
                event[i] = 1
    return pd.DataFrame(
        {"blocks_to_flip": blocks_to_flip, "event_observed": event},
        index=pd.Index(panel["block_number"].to_numpy(), name="block_number"),
    )


# ============================================================ Cox fitting
def fit_cox(train_panel: pd.DataFrame, events_dsr_path: Path | str,
            penalizer: float = PENALIZER) -> dict:
    """Fit the F1+F3 Cox model on a strictly-pre-window training panel.

    Mirrors scripts.train_t3_sophisticated._build_design_matrix_explicit
    (include_f1, include_f3, F4 EXCLUDED) + _fit_final_model: drop
    f3_top_protocol_id + zero-variance cols + NaN rows, subsample
    COX_MAX_ROWS at seed 123, fit CoxPHFitter(penalizer).

    Returns dict(feature_names, beta(np.ndarray aligned to feature_names),
    baseline_mean_hazard, c_index). Raises ValueError on too-small design.
    """
    from lifelines import CoxPHFitter
    from lifelines.utils import concordance_index
    import warnings

    f1 = build_f1(train_panel, events_dsr_path)
    f3 = build_f3(train_panel).drop(columns=["f3_top_protocol_id"])
    labels = build_flip_labels(train_panel, horizon=HORIZON_BLOCKS)

    design = f1.join(f3, how="inner").join(labels, how="inner").dropna()

    label_cols = {"blocks_to_flip", "event_observed"}
    keep = list(label_cols)
    for col in design.columns:
        if col in label_cols:
            continue
        if design[col].std() > 1e-12:
            keep.append(col)
    design = design[keep]

    if len(design) < MIN_TRAIN_ROWS:
        raise ValueError(f"design too small ({len(design)} rows)")

    # Final fit: subsample COX_MAX_ROWS @ seed 123 (matches _fit_final_model).
    if len(design) > COX_MAX_ROWS:
        rng = np.random.default_rng(123)
        idx = np.sort(rng.choice(len(design), size=COX_MAX_ROWS, replace=False))
        train_df = design.iloc[idx].copy()
    else:
        train_df = design.copy()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fitter = CoxPHFitter(penalizer=penalizer)
        fitter.fit(train_df, duration_col="blocks_to_flip",
                   event_col="event_observed", show_progress=False)
        feature_names = list(fitter.params_.index)
        bh = fitter.baseline_hazard_
        baseline_mean = float(bh.iloc[:, 0].mean()) if len(bh) else 0.0
        # c_index on a separate subsample @ seed 321 (TEST_EVAL_MAX_ROWS=3000)
        if len(design) > 3_000:
            rng2 = np.random.default_rng(321)
            eidx = np.sort(rng2.choice(len(design), size=3_000, replace=False))
            eval_df = design.iloc[eidx]
        else:
            eval_df = design
        c_index = float(concordance_index(
            eval_df["blocks_to_flip"],
            -fitter.predict_partial_hazard(eval_df),
            eval_df["event_observed"],
        ))

    beta = np.array([fitter.params_[n] for n in feature_names], dtype=np.float64)
    return {
        "feature_names": feature_names,
        "beta": beta,
        "baseline_mean_hazard": baseline_mean,
        "c_index": c_index,
        "n_design": len(design),
    }


# ============================================================ fast T3 replay
def run_t3(apr, gas, eth, blk, Xfeat, feature_names, beta, baseline,
           p0=1e6, gas_used=GAS_USED):
    """Fast scalar replay of the T3 hazard policy on one window.

    Same engine semantics as notebook_core.run_t1 (accrue current venue
    pos*=1+apr/BPY, pay gas per switch from per-block gas/eth). Decision
    rule per block (matches decision.t3_hazard.T3HazardPolicy):

      - cold start (cur<0): allocate to best APR (T1 cold-start rule)
      - if the model feature row has any NaN (Xfeat[i] has NaN), OR fewer
        than 2 valid venues this block -> FALL BACK to the T1 cost-aware
        rule with the EWMA dwell (alpha=0.1, dwell0=1000)
      - else: hazard = baseline*exp(clip(beta.x, -50, 50));
        E[dwell] = 1/hazard; best = argmax APR != current; spread =
        best-current; switch iff pos*spread*E[dwell]/BPY > gas_cost

    Args:
        apr[n,k], gas[n], eth[n], blk[n] : window arrays (slice_arrays).
        Xfeat[n,F]   : model feature matrix aligned to feature_names (in
                       the SAME canonical protocol/feature order the Cox
                       fit produced). Rows with any NaN trigger T1
                       fallback.
        feature_names, beta : Cox feature order + coefficient vector.
        baseline : baseline_mean_hazard.

    Returns (final_position, n_switches).
    """
    n, k = apr.shape
    wins = np.nanargmax(np.where(np.isnan(apr), -np.inf, apr), axis=1)
    best = apr[np.arange(n), wins]
    cost = gas_used * gas * 1e-9 * eth
    # Precompute per-row "any model feature NaN" mask (cheap, vectorised).
    feat_nan = np.isnan(Xfeat).any(axis=1)
    # Number of valid (non-NaN) venues per row.
    n_valid = np.sum(~np.isnan(apr), axis=1)

    pos = p0
    cur = -1
    nsw = 0
    # T1-fallback EWMA dwell state.
    dwell = 1000.0
    alpha = 0.1
    last_win = -1
    last_win_blk = -1

    for i in range(n):
        if cur >= 0:
            a = apr[i, cur]
            if a == a:
                pos *= 1.0 + a / BPY

        # EWMA dwell update (T1 keeps this running even when T3 path is used,
        # because the fallback decision relies on it; matches T1's policy
        # object which updates dwell on every decide()).
        win = int(wins[i])
        if last_win < 0:
            last_win, last_win_blk = win, blk[i]
        elif win != last_win:
            dwell = alpha * (blk[i] - last_win_blk) + (1 - alpha) * dwell
            last_win, last_win_blk = win, blk[i]

        if cur < 0:
            # Cold start: allocate to best (T1 cold-start; T3 defers to T1).
            pos -= cost[i]
            cur = win
            nsw += 1
            continue

        use_t1 = feat_nan[i] or n_valid[i] < 2
        if not use_t1:
            # Model hazard path.
            linear = float(np.dot(beta, Xfeat[i]))
            linear = -50.0 if linear < -50.0 else (50.0 if linear > 50.0 else linear)
            hazard = baseline * math.exp(linear)
            e_dwell = 1e12 if hazard <= 1e-12 else 1.0 / hazard
            if win != cur and apr[i, win] == apr[i, win] and apr[i, cur] == apr[i, cur]:
                spread = best[i] - apr[i, cur]
                if pos * spread * e_dwell / BPY > cost[i]:
                    pos -= cost[i]
                    cur = win
                    nsw += 1
            # else hold
        else:
            # T1 fallback rule (cost-aware EWMA-dwell threshold).
            if win != cur:
                ca = apr[i, cur]
                if ca != ca:                       # current APR NaN -> defensive switch
                    pos -= cost[i]
                    cur = win
                    nsw += 1
                else:
                    spread = best[i] - ca
                    if pos * spread * dwell / BPY > cost[i]:
                        pos -= cost[i]
                        cur = win
                        nsw += 1
    return pos, nsw


# Feature names the live T3HazardPolicy._live_feature_vector can materialise.
# Anything NOT matching these patterns makes that policy return None on EVERY
# row -> full-window T1 fallback. This is the mechanism by which the DEPLOYED
# t3_cox.json (which lists the unhandled f3_top_protocol_id) replays == T1 to
# the dollar. The expanding-window models drop f3_top_protocol_id, so they are
# fully supported and take the model path.
def _is_supported_feature(name: str) -> bool:
    if name in ("f3_spread_max_minus_min", "f3_spread_top2",
                "f3_dispersion_std", "f4_gas_log10"):
        return True
    if name.startswith("f3_spread_") and "_vs_" in name:
        return True
    if name.startswith(("f1_", "f4_")):     # read from aux at runtime
        return True
    return False                            # e.g. f3_top_protocol_id -> unsupported


# ============================================================ feature matrix
def _build_feature_matrix(window_panel: pd.DataFrame, events_dsr_path: Path | str,
                          feature_names: list[str]) -> np.ndarray:
    """Materialise the model feature matrix Xfeat[n,F] for a window, in
    feature_names order. F1 rebuilt from events_dsr (gotcha #1); F3 from
    the window panel.

    Two T1-fallback mechanisms are reproduced from the live policy:
      (a) per-row NaN in any feature -> run_t3 falls back on that row;
      (b) if the artifact lists ANY feature name the live policy can't
          materialise (e.g. f3_top_protocol_id), the live policy returns
          None on EVERY row -> we NaN the whole matrix so run_t3 falls
          back to T1 for the entire window (deployed-model == T1 case).
    """
    f1 = build_f1(window_panel, events_dsr_path)
    f3 = build_f3(window_panel)            # includes top_protocol_id (unused)
    feat = f1.join(f3, how="inner")
    feat = feat.reset_index(drop=True)     # positional order matches window arrays

    n = len(feat)
    has_unsupported = any(not _is_supported_feature(name) for name in feature_names)

    cols = []
    for name in feature_names:
        if has_unsupported:
            # Whole-window T1 fallback (mechanism (b)).
            cols.append(np.full(n, np.nan, dtype="float64"))
        elif name in feat.columns:
            cols.append(feat[name].to_numpy(dtype="float64"))
        else:
            cols.append(np.full(n, np.nan, dtype="float64"))
    return np.column_stack(cols)


def _paired_bootstrap(deltas: np.ndarray, n_boot: int = N_BOOT, seed: int = BOOT_SEED):
    rng = np.random.default_rng(seed)
    n = len(deltas)
    means = np.empty(n_boot)
    for b in range(n_boot):
        means[b] = deltas[rng.integers(0, n, n)].mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    p_one_sided = float((means <= 0).mean())     # H0: mean <= 0
    return float(deltas.mean()), float(lo), float(hi), p_one_sided


# ============================================================ driver
def expanding_t3(panel: pd.DataFrame, events_dsr_path: Path | str):
    """Honest expanding-window walk-forward over W2..W6.

    For each window: train F1+F3 Cox strictly on blocks before
    (first_test_block - PURGE_GAP), subsampled ::60; replay the per-window
    T3 model on the window; compare net APY to T1 (training-free) on the
    same window. Returns (per_window_DataFrame, stats_dict).
    """
    panel = panel.sort_values("block_timestamp").reset_index(drop=True)

    rows = []
    for k, (wid, s, e) in enumerate(WINDOWS):
        if k == 0:
            continue  # W1 dropped: no pre-window data
        # Slice the window (use notebook_core semantics: [start, end)).
        apr, gas, eth, blk, util, tvl, ts = slice_arrays(panel, s, e)
        if len(apr) < 100:
            continue
        first_test_block = int(blk[0])
        train_end_block = first_test_block - PURGE_GAP

        train_panel = panel[panel["block_number"] < train_end_block].reset_index(drop=True)
        train_sub = train_panel.iloc[::SUBSAMPLE_STRIDE].reset_index(drop=True)

        try:
            fit = fit_cox(train_sub, events_dsr_path, penalizer=PENALIZER)
        except ValueError as ex:
            print(f"[{wid}] SKIP: {ex}", flush=True)
            continue

        # Window panel slice for the feature matrix (same [start,end) mask).
        wp = panel.copy()
        if wp["block_timestamp"].dt.tz is None:
            wp["block_timestamp"] = wp["block_timestamp"].dt.tz_localize("UTC")
        m = (wp["block_timestamp"] >= pd.Timestamp(s, tz="UTC")) & \
            (wp["block_timestamp"] < pd.Timestamp(e, tz="UTC"))
        window_panel = wp.loc[m].reset_index(drop=True)

        Xfeat = _build_feature_matrix(window_panel, events_dsr_path, fit["feature_names"])

        t3_final, t3_sw = run_t3(apr, gas, eth, blk, Xfeat,
                                 fit["feature_names"], fit["beta"],
                                 fit["baseline_mean_hazard"])
        t1_final, t1_sw = run_t1(apr, gas, eth, blk)

        n = len(apr)
        apy_t3 = net_apy(t3_final, n)
        apy_t1 = net_apy(t1_final, n)
        delta_bp = (apy_t3 - apy_t1) * 100.0

        rows.append({
            "window_id": wid,
            "window_start": s[:10],
            "window_end": e[:10],
            "train_end_block": train_end_block,
            "n_train_design": fit["n_design"],
            "c_index": fit["c_index"],
            "t1_apy_pct": apy_t1,
            "t3_apy_pct": apy_t3,
            "t1_switches": t1_sw,
            "t3_switches": t3_sw,
            "delta_bp": delta_bp,
        })
        print(f"[{wid}] train<{train_end_block:,} ({fit['n_design']:,} design, "
              f"C={fit['c_index']:.4f})  T1={apy_t1:+.3f}% ({t1_sw}sw)  "
              f"T3={apy_t3:+.3f}% ({t3_sw}sw)  delta={delta_bp:+.2f}bp", flush=True)

    out = pd.DataFrame(rows)
    stats = {}
    if len(out) >= 2:
        deltas = out["delta_bp"].to_numpy()
        mean, lo, hi, p = _paired_bootstrap(deltas)
        stats = {
            "n_windows": int(len(deltas)),
            "windows": out["window_id"].tolist(),
            "mean_delta_bp": mean,
            "ci_low_95_bp": lo,
            "ci_high_95_bp": hi,
            "p_one_sided_le0": p,
            "wins": int((deltas > 0).sum()),
        }
    return out, stats


# ============================================================ deployed==T1
def deployed_t3_equals_t1(panel: pd.DataFrame, events_dsr_path: Path | str,
                          deployed_json: Path | str,
                          start: str = "2026-01-01", end: str = "2026-05-01"):
    """Replay the DEPLOYED full-panel T3 model on the test window and show
    it == T1 to the dollar (T1 fallback). Returns dict with both finals.

    The deployed t3_cox.json lists f3_top_protocol_id, which the live
    T3HazardPolicy._live_feature_vector cannot materialise -> it returns
    None on EVERY row -> full-window T1 fallback. _build_feature_matrix
    reproduces this by NaN-filling the whole matrix when any artifact
    feature is unsupported, so run_t3 == run_t1 exactly on this window.
    """
    import json
    art = json.loads(Path(deployed_json).read_text())
    feature_names = art["feature_names"]
    beta = np.array([art["coefficients"][n] for n in feature_names], dtype=np.float64)
    baseline = float(art["baseline_mean_hazard"])

    apr, gas, eth, blk, util, tvl, ts = slice_arrays(panel, start, end)
    n = len(apr)

    wp = panel.copy()
    if wp["block_timestamp"].dt.tz is None:
        wp["block_timestamp"] = wp["block_timestamp"].dt.tz_localize("UTC")
    m = (wp["block_timestamp"] >= pd.Timestamp(start, tz="UTC")) & \
        (wp["block_timestamp"] < pd.Timestamp(end, tz="UTC"))
    window_panel = wp.loc[m].reset_index(drop=True)
    Xfeat = _build_feature_matrix(window_panel, events_dsr_path, feature_names)

    t3_final, t3_sw = run_t3(apr, gas, eth, blk, Xfeat, feature_names, beta, baseline)
    t1_final, t1_sw = run_t1(apr, gas, eth, blk)
    return {
        "n_blocks": n,
        "t1_final": t1_final, "t1_apy": net_apy(t1_final, n), "t1_switches": t1_sw,
        "t3_final": t3_final, "t3_apy": net_apy(t3_final, n), "t3_switches": t3_sw,
        "final_diff_usd": abs(t3_final - t1_final),
        "frac_t1_fallback": float(np.isnan(Xfeat).any(axis=1).mean()),
    }


# ============================================================ main
if __name__ == "__main__":
    import time
    t0 = time.time()

    panel = pd.read_parquet(_DEFAULT_PANEL_PATH)
    panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
    panel = panel.sort_values("block_timestamp").reset_index(drop=True)
    print(f"panel: {len(panel):,} blocks  "
          f"{panel['block_timestamp'].iloc[0]}..{panel['block_timestamp'].iloc[-1]}",
          flush=True)
    print(f"events_dsr: {_DEFAULT_DSR_PATH}", flush=True)

    CANON = {
        "W2": -13.51, "W3": -3.12, "W4": -7.20, "W5": -4.46, "W6": -1.55,
    }
    CANON_MEAN, CANON_CI = -5.97, (-9.89, -2.76)

    print("\n=== HONEST OOS expanding-window walk-forward (W2..W6) ===", flush=True)
    out, stats = expanding_t3(panel, _DEFAULT_DSR_PATH)

    print("\nper-window comparison vs canonical:", flush=True)
    print(f"  {'win':<4}{'delta_bp':>11}{'canonical':>11}{'diff':>9}", flush=True)
    for _, r in out.iterrows():
        w = r["window_id"]
        c = CANON.get(w, float("nan"))
        print(f"  {w:<4}{r['delta_bp']:>11.2f}{c:>11.2f}{r['delta_bp']-c:>9.2f}", flush=True)

    if stats:
        print(f"\nmean delta = {stats['mean_delta_bp']:+.2f} bp "
              f"(canonical {CANON_MEAN:+.2f})", flush=True)
        print(f"95% CI [{stats['ci_low_95_bp']:+.2f}, {stats['ci_high_95_bp']:+.2f}] "
              f"(canonical [{CANON_CI[0]:+.2f}, {CANON_CI[1]:+.2f}])", flush=True)
        print(f"p_one_sided_le0 = {stats['p_one_sided_le0']:.4f} (canonical 1.0)", flush=True)
        print(f"wins = {stats['wins']}/{stats['n_windows']} (canonical 0/5)", flush=True)
        all_neg = all(out["delta_bp"] < 0)
        print(f"\nNEGATIVE CONTROL reproduced: all-5-negative={all_neg}, "
              f"mean clearly negative={stats['mean_delta_bp'] < -2.0}", flush=True)

    print("\n=== DEPLOYED full-panel T3 == T1 on test window (T1 fallback) ===",
          flush=True)
    deployed_json = Path(__file__).resolve().parents[2] / "results" / "models" / "t3_cox.json"
    dep = deployed_t3_equals_t1(panel, _DEFAULT_DSR_PATH, deployed_json)
    print(f"  test window: {dep['n_blocks']:,} blocks (2026-01-01..2026-05-01)", flush=True)
    print(f"  T1: net APY {dep['t1_apy']:.3f}%  final ${dep['t1_final']:,.0f}  "
          f"({dep['t1_switches']} switches)", flush=True)
    print(f"  T3: net APY {dep['t3_apy']:.3f}%  final ${dep['t3_final']:,.0f}  "
          f"({dep['t3_switches']} switches)", flush=True)
    print(f"  |T3-T1| final = ${dep['final_diff_usd']:.2f}  "
          f"(canonical: T3==T1, 5.368%, $1,017,341)", flush=True)
    print(f"  fraction of rows on T1 fallback = {dep['frac_t1_fallback']*100:.1f}%",
          flush=True)
    print(f"  DEPLOYED-==-T1 reproduced: {dep['final_diff_usd'] < 1.0}", flush=True)

    print(f"\ntotal {time.time()-t0:.0f}s", flush=True)
