"""Feature engineering: kink subtraction + rate residual + cross-protocol spread.

Core function `f_kink(u, kink_params)` reproduces the Aave/Compound piecewise-linear
rate function from on-chain kink parameters (optimalUtilization, slope1, slope2,
reserveFactor), letting the forecaster see only the residual `epsilon = r - f_kink(u)`.

Per PROJECT_2_PLAN.md S2.2 and DEEP_RESEARCH.md S VI.B (Branch A target).

Functions:
    f_kink(u, p)             -> deterministic protocol rate
    rate_residual(r, u, p)   -> r - f_kink(u, p)
    cross_protocol_spread(...) -> r_aave - r_compound and resid_aave - resid_compound
    extract_features(raw_a, raw_c, t, gas, eth_usd) -> dict matching forecaster input
    fetch_kink_history(...)  -> historical kink params from on-chain Configurator events
"""
# TODO Week 1 Day 4 (21 May 2026); kink-history fetcher per DEEP_RESEARCH.md S V.E note 6
raise NotImplementedError("Implement in Week 1 Day 4")
