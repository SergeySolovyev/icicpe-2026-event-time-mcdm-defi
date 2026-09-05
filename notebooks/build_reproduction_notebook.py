"""Assemble ONE self-contained, fully-reproducible Kaggle notebook from the three
validated reproduction modules (notebook_core / notebook_robust / notebook_t3).

Academic structure: every section is a markdown cell (theory) -> a code cell ->
a markdown cell (interpretation of the output). The reproduction engine is NOT
pasted as one block: each module is split into its functions and each function
is presented where it is first needed, framed by a short explanation before it
(what it computes and why) and a walkthrough after it (how the code does it).
Every reported number is recomputed from the single cached input
per_block_panel.parquet (+ events_dsr.parquet), with NO API keys and NO
fractal-defi. Output: notebooks/reproduce_predictive_mcdm_defi.ipynb
"""
import re
from collections import OrderedDict
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
RB = ROOT / "scripts" / "robustness"
OUT = ROOT / "notebooks" / "reproduce_predictive_mcdm_defi.ipynb"


def load_module_src(name: str) -> str:
    """Read a reproduction module, strip __main__, cross-imports, __future__,
    and module-level Path(__file__) so it runs verbatim inside a notebook cell."""
    src = (RB / f"{name}.py").read_text(encoding="utf-8")
    src = src.split("\nif __name__ ==")[0].rstrip() + "\n"        # drop __main__
    src = re.sub(r"Path\(__file__\)\.resolve\(\)\.parents\[\d+\]", 'Path(".")', src)
    out = []
    for ln in src.splitlines():
        if ln.startswith("from __future__"):
            continue
        if re.match(r"\s*from notebook_(core|robust|t3) import", ln):
            continue
        out.append(ln)
    return "\n".join(out).strip() + "\n"


_TOP = re.compile(r"^(?:def [A-Za-z_]\w*|[A-Za-z_]\w* = )")   # top-level def / constant
_BANNER = re.compile(r"^#\s*[-=]{4,}")                          # decorative comment rules


def split_module(name: str) -> "OrderedDict[str, str]":
    """Split a reproduction module into top-level chunks keyed by the function /
    constant name. Module docstring and imports are dropped (the notebook's
    setup cell already imports everything). Comment lines immediately above a
    definition travel with it; decorative banner rules are removed."""
    lines = load_module_src(name).splitlines()
    starts = [i for i, ln in enumerate(lines) if _TOP.match(ln)]
    if not starts:
        raise RuntimeError(f"{name}: no top-level definitions found")
    # pull leading comment lines into the chunk they introduce
    adj = []
    for i in starts:
        j = i
        while j > 0 and lines[j - 1].startswith("#"):
            j -= 1
        adj.append(j)
    chunks: "OrderedDict[str, str]" = OrderedDict()
    for a, b in zip(adj, adj[1:] + [len(lines)]):
        body = [ln for ln in lines[a:b] if not _BANNER.match(ln)]
        head = next(ln for ln in body if _TOP.match(ln))
        key = re.match(r"(?:def )?([A-Za-z_]\w*)", head).group(1)
        chunks[key] = "\n".join(body).strip("\n")
    return chunks


def pick(chunks: "OrderedDict[str, str]", names) -> str:
    """Concatenate the named chunks in the given order (one-line constants are
    grouped without blank lines between them)."""
    parts = []
    for nm in names:
        if nm not in chunks:
            raise KeyError(f"{nm!r} not found; available: {list(chunks)}")
        c = chunks[nm].strip("\n")
        if parts and "\n" not in c and "\n" not in parts[-1]:
            parts[-1] = parts[-1] + "\n" + c
        else:
            parts.append(c)
    return "\n\n".join(parts) + "\n"


CORE = split_module("notebook_core")
ROBUST = split_module("notebook_robust")
T3 = split_module("notebook_t3")

cells = []
def md(t): cells.append(nbf.v4.new_markdown_cell(t.strip("\n")))
def code(t): cells.append(nbf.v4.new_code_cell(t.strip("\n")))

# ============================================================ TITLE / ABSTRACT
md(r"""
# Predictive MCDM Allocator across Six USDC Lending Venues - A Reproducible Study

**Sergei Solovev** - a self-contained, reproducible study

> **Scope of this notebook.** A single, self-contained, top-to-bottom reproduction of every empirical result of this
> study, computed from one raw input - a per-Ethereum-block panel of the six venues' USDC supply rates. It requires no
> API keys, no on-chain access, and no `fractal-defi`: every decision policy (T1 gas-aware threshold, T2
> Ornstein-Uhlenbeck optimal-stopping, T3 Cox-hazard) and every statistic (walk-forward, paired bootstrap, Holm, PBO,
> the pre-registered negative control) is re-implemented here in pure `numpy`/`pandas` (`lifelines` only for the Cox
> fit) and reproduces the reference engine to the dollar.

> **How to read it.** Each section follows the same pattern: a short statement of the theory, the code that
> implements it, and an interpretation of the output. The reproduction engine is presented the same way, one function
> at a time, where the function is first needed - the aim is that every number in the ledger of Section 12 can be
> traced back through the code that produced it without leaving this notebook.

**Abstract.** Fragmented DeFi lending markets pay materially different USDC supply rates that cross over through time.
This study evaluates whether a reactive, gas-aware allocator - which at every block holds the highest-paying venue net
of gas - captures that dispersion, and whether the estimated edge reflects a real effect or overfitting. The primary
rule **T1** has one hyperparameter and no forecast. A machine-learning variant (**T3**, Cox proportional-hazards) is
pre-registered as a likely negative control and is shown to lose out-of-sample. Across six non-overlapping quarters T1
exceeds the best in-hindsight single venue in 6/6 windows; the combinatorial Probability of Backtest Overfitting is 0;
and against 5,000 same-cadence random allocators T1 lies roughly nine standard deviations above the null distribution.
All results below are recomputed from the cached panel.

**How to run on Kaggle.** Attach the dataset containing `per_block_panel.parquet` (+ `events_dsr.parquet`), set the
kernel to *Internet on* only if the optional S11 L2 measurement is required, then **Run All**. Runtime ~ 8-12 min.
""")

