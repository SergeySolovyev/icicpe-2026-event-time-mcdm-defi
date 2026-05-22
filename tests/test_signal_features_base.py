"""Contract test for the SignalFeatureBuilder ABC + flip-label helper.

Locks the shared interface that all three Plan C feature builders
(F1 lead, F3 fragmentation, F4 related) emit. The trainer (T3 Cox in
Task 5) joins the three feature-frames by block_number to assemble
the design matrix X for the regression.
"""
import pandas as pd
import pytest

from decision.features.base import (
    SignalFeatureBuilder,
    build_flip_labels,
    validate_feature_frame,
)


def _mini_panel(n: int = 300) -> pd.DataFrame:
    """3-protocol toy panel with rate-flips at known blocks."""
    block = list(range(1_000_000, 1_000_000 + n))
    ts = pd.date_range("2025-01-01", periods=n, freq="12s", tz="UTC")
    # Aave goes 4% -> 6% -> 4%; Compound flat 5%; Morpho flat 4.5%.
    # Top protocol: blocks 0-99 = compound, 100-199 = aave, 200-299 = compound.
    aave = [0.04] * 100 + [0.06] * 100 + [0.04] * 100
    comp = [0.05] * n
    morpho = [0.045] * n
    return pd.DataFrame({
        "block_number": block,
        "block_timestamp": ts,
        "aave_v3_lending_apr": aave,
        "compound_v3_lending_apr": comp,
        "morpho_blue_lending_apr": morpho,
    })


class _DummyF1(SignalFeatureBuilder):
    family = "f1"

    def build(self, panel: pd.DataFrame) -> pd.DataFrame:
        # NOTE: pd.Series[datetime64[ns, UTC]].values returns a tz-NAIVE
        # numpy array (the tz info lives on the Series wrapper, not the
        # underlying memory). Pass `.array` to preserve tz, or reset_index
        # and set after construction. Future builders MUST follow this
        # pattern or the validator will reject their output.
        return pd.DataFrame(
            {
                "block_timestamp": panel["block_timestamp"].array,
                "f1_dummy": [1.0] * len(panel),
            },
            index=pd.Index(panel["block_number"], name="block_number"),
        )


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


def test_validate_rejects_naive_timestamp():
    df = _DummyF1().build(_mini_panel())
    df["block_timestamp"] = df["block_timestamp"].dt.tz_localize(None)
    with pytest.raises(ValueError, match="tz-aware"):
        validate_feature_frame(df, expected_family="f1")


def test_validate_rejects_missing_block_timestamp():
    df = _DummyF1().build(_mini_panel()).drop(columns=["block_timestamp"])
    with pytest.raises(ValueError, match="block_timestamp"):
        validate_feature_frame(df, expected_family="f1")


def test_validate_rejects_wrong_index_name():
    df = _DummyF1().build(_mini_panel())
    df.index = df.index.rename("blknum")
    with pytest.raises(ValueError, match="block_number"):
        validate_feature_frame(df, expected_family="f1")


def test_build_flip_labels_basic_shape():
    """Top protocol flips compound -> aave at block 100, aave -> compound
    at block 200 in the _mini_panel. Right before each flip, blocks_to_flip
    must be small and event_observed=1."""
    panel = _mini_panel()
    labels = build_flip_labels(panel, horizon_blocks=500)
    assert "blocks_to_flip" in labels.columns
    assert "event_observed" in labels.columns
    assert labels.index.name == "block_number"
    assert len(labels) == len(panel)

    # Right before the 99->100 flip (compound -> aave).
    row99 = labels.iloc[99]
    assert int(row99["blocks_to_flip"]) == 1
    assert int(row99["event_observed"]) == 1


def test_build_flip_labels_censoring():
    """Blocks within horizon_blocks of the END of the panel with no
    further flip should be censored (event_observed=0)."""
    panel = _mini_panel(n=300)
    # Horizon 50 << remaining length after the last flip at block 200.
    labels = build_flip_labels(panel, horizon_blocks=50)
    last = labels.iloc[-1]
    assert int(last["event_observed"]) == 0
    assert int(last["blocks_to_flip"]) == 50


def test_build_flip_labels_requires_two_protocols():
    panel = _mini_panel().drop(
        columns=["compound_v3_lending_apr", "morpho_blue_lending_apr"]
    )
    with pytest.raises(ValueError, match="2"):
        build_flip_labels(panel, horizon_blocks=10)
