"""Data cleaning: outlier removal, forward-fill (<=6h), z-score normalization.

Pipeline (per PROJECT_2_PLAN.md S4.4):
1. Drop APY outside [0, 50%] (oracle glitches).
2. Rate-jump guard: |r(t) - r(t-1)| / r(t-1) > 5 -> interpolate.
3. Forward-fill missing data up to 6 hours; longer gaps marked as regime breaks.
4. Z-score features using training statistics only.
5. Sign-convention assertion: borrowing_rate(t) >= lending_rate(t) for all t.

Outputs cleaned parquet files alongside raw ones with `_clean` suffix.
"""
# TODO Week 1 Day 3 (20 May 2026)
raise NotImplementedError("Implement in Week 1 Day 3")