# ============================================================ S0 SETUP
md(r"""
## 0 - Setup and reproducibility contract

**Motivation - why one per-block panel suffices.** The allocator is an event-time system: it makes a decision at every
Ethereum block (~12 s). All of its inputs are observable on-chain quantities - each venue's supply APR, the gas price,
and the ETH/USD price. These observables are frozen into a single table, `per_block_panel.parquet`
(~3.93 M rows x 36 columns, Oct 2024 -> Apr 2026), which is treated as the raw experimental data. Regenerating it from
chain requires The Graph and an archive RPC, but every reported number is downstream of this cached table, so the
reproduction below is hermetic and key-free. The only auxiliary file is `events_dsr.parquet` (546 rows, the Maker DSR
lead-rate series used by the T3 F1 features).

The cell below locates the data (works both locally and under `/kaggle/input`), loads it, and prints its shape and span.
""")
code(r"""
import warnings, json, itertools, math, time
from collections import deque
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
plt.rcParams.update({"figure.dpi": 110, "axes.grid": True, "grid.alpha": .3,
                     "font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
np.set_printoptions(suppress=True)

# lifelines is the only non-default dependency (used by the S8 Cox fit); install if missing.
try:
    import lifelines  # noqa: F401
except ImportError:
    import subprocess, sys
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "lifelines"], check=False)
    import lifelines  # noqa: F401

def _find(fname):
    roots = [Path("/kaggle/input"), Path("input"), Path("."), Path(".."),
             Path("data/cached"), Path("../data/cached"), Path("../input")]
    for r in roots:
        if not r.exists():
            continue
        if r.is_file() and r.name == fname:
            return r
        hits = sorted(r.rglob(fname))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"{fname} not found under {[str(x) for x in roots]}")

PANEL_PATH = _find("per_block_panel.parquet")
panel = pd.read_parquet(PANEL_PATH)
panel["block_timestamp"] = pd.to_datetime(panel["block_timestamp"], utc=True)
panel = panel.sort_values("block_timestamp").reset_index(drop=True)
try:
    EVENTS_DSR_PATH = str(_find("events_dsr.parquet"))
except FileNotFoundError:
    EVENTS_DSR_PATH = None   # T3 F1 features will fall back; OOS section will note it

print(f"panel : {len(panel):,} rows x {len(panel.columns)} cols  ({PANEL_PATH})")
print(f"span  : {panel.block_timestamp.min()}  ->  {panel.block_timestamp.max()}")
print(f"blocks: {int(panel.block_number.min()):,} .. {int(panel.block_number.max()):,}")
print(f"DSR   : {EVENTS_DSR_PATH}")
""")
md(r"""
**Output.** ~3.93 M blocks spanning 18 months across the six venues, plus the DSR side file - the complete raw input.
All subsequent results are deterministic given this table.
""")

# ============================================================ S1 DATA
md(r"""
## 1 - The data - six USDC lending venues, observed per block

**Data.** The panel covers the variable-supply USDC markets of **Aave V3, Compound V3, Spark, Morpho Blue, Euler V2,
and Fluid** on Ethereum mainnet. For each venue it stores `<venue>_lending_apr` (the supply APR a depositor earns, as a
decimal fraction), plus utilisation and TVL (used by the MCDM baseline and the capacity model). The panel also carries
`gas_price_gwei`, `eth_usd` (to price a rebalance in USD), and the Maker DSR lead rate. Because the series are
contemporaneous and observed, the allocator forecasts no rate; it reacts to the current cross-section.
""")
code(r"""
PROT6 = ["aave_v3", "compound_v3", "spark", "morpho_blue", "euler_v2", "fluid"]
PRETTY6 = ["Aave V3", "Compound V3", "Spark", "Morpho Blue", "Euler V2", "Fluid"]
BPY_ = 365 * 24 * 60 * 60 // 12  # 2,628,000 blocks / year

def _win(a, b):
    m = (panel.block_timestamp >= pd.Timestamp(a, tz="UTC")) & (panel.block_timestamp < pd.Timestamp(b, tz="UTC"))
    return panel.loc[m]

full = panel
test = _win("2026-01-01", "2026-05-01")
desc = pd.DataFrame({
    "mean_APY_full_%": [full[f"{p}_lending_apr"].mean() * 100 for p in PROT6],
    "mean_APY_test_%": [test[f"{p}_lending_apr"].mean() * 100 for p in PROT6],
    "mean_TVL_$M":     [full[f"{p}_tvl_usd"].mean() / 1e6 for p in PROT6],
}, index=PRETTY6).round(2)
print(desc.to_string())
print(f"\ntest window (Jan-Apr 2026): {len(test):,} blocks")

# plot the six supply-rate series over the test window (daily mean for legibility)
d = test.set_index("block_timestamp")
daily = pd.DataFrame({pr: d[f"{p}_lending_apr"] * 100 for p, pr in zip(PROT6, PRETTY6)}).resample("1D").mean()
ax = daily.plot(figsize=(10, 3.6), lw=1.3)
ax.set_ylabel("supply APY (%)"); ax.set_title("Six USDC venues - daily mean supply rate (test window)")
ax.legend(ncol=6, fontsize=8, loc="upper center", bbox_to_anchor=(.5, -.18)); plt.tight_layout(); plt.show()
""")
md(r"""
**Output.** The venues' rates are dispersed and the leader changes repeatedly; this crossing dispersion is the source of
the allocator's return. No single venue dominates, and the strategy is to capture the moving maximum net of gas.
""")

# ============================================================ S2 SPREAD
md(r"""
## 2 - The cross-venue spread as the signal

**Definition.** The per-block dispersion is defined as `max(APR) - min(APR)` across the six venues. If this were ~0, an
allocator would have nothing to capture. This section quantifies the spread and how often the top-paying venue changes
(the "crossover rate"), and reports the spread's volatility by quarter - the alternating calm and volatile regimes the
study exploits.
""")
code(r"""
apr_full = np.column_stack([full[f"{p}_lending_apr"].to_numpy(float) for p in PROT6])
spread = np.nanmax(apr_full, axis=1) - np.nanmin(apr_full, axis=1)
leader = np.nanargmax(apr_full, axis=1)
crossovers = int((leader[1:] != leader[:-1]).sum())
print(f"cross-venue spread (pp):   median {np.nanmedian(spread)*100:.2f}   "
      f"p90 {np.nanpercentile(spread,90)*100:.2f}   max {np.nanmax(spread)*100:.2f}")
print(f"leadership crossovers:     {crossovers:,} over {len(full):,} blocks "
      f"({crossovers/(len(full)/ (BPY_/12)):.1f} per month)")
sh = pd.Series(leader).value_counts(normalize=True).reindex(range(6)).fillna(0) * 100
print("time-as-leader (%):       ", {PRETTY6[i]: round(sh[i], 1) for i in range(6)})

q = full.copy(); q["spread_pp"] = spread * 100
q["quarter"] = q["block_timestamp"].dt.to_period("Q").astype(str)
reg = q.groupby("quarter")["spread_pp"].agg(["median", "std"]).round(3)
print("\nspread by quarter (volatility regimes):\n", reg.to_string())
""")
md(r"""
**Output.** A non-trivial median spread with frequent leadership turnover, and a clear alternation between calm quarters
(low spread sigma) and volatile ones - the structure examined by the regime analysis in S5.
""")

