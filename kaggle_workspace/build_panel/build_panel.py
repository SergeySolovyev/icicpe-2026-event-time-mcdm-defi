"""Kaggle CPU kernel: build the per-block event-time panel.

Pulls 18 months of rate-update events from 7 sources:
    Aave V3, Spark, Compound V3, Morpho Blue, Fluid, Euler V2, Maker DSR
and stitches them onto a uniform per-block grid covering
2024-11-01 .. 2026-05-01 (~3.9 M blocks at 12 s/block).

Output: /kaggle/working/per_block_panel.parquet  (~150-250 MB)
        plus per-protocol events_<proto>.parquet for debugging.

Wall-clock estimate: 30-60 min (subgraph latency dominates).

The dataset slug 'sergeisolovyev/predictive-mcdm-defi-artifacts' must
include the new fetcher+stitcher modules (built locally and uploaded via
`kaggle datasets version`). The legacy data/cached/joined_clean.parquet
stays in the same dataset so the kernel can run a quick parity sanity
check at the end (5 bp tolerance on Aave/Compound APR hourly resample).

Required Kaggle secrets:
    THE_GRAPH_API_KEY    -- TheGraph gateway key for Aave/Spark
    ETHEREUM_RPC_URL     -- Alchemy / publicnode / Ankr archive RPC
"""
import os
import sys
import time
import traceback
from pathlib import Path


# -------------------------------------------------------------------------
# 1. Checkpoint files (mirror of v9 training kernel pattern). Each touched
#    file is visible in the Kaggle output — diagnoses crashes that the
#    Kaggle CLI doesn't always surface.
# -------------------------------------------------------------------------
_CKPT_DIR = Path("/kaggle/working/checkpoints")
_CKPT_DIR.mkdir(parents=True, exist_ok=True)


def _ck(name: str) -> None:
    (_CKPT_DIR / name).touch()
    print(f"[CK] {name}", flush=True)


_ck("00_started")


# -------------------------------------------------------------------------
# 2. Locate the input dataset (Kaggle auto-extracts ZIP datasets — files
#    live at /kaggle/input/<slug>/...).  Resolve dynamically via parquet
#    anchor.
# -------------------------------------------------------------------------
_anchors = list(
    Path("/kaggle/input").rglob("data/cached/joined_clean.parquet")
)
if not _anchors:
    raise RuntimeError(
        f"joined_clean.parquet not found under /kaggle/input/. "
        f"Contents: {[p.name for p in Path('/kaggle/input').iterdir()]}"
    )
parquet = _anchors[0]
PROJECT_ROOT = parquet.parent.parent.parent  # .../data/cached/x.parquet → root
print(f"[input] resolved PROJECT_ROOT = {PROJECT_ROOT}", flush=True)

py_files = list(PROJECT_ROOT.rglob("*.py"))
print(
    f"[input] {len(py_files)} .py files; "
    f"legacy parquet {parquet.stat().st_size / 1e6:.2f} MB",
    flush=True,
)

sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)
_ck("01_input_resolved")


# -------------------------------------------------------------------------
# 3. Dep install. Kaggle has pandas + pyarrow + requests already; we add
#    eth-utils (for keccak in DSR + Fluid).
# -------------------------------------------------------------------------
import subprocess

subprocess.check_call(
    [sys.executable, "-m", "pip", "install", "-q", "eth-utils"]
)
print("[deps] eth-utils installed", flush=True)
_ck("02_deps")


# -------------------------------------------------------------------------
# 4. Secrets — THE_GRAPH_API_KEY + ETHEREUM_RPC_URL must be attached to
#    the kernel via "Add-ons → Secrets".  Falling back to env vars in
#    case the kernel was launched manually with them already set.
# -------------------------------------------------------------------------
try:
    from kaggle_secrets import UserSecretsClient

    _sec = UserSecretsClient()
    for k in ("THE_GRAPH_API_KEY", "ETHEREUM_RPC_URL"):
        if not os.environ.get(k):
            try:
                os.environ[k] = _sec.get_secret(k)
                print(f"[secret] {k} loaded from Kaggle vault", flush=True)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[secret] {k} NOT in Kaggle vault ({exc}); "
                    f"some fetchers will skip if env var missing",
                    flush=True,
                )
