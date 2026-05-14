"""Markov-switching short-rate baseline forecaster.

Two-state regime-switching model on utilization-quantile cuts (Hamilton 1989
foundation; Smith-Naik-Tsai 2006 extension for short rates).

States typically: "low-utilization" (u < 0.5) and "high-utilization" (u >= 0.5),
each with its own CIR drift+volatility parameters. Forward-looking transition
probabilities estimated via Baum-Welch.

Per PROJECT_2_PLAN.md S10 ablation #4 (cheap regime-aware classical comparator).
Per DEEP_RESEARCH.md S VI.A tier 1 baseline #4.
"""
# TODO Week 2 Day 3-4 (28-29 May 2026)
raise NotImplementedError("Implement in Week 2 Day 3-4")