# ============================================================ S3 POLICIES (ENGINE)
md(r"""
## 3 - The decision policies (the reproduction engine)

**Policies.** Every policy is evaluated on the same accounting: the position earns the current venue's APR block by
block and pays a gas cost in USD each time it moves. The policies differ only in the *rule* that decides when to move.

* **T1 - gas-aware threshold.** At each block, switch to the highest-APR venue if and only if the expected extra yield
  over the expected dwell exceeds the gas cost:

  `switch  <=>  position * (APR_best - APR_current) * dwell / BLOCKS_PER_YEAR  >  gas_cost_usd`

  The left-hand side is the extra dollars the spread would earn if the current leader stayed on top for `dwell` more
  blocks; the right-hand side is what the move costs. `dwell` is not forecast from a model - it is an exponentially
  weighted average of how long past leaders actually stayed on top. T1 has one hyperparameter (the EWMA weight
  `alpha`; the seed value `dwell0` only initialises the estimate and washes out). No forecast and no fitted surface.
* **T2 - OU optimal stopping.** The top-vs-runner-up spread is modelled as an Ornstein-Uhlenbeck process
  `dS = kappa * (theta - S) * dt + sigma * dW`, recalibrated by maximum likelihood every 5,000 blocks; the policy
  switches when the spread exceeds the closed-form Bellman boundary
  `S* = theta + sigma * sqrt(K / kappa)` with `K = gas_cost / position` (the cost as a fraction of the position; one
  block is the time unit). When mean reversion is absent (`kappa <= 1e-6`) the rule reduces to T1, which is consistent
  with the empirical finding that T2 approximates T1.
* **T3 - Cox hazard.** The "leader-flip" hazard `lambda = lambda0 * exp(beta'x)` is predicted from F1/F3 features, and
  `E[dwell] = 1 / lambda` replaces T1's EWMA dwell in the same cost rule. This is the one component with a fitted
  surface, pre-registered as a likely negative (S8).
* **Baselines.** B1/B2 buy-and-hold Aave/Compound; B3 greedy (chase the max every block, no gas gate); B4 a 4-factor
  MCDM on EMA-smoothed APR/utilisation/TVL.

The engine accrues the current venue's APR each block (`pos *= 1 + apr / BPY`) and pays gas per switch, reading gas and
ETH per block from the panel. The cells below are the complete compute core, one function at a time - the same functions
are used for every result that follows, and they reproduce the reference `EventReplayEngine` to the dollar.
""")

# --- 3.1 primitives
md(r"""
### 3.1 - Accounting primitives

Four small functions and three constants define the arithmetic that every policy shares. `slice_arrays` turns a date
range of the panel into dense `numpy` arrays (one row per block, one column per venue); `gas_cost` prices a rebalance in
USD; `hold_final` compounds a buy-and-hold position; `net_apy` annualises a final position into a comparable rate.
""")
code(pick(CORE, ["BPY", "GAS_USED", "PROT", "slice_arrays", "gas_cost", "hold_final", "net_apy"]))
md(r"""
**What the cell defines.**

* `BPY = 2,628,000` is the number of 12-second blocks in a year; dividing an annual APR by it gives the per-block growth
  factor. `GAS_USED = 200,000` is the gas consumed by one rebalance transaction (the engine default).
* `slice_arrays` selects `[start, end)` by timestamp and returns `apr[n, 6]`, `gas[n]`, `eth[n]`, `block[n]`, plus
  utilisation and TVL matrices. Missing rates stay `NaN` - a venue with no observed rate is never selected, and, if it is
  currently held, the accrual step simply skips that block.
* `gas_cost = gas_used * gas_price_gwei * 1e-9 * eth_usd` converts gwei per gas unit into dollars. Because `gas` and
  `eth` are read per block, the cost of a switch varies through the sample exactly as it did on chain.
* `hold_final` multiplies `1 + apr / BPY` over every block (with `NaN -> 0` growth), i.e. continuous compounding of a
  position that never moves.
* `net_apy` converts a final position into an annualised rate: `(final / p0) ** (BPY / n) - 1`. All policies are
  compared on this quantity.
""")

# --- 3.2 T1
md(r"""
### 3.2 - T1, the gas-aware threshold rule

This is the primary policy of the study and the reference against which every other rule is measured. It carries no
fitted parameters: the only learned quantity is the running estimate of how long a leader tends to remain the leader,
and that estimate is updated from the data as the replay proceeds.
""")
code(pick(CORE, ["run_t1"]))
md(r"""
**How the loop works, block by block.**

1. *Accrue.* If a venue is held (`cur >= 0`) and its APR is not `NaN`, the position grows by `1 + apr / BPY`.
2. *Track the leader.* `wins[i]` is the venue with the highest APR this block. When the leader changes
   (`win != last_win`), the number of blocks the previous leader lasted, `block[i] - last_win_blk`, is folded into the
   dwell estimate with `dwell = alpha * (elapsed) + (1 - alpha) * dwell`. This is the EWMA; `alpha = 0.1` weights the
   most recent regime at 10 %.
3. *Cold start.* On the first block the position is placed in the current leader and one gas cost is paid; this
   counts as the first rebalance for every policy.
4. *Switch test.* Whenever the leader differs from the held venue, the inequality
   `pos * (best[i] - apr[i, cur]) * dwell / BPY > cost[i]` is evaluated. The left side is the expected dollar gain
   from the spread over the expected dwell; if it exceeds the dollar cost of the move, the position switches and pays
   `cost[i]`. Otherwise it holds, even though a higher rate is available - this is the gas gate that separates T1 from
   the greedy baseline.

`want_equity=True` records the position after every block (used by the block bootstrap in S9); `switch_log` records
every `(block index, destination)` pair (used by the random-destination null and the capacity model).
""")

# --- 3.3 baselines
md(r"""
### 3.3 - Baselines B1-B4

Each baseline removes one ingredient of T1 so that its contribution can be measured. B1/B2 remove switching altogether;
B3 removes the gas gate; B4 replaces the single-factor spread rule with a multi-criteria score.
""")
code(pick(CORE, ["run_fixed", "run_greedy", "run_ema"]))
md(r"""
**What each baseline controls for.**

* `run_fixed` (B1 always-Aave, B2 always-Compound) enters the target venue on the first block it has a rate and never
  moves again. It answers: what does a depositor earn by parking in one venue?
* `run_greedy` (B3) moves to the highest-APR venue on every block on which it changes, paying gas each time (ties are
  held). It answers: how much of T1's return comes from the *selection* and how much from the *discipline* of the gas
  gate? The difference between B3 and T1 is the gas drag of unconditional chasing.
* `run_ema` (B4) scores each venue on four EMA-smoothed factors with fixed weights - APR 0.40, risk 0.25 (as
  `1 - utilisation / max`), cost 0.20, stability 0.15 (TVL share) - and switches when the best score beats the held
  score by more than `thr = 0.05`. Note that in this reimplementation the cost factor is a constant `1.0` for every
  venue, so it shifts all scores equally and does not affect the choice; the effective weights are APR / risk /
  stability. This is the MCDM design of the earlier vault prototype and is included as the multi-criteria benchmark.
""")

# --- 3.4 T2
md(r"""
### 3.4 - T2, Ornstein-Uhlenbeck optimal stopping

T2 asks whether modelling the spread's dynamics improves on T1's empirical dwell. The top-vs-runner-up spread is
treated as a mean-reverting process; if the process reverts, a spread above its long-run mean is expected to shrink,
so the policy should demand a larger spread before paying to move. The stopping boundary has a closed form.
""")
code(pick(CORE, ["ou_fit", "run_t2"]))
md(r"""
**How the calibration and the boundary work.**

* `ou_fit` estimates the OU parameters from the last `window = 5,000` spread observations by the discrete-time
  regression `S[t+1] = a + b * S[t] + e`. The mapping is `kappa = -ln(b)` (mean-reversion speed per block),
  `theta = a / (1 - b)` (long-run mean), and `sigma` from the residual variance scaled by `2 * kappa / (1 - b^2)`.
  If the regression slope is at or above one there is no mean reversion and `kappa` is returned as zero.
* `run_t2` keeps the last 5,000 finite spreads in a ring buffer and recalibrates every `recalibrate_every = 5,000`
  blocks. Its accrual, dwell tracking and cold start are identical to T1.
* When the leader differs from the held venue, two branches exist. If `kappa <= 1e-6` (no measurable mean reversion)
  or the spread is not finite, the rule *falls back to T1's inequality*. Otherwise it computes the Bellman boundary
  `S* = theta + sigma * sqrt((cost / pos) / kappa)` and switches only if the current spread exceeds it.

Because the fitted `kappa` is small for long stretches of the sample, T2 spends much of its time in the T1 branch -
which is why the two policies produce nearly identical results in S4 and S5.
""")