except ImportError:
    print(
        "[secret] kaggle_secrets unavailable; relying on env vars",
        flush=True,
    )

print(
    f"[secret] THE_GRAPH_API_KEY={'set' if os.environ.get('THE_GRAPH_API_KEY') else 'MISSING'}",
    flush=True,
)
print(
    f"[secret] ETHEREUM_RPC_URL={'set' if os.environ.get('ETHEREUM_RPC_URL') else 'MISSING'}",
    flush=True,
)
_ck("03_secrets")


# -------------------------------------------------------------------------
# 5. Imports — load all 7 fetchers + stitcher + schema.
# -------------------------------------------------------------------------
import pandas as pd

from data.event_schema import validate_event_frame, empty_event_frame
from data.fetch_aave_events import fetch_aave_events_cached
from data.fetch_spark_events import fetch_spark_events_cached
from data.fetch_compound_events import fetch_compound_events_cached
from data.fetch_morpho_events import (
    fetch_morpho_events_cached,
    MORPHO_WSTETH_USDC,
)
from data.fetch_fluid_events import fetch_fluid_events_cached
from data.fetch_euler_events import fetch_euler_events_cached, EULER_PRIME_USDC
from data.fetch_dsr_events import fetch_dsr_events_cached
from data.build_per_block_panel import build_per_block_panel, _ts_to_block

print("[imports] all 7 fetchers + stitcher + schema OK", flush=True)
_ck("04_imports")


# -------------------------------------------------------------------------
# 6. Window — full 18 months Nov 2024 → Apr 2026 (matches 2026c study).
# -------------------------------------------------------------------------
OUT = Path("/kaggle/working")
START = pd.Timestamp("2024-11-01", tz="UTC")
END = pd.Timestamp("2026-05-01", tz="UTC")

BLOCK_START = _ts_to_block(int(START.timestamp()))
BLOCK_END = _ts_to_block(int(END.timestamp()))
N_BLOCKS_EST = BLOCK_END - BLOCK_START
print(
    f"[window] {START} → {END}  ({N_BLOCKS_EST:,} blocks ~12s each)",
    flush=True,
)


# -------------------------------------------------------------------------
# 7. Per-protocol fetch loop. Each protocol's failure does NOT abort the
#    whole build — we want a partial panel rather than a total miss.
#    Failures are logged + recorded as 99_<proto>_FAILED.txt for the
#    operator to inspect.
# -------------------------------------------------------------------------
FETCHERS = [
    (
        "aave_v3",
        lambda: fetch_aave_events_cached(
            START, END, cache_path=OUT / "events_aave.parquet", refresh=True
        ),
    ),
    (
        "spark",
        lambda: fetch_spark_events_cached(
            START, END, cache_path=OUT / "events_spark.parquet", refresh=True
        ),
    ),
    (
        "compound_v3",
        lambda: fetch_compound_events_cached(
            START,
            END,
            sample_every_n_blocks=100,
            cache_path=OUT / "events_compound.parquet",
            refresh=True,
        ),
    ),
    (
        "morpho_blue",
        lambda: fetch_morpho_events_cached(
            market_id=MORPHO_WSTETH_USDC,
            start=START,
            end=END,
            cache_path=OUT / "events_morpho.parquet",
            refresh=True,
        ),
    ),
    (
        "fluid",
        lambda: fetch_fluid_events_cached(
            start=START,
            end=END,
            sample_every_n_blocks=100,
            cache_path=OUT / "events_fluid.parquet",
            refresh=True,
        ),
    ),
    (
        "euler_v2",
        lambda: fetch_euler_events_cached(
            vault=EULER_PRIME_USDC,
            start=START,
            end=END,
            cache_path=OUT / "events_euler.parquet",
            refresh=True,
        ),
    ),
    (
        "dsr",
        lambda: fetch_dsr_events_cached(
            start=START,
            end=END,
            cache_path=OUT / "events_dsr.parquet",
            refresh=True,
        ),
    ),
]

frames: list[pd.DataFrame] = []
fetch_stats: list[dict] = []

