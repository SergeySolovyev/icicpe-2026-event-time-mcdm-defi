"""Canonical schema for per-event rate-update records.

All fetchers (data/fetch_*_events.py) emit dataframes with EXACTLY these
columns and dtypes. The stitcher (data/build_per_block_panel.py) consumes
them.

Invariants enforced by the validator:
  1. utilization in [0, 1.0001]  (clamp to 1.0; numerical fuzz tolerated)
  2. borrowing_rate_apr >= lending_rate_apr  (sign convention, CLAUDE.md S5)
  3. block_timestamp tz-aware UTC
  4. no duplicate (block_number, event_idx, protocol) keys
  5. protocol in KNOWN_PROTOCOLS

These invariants are also enforced incrementally by individual fetchers
(e.g., utilization.clip(0,1)) so validation rarely fails in practice --
validate_event_frame is the LAST line of defense before parquet write.
"""
from __future__ import annotations

import pandas as pd

# event_idx semantic (IMPORTANT, see Task A2 retrospective in KANBAN.md):
#   * At FETCH time, fetchers populate event_idx as a unique within-frame
#     counter (e.g. `pd.RangeIndex(len(df))`). block_number is sentinel -1
#     at this stage because the subgraph doesn't expose true block numbers
#     on the rate-history entity. The dedup key (block, idx, protocol) is
#     unique because event_idx is globally unique within the fetch frame.
#   * At STITCHER time (build_per_block_panel.py), after ts->block_number
#     is resolved, the stitcher re-cumcounts event_idx within
#     (block_number, protocol) to recover the semantic "within-block
#     ordering". From that point on event_idx means "kth event in this
#     block for this protocol".
# The validator enforces uniqueness on (block_number, event_idx, protocol)
# but does NOT require event_idx to start at 0 per timestamp -- that
# semantic is the stitcher's responsibility.

EVENT_ROW_DTYPES: dict[str, str] = {
    "block_number":        "int64",
    "block_timestamp":     "datetime64[ns, UTC]",
    "event_idx":           "int32",
    "protocol":            "category",
    "event_type":          "category",
    "lending_rate_apr":    "float64",
    "borrowing_rate_apr":  "float64",
    "utilization":         "float64",
    "total_supplied_usd":  "float64",
    "total_borrowed_usd":  "float64",
    "tx_hash":             "string",
    "source":              "category",
}

KNOWN_PROTOCOLS = (
    "aave_v3", "spark", "compound_v3",
    "morpho_blue", "fluid", "euler_v2", "dsr",
)


def validate_event_frame(df: pd.DataFrame) -> None:
    """Raise ValueError if the dataframe violates the EventRow contract."""
    missing = set(EVENT_ROW_DTYPES) - set(df.columns)
    if missing:
        raise ValueError(f"event frame missing columns: {sorted(missing)}")

    if df["block_timestamp"].dt.tz is None:
        raise ValueError("event frame block_timestamp must be tz-aware UTC")

    u = df["utilization"].dropna()
    if ((u < 0) | (u > 1.0001)).any():
        bad = u[(u < 0) | (u > 1.0001)]
        raise ValueError(f"utilization out of [0,1]: {bad.head().to_list()}")

    spread = df["borrowing_rate_apr"] - df["lending_rate_apr"]
    if (spread < -1e-9).any():
        idx = spread[spread < -1e-9].index[:5]
        raise ValueError(
            f"borrowing_rate_apr < lending_rate_apr at rows {list(idx)}"
        )

    dupes = df.duplicated(subset=["block_number", "event_idx", "protocol"])
    if dupes.any():
        raise ValueError(
            f"duplicate (block_number, event_idx, protocol) keys: "
            f"{int(dupes.sum())} rows"
        )

    bad_proto = set(df["protocol"].dropna().unique()) - set(KNOWN_PROTOCOLS)
    if bad_proto:
        raise ValueError(f"unknown protocol values: {sorted(bad_proto)}")


def empty_event_frame() -> pd.DataFrame:
    """Return an empty frame with the canonical dtypes -- for early-return paths."""
    return pd.DataFrame(
        {col: pd.Series(dtype=dtype) for col, dtype in EVENT_ROW_DTYPES.items()}
    )


if __name__ == "__main__":
    # Smoke: ensure empty frame validates.
    validate_event_frame(empty_event_frame())
    print("event_schema smoke OK")
