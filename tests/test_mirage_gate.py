"""Decision-boundary checks using the existing T1 and replay engine."""
from dataclasses import replace

import pandas as pd
import pytest

from backtest.replay_per_block import EventReplayEngine
from decision.base import Action, BlockState, DecisionPolicy
from decision.t1_threshold import T1ThresholdPolicy
from mirage.gate import MirageGatedPolicy
from mirage.verdict import Finding, MarketReport, MarketVerdict, Severity


MARKET = "0x" + "ab" * 32
VENUE = "morpho_case"


def _state(*, current="aave_v3", block=100, tvl=6_212_914_536.0):
    return BlockState(
        block_number=block,
        block_timestamp=pd.Timestamp("2026-09-09", tz="UTC"),
        protocols=("aave_v3", VENUE),
        lending_apr={"aave_v3": 0.03, VENUE: 0.15},
        utilization={"aave_v3": 0.7, VENUE: 1.0},
        tvl_usd={"aave_v3": 1e9, VENUE: tvl},
        current_protocol=current,
        position_usd=1_000_000.0,
        gas_price_gwei=25.0,
        eth_price_usd=3500.0,
        gas_used_estimate=200_000,
    )


def _report(severity=Severity.BLOCK, *, block=100, include_market=True):
    findings = (
        Finding(
            code="share_exchange_rate",
            severity=severity,
            summary="Test verdict for an explicitly mapped market",
            metrics={},
            evidence=(),
        ),
    )
    return MarketReport(
        chain_id=1,
        block_number=block,
        block_hash="0x" + "11" * 32,
        source={"kind": "unit_test"},
        markets=(MarketVerdict(MARKET, block, findings),) if include_market else (),
    )


class RecordingPolicy(DecisionPolicy):
    name = "recording"

    def __init__(self, action):
        self.action = action
        self.states = []

    def decide(self, state):
        self.states.append(state)
        return self.action


def _gate(inner, report=None, **kwargs):
    return MirageGatedPolicy(
        inner,
        _report() if report is None else report,
        venue_to_market={VENUE: MARKET},
        **kwargs,
    )


def test_real_t1_is_invariant_to_tvl_then_gate_vetoes_explicit_market():
    """Corrected accounting alone cannot alter the rate-only T1 decision."""
    advertised = _state()
    shares_scaled = _state(tvl=93_828.25)
    before = T1ThresholdPolicy(initial_dwell_blocks=100_000).decide(advertised)
    corrected = T1ThresholdPolicy(initial_dwell_blocks=100_000).decide(shares_scaled)
    assert before == corrected
    assert before.kind == "switch" and before.target_protocol == VENUE
    gated = _gate(T1ThresholdPolicy(initial_dwell_blocks=100_000)).decide(advertised)
    assert gated.kind == "hold" and gated.target_protocol is None
    assert "share_exchange_rate" in gated.rationale


def test_veto_calls_inner_once_with_entire_original_state():
    state = _state()
    inner = RecordingPolicy(Action("switch", VENUE, "highest APR"))
    assert _gate(inner).decide(state).kind == "hold"
    assert len(inner.states) == 1 and inner.states[0] is state
    assert set(inner.states[0].lending_apr) == {"aave_v3", VENUE}


@pytest.mark.parametrize("severity", [Severity.PASS, Severity.WARN])
def test_pass_and_warn_keep_original_switch(severity):
    proposal = Action("switch", VENUE, "highest APR")
    inner = RecordingPolicy(proposal)
    assert _gate(inner, _report(severity)).decide(_state()) is proposal


def test_insufficient_verdict_refuses_entry():
    inner = RecordingPolicy(Action("switch", VENUE))
    assert _gate(inner, _report(Severity.INSUFFICIENT)).decide(_state()).kind == "hold"


@pytest.mark.parametrize(
    ("report_kwargs", "reason"),
    [
        ({"include_market": False}, "missing_market_verdict"),
        ({"block": 99}, "stale_report"),
        ({"block": 101}, "future_report"),
    ],
)
def test_missing_stale_and_future_reports_refuse_mapped_entry(report_kwargs, reason):
    inner = RecordingPolicy(Action("switch", VENUE))
    result = _gate(inner, _report(Severity.PASS, **report_kwargs)).decide(_state())
    assert result.kind == "hold" and reason in result.rationale


def test_older_report_requires_explicit_tolerance_and_never_allows_future():
    proposal = Action("switch", VENUE)
    accepted = _gate(
        RecordingPolicy(proposal), _report(Severity.PASS, block=99), max_age_blocks=1
    )
    assert accepted.decide(_state()) is proposal
    future = _gate(
        RecordingPolicy(proposal), _report(Severity.PASS, block=101), max_age_blocks=10
    )
    assert "future_report" in future.decide(_state()).rationale


def test_verdict_block_must_match_report():
    report = _report(Severity.PASS)
    report = replace(report, markets=(replace(report.markets[0], block_number=99),))
    action = _gate(RecordingPolicy(Action("switch", VENUE)), report).decide(_state())
    assert action.kind == "hold" and "inconsistent_report_block" in action.rationale


def test_existing_blocked_position_is_not_forced_out():
    state = _state(current=VENUE)
    policy = _gate(T1ThresholdPolicy(), _report(block=99))
    result = policy.decide(state)
    assert result.kind == "hold" and result.rationale.startswith("already at best")


def test_exit_to_unmapped_venue_remains_available_despite_bad_report():
    proposal = Action("switch", "aave_v3", "exit proposed by original policy")
    policy = _gate(RecordingPolicy(proposal), _report(block=101))
    assert policy.decide(_state(current=VENUE)) is proposal


def test_replay_veto_prevents_entry_and_gas_charge():
    """The engine consumes the adapter without any modification."""
    panel = pd.DataFrame(
        {
            "block_number": [100, 101],
            "block_timestamp": pd.date_range("2026-09-09", periods=2, freq="12s"),
            "aave_v3_lending_apr": [0.03, 0.03],
            f"{VENUE}_lending_apr": [0.15, 0.15],
        }
    )
    engine = EventReplayEngine()
    before, raw_summary = engine.run(panel=panel, policy=T1ThresholdPolicy())
    after, gated_summary = engine.run(
        panel=panel, policy=_gate(T1ThresholdPolicy(), max_age_blocks=1)
    )
    assert before.current_protocol.tolist() == [VENUE, VENUE]
    assert raw_summary.n_switches == 1
    assert after.current_protocol.isna().all()
    assert gated_summary.n_switches == 0 and gated_summary.total_gas_usd == 0
    assert gated_summary.final_position_usd == engine.initial_capital_usd


@pytest.mark.parametrize("market_id", ["morpho_blue", "0x123", "0x" + "zz" * 32])
def test_mapping_requires_actual_market_id(market_id):
    with pytest.raises(ValueError, match="32-byte"):
        MirageGatedPolicy(T1ThresholdPolicy(), _report(), venue_to_market={VENUE: market_id})


@pytest.mark.parametrize("age", [-1, 0.5, True])
def test_age_bound_must_be_nonnegative_integer(age):
    with pytest.raises(ValueError, match="nonnegative integer"):
        _gate(T1ThresholdPolicy(), max_age_blocks=age)
