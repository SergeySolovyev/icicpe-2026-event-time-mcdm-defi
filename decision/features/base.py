"""Shared contract for the T3 signal feature builders.

Every concrete builder is a callable
    .build(panel: pd.DataFrame) -> pd.DataFrame
that takes the per-block panel from Plan A
(`data/cached/per_block_panel.parquet`) and emits a feature frame:
    index name: 'block_number' (int64, monotonic)
    columns:
        - block_timestamp (datetime64[ns, UTC])
        - <family>_<feature_name>* (one or more float64 columns)

All value-column names MUST start with the builder's family prefix
(`f1_`, `f3_`, or `f4_`). The validator enforces this so a downstream
join `pd.concat([f1, f3, f4], axis=1)` produces no name collisions.

This file also exposes `build_flip_labels`: the supervised target for
T3 training -- "blocks until the top-APR protocol changes" with
right-censoring at `horizon_blocks`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


_KNOWN_FAMILIES = {"f1", "f3", "f4"}


class SignalFeatureBuilder(ABC):
    """Abstract base for the three Plan C feature builders (F1/F3/F4).

    Subclasses MUST set the class attribute `family` to one of
    {'f1', 'f3', 'f4'} -- enforced at __init__ time so a typo can't slip
    through and produce features that fail the joint design-matrix
    construction in T3 training.
    """

    family: str = ""

    def __init__(self) -> None:
        if not self.family:
            raise NotImplementedError(
                f"{self.__class__.__name__} must set `family` class "
                f"attribute (one of {sorted(_KNOWN_FAMILIES)})"
            )
        if self.family not in _KNOWN_FAMILIES:
            raise ValueError(
                f"{self.__class__.__name__}.family = {self.family!r}; "
                f"must be one of {sorted(_KNOWN_FAMILIES)}"
            )

    @abstractmethod
    def build(self, panel: pd.DataFrame) -> pd.DataFrame:
        """Return a feature frame indexed by block_number with a
        block_timestamp column + one or more `{family}_*` float64
        feature columns. NaN values are allowed per cell.
        """


def validate_feature_frame(
    df: pd.DataFrame, *, expected_family: str
) -> None:
    """Raise ValueError if `df` violates the feature-frame contract."""
    if df.index.name != "block_number":
        raise ValueError(
            f"feature frame index must be named 'block_number', "
            f"got {df.index.name!r}"
        )
    if df.index.dtype != "int64":
        raise ValueError(
            f"feature frame index dtype must be int64, "
            f"got {df.index.dtype}"
        )
    if "block_timestamp" not in df.columns:
        raise ValueError(
            "feature frame must include a 'block_timestamp' column"
        )
    ts = df["block_timestamp"]
    if not pd.api.types.is_datetime64_any_dtype(ts):
        raise ValueError(
            "feature frame block_timestamp must be datetime, "
            f"got {ts.dtype}"
        )
    if getattr(ts.dt, "tz", None) is None:
        raise ValueError(
            "feature frame block_timestamp must be tz-aware UTC"
        )

    expected_prefix = expected_family + "_"
    value_cols = [c for c in df.columns if c != "block_timestamp"]
    if not value_cols:
        raise ValueError(
            f"feature frame must have at least one {expected_prefix}* "
            f"column besides block_timestamp"
        )
    for col in value_cols:
        if not col.startswith(expected_prefix):
            raise ValueError(
                f"feature column {col!r} missing prefix "
                f"{expected_prefix!r} (this is the {expected_family} "
                f"builder)"
            )
        if df[col].dtype != "float64":
            raise ValueError(
                f"feature column {col!r} must be float64, "
                f"got {df[col].dtype}"
            )


def build_flip_labels(
    panel: pd.DataFrame, *, horizon_blocks: int
) -> pd.DataFrame:
    """Build supervised survival labels for the T3 Cox regression.

    For each block in `panel`, computes the lag (in blocks) until the
    next change in the argmax-APR protocol. If no such change occurs
    within `horizon_blocks` blocks, the row is right-censored.

    Args:
        panel: per-block panel from Plan A's stitcher, with one or more
            `<proto>_lending_apr` columns and a `block_number` column.
        horizon_blocks: censoring horizon. Choose this consistent with
            the strategy's holding-period assumptions (e.g. 7200 blocks
            = ~24 hours).

    Returns:
        DataFrame indexed by block_number with two columns:
            blocks_to_flip   int64    blocks until next flip OR horizon
            event_observed   int8     1 = real flip seen, 0 = censored
    """
    proto_cols = [c for c in panel.columns if c.endswith("_lending_apr")]
    if len(proto_cols) < 2:
        raise ValueError(
            f"need at least 2 *_lending_apr protocol columns to "
            f"compute flip labels, got {len(proto_cols)} ({proto_cols})"
        )

    apr = panel[proto_cols].to_numpy(dtype="float64")
    # NaN -> -inf so it's never the argmax winner.
    apr_safe = np.where(np.isnan(apr), -np.inf, apr)
    top_idx = np.argmax(apr_safe, axis=1)

    # Positions (relative to the panel start) where the top protocol
    # changes. flips[t] is True iff top_idx[t] != top_idx[t-1].
    flips_mask = np.diff(top_idx) != 0
    flip_positions = np.nonzero(flips_mask)[0] + 1  # position of NEW top

    n = len(panel)
    blocks_to_flip = np.full(n, horizon_blocks, dtype=np.int64)
    event = np.zeros(n, dtype=np.int8)

    # For each block i, find the first flip_position > i. We sweep i
    # monotonically so a single index `j` into flip_positions suffices.
    j = 0
    for i in range(n):
        while j < len(flip_positions) and flip_positions[j] <= i:
            j += 1
        if j < len(flip_positions):
            delta = int(flip_positions[j] - i)
            if delta <= horizon_blocks:
                blocks_to_flip[i] = delta
                event[i] = 1
            # else: stays censored at horizon_blocks

    return pd.DataFrame(
        {
            "blocks_to_flip": blocks_to_flip,
            "event_observed": event,
        },
        index=pd.Index(panel["block_number"].to_numpy(), name="block_number"),
    )
