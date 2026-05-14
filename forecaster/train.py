"""Training loop for DualBranchKinkSubtractionForecaster with MLflow grid search.

Hyperparameter grid (per PROJECT_2_PLAN.md S5.1):
- hidden_dim_per_branch in {32, 64, 96, 128}
- num_layers in {1, 2}
- cnn_kernels in {[3,5,7], [3,5], [5]}
- dropout in {0.0, 0.1, 0.2}
- lr in {1e-3, 2e-3, 5e-3}
- batch_size in {16, 32, 64}
- seq_len in {72, 168, 336}
- loss_weights via 3-point grid

Selection criterion: validation weighted Pearson + directional accuracy >= 55%.

Split (strict block_number filter):
- Train: 2024-11-01 -> 2025-08-31 (~7,300 hourly bars)
- Valid: 2025-09-01 -> 2025-12-31 (~2,900)
- Test:  2026-01-01 -> 2026-04-30 (~2,900, held out)

Each run logs MLflow `params`, `metrics`, and `strategy_backtest_data.csv`.
"""
# TODO Week 1 Day 6-7 (23-24 May 2026)
raise NotImplementedError("Implement in Week 1 Day 6-7")