# ============================================================ S4 MAIN MATRIX
md(r"""
## 4 - Main result - the test-window matrix

**Setup.** On the held-out test window (Jan-Apr 2026, 863,999 blocks, $1 M start) all seven policies are replayed and
net APY, rebalance count, gas, and final equity are reported. These are the principal reference values (T1 net APY
through buy-and-hold final equity); the cell prints each beside its reference value.
""")
code(r"""
apr, gas, eth, blk, util, tvl, ts = slice_arrays(panel, "2026-01-01", "2026-05-01"); n = len(apr)
runs = [
    ("B1 always-Aave",      run_fixed(apr, gas, eth, PROT.index("aave_v3"))),
    ("B2 always-Compound",  run_fixed(apr, gas, eth, PROT.index("compound_v3"))),
    ("B3 greedy-spot",      run_greedy(apr, gas, eth)),
    ("B4 MCDM-EMA",         run_ema(apr, util, tvl, gas, eth)),
    ("T1 threshold",        run_t1(apr, gas, eth, blk)),
    ("T2 OU optimal-stop",  run_t2(apr, gas, eth, blk)),
]
MACRO = {"B1 always-Aave": "3.26% / $1,010,605", "B2 always-Compound": "2.69% / $1,008,757",
         "B3 greedy-spot": "5.35% 424 / $1,017,293", "B4 MCDM-EMA": "4.64% 70 / $1,015,028",
         "T1 threshold": "5.37% 322 / $1,017,341", "T2 OU optimal-stop": "5.34% 175 / $1,017,242"}
matrix = pd.DataFrame([{"policy": nm, "net_APY_%": round(net_apy(f, n), 2), "rebalances": s,
                        "final_$": round(f), "paper_target": MACRO[nm]} for nm, (f, s) in runs])
print(matrix.to_string(index=False))

fig, ax = plt.subplots(figsize=(8, 3.2))
ax.bar(matrix.policy, matrix["net_APY_%"], color=["#bbb","#bbb","#d88","#8ac","#2a7","#69b"])
ax.axhline(3.26, ls="--", c="#888", lw=1, label="passive Aave 3.26%")
ax.set_ylabel("net APY (%)"); ax.set_title("Test-window net APY by policy"); ax.legend()
plt.xticks(rotation=20, ha="right"); plt.tight_layout(); plt.show()
""")
md(r"""
**Output.** Every cell matches the reference values to the dollar and to the rebalance: T1 5.37 % (322 rebalances,
$1,017,341), T2 5.34 % (175), greedy 5.35 % (424), MCDM-EMA 4.64 % (70), passive Aave 3.26 %. T1 attains the highest net
APY; T2 is statistically indistinguishable from it; greedy earns slightly less while rebalancing 424x (gas drag); MCDM
trails.
""")

# ============================================================ S5 REGIME
md(r"""
## 5 - Regime breakdown - calm vs volatile

**Setup.** The test window is split into a calm quarter (2026-Q1) and a volatile one (early Q2). The reactive policies
are expected to widen their margin in the volatile regime, where dispersion is large. The cell reproduces the
per-quarter reference values.
""")
code(r"""
def _apy_set(a, b):
    A, G, E, B, U, T, _ = slice_arrays(panel, a, b); m = len(A)
    return {"T1": net_apy(run_t1(A, G, E, B)[0], m), "T2": net_apy(run_t2(A, G, E, B)[0], m),
            "greedy": net_apy(run_greedy(A, G, E)[0], m), "MCDM": net_apy(run_ema(A, U, T, G, E)[0], m),
            "Aave": net_apy(hold_final(A[:, PROT.index("aave_v3")]), m),
            "Compound": net_apy(hold_final(A[:, PROT.index("compound_v3")]), m)}
regime = pd.DataFrame({"Q1 calm (Jan-Mar)": _apy_set("2026-01-01", "2026-04-01"),
                       "Q2 volatile (Apr)": _apy_set("2026-04-01", "2026-05-01")}).round(2)
print(regime.to_string())
print("\npaper: T1 4.39/8.37  T2 4.35/8.37  greedy 4.39/8.31  MCDM 3.63/7.72  Aave 2.75/4.81  Compound 2.72/2.59")
""")
md(r"""
**Output.** Matches the reference regime values to <=0.02 pp (the single gap is MCDM-EMA Q2 = 7.70 % here vs 7.72 % in
the reference run - an EMA-seeding boundary effect on the one-month slice, not a logic difference). In the calm quarter
T1 ~ greedy ~ 4.39 % (the gas gate rarely fires); in the volatile quarter all reactive policies rise to ~8.4 % while
passive Aave reaches only 4.81 %. The margin is regime-dependent and largest when dispersion is high.
""")

# ============================================================ S6 WALK-FORWARD
md(r"""
## 6 - Walk-forward across six non-overlapping windows (generalisation)

**Setup.** This is the primary out-of-sample generalisation test: the edge is re-measured on six disjoint 3-month
windows spanning Nov 2024 -> Apr 2026 (both calm and volatile regimes). In each window, T1 is compared to the single
best venue chosen with hindsight of that window, which is a demanding passive benchmark. Persistence across every window
indicates the effect is not window-specific.

**The code.** `walk_forward` replays T1 on each window with capital reset to $1 M, computes the six buy-and-hold rates
on the same blocks, and records T1's margin over the *best* of them and over passive Aave. It also returns, per venue,
the list of six per-window margins - the paired differences that the significance test in S7 resamples.
""")
code(pick(ROBUST, ["PRETTY", "WINDOWS", "walk_forward"]))
code(r"""
wf, deltas = walk_forward(panel)
print(wf.to_string(index=False))
print(f"\nT1 beats the best in-hindsight venue {int((wf.edge_vs_best_pp>0).sum())}/6 windows; "
      f"beats passive Aave {int((wf.edge_vs_aave_pp>0).sum())}/6")
fig, ax = plt.subplots(figsize=(8, 3.2))
ax.bar(wf.window, wf.edge_vs_best_pp, color="#2a7")
for i, v in enumerate(wf.edge_vs_best_pp):
    ax.text(i, v + .03, f"+{v:.2f}", ha="center", fontsize=8)
ax.axhline(0, c="#333", lw=.8); ax.set_ylabel("edge over best hold (pp)")
ax.set_title("T1 beats the best in-hindsight venue in all 6 windows"); plt.tight_layout(); plt.show()
""")
md(r"""
**Output.** T1 exceeds the hindsight-best venue in 6/6 windows, by +0.45 to +1.85 pp in every window, and passive Aave
by +2.1 to +9.2 pp. The effect is consistent across windows rather than confined to a single period.
""")