for proto, fn in FETCHERS:
    t0 = time.time()
    try:
        print(f"[fetch] {proto} starting...", flush=True)
        df = fn()
        elapsed = time.time() - t0
        nrows = len(df)
        print(
            f"[fetch] {proto:>14}  {nrows:>8,} rows  {elapsed:6.1f} s",
            flush=True,
        )
        # Sanity validation; if a fetcher emits a broken frame we want to
        # know before the stitcher chokes on it.
        if not df.empty:
            validate_event_frame(df)
        frames.append(df)
        fetch_stats.append({"protocol": proto, "n_rows": nrows, "seconds": elapsed, "status": "OK"})
        _ck(f"10_fetch_{proto}_OK")
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        elapsed = time.time() - t0
        print(f"[fetch] {proto:>14}  FAILED after {elapsed:.1f}s:\n{tb}", flush=True)
        (_CKPT_DIR / f"99_{proto}_FAILED.txt").write_text(
            f"protocol={proto}\nelapsed={elapsed:.1f}\n\n{tb}"
        )
        fetch_stats.append({"protocol": proto, "n_rows": 0, "seconds": elapsed, "status": str(exc)[:200]})

_ck("20_all_fetches_done")
print(f"[fetch] total frames: {len(frames)} non-empty / {len(FETCHERS)} attempted", flush=True)


# -------------------------------------------------------------------------
# 8. Persist fetch stats so the operator can inspect even if stitcher OOMs.
# -------------------------------------------------------------------------
pd.DataFrame(fetch_stats).to_csv(OUT / "fetch_stats.csv", index=False)
print("[stats] fetch_stats.csv written", flush=True)


# -------------------------------------------------------------------------
# 9. Stitch.
# -------------------------------------------------------------------------
print(
    f"[stitch] building panel over blocks "
    f"[{BLOCK_START:,}, {BLOCK_END:,})  =  {N_BLOCKS_EST:,} rows",
    flush=True,
)
t0 = time.time()
panel = build_per_block_panel(
    event_frames=frames,
    block_start=BLOCK_START,
    block_end=BLOCK_END,
)
stitch_elapsed = time.time() - t0
print(
    f"[stitch] done in {stitch_elapsed:.1f} s; "
    f"panel: {len(panel):,} rows × {len(panel.columns)} cols",
    flush=True,
)
_ck("30_stitch_done")


# -------------------------------------------------------------------------
# 10. Write the panel. Parquet with snappy compression is the default;
#     ~10x smaller than CSV at ~200 MB for 3.9M rows × 28 cols.
# -------------------------------------------------------------------------
out_path = OUT / "per_block_panel.parquet"
panel.to_parquet(out_path, index=False)
size_mb = out_path.stat().st_size / 1e6
print(f"[write] {out_path}  ({size_mb:.1f} MB)", flush=True)
_ck("40_panel_written")


# -------------------------------------------------------------------------
# 11. In-kernel parity sanity (the local test_event_parity.py logic, but
#     run here against the freshly-built panel without round-tripping
#     through download).
# -------------------------------------------------------------------------
print("[parity] hourly-resample sanity vs legacy 2026c joined_clean.parquet:", flush=True)

legacy = pd.read_parquet(parquet)
panel_indexed = panel.set_index("block_timestamp")

for proto_col, legacy_col, label in [
    ("aave_v3_lending_apr", "r_aave", "Aave"),
    ("compound_v3_lending_apr", "r_compound", "Compound"),
]:
    if proto_col not in panel.columns or legacy_col not in legacy.columns:
        print(f"  {label}: SKIP (column missing)", flush=True)
        continue
    new_hourly = panel_indexed[proto_col].resample("1h").last().dropna()
    legacy_apr = legacy[legacy_col] * 365 * 24
    joined = pd.concat(
        [new_hourly.rename("new"), legacy_apr.rename("legacy")], axis=1
    ).dropna()
    if len(joined) < 50:
        print(f"  {label}: SKIP (only {len(joined)} overlapping rows)", flush=True)
        continue
    diff = (joined["new"] - joined["legacy"]).abs()
    median_bp = diff.median() * 1e4
    p95_bp = diff.quantile(0.95) * 1e4
    status = "PASS" if median_bp < 5.0 else "FAIL (>5 bp)"
    print(
        f"  {label:>9}: n={len(joined):>5,}  median={median_bp:5.2f} bp  "
        f"p95={p95_bp:5.2f} bp  → {status}",
        flush=True,
    )

_ck("50_parity_done")
_ck("99_kernel_done")
print("[kernel] FINISHED", flush=True)
