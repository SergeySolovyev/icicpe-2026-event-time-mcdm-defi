"""Veto new allocations using a previously computed MIRAGE market report.

This adapter leaves the underlying policy's candidate set and observations
intact. It does not liquidate an existing position, find an alternative target,
or perform network calls. The venue-to-market mapping must be explicit: a
protocol label such as ``morpho_blue`` is not itself a Morpho market ID.
"""
from __future__ import annotations

from collections.abc import Mapping
import re

from decision.base import Action, BlockState, DecisionPolicy
from mirage.verdict import MarketReport, Severity


_MARKET_ID = re.compile(r"0x[0-9a-fA-F]{64}\Z")


class MirageGatedPolicy(DecisionPolicy):
    """Call ``inner`` once, then veto entry into an unsafe mapped market.

    Unmapped venues retain the inner policy's behavior and are outside MIRAGE
    coverage. A mapped market without usable, sufficiently recent evidence is
    refused. By default, the report must describe the exact decision block.
    Accepting older reports requires an explicit ``max_age_blocks`` value;
    future reports are always refused to avoid backtest look-ahead.
    """

    def __init__(
        self,
        inner: DecisionPolicy,
        report: MarketReport,
        *,
        venue_to_market: Mapping[str, str],
        veto_on: frozenset[Severity] = frozenset(
            {Severity.BLOCK, Severity.INSUFFICIENT}
        ),
        max_age_blocks: int = 0,
    ) -> None:
        if (
            isinstance(max_age_blocks, bool)
            or not isinstance(max_age_blocks, int)
            or max_age_blocks < 0
        ):
            raise ValueError("max_age_blocks must be a nonnegative integer")
        if not isinstance(venue_to_market, Mapping):
            raise TypeError("venue_to_market must explicitly map venues to market IDs")
        mapping: dict[str, str] = {}
        for venue, market_id in venue_to_market.items():
            if not isinstance(venue, str) or not venue.strip():
                raise ValueError("venue names must be nonempty strings")
            if not isinstance(market_id, str) or not _MARKET_ID.fullmatch(market_id):
                raise ValueError(f"market ID for {venue!r} must be a 32-byte hex value")
            mapping[venue] = market_id.lower()

        self.inner = inner
        self.report = report
        self.venue_to_market = mapping
        self.veto_on = frozenset(Severity(value) for value in veto_on)
        self.max_age_blocks = max_age_blocks
        self.name = f"mirage_gated_{inner.name}"
        self._markets = {}
        for verdict in report.markets:
            market_id = verdict.market_id.lower()
            if market_id in self._markets:
                raise ValueError(f"duplicate market verdict: {market_id}")
            self._markets[market_id] = verdict

    def decide(self, state: BlockState) -> Action:
        action = self.inner.decide(state)
        if action.kind != "switch" or action.target_protocol == state.current_protocol:
            return action
        market_id = self.venue_to_market.get(action.target_protocol)
        if market_id is None:
            return action

        reason = None
        age = state.block_number - self.report.block_number
        verdict = self._markets.get(market_id)
        if age < 0:
            reason = "future_report"
        elif age > self.max_age_blocks:
            reason = "stale_report"
        elif verdict is None:
            reason = "missing_market_verdict"
        elif verdict.block_number != self.report.block_number:
            reason = "inconsistent_report_block"
        elif verdict.severity in self.veto_on:
            codes = [
                finding.code
                for finding in verdict.findings
                if finding.severity in self.veto_on
            ]
            reason = ",".join(codes) or verdict.severity.value

        if reason is None:
            return action
        return Action(
            kind="hold",
            target_protocol=None,
            rationale=(
                f"mirage:{reason}; entry to {action.target_protocol} "
                f"({market_id}) vetoed; proposed: {action.rationale}"
            ),
        )