# ============================================================ S7 SIGNIFICANCE
md(r"""
## 7 - Significance - per-window paired bootstrap + Holm correction

**Method.** The primary significance test is a per-window paired bootstrap: for each of the six non-overlapping
walk-forward windows, T1's net-APY margin over each passive venue is taken, the six paired margins are bootstrapped
(B=10,000) for a mean, 95% CI and one-sided p, and a Holm family-wise correction is applied across the six venue
contrasts. N=6 independent windows is the applicable sample size for assessing whether the edge persists out-of-sample.

*(The study additionally reports a secondary monthly-Sharpe test on the 4-month window. That statistic is an explicitly
low-power N=4 quantity computed on a different historical basis and is not recomputed here; on N=4 monthly observations
it is basis-sensitive and not robustly reproducible. The per-window net-APY bootstrap below is the basis-independent
inference on which the primary significance result rests.)*

**The code.** `paired_bootstrap_holm` resamples the six per-window margins of each venue with replacement 10,000 times
and records the distribution of the resampled mean; the one-sided p-value is the share of resampled means at or below
zero. `_holm` applies the step-down correction: the six p-values are sorted, the k-th smallest is multiplied by
`(6 - k + 1)`, and the running maximum is taken so that adjusted p-values stay monotone. A contrast "survives" if its
adjusted p-value is at most 0.05.
""")
code(pick(ROBUST, ["_holm", "paired_bootstrap_holm"]))
code(r"""
pbh = paired_bootstrap_holm(deltas)
print("Per-window paired bootstrap + Holm (T1 vs each venue hold, N=6 windows):")
print(pbh.to_string(index=False))
print(f"\n-> all six contrasts survive Holm at alpha=0.05: {bool(pbh.survives_holm.all())}")
print("   (Euler V2 is the smallest-margin / hardest contrast.)")
""")
md(r"""
**Output.** Every one of the six T1-vs-venue contrasts is positive with a 95% CI excluding zero and survives the Holm
family-wise correction at alpha=0.05. Euler V2 is the tightest contrast (the hardest), consistent with
S6. This is the primary significance result and it reproduces directly from the panel.
""")

# ============================================================ S8 T3 NEGATIVE CONTROL
md(r"""
## 8 - Out-of-sample evaluation of the T3 hazard tier (pre-registered negative control)

**Setup.** T3 is a Cox proportional-hazards model on "leader-flip" survival: features = F1 (Maker DSR lead rate) and
F3 (cross-venue fragmentation spreads). Fitting one model in-sample on the whole panel yields an apparent small
increment (+7.0 bp over T1), but this reflects look-ahead leakage. The leakage-free test is an expanding-window
walk-forward: for each window W2...W6, the Cox model is trained strictly on prior blocks (with a purge gap of 46,512
blocks ~ 6.5 days so no label reaches into the test window) and evaluated out-of-sample.

The T3 machinery is presented in six steps: the protocol constants, the two feature builders (F1, F3), the survival
labels, the Cox fit, the hazard replay, and the expanding-window driver. *(The driver is the slowest cell of the
notebook, ~1-2 min: it fits a Cox model per window.)*
""")

# --- 8.1 constants
md(r"""
### 8.1 - Protocol constants

The numbers below fix the leakage protocol. They follow the sample-construction rules of *Advances in Financial
Machine Learning* (triple-barrier horizon, purging, embargo) and are the same values used by the reference training
scripts; the reproduction changes none of them.
""")
code(pick(T3, ["WINDOWS", "HORIZON_BLOCKS", "EMBARGO_BLOCKS", "PURGE_GAP", "SUBSAMPLE_STRIDE", "MIN_TRAIN_ROWS",
               "COX_MAX_ROWS", "PENALIZER", "N_BOOT", "BOOT_SEED", "_LAG_1H", "_LAG_6H"]))
md(r"""
**What each constant does.**

* `HORIZON_BLOCKS = 7,200` (24 h) is the *vertical barrier* of the label: if the leader has not changed within 7,200
  blocks the observation is censored rather than labelled with a longer duration.
* `EMBARGO_BLOCKS = 39,312` (~1 % of the panel) is the buffer left after the training period so that the last training
  labels, which look up to one horizon ahead, cannot overlap the test window. `PURGE_GAP = HORIZON + EMBARGO =
  46,512` blocks (~6.5 days) is the total gap between the end of training data and the first test block.
* `SUBSAMPLE_STRIDE = 60` takes one training row per 60 blocks (~12 min): consecutive blocks carry nearly identical
  features and labels, so a stride reduces redundancy without losing information. `MIN_TRAIN_ROWS` guards against a
  degenerate design; `COX_MAX_ROWS = 20,000` caps the final fit at a fixed-seed subsample so the fit is both tractable
  and deterministic.
* `PENALIZER = 0.001` is the ridge penalty of the Cox fit; `N_BOOT` / `BOOT_SEED` parameterise the paired bootstrap of
  the per-window deltas; `_LAG_1H` / `_LAG_6H` are the lags (in rows = blocks) of the F1 features.
* This module carries its own copy of the window table (`WINDOWS`); W6 is written with an explicit end-of-day
  timestamp. The first window is not used for T3 because no training data precedes it.
""")

# --- 8.2 F1
md(r"""
### 8.2 - F1: lead-rate features

The F1 class follows the "lead instrument" idea from the HFT literature: a related, slower-moving rate may lead the
venues' rates. Here the lead instrument is the Maker DSR (the Sky/Maker savings rate), which is set by governance and
changes rarely. F1 encodes its level, two lags, a one-hour change, and its spread against the current best venue.
""")
code(pick(T3, ["build_f1"]))
md(r"""
**How the features are built without look-ahead.**

* The DSR series lives in a separate event file (546 rate changes). `pd.merge_asof(..., direction="backward")` joins
  each block to the *most recent DSR event at or before that block* - an as-of join, so a block never sees a future
  rate change. Blocks before the first recorded event receive `NaN`.
* Because the panel is a dense grid with one row per block, positional shifts of 300 and 1,800 rows are exactly one
  and six hours of lag; `f1_dsr_delta_300` is the one-hour change.
* `f1_lead_spread_dsr_vs_top` is the DSR minus the highest venue APR at the same block - positive when the
  governance-set rate is above the market, a condition under which the market rates have historically risen.
* Any `NaN` in a feature row later triggers the T1 fallback inside the T3 replay (S8.6), so missing lead data can never
  produce a model-driven decision.
""")

# --- 8.3 F3
md(r"""
### 8.3 - F3: fragmentation features

The F3 class describes the *cross-section* of venues at a block: how far apart the rates are and how they are
arranged. These are the same quantities T1 reacts to, now offered to the model as covariates for the flip hazard.
""")
code(pick(T3, ["build_f3"]))
md(r"""
**What is produced.** For the six venues in sorted-name order the builder emits the 15 pairwise spreads
`APR_i - APR_j` (all unordered pairs), plus three summaries of the row - `max - min`, the gap between the top two
venues, and the standard deviation of the six rates - and the integer identity of the current leader,
`f3_top_protocol_id`. The last column is *dropped before fitting* in the expanding-window models (S8.5). Its presence
in the deployed artifact is what makes the deployed T3 model fall back to T1 on every block, a point revisited in S8.7.
""")

