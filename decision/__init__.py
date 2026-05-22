"""Decision-policy module for the event-time DeFi lending allocator.

Three policies, each implementing the DecisionPolicy ABC from base.py:
    T1 (decision.t1_threshold)        -- gas-aware threshold rule (no ML)
    T2 (decision.t2_optimal_stopping) -- OU spread + Bellman threshold
    T3 (decision.t3_hazard, Plan C)   -- Cox / Weibull hazard (ML)

All three share the same .decide(state) -> Action interface and are
benchmarked head-to-head against B1-B4 baselines (in
backtest.run_baselines_event_time) on the same per-block panel produced
by Plan A.
"""
