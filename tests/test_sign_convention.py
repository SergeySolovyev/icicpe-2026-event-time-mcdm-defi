"""Lock-in test: borrowing_rate(t) >= lending_rate(t) for all t, both protocols.

Defends against the fractal-defi pre-v1.4.0 Aave loader sign-flip bug
(documented in CHANGELOG.md and ARCHITECTURE.md). Since we are pinning v1.3.2
(see README ERRATA), we cannot rely on the version tag to certify the fix —
the assertion runs against actual cached data instead.

Per PROJECT_2_PLAN.md S4.4 cleaning step 4 and S14 risk #2.
"""
# TODO Week 1 Day 3 (20 May 2026) - blocks Week 2 strategy work
import pytest


@pytest.mark.skip(reason="Implement in Week 1 Day 3 after fetch_aave + fetch_compound run")
def test_aave_sign_convention() -> None:
    """borrowing_rate >= lending_rate for every hourly bar in the Aave cache."""
    raise NotImplementedError


@pytest.mark.skip(reason="Implement in Week 1 Day 3 after fetch_compound run")
def test_compound_sign_convention() -> None:
    """borrowing_rate >= lending_rate for every hourly bar in the Compound cache."""
    raise NotImplementedError


@pytest.mark.skip(reason="Implement in Week 1 Day 3")
def test_rates_in_sane_range() -> None:
    """Both rates in [0, 0.50] -- no oracle glitches survived cleaning."""
    raise NotImplementedError