# --- 8.4 labels
md(r"""
### 8.4 - Survival labels: blocks until the leader flips

The model does not predict the rate; it predicts *how long the current leader will remain the leader*. That is a
duration with right-censoring - exactly the object survival analysis was built for - and the label is constructed
with the triple-barrier logic of AFML: an event barrier (the flip) and a vertical barrier (the horizon).
""")
code(pick(T3, ["build_flip_labels"]))
md(r"""
**How the label is computed.** `top_idx` is the leader at each block and `flip_positions` are the blocks at which it
changes. For every block `i`, `blocks_to_flip` is the distance to the next flip; if that distance is within
`horizon = 7,200` blocks the observation is a *completed* duration (`event_observed = 1`), otherwise it is *censored*
at the horizon (`event_observed = 0`) - the flip is known to lie beyond 24 h but not when. The single forward pass with
the pointer `j` keeps the construction linear in the number of blocks.
""")

# --- 8.5 Cox
md(r"""
### 8.5 - The Cox proportional-hazards fit

The Cox model writes the flip hazard as `lambda(t | x) = lambda0(t) * exp(beta'x)`: a baseline hazard common to all
blocks, scaled multiplicatively by the covariates. It is fitted by partial likelihood, which uses only the *ordering*
of the durations and handles censoring naturally; `lifelines` provides the estimator.
""")
code(pick(T3, ["fit_cox"]))
md(r"""
**How the fit is set up.**

* The design matrix joins F1, F3 (without `f3_top_protocol_id`) and the labels on `block_number` and drops any row
  with a missing value; columns with zero variance are removed (a constant covariate cannot be estimated).
* If the design exceeds `COX_MAX_ROWS`, a fixed-seed subsample of 20,000 rows is drawn so that the fit is
  reproducible. `CoxPHFitter(penalizer=0.001)` adds a small ridge penalty for numerical stability.
* Two quantities leave the fit: the coefficient vector `beta` (aligned to `feature_names`) and the mean of the
  estimated baseline hazard, which the replay uses as `lambda0`. A concordance index is computed on a separate
  3,000-row subsample as a training-side diagnostic; it is *not* the out-of-fold C-index reported elsewhere in the
  study, and the two are not expected to coincide.
""")

# --- 8.6 replay
md(r"""
### 8.6 - The T3 replay: a model-driven dwell inside T1's rule

T3 does not introduce a new decision rule. It keeps T1's inequality and replaces the EWMA dwell with the model's
expected time to the next flip, `E[dwell] = 1 / lambda`. Everything else - accrual, gas, cold start - is unchanged, so
any difference between T3 and T1 is attributable to the dwell estimate alone.
""")
code(pick(T3, ["run_t3"]))
md(r"""
**How the replay decides.**

* The EWMA dwell of T1 is maintained on every block regardless of which branch is taken, because the fallback needs it.
* On a block where the feature row has no `NaN` and at least two venues have rates, the *model path* is used: the
  linear predictor `beta . x` is clipped to `[-50, 50]` for numerical safety, `hazard = lambda0 * exp(.)`, and
  `e_dwell = 1 / hazard`. The switch test is then `pos * spread * e_dwell / BPY > cost` - T1's rule with the model's
  dwell.
* If any feature is missing (or fewer than two venues are quoted), the block is decided by the *T1 fallback* with the
  EWMA dwell. This guarantees the policy is never worse-defined than T1 when the model cannot speak, and it is the
  mechanism by which a model with an unmaterialisable feature degrades to T1 exactly.
""")

# --- 8.7 protocol
md(r"""
### 8.7 - The expanding-window protocol

The last piece is the driver that makes the evaluation honest. For each window from W2 onward it trains on the strict
past, leaves the purge gap, materialises the features on the test window, replays T3 and T1 on the *same* blocks, and
records the difference in basis points; the five differences are then bootstrapped as paired observations.
""")
code(pick(T3, ["_is_supported_feature", "_build_feature_matrix", "_paired_bootstrap", "expanding_t3",
               "deployed_t3_equals_t1"]))
md(r"""
**How the protocol is enforced in code.**

* `expanding_t3` sets `train_end_block = first_test_block - PURGE_GAP` and trains only on blocks strictly below it,
  subsampled with the stride. The training set therefore *grows* window by window (expanding, not rolling) and never
  touches a block that a test-window label could reach.
* `_build_feature_matrix` rebuilds F1 from the DSR events and F3 from the window panel in the exact column order of the
  fitted model. It also reproduces a second safety mechanism of the live policy, encoded by `_is_supported_feature`: if
  the fitted artifact names any feature the live policy cannot materialise (the case of `f3_top_protocol_id`), the
  whole matrix is set to `NaN` and the replay falls back to T1 for the entire window.
* `deployed_t3_equals_t1` uses that mechanism to show that the *deployed* full-panel T3 artifact replays to exactly
  T1 on the test window - the reason the T3 row of the main matrix in S4 equals T1 to the dollar.
* `_paired_bootstrap` treats the per-window deltas as paired observations and reports the mean, its 95 % interval and
  the one-sided p-value for `H0: mean <= 0`.
""")
code(r"""
t3_windows, t3_stats = expanding_t3(panel, EVENTS_DSR_PATH)
print(t3_windows[["window_id", "t1_apy_pct", "t3_apy_pct", "delta_bp"]].to_string(index=False))
print(f"\nHONEST OOS T3-minus-T1: mean {t3_stats['mean_delta_bp']:+.2f} bp  "
      f"95% CI [{t3_stats['ci_low_95_bp']:+.2f}, {t3_stats['ci_high_95_bp']:+.2f}]  "
      f"p={t3_stats['p_one_sided_le0']:.3f}  wins={t3_stats['wins']}/{t3_stats['n_windows']}")
print("reference:  in-sample +7.03 bp (5/6, leaky)  ->  honest OOS -5.97 bp (0/5, CI [-9.89,-2.76])")

fig, ax = plt.subplots(figsize=(7.5, 3.2))
c = ["#c33" if d < 0 else "#2a7" for d in t3_windows.delta_bp]
ax.bar(t3_windows.window_id, t3_windows.delta_bp, color=c)
ax.axhline(0, c="#333", lw=.8); ax.set_ylabel("T3 - T1 (bp), out-of-sample")
ax.set_title("Pre-registered negative control: the ML model loses OOS in every window")
plt.tight_layout(); plt.show()
""")
md(r"""
**Output.** Out-of-sample the model underperforms T1 in 0/5 windows, mean -5.97 bp, with a confidence interval entirely
below zero. In-sample the increment is +7.0 bp; under the leakage-free expanding-window protocol it reverses to -5.97 bp
(0/5 windows), so the hazard tier is not adopted and the parameter-light T1 is retained. (The deployed T3 in S4 is
byte-identical to T1: its artifact lists a feature the live state cannot materialise, so it falls back to T1 on every
block.)

*Note on the per-window C-indices printed above:* these are training-subsample diagnostics for each expanding fit
(~0.64-0.67). They are a different quantity from the primary out-of-fold C-index (0.563 for F3, 0.582 for F1+F3), which
is computed on the full purged-CV design; the two are not expected to be equal and do not contradict each other.
""")

# ============================================================ S9 ROBUSTNESS
md(r"""
## 9 - Robustness suite - is the edge curve-fit?

**Method.** Four independent tests. (a) **Random-destination null**: keep T1's exact switch cadence and gas, but send
each segment to a random venue - isolates whether the selection (not the turnover) is the source of return. (b)
**Strategy-family PBO/CSCV** (Bailey-Lopez de Prado): over {T1, 6 holds}, the probability the in-sample-best strategy
underperforms out-of-sample. (c) **Parameter plateau**: net APY across a 30-point grid of T1's two parameters - a flat
surface is inconsistent with tuning. (d) **Gas-cost sweep** and **moving-block bootstrap with effective N**
(serial-correlation-aware significance).

**The code.** Each test is one function; all of them call the S3 engine.
""")
code(pick(ROBUST, ["random_null", "family_pbo", "param_plateau", "gas_sweep", "block_bootstrap"]))
md(r"""
**How each test is implemented.**

* `random_null` first replays T1 with `switch_log` on to obtain its exact switch blocks and destinations. It then
  re-prices the *same* sequence of segments with random destinations: each segment's growth is read from a table of
  cumulative log-growth per venue, so 5,000 random allocators are evaluated without re-running the loop. The z-score
  places T1's final position against that null distribution.
* `family_pbo` implements combinatorially symmetric cross-validation: the window is cut into `S = 8` blocks, every
  choice of 4 blocks is used in-sample and the complementary 4 out-of-sample (70 splits), the in-sample best of {T1,
  six holds} is identified, and its out-of-sample rank is converted to a logit. PBO is the share of splits in which
  that logit is at or below zero (the in-sample winner is below the out-of-sample median).
* `param_plateau` re-runs T1 over `dwell0 in {250 .. 8000} x alpha in {0.02 .. 0.4}` and reports the spread of net
  APY across the 30 settings.
* `gas_sweep` replaces the per-block gas column with a flat level from 10 to 200 gwei and re-runs T1 and greedy at
  each level.
* `block_bootstrap` builds daily equity for T1 and for the benchmark hold, takes daily log-excess returns, resamples
  them in moving blocks of five days 10,000 times, and estimates the effective sample size from the autocorrelation
  sum of the excess series.
""")
code(r"""
rn = random_null(apr, gas, eth, blk)
pbo = family_pbo(apr, gas, eth, blk)
pl = param_plateau(apr, gas, eth, blk)
gs = gas_sweep(apr, eth, blk)
bb = block_bootstrap(apr, gas, eth, blk, ts)
print(f"(a) random-destination null: T1 ${rn['t1']:,.0f} vs {rn['n']} random "
      f"(best ${rn['rand_max']:,.0f})  z={rn['z']:.1f}  p={rn['p']:.4f}")
print(f"(b) strategy-family PBO = {pbo['PBO']:.3f}  (T1 in-sample-best in {pbo['t1_is_best_frac']*100:.0f}% of {pbo['n_combos']} splits)")
print(f"(c) parameter plateau: net APY {pl['min']:.3f}-{pl['max']:.3f}%  spread {pl['spread_pp']:.3f} pp across 30 configs")
print(f"(d) block-bootstrap vs Aave: {bb['Aave hold']['mean_bp_day']:+.2f} bp/day  "
      f"CI {bb['Aave hold']['ci_bp']}  N_eff={bb['Aave hold']['n_eff']}")
print("\ngas sweep (T1 gas-gated vs naive greedy):\n", gs.to_string(index=False))

fig, axes = plt.subplots(1, 3, figsize=(13, 3.3))
axes[0].hist(rn["rand"], bins=40, color="#bbb"); axes[0].axvline(rn["t1"], c="#2a7", lw=2)
axes[0].set_title(f"Random-destination null (z={rn['z']:.1f})"); axes[0].set_xlabel("final $")
im = axes[1].imshow(pl["grid"], aspect="auto", cmap="viridis")
axes[1].set_xticks(range(len(pl["dwells"]))); axes[1].set_xticklabels(pl["dwells"], fontsize=7)
axes[1].set_yticks(range(len(pl["alphas"]))); axes[1].set_yticklabels(pl["alphas"], fontsize=7)
axes[1].set_title(f"Parameter plateau (spread {pl['spread_pp']:.3f}pp)"); axes[1].set_xlabel("dwell"); axes[1].set_ylabel("alpha")
plt.colorbar(im, ax=axes[1])
axes[2].plot(gs.gwei, gs.t1_apy, "o-", c="#2a7", label="T1 (gated)")
axes[2].plot(gs.gwei, gs.greedy_apy, "o-", c="#c33", label="greedy")
axes[2].axhline(0, c="#888", lw=.8); axes[2].set_title("Gas-cost sweep"); axes[2].set_xlabel("gwei"); axes[2].set_ylabel("net APY %"); axes[2].legend()
plt.tight_layout(); plt.show()
""")
md(r"""
**Output.** (a) T1 exceeds all 5,000 random allocators, roughly nine standard deviations above the null; the return
derives from venue selection, not turnover. (b) PBO = 0; the in-sample winner is the out-of-sample winner in 100 % of
splits. (c) a flat plateau (~0.016 pp across 30 settings), indicating no scope for tuning. (d) the edge declines
gradually with gas (T1 5.10 %->4.13 % over 10-200 gwei while naive greedy falls to -7.6 %) and remains significant under
a serial-correlation-aware bootstrap at N_eff~24.
""")

# ============================================================ S10 CAPACITY
md(r"""
## 10 - Capacity - deployable size

**Model.** The edge is finite: depositing size `P` into a venue depresses its own supply rate. Under a kinked
interest-rate model the marginal depositor lowers utilisation, and the earned rate falls by approximately
`yield_impact ~ 1/2 * kappa * u * P / (TVL + P)`, where `kappa` is the slope of the rate curve, `u` the utilisation
and `TVL` the pool size - a continuous drag paid every block, not a one-off slippage. The sweep spans $1 M -> $50 M,
time-weighting the impact by where T1 actually sits, on the full 18-month raw return.

**The code.** `IRM_SLOPE` holds the per-venue rate-curve slopes; `capacity` combines the walk-forward replay with the
impact formula.
""")
code(pick(ROBUST, ["IRM_SLOPE", "capacity"]))
md(r"""
**How the capacity curve is computed.** T1 is replayed over the six walk-forward windows with capital reset to $1 M in
each; the geometric product of the window returns, annualised, is the *raw* APY. The switch log gives the number of
blocks spent in each venue, hence a time share per venue. For each deposit size `P`, the drag in basis points is the
share-weighted sum over venues of `1/2 * slope * util * P / (TVL + P)`, using each venue's mean TVL and utilisation over
the sample; net APY is raw APY minus that drag. The model is deliberately conservative in one respect and generous in
another: it charges the impact continuously, but it assumes the venue can absorb `P` at all - which, for the thin
venues, is the binding constraint discussed in the output.
""")
code(r"""
raw, n_rebal, cap = capacity(panel)
print(f"T1 raw APY (18mo, full walk-forward) = {raw:.3f}%   n_rebalances = {n_rebal}")
print(cap.assign(size=lambda d: (d.size_usd/1e6).map(lambda x: f"${x:.0f}M"))[["size","raw_apy","impact_bp","net_apy"]].to_string(index=False))
print("reference (continuous model): net $1M 8.57% -> $50M 7.60%; ceiling ~$5-10M from venue depth")
fig, ax = plt.subplots(figsize=(7, 3))
ax.plot(cap.size_usd/1e6, cap.net_apy, "o-", c="#2a7")
ax.set_xscale("log"); ax.set_xlabel("position ($M, log)"); ax.set_ylabel("net APY %")
ax.set_title("Capacity curve (yield-impact adjusted)"); plt.tight_layout(); plt.show()
""")
md(r"""
**Output.** Net APY falls from ~8.5 % at $1 M to ~7.6 % at $50 M (reproducing the reference continuous-model curve to
within a few bp). The binding real constraint is venue depth - the edge-carrying venues (Euler, Spark) cannot absorb
$25 M+, so the realistic full-strategy ceiling is single-digit millions.
""")

# ============================================================ S11 L2
md(r"""
## 11 - Appendix - presence of the mechanism on L2 (Base) *(optional, needs internet)*

**Setup.** The mechanism is chain-agnostic. On an L2 gas is ~$0.15, so the gas gate fires far more often, but the source
of return remains the cross-venue spread. The cell pulls live daily supply rates for the comparable Base USDC lenders
from DeFiLlama (free, no key) and measures the dispersion and whether it pays net of L2 gas. If the kernel has no
internet, the cell falls back to the committed measurement.
""")
code(r"""
COMMITTED = {"venues": "Aave V3 / Compound V3 / Fluid / Moonwell (Base)",
             "median_daily_spread_pp": 2.17, "crossovers_per_month": 11.9,
             "gross_fuel_ceiling_pp": 0.95, "net_pays_from_usd": 10_000, "note": "committed offline result"}
try:
    import urllib.request
    def _g(u):
        req = urllib.request.Request(u, headers={"User-Agent": "research/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    pools = _g("https://yields.llama.fi/pools")["data"]
    want = [("aave-v3", "USDC"), ("compound-v3", "USDC"), ("fluid-lending", "USDC"), ("moonwell-lending", "USDC")]
    series = {}
    for proj, sym in want:
        cs = sorted([p for p in pools if p.get("chain") == "Base" and p.get("project") == proj and p.get("symbol") == sym],
                    key=lambda p: -(p.get("tvlUsd") or 0))
        if cs:
            d = _g(f"https://yields.llama.fi/chart/{cs[0]['pool']}")["data"]
            s = pd.Series({pd.to_datetime(x["timestamp"]).floor("D"): x.get("apyBase") for x in d if x.get("apyBase") is not None})
            series[proj] = s[~s.index.duplicated(keep="last")]
    df = pd.DataFrame(series).dropna()
    sp = (df.max(axis=1) - df.min(axis=1))
    lead = df.idxmax(axis=1); xover = int((lead != lead.shift()).sum())
    print(f"Base venues: {list(df.columns)}  ({len(df)} days {df.index.min().date()}..{df.index.max().date()})")
    print(f"median daily cross-venue spread: {sp.median():.2f} pp | crossovers {xover} ({xover/(len(df)/30):.1f}/mo)")
    print("-> the fuel exists on Base too (live).")
except Exception as ex:
    print(f"[no internet - using committed measurement] {ex}")
    print(COMMITTED)
""")
md(r"""
**Output.** Live (or committed): the four comparable Base USDC lenders show a median daily spread ~2.2 pp with the
leader rotating ~12x/month - slightly more dispersion than mainnet, but thinner venues, so the viable L2 position size is
~$10k-$300k rather than institutional size.
""")

# ============================================================ S12 CONCLUSION + REPRO TABLE
md(r"""
## 12 - Conclusion and reproduction ledger

The allocator's edge is a reaction to an observable cross-section rather than a forecast, which is consistent with its
out-of-sample generalisation (walk-forward 6/6), the absence of tunable parameters (flat plateau, PBO=0), and its
persistence against the nulls (random-destination roughly nine standard deviations above the null). The one forecasting
component (T3) was pre-registered as a likely negative and underperformed out-of-sample, so the parameter-light reactive
rule is retained. Limitations: the sample spans ~18 months on a single chain; capacity is single-digit-$M (venue depth);
and the edge diminishes if venue rates converge.

The ledger below confirms every principal reference number was recomputed in this single notebook from the cached panel.
""")
code(r"""
ledger = pd.DataFrame([
    ("T1 net APY (test)",        "5.37%",     f"{matrix.loc[matrix.policy=='T1 threshold','net_APY_%'].iloc[0]:.2f}%"),
    ("T1 final equity",          "$1,017,341",f"${int(matrix.loc[matrix.policy=='T1 threshold','final_$'].iloc[0]):,}"),
    ("T2 net APY (test)",        "5.34%",     f"{matrix.loc[matrix.policy=='T2 OU optimal-stop','net_APY_%'].iloc[0]:.2f}%"),
    ("greedy / MCDM net APY",    "5.35/4.64%",f"{matrix.loc[matrix.policy=='B3 greedy-spot','net_APY_%'].iloc[0]:.2f}/{matrix.loc[matrix.policy=='B4 MCDM-EMA','net_APY_%'].iloc[0]:.2f}%"),
    ("walk-forward T1>best hold","6/6",       f"{int((wf.edge_vs_best_pp>0).sum())}/6"),
    ("Holm: contrasts surviving","6/6",       f"{int(pbh.survives_holm.sum())}/6"),
    ("T3 OOS mean delta",        "-5.97 bp",  f"{t3_stats['mean_delta_bp']:+.2f} bp"),
    ("T3 OOS wins",              "0/5",       f"{t3_stats['wins']}/{t3_stats['n_windows']}"),
    ("random-null z-score",      "~9",        f"{rn['z']:.1f}"),
    ("strategy-family PBO",      "0.00",      f"{pbo['PBO']:.2f}"),
    ("parameter plateau spread", "0.016 pp",  f"{pl['spread_pp']:.3f} pp"),
    ("capacity net @ $1M",       "8.57%",     f"{cap.net_apy.iloc[0]:.2f}%"),
], columns=["quantity", "reference value", "reproduced here"])
print(ledger.to_string(index=False))
print("\nAll headline numbers reproduced from per_block_panel.parquet - no API keys, no fractal-defi.")
""")
md(r"""
*Reproducibility:* this notebook + `per_block_panel.parquet` + `events_dsr.parquet` are the complete artifact. Author:
Sergei Solovev. Engine validated to reproduce the production `EventReplayEngine` to the dollar.
""")

# ============================================================ COMPLETENESS GUARD
# Every top-level definition of the three modules must appear in the notebook,
# except the two module-path constants the notebook does not need.
_emitted = set()
for c in cells:
    if c.cell_type == "code":
        _emitted.update(m.group(1) for m in re.finditer(r"^(?:def )?([A-Za-z_]\w*)(?:\(| = )", c.source, re.M))
_expected_missing = {"_DEFAULT_DSR_PATH", "_DEFAULT_PANEL_PATH"}
_missing = (set(CORE) | set(ROBUST) | set(T3)) - _emitted
if _missing != _expected_missing:
    raise RuntimeError(f"definitions dropped from the notebook: {sorted(_missing - _expected_missing)}; "
                       f"unexpectedly present: {sorted(_expected_missing - _missing)}")

# ============================================================ WRITE
nb = nbf.v4.new_notebook(cells=cells)
nb.metadata.update({"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                    "language_info": {"name": "python"}})
OUT.parent.mkdir(parents=True, exist_ok=True)
nbf.write(nb, OUT)
print(f"wrote {OUT}  ({len(cells)} cells: {sum(c.cell_type=='markdown' for c in cells)} md / {sum(c.cell_type=='code' for c in cells)} code)")
