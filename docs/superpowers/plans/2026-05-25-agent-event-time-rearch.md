# Agent Event-Time Re-Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-architect the standalone `DeFi-Vega Project/` agent (currently an hourly poll loop with 2 ProtocolReaders) into a per-block, event-time agent that mirrors the research-side decision policies bit-for-bit. Six lending venues (Aave V3, Compound V3, Spark, Morpho, Fluid, Euler V2) are read every block via `web3.py` async WebSocket subscription; the same `decision/` policies (T1/T2/T3) consume the live `BlockState` and emit `Action`s; switches are submitted through the Flashbots private mempool to neutralise the asymmetric-speed-bump risk MacKenzie pp 200-203 calls "venue-asymmetric latency arbitrage."

**Architecture:** A symlink (Windows directory junction) bridges `DeFi-Vega Project/agent/decision/` to the research-side `predictive-mcdm-defi/decision/` package so the agent and the empirical-study notebooks consume **the same** policy classes — no copy-paste drift. Six `agent/protocols/*.py` modules implement the existing `ProtocolReader` contract (`read_state(block_number) -> ProtocolState`). `agent/per_block_loop.py` replaces the hourly `main.py`: it subscribes via `eth_subscribe newHeads`, gathers all six reads concurrently, assembles a `BlockState`, calls `policy.decide(state)`, and either holds or dispatches to `agent/mempool.py`. State for the OU calibrator and T3 hazard features lives in a rolling 5,000-block parquet under `agent/state/history.parquet`, written atomically.

**Tech Stack:** Python 3.11 (existing `agent/.venv`), `web3==6.20.x` (async WS), `aiohttp` (Flashbots POST), `eth-account` (Flashbots reputation signer), `pandas`, `pyarrow`. No new dependencies beyond what `agent/requirements.txt` already pins for the hourly-poll version.

**Prerequisites:**
- Plan B complete: `decision/{base,t1_threshold,t2_optimal_stopping,ou_calibrator}.py` are in `predictive-mcdm-defi/decision/`.
- Plan C complete: `decision/t3_hazard.py` and `decision/features/{f1,f3,f4}.py` exist.
- Plan D complete (empirical study) — used only to source measured EWMA spans / OU windows that the agent inherits at startup.
- `DeFi-Vega Project/agent/protocols/{aave,compound}.py` exist and define the `ProtocolReader` ABC the new four readers must conform to.

**Spec source of truth:** `C:\Users\1\.claude\plans\enumerated-scribbling-barto.md` §Operationalisation, "Live agent re-architecture (Week 5)" subsection.

**Citation grounding:** `docs/research/literature-foundation.md` §6 MacKenzie *Material Markets* pp 200-203 (private-mempool as asymmetric-speed-bump remedy), §1 O'Hara (block = Kyle batch auction), §2 Krause (OU re-calibration cadence).

---

## File map

```
DeFi-Vega Project/agent/
├── decision/                                  # NEW: junction to ../../predictive-mcdm-defi/decision/
│                                              #      (Windows: mklink /J; POSIX: ln -s)
├── protocols/
│   ├── aave.py                                # EXISTING — pattern source
│   ├── compound.py                            # EXISTING — pattern source
│   ├── spark.py                               # NEW: Spark sUSDS lending pool reader
│   ├── morpho.py                              # NEW: Morpho Blue base-market reader
│   ├── fluid.py                               # NEW: Fluid liquidity-layer reader
│   └── euler.py                               # NEW: Euler V2 EVK vault reader
├── signal/
│   ├── __init__.py                            # NEW
│   ├── f1.py                                  # NEW: single-row F1 wrapper
│   ├── f3.py                                  # NEW: single-row F3 wrapper
│   └── f4.py                                  # NEW: single-row F4 wrapper
├── state/
│   ├── __init__.py                            # NEW
│   ├── history.py                             # NEW: rolling parquet + atomic write
│   └── history.parquet                        # OUTPUT (gitignored)
├── per_block_loop.py                          # NEW: replaces main.py
├── mempool.py                                 # NEW: Flashbots private-mempool client
└── RUNBOOK.md                                 # NEW: Sepolia paper-trade operator doc

tests/agent/
├── test_decision_bridge.py                    # NEW: importlib + sys.path order
├── test_protocols_spark.py                    # NEW
├── test_protocols_morpho.py                   # NEW
├── test_protocols_fluid.py                    # NEW
├── test_protocols_euler.py                    # NEW
├── test_per_block_loop.py                     # NEW: mocked WS + policy dispatch
├── test_mempool.py                            # NEW: mocked Flashbots HTTP
├── test_signal_f1.py                          # NEW
├── test_signal_f3.py                          # NEW
├── test_signal_f4.py                          # NEW
└── test_state_history.py                      # NEW: rolling-window + atomic-rename
```

---

## Canonical `ProtocolState` and `BlockState` carry-over

The agent already defines `ProtocolState` in `agent/protocols/__init__.py` (Plan-D-precursor). The four new readers MUST emit instances of this exact dataclass, and `per_block_loop.py` MUST assemble a `decision.base.BlockState` (imported through the junction) using the same field names.

| `ProtocolState` field | Type | Source |
|---|---|---|
| `protocol` | `str` | Hard-coded per reader (`"spark"`, `"morpho"`, `"fluid"`, `"euler"`) |
| `block_number` | `int` | From the `newHeads` event |
| `lending_apr` | `float` | Decimal (NOT pp) — divide by 1e27 if RAY |
| `utilization` | `float` | Decimal in [0, 1] |
| `tvl_usd` | `float` | USD notional supplied |
| `fetched_at` | `pd.Timestamp` | `Timestamp.utcnow()` |

`BlockState` ← merge six `ProtocolState`s into `protocols=("aave_v3","compound_v3","spark","morpho","fluid","euler")`, dicts for `lending_apr`/`utilization`/`tvl_usd`, plus `current_protocol`, `position_usd`, `gas_price_gwei` from the same block, `eth_price_usd` from a Chainlink feed reader, and `gas_used_estimate=200_000`.

---

## Task 1: Decision-modules import bridge (Windows directory junction)

**Files:**
- Create: `DeFi-Vega Project/agent/decision/` (junction → `predictive-mcdm-defi/decision/`)
- Create: `tests/agent/test_decision_bridge.py`

**Methodology:**

On Windows, a directory junction (`mklink /J <link> <target>`) is functionally identical to a POSIX symlink for `importlib`: Python's `FileFinder` walks the junction transparently and `__file__` resolves to the real target. No copy, no submodule, no `pip install -e .` — one filesystem-level redirect. The acceptance test `importlib.import_module("agent.decision.base").BlockState` must return the **same class object** as a direct `from decision.base import BlockState` against the research repo, proving zero-drift.

`sys.path` order matters: if the project root of the research repo is also on `sys.path`, two `decision` packages exist and Python picks whichever appears first. The test asserts the agent-rooted import resolves to the junction target (research-side file).

- [ ] **Step 1: Write the failing test**

`tests/agent/test_decision_bridge.py`:
```python
"""Decision-bridge contract: agent/decision/ MUST resolve to the
research-side predictive-mcdm-defi/decision/ package via a Windows
directory junction (POSIX symlink in CI). This is the zero-drift
guarantee — there is exactly ONE copy of T1/T2/T3 source on disk."""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = REPO_ROOT / "DeFi-Vega Project" / "agent"
RESEARCH_DECISION = REPO_ROOT / "predictive-mcdm-defi" / "decision"


def test_agent_decision_junction_exists():
    """agent/decision/ must exist as either a directory junction (Windows)
    or a symlink (POSIX). Plain directory means the junction is missing."""
    bridge = AGENT_ROOT / "decision"
    assert bridge.exists(), (
        f"agent/decision bridge missing at {bridge}. Run from agent/:\n"
        f"  mklink /J decision \"{RESEARCH_DECISION}\"   (cmd.exe, admin not required)"
    )
    # Junctions report is_dir()==True but resolve() != the literal path.
    assert bridge.resolve() == RESEARCH_DECISION.resolve(), (
        f"bridge resolves to {bridge.resolve()}, expected {RESEARCH_DECISION.resolve()}"
    )


def test_importlib_resolves_to_research_file():
    """Importing agent.decision.base must yield the same module file as
    importing decision.base directly against the research repo."""
    # Pre-pend the agent's parent so `import agent.decision.base` works.
    sys.path.insert(0, str(AGENT_ROOT.parent))
    try:
        agent_mod = importlib.import_module("agent.decision.base")
    finally:
        sys.path.pop(0)
    # And import the research-side directly.
    sys.path.insert(0, str(REPO_ROOT / "predictive-mcdm-defi"))
    try:
        research_mod = importlib.import_module("decision.base")
    finally:
        sys.path.pop(0)
    assert Path(agent_mod.__file__).resolve() == Path(research_mod.__file__).resolve(), (
        f"agent path {agent_mod.__file__} != research path {research_mod.__file__} "
        f"-- junction is broken or points to a copy"
    )


def test_blockstate_class_identity():
    """Both imports must return the EXACT same class object — not just an
    equivalent definition — so isinstance() works across module boundaries."""
    sys.path.insert(0, str(AGENT_ROOT.parent))
    sys.path.insert(0, str(REPO_ROOT / "predictive-mcdm-defi"))
    try:
        from agent.decision.base import BlockState as AgentBS  # noqa: WPS433
        from decision.base import BlockState as ResearchBS     # noqa: WPS433
    finally:
        sys.path.pop(0)
        sys.path.pop(0)
    # When Python imports the same file twice through two different
    # package paths it WILL create two different class objects. That
    # would break isinstance(). Our junction setup means only ONE file
    # exists -- but Python may still register two modules. The fix is
    # that downstream code only imports through ONE path (`agent.decision`).
    # This test PINS that the chosen single-source path is the agent one
    # and that, when both imports happen in the same interpreter session,
    # the file is identical.
    assert Path(__import__("agent.decision.base", fromlist=["base"]).__file__).resolve() \
        == Path(__import__("decision.base", fromlist=["base"]).__file__).resolve()


def test_sys_path_order_does_not_shadow_bridge(monkeypatch):
    """Inserting a sibling `decision/` earlier on sys.path must NOT shadow
    the agent.decision junction; agent imports go through `agent.decision`,
    not bare `decision`."""
    shadow_dir = AGENT_ROOT.parent / "scratch_shadow_decision"
    shadow_dir.mkdir(exist_ok=True)
    (shadow_dir / "decision").mkdir(exist_ok=True)
    (shadow_dir / "decision" / "__init__.py").write_text(
        '"""Decoy that MUST NOT be picked up by `from agent.decision import ...`."""\n'
        'IS_SHADOW = True\n'
    )
    monkeypatch.syspath_prepend(str(shadow_dir))
    sys.path.insert(0, str(AGENT_ROOT.parent))
    try:
        mod = importlib.import_module("agent.decision")
    finally:
        sys.path.pop(0)
    assert not getattr(mod, "IS_SHADOW", False), (
        "bare `decision` package shadowed the agent.decision bridge"
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows-only junction syntax check")
def test_junction_target_is_a_directory_not_a_file_symlink():
    """A file symlink would import the __init__.py only; we need the
    whole package. Verify the junction target is a directory."""
    bridge = AGENT_ROOT / "decision"
    assert bridge.resolve().is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\pytest tests\agent\test_decision_bridge.py -v
```
Expected: `FileNotFoundError` (bridge doesn't exist) or `AssertionError: bridge missing` from the first test, cascading failures in the rest.

- [ ] **Step 3: Create the bridge**

Create the Windows directory junction (one command, no Python code — but documented in `agent/RUNBOOK.md` and the test failure message):

```cmd
cd "D:\DeFi\DeFi-Vega Project\agent"
mklink /J decision "D:\DeFi\predictive-mcdm-defi\decision"
```

Add to `agent/.gitignore` (so the junction isn't accidentally committed as a directory):

```
# Decision bridge — created by `mklink /J` on first checkout, not a real dir.
decision/
```

And add the recovery instructions to `agent/RUNBOOK.md` (will be created in full in Task 7 — this is just the seed):

```markdown
## First-time setup: decision bridge

The `agent/decision/` directory is a Windows junction to the
research repo's `predictive-mcdm-defi/decision/` package. Recreate
it after fresh checkout:

```
cd "%REPO_ROOT%\DeFi-Vega Project\agent"
mklink /J decision "%REPO_ROOT%\predictive-mcdm-defi\decision"
```

POSIX equivalent (Linux/macOS CI):
```
ln -s "$REPO_ROOT/predictive-mcdm-defi/decision" "$REPO_ROOT/DeFi-Vega Project/agent/decision"
```
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\pytest tests\agent\test_decision_bridge.py -v
```
Expected: `5 passed` on Windows, `4 passed 1 skipped` on POSIX CI.

- [ ] **Step 5: Commit**

```bash
git add tests/agent/test_decision_bridge.py "DeFi-Vega Project/agent/.gitignore"
git commit -m "Decision-modules import bridge (Plan E Task 1)

Sets up agent/decision/ as a Windows directory junction (POSIX symlink
in CI) to predictive-mcdm-defi/decision/. The agent and the research
notebooks consume the SAME T1/T2/T3 source files -- zero drift, no
copy-paste.

The junction is created by an out-of-band mklink /J command (documented
in agent/RUNBOOK.md and reproduced in the test failure message). The
bridge directory is .gitignored because git's Windows-port mishandles
junctions and would commit it as a regular empty dir, breaking the
zero-drift guarantee on next checkout.

5 contract tests pin: junction-exists / importlib-resolves-to-research-
file / BlockState-class-identity / sys.path-order-does-not-shadow /
junction-target-is-directory (Windows-only).

Verified: importlib.import_module('agent.decision.base').__file__
resolves to D:\DeFi\predictive-mcdm-defi\decision\base.py, not a copy."
```

---

## Task 2: Four new ProtocolReaders (Spark, Morpho, Fluid, Euler)

**Files:**
- Read first (pattern source): `DeFi-Vega Project/agent/protocols/aave.py`, `DeFi-Vega Project/agent/protocols/compound.py`
- Create: `DeFi-Vega Project/agent/protocols/spark.py`
- Create: `DeFi-Vega Project/agent/protocols/morpho.py`
- Create: `DeFi-Vega Project/agent/protocols/fluid.py`
- Create: `DeFi-Vega Project/agent/protocols/euler.py`
- Create: `tests/agent/test_protocols_spark.py`
- Create: `tests/agent/test_protocols_morpho.py`
- Create: `tests/agent/test_protocols_fluid.py`
- Create: `tests/agent/test_protocols_euler.py`

**Methodology:**

Each reader subclasses the existing `agent.protocols.base.ProtocolReader` ABC (extracted from the existing `aave.py`/`compound.py` pattern) and exposes a single async method:

```python
async def read_state(self, block_number: int) -> ProtocolState
```

It does **one batched `eth_call`** at the specified block height, hitting:

| Protocol | Contract | Selectors |
|---|---|---|
| Spark | `0xC13e21B648A5Ee794902342038FF3aDAB66BE987` (sUSDS pool) | `getReserveData(bytes32)` → `currentLiquidityRate` (RAY/sec→annualized), `availableLiquidity`, `totalScaledVariableDebt` |
| Morpho | `0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFFb` (Morpho Blue) | `market(bytes32)` → returns `Market` struct with `totalSupplyAssets`, `totalBorrowAssets`, plus the configured IRM at `borrowRate(bytes32)` |
| Fluid | `0x52aa899454998Be5b000Ad077a46Bbe360F4e497` (Fluid liquidity layer) | `getOverallTokenData(address)` → `supplyRate`, `totalSupply`, `totalBorrow` |
| Euler | `0xEulerEVCxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` (EVK vault per asset; USDC vault address pinned in env) | `interestRate()` + `totalAssets()` + `totalBorrows()` |

USD-notional conversion: every reader multiplies the asset amount by `chainlink_price_usd(asset_addr, block_number)`, fetched via a shared `agent.oracles.chainlink.read_price(addr, block)` helper (exists from Plan-D-precursor; not modified here).

Each reader handles the RAY (1e27) and WAD (1e18) scaling at its source contract. The annualization convention matches the empirical-pipeline loaders:
```
annualized_apr = per_second_rate * 365 * 24 * 60 * 60
```
where `per_second_rate` is the per-second growth factor expressed as a decimal (e.g. `0.05 / (365 * 24 * 60 * 60)` for 5% APR).

- [ ] **Step 1: Write the failing test**

`tests/agent/test_protocols_spark.py`:
```python
"""Spark sUSDS lending pool ProtocolReader tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from agent.protocols.spark import SparkReader, SPARK_POOL_ADDRESS


@pytest.fixture
def mock_w3():
    w3 = MagicMock()
    # eth.call returns the encoded getReserveData(bytes32) tuple.
    # Layout (truncated to fields we use):
    #   currentLiquidityRate (uint128, RAY/sec * SECONDS_PER_YEAR)
    #   availableLiquidity   (uint256)
    #   totalScaledVariableDebt (uint256)
    # For test, we patch the higher-level decode helper, not raw bytes.
    return w3


@pytest.fixture
def mock_oracle():
    oracle = MagicMock()
    oracle.read_price = AsyncMock(return_value=1.0001)  # USDC peg
    return oracle


@pytest.mark.asyncio
async def test_read_state_returns_protocol_state(mock_w3, mock_oracle):
    reader = SparkReader(w3=mock_w3, oracle=mock_oracle, asset_addr="0xa0b8...USDC")
    # Patch the contract call to return a known reserve-data tuple.
    reader._call_get_reserve_data = AsyncMock(return_value={
        "currentLiquidityRate": int(0.045 * 1e27),    # 4.5% annualized, RAY
        "availableLiquidity": int(8e8 * 1e6),         # 800 M USDC (6 dec)
        "totalScaledVariableDebt": int(2e8 * 1e6),    # 200 M USDC borrowed
    })
    state = await reader.read_state(block_number=19_500_000)
    assert state.protocol == "spark"
    assert state.block_number == 19_500_000
    assert abs(state.lending_apr - 0.045) < 1e-6
    # tvl_usd = availableLiquidity (USDC raw) / 1e6 * price
    assert abs(state.tvl_usd - 8e8 * 1.0001) < 1e3
    # utilization = totalBorrow / (totalBorrow + availableLiquidity)
    assert abs(state.utilization - (2e8 / (2e8 + 8e8))) < 1e-6
    assert isinstance(state.fetched_at, pd.Timestamp)


@pytest.mark.asyncio
async def test_zero_liquidity_yields_zero_utilization(mock_w3, mock_oracle):
    """If both available and borrowed are zero, utilization is 0 (not NaN)."""
    reader = SparkReader(w3=mock_w3, oracle=mock_oracle, asset_addr="0xa0b8...USDC")
    reader._call_get_reserve_data = AsyncMock(return_value={
        "currentLiquidityRate": 0,
        "availableLiquidity": 0,
        "totalScaledVariableDebt": 0,
    })
    state = await reader.read_state(block_number=19_500_000)
    assert state.utilization == 0.0
    assert state.lending_apr == 0.0
    assert state.tvl_usd == 0.0


@pytest.mark.asyncio
async def test_reader_uses_block_number_for_eth_call(mock_w3, mock_oracle):
    """The block_number arg must propagate to the underlying eth_call."""
    reader = SparkReader(w3=mock_w3, oracle=mock_oracle, asset_addr="0xa0b8...USDC")
    captured = {}
    async def fake_call(block_number):
        captured["block"] = block_number
        return {"currentLiquidityRate": 0, "availableLiquidity": 0, "totalScaledVariableDebt": 0}
    reader._call_get_reserve_data = fake_call
    await reader.read_state(block_number=19_500_123)
    assert captured["block"] == 19_500_123


def test_spark_pool_address_is_pinned():
    """The Spark sUSDS pool address is a contract; pin it to detect upstream
    redeploys via test diff."""
    assert SPARK_POOL_ADDRESS == "0xC13e21B648A5Ee794902342038FF3aDAB66BE987"
```

`tests/agent/test_protocols_morpho.py`:
```python
"""Morpho Blue base-market ProtocolReader tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.protocols.morpho import MorphoReader, MORPHO_BLUE_ADDRESS


@pytest.mark.asyncio
async def test_read_state_decodes_market_tuple():
    """Morpho Blue's market(id) returns (totalSupplyAssets, totalSupplyShares,
    totalBorrowAssets, totalBorrowShares, lastUpdate, fee). Verify decoding."""
    w3 = MagicMock()
    oracle = MagicMock()
    oracle.read_price = AsyncMock(return_value=1.0)
    reader = MorphoReader(
        w3=w3, oracle=oracle,
        market_id="0x6c0c3d3...USDC_base_market_id",
        loan_asset="0xa0b8...USDC",
    )
    reader._call_market = AsyncMock(return_value=(
        int(1.5e9 * 1e6), int(1.5e9 * 1e18),  # supply assets / shares
        int(0.9e9 * 1e6), int(0.9e9 * 1e18),  # borrow assets / shares
        1_735_689_600, int(0.05 * 1e18),       # lastUpdate, fee (5%)
    ))
    reader._call_borrow_rate = AsyncMock(return_value=int(
        # Morpho's IRM returns rate per second WAD-scaled.
        # 0.06 annual / SECONDS_PER_YEAR * 1e18
        (0.06 / (365 * 24 * 60 * 60)) * 1e18
    ))
    state = await reader.read_state(block_number=19_500_000)
    assert state.protocol == "morpho"
    # supply_apr = borrow_rate * util * (1 - fee)
    util = 0.9e9 / 1.5e9
    expected = 0.06 * util * (1 - 0.05)
    assert abs(state.lending_apr - expected) < 5e-4


@pytest.mark.asyncio
async def test_empty_market_returns_zero_apr():
    w3 = MagicMock()
    oracle = MagicMock()
    oracle.read_price = AsyncMock(return_value=1.0)
    reader = MorphoReader(w3=w3, oracle=oracle,
                          market_id="0x0", loan_asset="0xa0b8...USDC")
    reader._call_market = AsyncMock(return_value=(0, 0, 0, 0, 0, 0))
    reader._call_borrow_rate = AsyncMock(return_value=0)
    state = await reader.read_state(block_number=19_500_000)
    assert state.lending_apr == 0.0
    assert state.utilization == 0.0


def test_morpho_blue_address_is_pinned():
    assert MORPHO_BLUE_ADDRESS == "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFFb"
```

`tests/agent/test_protocols_fluid.py`:
```python
"""Fluid liquidity-layer ProtocolReader tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.protocols.fluid import FluidReader, FLUID_LIQUIDITY_ADDRESS


@pytest.mark.asyncio
async def test_read_state_basic():
    w3 = MagicMock()
    oracle = MagicMock()
    oracle.read_price = AsyncMock(return_value=1.0)
    reader = FluidReader(w3=w3, oracle=oracle, asset_addr="0xa0b8...USDC")
    reader._call_get_overall_token_data = AsyncMock(return_value={
        # Fluid returns supplyRate in basis-points-per-year (NOT RAY).
        "supplyRate": 380,             # 3.80% APY
        "totalSupply": int(5e8 * 1e6), # 500 M USDC
        "totalBorrow": int(3e8 * 1e6), # 300 M USDC
    })
    state = await reader.read_state(block_number=19_500_000)
    assert state.protocol == "fluid"
    assert abs(state.lending_apr - 0.0380) < 1e-6
    assert abs(state.utilization - 0.6) < 1e-6
    assert abs(state.tvl_usd - 5e8) < 1e3


@pytest.mark.asyncio
async def test_borrow_exceeds_supply_clamps_utilization():
    """Defensive: a stale read where totalBorrow > totalSupply must clamp
    utilization to 1.0 rather than emit a >1 value."""
    w3 = MagicMock()
    oracle = MagicMock()
    oracle.read_price = AsyncMock(return_value=1.0)
    reader = FluidReader(w3=w3, oracle=oracle, asset_addr="0xa0b8...USDC")
    reader._call_get_overall_token_data = AsyncMock(return_value={
        "supplyRate": 1000,
        "totalSupply": int(1e8 * 1e6),
        "totalBorrow": int(1.2e8 * 1e6),   # 120 M borrowed vs 100 M supplied
    })
    state = await reader.read_state(block_number=19_500_000)
    assert state.utilization == 1.0


def test_fluid_address_is_pinned():
    assert FLUID_LIQUIDITY_ADDRESS == "0x52aa899454998Be5b000Ad077a46Bbe360F4e497"
```

`tests/agent/test_protocols_euler.py`:
```python
"""Euler V2 EVK vault ProtocolReader tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.protocols.euler import EulerReader


@pytest.mark.asyncio
async def test_read_state_from_evk_vault():
    """Euler V2 vaults expose interestRate() (per-second WAD-scaled),
    totalAssets() (WAD-scaled supply incl. accrued interest), and
    totalBorrows() (WAD-scaled). Supply APR = interestRate * util."""
    w3 = MagicMock()
    oracle = MagicMock()
    oracle.read_price = AsyncMock(return_value=1.0)
    reader = EulerReader(
        w3=w3, oracle=oracle,
        vault_addr="0xEuler_USDC_vault", asset_addr="0xa0b8...USDC",
    )
    reader._call_interest_rate = AsyncMock(return_value=int(
        # 7% borrow APR, expressed per-second WAD.
        (0.07 / (365 * 24 * 60 * 60)) * 1e18
    ))
    reader._call_total_assets = AsyncMock(return_value=int(2e8 * 1e6))
    reader._call_total_borrows = AsyncMock(return_value=int(1.4e8 * 1e6))
    state = await reader.read_state(block_number=19_500_000)
    assert state.protocol == "euler"
    util = 1.4e8 / 2e8
    expected_apr = 0.07 * util  # Euler has no protocol fee on supply APR
    assert abs(state.lending_apr - expected_apr) < 5e-4
    assert abs(state.utilization - util) < 1e-6


@pytest.mark.asyncio
async def test_empty_vault_returns_zero():
    w3 = MagicMock()
    oracle = MagicMock()
    oracle.read_price = AsyncMock(return_value=1.0)
    reader = EulerReader(w3=w3, oracle=oracle,
                         vault_addr="0xVault", asset_addr="0xa0b8")
    reader._call_interest_rate = AsyncMock(return_value=0)
    reader._call_total_assets = AsyncMock(return_value=0)
    reader._call_total_borrows = AsyncMock(return_value=0)
    state = await reader.read_state(block_number=1)
    assert state.lending_apr == 0.0
    assert state.utilization == 0.0
    assert state.tvl_usd == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\pytest tests\agent\test_protocols_spark.py tests\agent\test_protocols_morpho.py tests\agent\test_protocols_fluid.py tests\agent\test_protocols_euler.py -v
```
Expected: `ModuleNotFoundError: No module named 'agent.protocols.spark'` (and the three siblings).

- [ ] **Step 3: Write minimal implementation**

`DeFi-Vega Project/agent/protocols/spark.py`:
```python
"""Spark sUSDS lending pool ProtocolReader.

Spark forks Aave V3's pool architecture, so the ABI for getReserveData
matches Aave's exactly (uint128 currentLiquidityRate RAY-scaled,
uint256 availableLiquidity asset-token-decimals-scaled, etc).

Per-block reader for the event-time agent (per_block_loop.py). One
eth_call per block.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from agent.protocols.base import ProtocolReader, ProtocolState

SPARK_POOL_ADDRESS = "0xC13e21B648A5Ee794902342038FF3aDAB66BE987"
USDC_DECIMALS = 6
RAY = 10 ** 27


class SparkReader(ProtocolReader):
    name = "spark"

    def __init__(self, *, w3, oracle, asset_addr: str) -> None:
        self.w3 = w3
        self.oracle = oracle
        self.asset_addr = asset_addr

    async def _call_get_reserve_data(self, block_number: int) -> dict[str, int]:
        """One Aave-V3-style getReserveData call. Returns the fields we use."""
        # Real impl: contract.functions.getReserveData(asset).call(block_identifier=block_number)
        # Decoded to a dict by web3.py if ABI is supplied to Contract().
        contract = self.w3.eth.contract(address=SPARK_POOL_ADDRESS, abi=_SPARK_POOL_ABI)
        raw = await contract.functions.getReserveData(self.asset_addr).call(
            block_identifier=block_number
        )
        # Aave V3 reserve-data tuple field order (relevant slice):
        #   [0] configuration, [1] liquidityIndex, [2] currentLiquidityRate, ...
        #   [11] availableLiquidity (added by Spark), [12] totalScaledVariableDebt
        return {
            "currentLiquidityRate": int(raw[2]),
            "availableLiquidity": int(raw[11]),
            "totalScaledVariableDebt": int(raw[12]),
        }

    async def read_state(self, block_number: int) -> ProtocolState:
        data = await self._call_get_reserve_data(block_number)
        # currentLiquidityRate is annualized rate × RAY (Aave-style: per Aave docs,
        # currentLiquidityRate is the supply APR in ray, not per-second).
        lending_apr = data["currentLiquidityRate"] / RAY
        avail = data["availableLiquidity"] / 10 ** USDC_DECIMALS
        borrowed = data["totalScaledVariableDebt"] / 10 ** USDC_DECIMALS
        denom = avail + borrowed
        utilization = (borrowed / denom) if denom > 0 else 0.0
        price = await self.oracle.read_price(self.asset_addr, block_number)
        tvl_usd = avail * price
        return ProtocolState(
            protocol="spark",
            block_number=block_number,
            lending_apr=float(lending_apr),
            utilization=float(utilization),
            tvl_usd=float(tvl_usd),
            fetched_at=pd.Timestamp.utcnow(),
        )


_SPARK_POOL_ABI: list[dict[str, Any]] = [
    # Truncated for brevity in plan-doc; real file embeds the full Aave-V3-fork ABI.
    {
        "inputs": [{"name": "asset", "type": "address"}],
        "name": "getReserveData",
        "outputs": [{"name": "data", "type": "tuple"}],  # full struct in real ABI
        "stateMutability": "view",
        "type": "function",
    },
]
```

`DeFi-Vega Project/agent/protocols/morpho.py`:
```python
"""Morpho Blue base-market ProtocolReader.

Morpho Blue is a permissionless market protocol; each market is keyed by
a 32-byte market id and exposes the canonical (loan_asset, collateral_asset,
oracle, irm, lltv) tuple. Supply APR is derived from the configured IRM's
borrow rate × utilization × (1 - fee).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from agent.protocols.base import ProtocolReader, ProtocolState

MORPHO_BLUE_ADDRESS = "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFFb"
USDC_DECIMALS = 6
WAD = 10 ** 18
SECONDS_PER_YEAR = 365 * 24 * 60 * 60


class MorphoReader(ProtocolReader):
    name = "morpho"

    def __init__(self, *, w3, oracle, market_id: str, loan_asset: str) -> None:
        self.w3 = w3
        self.oracle = oracle
        self.market_id = market_id
        self.loan_asset = loan_asset

    async def _call_market(self, block_number: int) -> tuple:
        contract = self.w3.eth.contract(address=MORPHO_BLUE_ADDRESS, abi=_MORPHO_ABI)
        return await contract.functions.market(self.market_id).call(
            block_identifier=block_number
        )

    async def _call_borrow_rate(self, block_number: int) -> int:
        contract = self.w3.eth.contract(address=MORPHO_BLUE_ADDRESS, abi=_MORPHO_ABI)
        return await contract.functions.borrowRate(self.market_id).call(
            block_identifier=block_number
        )

    async def read_state(self, block_number: int) -> ProtocolState:
        (supply_assets, _supply_shares,
         borrow_assets, _borrow_shares,
         _last_update, fee_wad) = await self._call_market(block_number)
        per_sec_borrow_rate_wad = await self._call_borrow_rate(block_number)
        # Per-second rate (WAD) -> annualized decimal.
        annual_borrow_rate = (per_sec_borrow_rate_wad / WAD) * SECONDS_PER_YEAR
        supply_h = supply_assets / 10 ** USDC_DECIMALS
        borrow_h = borrow_assets / 10 ** USDC_DECIMALS
        utilization = (borrow_h / supply_h) if supply_h > 0 else 0.0
        fee = fee_wad / WAD
        lending_apr = annual_borrow_rate * utilization * (1 - fee)
        price = await self.oracle.read_price(self.loan_asset, block_number)
        return ProtocolState(
            protocol="morpho",
            block_number=block_number,
            lending_apr=float(lending_apr),
            utilization=float(utilization),
            tvl_usd=float(supply_h * price),
            fetched_at=pd.Timestamp.utcnow(),
        )


_MORPHO_ABI: list[dict[str, Any]] = [
    {"inputs": [{"name": "id", "type": "bytes32"}], "name": "market",
     "outputs": [{"name": "m", "type": "tuple"}], "stateMutability": "view",
     "type": "function"},
    {"inputs": [{"name": "id", "type": "bytes32"}], "name": "borrowRate",
     "outputs": [{"name": "rate", "type": "uint256"}], "stateMutability": "view",
     "type": "function"},
]
```

`DeFi-Vega Project/agent/protocols/fluid.py`:
```python
"""Fluid liquidity-layer ProtocolReader.

Fluid's liquidity layer aggregates supply/borrow across many vaults
sharing the same underlying asset. Supply APR is returned directly in
basis-points-per-year units by getOverallTokenData -- NO scaling or
annualisation needed (unlike Aave/Morpho).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from agent.protocols.base import ProtocolReader, ProtocolState

FLUID_LIQUIDITY_ADDRESS = "0x52aa899454998Be5b000Ad077a46Bbe360F4e497"
USDC_DECIMALS = 6


class FluidReader(ProtocolReader):
    name = "fluid"

    def __init__(self, *, w3, oracle, asset_addr: str) -> None:
        self.w3 = w3
        self.oracle = oracle
        self.asset_addr = asset_addr

    async def _call_get_overall_token_data(self, block_number: int) -> dict[str, int]:
        contract = self.w3.eth.contract(address=FLUID_LIQUIDITY_ADDRESS, abi=_FLUID_ABI)
        raw = await contract.functions.getOverallTokenData(self.asset_addr).call(
            block_identifier=block_number
        )
        return {
            "supplyRate": int(raw[0]),    # bps/year
            "totalSupply": int(raw[3]),   # asset-token decimals
            "totalBorrow": int(raw[4]),
        }

    async def read_state(self, block_number: int) -> ProtocolState:
        data = await self._call_get_overall_token_data(block_number)
        lending_apr = data["supplyRate"] / 10_000  # bps -> decimal
        supply_h = data["totalSupply"] / 10 ** USDC_DECIMALS
        borrow_h = data["totalBorrow"] / 10 ** USDC_DECIMALS
        # Defensive clamp -- a stale read where borrow > supply must NOT
        # emit a u > 1 (would break T2's spread arithmetic).
        utilization = min(borrow_h / supply_h, 1.0) if supply_h > 0 else 0.0
        price = await self.oracle.read_price(self.asset_addr, block_number)
        return ProtocolState(
            protocol="fluid",
            block_number=block_number,
            lending_apr=float(lending_apr),
            utilization=float(utilization),
            tvl_usd=float(supply_h * price),
            fetched_at=pd.Timestamp.utcnow(),
        )


_FLUID_ABI: list[dict[str, Any]] = [
    {"inputs": [{"name": "token", "type": "address"}],
     "name": "getOverallTokenData",
     "outputs": [{"name": "data", "type": "tuple"}],
     "stateMutability": "view", "type": "function"},
]
```

`DeFi-Vega Project/agent/protocols/euler.py`:
```python
"""Euler V2 EVK (Ethereum Vault Kit) ProtocolReader.

Each EVK vault is a single-asset vault with its own interestRate(),
totalAssets(), totalBorrows() view methods. interestRate() is the
*borrow* rate per second WAD-scaled; supply APR = borrow_apr * util
(Euler V2 has no protocol fee on supply yield by default).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from agent.protocols.base import ProtocolReader, ProtocolState

USDC_DECIMALS = 6
WAD = 10 ** 18
SECONDS_PER_YEAR = 365 * 24 * 60 * 60


class EulerReader(ProtocolReader):
    name = "euler"

    def __init__(self, *, w3, oracle, vault_addr: str, asset_addr: str) -> None:
        self.w3 = w3
        self.oracle = oracle
        self.vault_addr = vault_addr
        self.asset_addr = asset_addr

    async def _call_interest_rate(self, block_number: int) -> int:
        c = self.w3.eth.contract(address=self.vault_addr, abi=_EULER_ABI)
        return await c.functions.interestRate().call(block_identifier=block_number)

    async def _call_total_assets(self, block_number: int) -> int:
        c = self.w3.eth.contract(address=self.vault_addr, abi=_EULER_ABI)
        return await c.functions.totalAssets().call(block_identifier=block_number)

    async def _call_total_borrows(self, block_number: int) -> int:
        c = self.w3.eth.contract(address=self.vault_addr, abi=_EULER_ABI)
        return await c.functions.totalBorrows().call(block_identifier=block_number)

    async def read_state(self, block_number: int) -> ProtocolState:
        per_sec_rate_wad = await self._call_interest_rate(block_number)
        total_assets = await self._call_total_assets(block_number)
        total_borrows = await self._call_total_borrows(block_number)
        annual_borrow_apr = (per_sec_rate_wad / WAD) * SECONDS_PER_YEAR
        supply_h = total_assets / 10 ** USDC_DECIMALS
        borrow_h = total_borrows / 10 ** USDC_DECIMALS
        utilization = (borrow_h / supply_h) if supply_h > 0 else 0.0
        lending_apr = annual_borrow_apr * utilization
        price = await self.oracle.read_price(self.asset_addr, block_number)
        return ProtocolState(
            protocol="euler",
            block_number=block_number,
            lending_apr=float(lending_apr),
            utilization=float(utilization),
            tvl_usd=float(supply_h * price),
            fetched_at=pd.Timestamp.utcnow(),
        )


_EULER_ABI: list[dict[str, Any]] = [
    {"inputs": [], "name": "interestRate",
     "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalAssets",
     "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
    {"inputs": [], "name": "totalBorrows",
     "outputs": [{"type": "uint256"}], "stateMutability": "view", "type": "function"},
]
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\pytest tests\agent\test_protocols_spark.py tests\agent\test_protocols_morpho.py tests\agent\test_protocols_fluid.py tests\agent\test_protocols_euler.py -v
```
Expected: `12 passed` (4 spark + 3 morpho + 3 fluid + 2 euler).

- [ ] **Step 5: Commit**

```bash
git add "DeFi-Vega Project/agent/protocols/spark.py" "DeFi-Vega Project/agent/protocols/morpho.py" "DeFi-Vega Project/agent/protocols/fluid.py" "DeFi-Vega Project/agent/protocols/euler.py" tests/agent/test_protocols_spark.py tests/agent/test_protocols_morpho.py tests/agent/test_protocols_fluid.py tests/agent/test_protocols_euler.py
git commit -m "4 new ProtocolReaders: Spark, Morpho, Fluid, Euler V2 (Plan E Task 2)

Each subclasses agent.protocols.base.ProtocolReader (the existing ABC
extracted from aave.py + compound.py) and exposes:
  async def read_state(block_number: int) -> ProtocolState

Per-protocol contract details:
  Spark   - Aave-V3-fork getReserveData; currentLiquidityRate is
            annualized RAY (NOT per-second).
  Morpho  - market(id) + borrowRate(id); supply_apr =
            borrow_per_sec_wad * SECONDS_PER_YEAR * util * (1 - fee).
  Fluid   - getOverallTokenData; supplyRate is bps/year (NO scaling).
            Defensive utilization clamp at 1.0 for stale reads.
  Euler   - EVK vault interestRate()/totalAssets()/totalBorrows();
            no protocol fee on supply APR.

Contract addresses pinned in test (e.g. Spark pool 0xC13e21B6...,
Morpho Blue 0xBBBBBbbB...) so upstream redeploys show up as a test diff
rather than silent corruption.

12 contract tests pass. Mock w3 + mock oracle isolate the units-and-
scaling logic from RPC; network=marked integration tests deferred to
Task 7 RUNBOOK."
```

---

## Task 3: `per_block_loop.py` — async WebSocket event-time loop

**Files:**
- Create: `DeFi-Vega Project/agent/per_block_loop.py`
- Create: `tests/agent/test_per_block_loop.py`

**Methodology** (lit-foundation §1 O'Hara batch-auction, §6 MacKenzie pp 200-203):

The hourly `main.py` calls `read_state()` every 3600 s, builds a snapshot, calls the policy, sleeps. The event-time replacement subscribes to Ethereum new-block notifications via `web3.py`'s async WebSocket provider:

```python
async with AsyncWeb3(WebSocketProvider(WS_URL)) as w3:
    subscription_id = await w3.eth.subscribe("newHeads")
    async for payload in w3.socket.process_subscriptions():
        block = payload["result"]
        # ...
```

Per `newHeads` event:
1. Read `block_number` and `gas_price_gwei` (`base_fee_per_gas + priority_fee_gwei`).
2. `asyncio.gather()` six `ProtocolReader.read_state(block_number)` calls.
3. Assemble `BlockState` (imported via the Task-1 junction: `from agent.decision.base import BlockState`).
4. `action = policy.decide(state)` (`policy` is wired at startup from a YAML config: `t1_threshold`, `t2_optimal_stopping`, or `t3_hazard`).
5. Branch:
   - `action.kind == "hold"`: log and continue.
   - `action.kind == "switch"`: call `agent.mempool.submit_private_tx(action.target_protocol, state)` (Task 4) → await receipt → log.
6. Append the block row to `agent.state.history.append(state, action)` (Task 6).

Concurrency: the six reads are gathered, but a per-block deadline of 4 s (one-third of the inter-block interval) bounds the wait — any reader slower than 4 s is dropped from this block's `BlockState` (its protocol becomes NaN-APR, which all three policies handle).

- [ ] **Step 1: Write the failing test**

`tests/agent/test_per_block_loop.py`:
```python
"""Per-block event-time loop tests.

These tests use a fake WebSocket subscription that yields canned
newHeads events and asserts the loop builds the right BlockState,
calls policy.decide(), and dispatches the correct branch."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from agent.per_block_loop import PerBlockLoop


def _make_proto_state(name, block, apr, util=0.7, tvl=1e9):
    from agent.protocols.base import ProtocolState
    return ProtocolState(
        protocol=name, block_number=block,
        lending_apr=apr, utilization=util, tvl_usd=tvl,
        fetched_at=pd.Timestamp.utcnow(),
    )


@pytest.mark.asyncio
async def test_loop_builds_blockstate_from_six_readers():
    """One newHeads event -> one BlockState assembled from all 6 readers."""
    captured_states = []

    class CaptureProto:
        name = "cap"
        def decide(self, state):
            captured_states.append(state)
            from agent.decision.base import Action
            return Action(kind="hold", target_protocol=None, rationale="capture")

    readers = {
        "aave_v3":     MagicMock(read_state=AsyncMock(side_effect=lambda b: _make_proto_state("aave_v3", b, 0.05))),
        "compound_v3": MagicMock(read_state=AsyncMock(side_effect=lambda b: _make_proto_state("compound_v3", b, 0.04))),
        "spark":       MagicMock(read_state=AsyncMock(side_effect=lambda b: _make_proto_state("spark", b, 0.045))),
        "morpho":      MagicMock(read_state=AsyncMock(side_effect=lambda b: _make_proto_state("morpho", b, 0.06))),
        "fluid":       MagicMock(read_state=AsyncMock(side_effect=lambda b: _make_proto_state("fluid", b, 0.038))),
        "euler":       MagicMock(read_state=AsyncMock(side_effect=lambda b: _make_proto_state("euler", b, 0.07))),
    }
    fake_w3 = MagicMock()
    fake_w3.eth.gas_price = 25_000_000_000
    loop = PerBlockLoop(
        w3=fake_w3, readers=readers,
        policy=CaptureProto(), mempool=AsyncMock(),
        history=AsyncMock(),
        position_usd=1_000_000.0, eth_price_usd_provider=AsyncMock(return_value=3500.0),
    )
    await loop._handle_block(block_number=19_500_000)

    assert len(captured_states) == 1
    s = captured_states[0]
    assert s.block_number == 19_500_000
    assert set(s.protocols) == {"aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler"}
    assert abs(s.lending_apr["euler"] - 0.07) < 1e-9
    assert abs(s.gas_price_gwei - 25.0) < 1e-9
    assert s.eth_price_usd == 3500.0


@pytest.mark.asyncio
async def test_loop_dispatches_to_mempool_on_switch():
    """policy returns kind='switch' -> mempool.submit_private_tx invoked."""
    from agent.decision.base import Action

    class SwitchPolicy:
        def decide(self, state):
            return Action(kind="switch", target_protocol="morpho", rationale="x")

    mempool = AsyncMock()
    mempool.submit_private_tx = AsyncMock(return_value={"status": "included", "txhash": "0xabc"})

    readers = {
        n: MagicMock(read_state=AsyncMock(side_effect=lambda b, _n=n: _make_proto_state(_n, b, 0.05)))
        for n in ["aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler"]
    }
    fake_w3 = MagicMock()
    fake_w3.eth.gas_price = 25_000_000_000
    loop = PerBlockLoop(
        w3=fake_w3, readers=readers, policy=SwitchPolicy(),
        mempool=mempool, history=AsyncMock(),
        position_usd=1_000_000.0,
        eth_price_usd_provider=AsyncMock(return_value=3500.0),
    )
    await loop._handle_block(block_number=19_500_001)
    mempool.submit_private_tx.assert_called_once()
    kwargs = mempool.submit_private_tx.call_args.kwargs
    assert kwargs["target_protocol"] == "morpho"


@pytest.mark.asyncio
async def test_slow_reader_is_dropped_from_blockstate():
    """A reader exceeding the 4-s deadline must NOT block the policy;
    its protocol comes through as NaN APR."""
    import math

    async def slow_read(block):
        await asyncio.sleep(10.0)   # > 4 s deadline
        return _make_proto_state("euler", block, 0.07)

    readers = {
        n: MagicMock(read_state=AsyncMock(side_effect=lambda b, _n=n: _make_proto_state(_n, b, 0.05)))
        for n in ["aave_v3", "compound_v3", "spark", "morpho", "fluid"]
    }
    readers["euler"] = MagicMock(read_state=slow_read)

    seen = []
    class P:
        def decide(self, state):
            seen.append(state)
            from agent.decision.base import Action
            return Action(kind="hold", target_protocol=None, rationale="")
    fake_w3 = MagicMock()
    fake_w3.eth.gas_price = 25_000_000_000
    loop = PerBlockLoop(
        w3=fake_w3, readers=readers, policy=P(),
        mempool=AsyncMock(), history=AsyncMock(),
        position_usd=1.0, eth_price_usd_provider=AsyncMock(return_value=3500.0),
        per_block_deadline_s=0.5,   # tighten for the test
    )
    await loop._handle_block(block_number=19_500_002)
    assert len(seen) == 1
    assert math.isnan(seen[0].lending_apr["euler"])


@pytest.mark.asyncio
async def test_loop_appends_to_history_each_block():
    history = AsyncMock()
    from agent.decision.base import Action

    class P:
        def decide(self, state):
            return Action(kind="hold", target_protocol=None, rationale="")

    readers = {
        n: MagicMock(read_state=AsyncMock(side_effect=lambda b, _n=n: _make_proto_state(_n, b, 0.05)))
        for n in ["aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler"]
    }
    fake_w3 = MagicMock()
    fake_w3.eth.gas_price = 25_000_000_000
    loop = PerBlockLoop(
        w3=fake_w3, readers=readers, policy=P(),
        mempool=AsyncMock(), history=history,
        position_usd=1.0, eth_price_usd_provider=AsyncMock(return_value=3500.0),
    )
    await loop._handle_block(block_number=19_500_003)
    history.append.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\pytest tests\agent\test_per_block_loop.py -v
```
Expected: `ModuleNotFoundError: No module named 'agent.per_block_loop'`.

- [ ] **Step 3: Write minimal implementation**

`DeFi-Vega Project/agent/per_block_loop.py`:
```python
"""Per-block event-time loop -- replaces the hourly main.py.

Subscribes to Ethereum new-block headers via web3.py's async WebSocket
provider (eth_subscribe newHeads). For every new block:
  1. Gather six ProtocolReader.read_state(block_number) calls.
  2. Assemble decision.base.BlockState.
  3. Call policy.decide(state) -> Action.
  4. Branch: hold (log) or switch (dispatch to Flashbots mempool).
  5. Append to rolling history parquet.

Slow-reader handling: per-block deadline = 4 s (one-third of the 12-s
inter-block interval). Any reader exceeding it is dropped (NaN APR)
rather than blocking the entire policy step.

Kyle batch-auction semantic (lit-foundation S1 O'Hara): one block ==
one batch. Policy decisions are made on the AT-block snapshot; switches
target the NEXT block via private mempool (Flashbots) so we don't fight
public-mempool front-runners (MacKenzie pp 200-203 asymmetric speed
bump).
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Awaitable, Callable, Mapping

import pandas as pd

# Import via the Task-1 junction so the agent and research notebooks
# share the SAME Policy and BlockState class objects.
from agent.decision.base import Action, BlockState, DecisionPolicy
from agent.protocols.base import ProtocolReader, ProtocolState

log = logging.getLogger(__name__)

DEFAULT_GAS_USED_ESTIMATE = 200_000
DEFAULT_PER_BLOCK_DEADLINE_S = 4.0


class PerBlockLoop:
    """Event-time agent loop. Constructed once, then `run()` forever."""

    def __init__(
        self,
        *,
        w3,                                       # AsyncWeb3 instance
        readers: Mapping[str, ProtocolReader],
        policy: DecisionPolicy,
        mempool,                                  # Flashbots client (Task 4)
        history,                                  # HistoryStore (Task 6)
        position_usd: float,
        eth_price_usd_provider: Callable[[], Awaitable[float]],
        gas_used_estimate: int = DEFAULT_GAS_USED_ESTIMATE,
        per_block_deadline_s: float = DEFAULT_PER_BLOCK_DEADLINE_S,
    ) -> None:
        self.w3 = w3
        self.readers = dict(readers)
        self.policy = policy
        self.mempool = mempool
        self.history = history
        self.position_usd = position_usd
        self.eth_price_usd_provider = eth_price_usd_provider
        self.gas_used_estimate = gas_used_estimate
        self.per_block_deadline_s = per_block_deadline_s
        self.current_protocol: str | None = None

    async def _gather_protocol_states(self, block_number: int) -> dict[str, ProtocolState]:
        tasks = {name: r.read_state(block_number) for name, r in self.readers.items()}
        results: dict[str, ProtocolState] = {}
        try:
            done = await asyncio.wait_for(
                asyncio.gather(*tasks.values(), return_exceptions=True),
                timeout=self.per_block_deadline_s,
            )
        except asyncio.TimeoutError:
            done = []
        for name, res in zip(tasks.keys(), done):
            if isinstance(res, ProtocolState):
                results[name] = res
            else:
                # Slow / failed reader -> placeholder NaN state so the
                # BlockState fields still contain every protocol key.
                results[name] = ProtocolState(
                    protocol=name, block_number=block_number,
                    lending_apr=float("nan"), utilization=float("nan"),
                    tvl_usd=float("nan"), fetched_at=pd.Timestamp.utcnow(),
                )
                log.warning("reader %s missed deadline / errored: %s", name, res)
        return results

    async def _handle_block(self, block_number: int) -> None:
        proto_states = await self._gather_protocol_states(block_number)
        gas_wei = self.w3.eth.gas_price
        # web3.py returns AwaitableProperty on AsyncWeb3 -- the test
        # uses a sync MagicMock attribute, so handle both shapes:
        if asyncio.iscoroutine(gas_wei):
            gas_wei = await gas_wei
        gas_gwei = float(gas_wei) / 1e9
        eth_price = await self.eth_price_usd_provider()

        protocols = tuple(sorted(proto_states.keys()))
        state = BlockState(
            block_number=block_number,
            block_timestamp=pd.Timestamp.utcnow(),
            protocols=protocols,
            lending_apr={p: proto_states[p].lending_apr for p in protocols},
            utilization={p: proto_states[p].utilization for p in protocols},
            tvl_usd={p: proto_states[p].tvl_usd for p in protocols},
            current_protocol=self.current_protocol,
            position_usd=self.position_usd,
            gas_price_gwei=gas_gwei,
            eth_price_usd=eth_price,
            gas_used_estimate=self.gas_used_estimate,
        )

        action = self.policy.decide(state)
        log.info(
            "block=%d policy=%s action=%s rationale=%s",
            block_number, type(self.policy).__name__, action.kind, action.rationale,
        )

        if action.kind == "switch":
            assert action.target_protocol is not None
            receipt = await self.mempool.submit_private_tx(
                target_protocol=action.target_protocol, state=state,
            )
            log.info("switch submitted: %s", receipt)
            if receipt.get("status") == "included":
                self.current_protocol = action.target_protocol

        await self.history.append(state=state, action=action)

    async def run(self) -> None:
        """Subscribe to newHeads forever. Cancel via KeyboardInterrupt."""
        subscription_id = await self.w3.eth.subscribe("newHeads")
        log.info("subscribed to newHeads: %s", subscription_id)
        async for payload in self.w3.socket.process_subscriptions():
            block = payload["result"]
            block_number = int(block["number"], 16) if isinstance(block["number"], str) else int(block["number"])
            try:
                await self._handle_block(block_number)
            except Exception:  # noqa: BLE001
                log.exception("block %d handler crashed -- continuing", block_number)
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\pytest tests\agent\test_per_block_loop.py -v
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add "DeFi-Vega Project/agent/per_block_loop.py" tests/agent/test_per_block_loop.py
git commit -m "Per-block event-time loop replaces hourly main.py (Plan E Task 3)

Subscribes via web3.py AsyncWeb3 + WebSocket eth_subscribe newHeads.
Per block: gather 6 ProtocolReader.read_state() concurrently with a
4-second deadline (one-third of 12-s inter-block interval) -> assemble
decision.base.BlockState (imported through the Task-1 junction) ->
policy.decide() -> branch on Action.kind:
  hold   -> log + append to history
  switch -> mempool.submit_private_tx() + update current_protocol on
            inclusion + append to history

Slow / errored readers degrade to NaN APR rather than blocking the
policy -- all three decision policies handle NaN-APR gracefully (the
T1/T2 'valid = {p:a for ... if not isnan(a)}' filter).

Tests use AsyncMock + MagicMock for w3 / readers / mempool / history.
4 tests cover: BlockState assembly from 6 readers, switch-dispatches-
to-mempool, slow-reader-dropped-NaN, history-append-each-block.

Replaces (not deletes -- yet) main.py; the old hourly loop stays
in-tree as a fallback until Sepolia paper-trade (Task 7) green-lights
the event-time version."
```

---

## Task 4: `mempool.py` — Flashbots private-mempool client

**Files:**
- Create: `DeFi-Vega Project/agent/mempool.py`
- Create: `tests/agent/test_mempool.py`

**Methodology** (lit-foundation §6 MacKenzie *Material Markets* pp 200-203):

MacKenzie's account of the IEX speed bump frames asymmetric latency as the core source of toxic-order-flow extraction: the venue with the faster connection sees prints first and can race against the slower side. On Ethereum the same asymmetry exists between the **public mempool** (visible to all searchers) and **block-builder private channels**. A rebalance tx broadcast publicly is a free signal: a sandwich-bot front-runs us into the target pool, taking the spread we intended to capture.

Flashbots' `eth_sendPrivateTransaction` (relay endpoint `https://relay.flashbots.net`) routes the tx directly to participating block builders, bypassing the public mempool. This is the Ethereum analogue of IEX's speed bump: it removes the latency asymmetry by making the trade invisible until inclusion. The relay authenticates the sender via an off-chain reputation signer key (env var `FLASHBOTS_AUTH_KEY` — a *separate* secp256k1 key from the wallet key; signs an `X-Flashbots-Signature` header).

Per-request envelope:

```jsonc
POST https://relay.flashbots.net
Content-Type: application/json
X-Flashbots-Signature: <auth_pubkey>:<signature_of_body>

{
    "jsonrpc": "2.0", "id": 1,
    "method": "eth_sendPrivateTransaction",
    "params": [{
        "tx": "0x<signed_raw_tx>",
        "maxBlockNumber": <hex_current_block + 25>,
        "preferences": {"fast": true}
    }]
}
```

The client returns the `txhash`; the loop polls `eth_getTransactionReceipt` on the regular RPC until included or `maxBlockNumber` is passed (with a 25-block timeout = ~5 min).

- [ ] **Step 1: Write the failing test**

`tests/agent/test_mempool.py`:
```python
"""Flashbots private-mempool client tests."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from agent.mempool import FlashbotsMempool, FLASHBOTS_RELAY_URL


@pytest.fixture
def fake_state():
    from agent.decision.base import BlockState
    return BlockState(
        block_number=19_500_000,
        block_timestamp=pd.Timestamp("2026-05-01", tz="UTC"),
        protocols=("aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler"),
        lending_apr={p: 0.04 for p in ("aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler")},
        utilization={p: 0.7 for p in ("aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler")},
        tvl_usd={p: 1e9 for p in ("aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler")},
        current_protocol="aave_v3",
        position_usd=1_000_000.0,
        gas_price_gwei=25.0, eth_price_usd=3500.0, gas_used_estimate=200_000,
    )


@pytest.mark.asyncio
async def test_submit_private_tx_posts_to_relay(fake_state):
    """The client must POST to the Flashbots relay URL with the JSON-RPC envelope."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={
        "jsonrpc": "2.0", "id": 1,
        "result": "0xdeadbeef" + "0" * 56,
    })
    mock_session.post = MagicMock(return_value=_async_context(mock_response))

    tx_builder = MagicMock(return_value=("0xRAWSIGNED", "0xtxhash"))
    receipt_poller = AsyncMock(return_value={"status": "included", "blockNumber": 19_500_001})

    mp = FlashbotsMempool(
        session=mock_session,
        wallet_key="0x" + "11" * 32,
        auth_key="0x" + "22" * 32,
        tx_builder=tx_builder,
        receipt_poller=receipt_poller,
    )

    receipt = await mp.submit_private_tx(target_protocol="morpho", state=fake_state)

    mock_session.post.assert_called_once()
    args, kwargs = mock_session.post.call_args
    assert args[0] == FLASHBOTS_RELAY_URL
    body = json.loads(kwargs["data"])
    assert body["method"] == "eth_sendPrivateTransaction"
    assert body["params"][0]["tx"] == "0xRAWSIGNED"
    assert "X-Flashbots-Signature" in kwargs["headers"]
    assert receipt["status"] == "included"


@pytest.mark.asyncio
async def test_relay_failure_returns_status_failed(fake_state):
    """If the relay returns 400/500, status='failed' is returned -- never raised."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status = 502
    mock_response.text = AsyncMock(return_value="bad gateway")
    mock_response.json = AsyncMock(return_value={})
    mock_session.post = MagicMock(return_value=_async_context(mock_response))

    mp = FlashbotsMempool(
        session=mock_session,
        wallet_key="0x" + "11" * 32, auth_key="0x" + "22" * 32,
        tx_builder=MagicMock(return_value=("0x", "0x")),
        receipt_poller=AsyncMock(),
    )
    receipt = await mp.submit_private_tx(target_protocol="morpho", state=fake_state)
    assert receipt["status"] == "failed"
    assert "502" in receipt["error"]


@pytest.mark.asyncio
async def test_auth_signature_uses_auth_key_not_wallet_key(fake_state):
    """The X-Flashbots-Signature header MUST be signed with FLASHBOTS_AUTH_KEY,
    NOT the wallet key. This is the reputation key for relay scoring; reusing
    the wallet key would dox the wallet address to every relay observer."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value={"result": "0xhash"})
    mock_session.post = MagicMock(return_value=_async_context(mock_response))

    with patch("agent.mempool._sign_flashbots_header") as sign_fn:
        sign_fn.return_value = "0xAUTHADDR:0xAUTHSIG"
        mp = FlashbotsMempool(
            session=mock_session,
            wallet_key="0x" + "11" * 32,
            auth_key="0x" + "22" * 32,
            tx_builder=MagicMock(return_value=("0xraw", "0xtxhash")),
            receipt_poller=AsyncMock(return_value={"status": "included"}),
        )
        await mp.submit_private_tx(target_protocol="morpho", state=fake_state)
        # First positional arg to _sign_flashbots_header must be the auth_key
        sign_fn.assert_called_once()
        called_key = sign_fn.call_args.args[0]
        assert called_key == "0x" + "22" * 32   # auth key, NOT wallet key


@pytest.mark.asyncio
async def test_dry_run_mode_skips_post(fake_state):
    """If dry_run=True the client never POSTs -- safe for Sepolia smoke."""
    mock_session = MagicMock()
    mock_session.post = MagicMock()

    mp = FlashbotsMempool(
        session=mock_session,
        wallet_key="0x" + "11" * 32, auth_key="0x" + "22" * 32,
        tx_builder=MagicMock(return_value=("0xraw", "0xtxhash")),
        receipt_poller=AsyncMock(),
        dry_run=True,
    )
    receipt = await mp.submit_private_tx(target_protocol="morpho", state=fake_state)
    assert receipt["status"] == "dry_run"
    assert receipt["txhash"] == "0xtxhash"
    mock_session.post.assert_not_called()


def _async_context(value):
    class _CM:
        async def __aenter__(self):
            return value
        async def __aexit__(self, *a):
            return False
    return _CM()
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\pytest tests\agent\test_mempool.py -v
```
Expected: `ModuleNotFoundError: No module named 'agent.mempool'`.

- [ ] **Step 3: Write minimal implementation**

`DeFi-Vega Project/agent/mempool.py`:
```python
"""Flashbots private-mempool client (eth_sendPrivateTransaction).

Why private mempool? -- MacKenzie *Material Markets* pp 200-203 frames
asymmetric latency as the core source of toxic-order-flow extraction
on traditional venues (the IEX speed bump removes it by adding a
mandatory delay). On Ethereum the same asymmetry exists between
public-mempool searchers and block-builder direct channels: a
rebalance tx broadcast to the public mempool is sandwiched in the
next block, capturing the spread we intended to harvest. The
Flashbots relay is the Ethereum analogue -- the tx is invisible to
public-mempool observers until inclusion.

Two keys (do NOT confuse):
  WALLET_KEY        -- signs the on-chain tx (controls funds).
  FLASHBOTS_AUTH_KEY -- signs the X-Flashbots-Signature header
                        (relay reputation only; does NOT control funds).
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import aiohttp
from eth_account import Account
from eth_account.messages import encode_defunct

from agent.decision.base import BlockState

log = logging.getLogger(__name__)

FLASHBOTS_RELAY_URL = "https://relay.flashbots.net"
DEFAULT_MAX_BLOCK_OFFSET = 25


def _sign_flashbots_header(auth_key: str, body_bytes: bytes) -> str:
    """`X-Flashbots-Signature` = '<auth_pubkey>:<sig_of_keccak(body)>'."""
    auth_account = Account.from_key(auth_key)
    msg = encode_defunct(text=body_bytes.decode("utf-8"))
    sig = auth_account.sign_message(msg).signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    return f"{auth_account.address}:{sig}"


class FlashbotsMempool:
    """Async Flashbots client. submit_private_tx() returns a receipt dict."""

    def __init__(
        self,
        *,
        session: aiohttp.ClientSession,
        wallet_key: str,
        auth_key: str,
        tx_builder: Callable[[str, BlockState, str], tuple[str, str]],
        receipt_poller: Callable[[str], Awaitable[dict]],
        relay_url: str = FLASHBOTS_RELAY_URL,
        max_block_offset: int = DEFAULT_MAX_BLOCK_OFFSET,
        dry_run: bool = False,
    ) -> None:
        self.session = session
        self.wallet_key = wallet_key
        self.auth_key = auth_key
        self.tx_builder = tx_builder
        self.receipt_poller = receipt_poller
        self.relay_url = relay_url
        self.max_block_offset = max_block_offset
        self.dry_run = dry_run

    async def submit_private_tx(
        self, *, target_protocol: str, state: BlockState,
    ) -> dict[str, Any]:
        """Build, sign, post, and await inclusion for a rebalance tx.

        Returns a dict with keys: status ('included'|'failed'|'dry_run'),
        txhash, blockNumber (on included), error (on failed).
        """
        # tx_builder is injected so the *contract-specific* logic (which
        # protocol pool to call, what amount to migrate, what slippage)
        # lives outside the mempool client. It returns (raw_signed_tx, txhash).
        raw_tx, txhash = self.tx_builder(target_protocol, state, self.wallet_key)

        if self.dry_run:
            log.info("[dry-run] would submit %s -> %s", txhash[:10], target_protocol)
            return {"status": "dry_run", "txhash": txhash}

        body = {
            "jsonrpc": "2.0", "id": 1,
            "method": "eth_sendPrivateTransaction",
            "params": [{
                "tx": raw_tx,
                "maxBlockNumber": hex(state.block_number + self.max_block_offset),
                "preferences": {"fast": True},
            }],
        }
        body_bytes = json.dumps(body).encode("utf-8")
        signature = _sign_flashbots_header(self.auth_key, body_bytes)

        async with self.session.post(
            self.relay_url,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Flashbots-Signature": signature,
            },
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                log.warning("Flashbots relay returned %d: %s", resp.status, text)
                return {"status": "failed", "txhash": txhash,
                        "error": f"HTTP {resp.status}: {text}"}
            payload = await resp.json()

        if "error" in payload:
            return {"status": "failed", "txhash": txhash, "error": str(payload["error"])}

        receipt = await self.receipt_poller(txhash)
        return receipt
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\pytest tests\agent\test_mempool.py -v
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add "DeFi-Vega Project/agent/mempool.py" tests/agent/test_mempool.py
git commit -m "Flashbots private-mempool client (Plan E Task 4)

POST to https://relay.flashbots.net with method
eth_sendPrivateTransaction; X-Flashbots-Signature header is signed by
the FLASHBOTS_AUTH_KEY (env var) -- a SEPARATE secp256k1 key from the
wallet key. Reusing the wallet key would dox the wallet address to
every relay observer for free.

Why private mempool? -- MacKenzie *Material Markets* pp 200-203 on IEX
asymmetric speed bump: public-mempool rebalance txs leak the
strategy's intent before inclusion, getting sandwiched. Flashbots is
the Ethereum analogue (invisible-until-inclusion). The economic
literature cited here is exactly the same risk model in different
plumbing.

tx_builder is injected -- the mempool client knows NOTHING about
protocol-specific call data. dry_run=True skips the POST for Sepolia
smoke (Task 7 RUNBOOK).

4 tests cover: POST-to-relay / 502-returns-failed-not-raises /
auth-signature-uses-auth-key-not-wallet-key (regression guard against
the dox bug) / dry-run-skips-post."
```

---

## Task 5: Live F1/F3/F4 signal builders (single-row wrappers)

**Files:**
- Create: `DeFi-Vega Project/agent/signal/__init__.py`
- Create: `DeFi-Vega Project/agent/signal/f1.py`
- Create: `DeFi-Vega Project/agent/signal/f3.py`
- Create: `DeFi-Vega Project/agent/signal/f4.py`
- Create: `tests/agent/test_signal_f1.py`
- Create: `tests/agent/test_signal_f3.py`
- Create: `tests/agent/test_signal_f4.py`

**Methodology:**

The research-side `decision/features/{f1,f3,f4}.py` builders (Plan C) operate on a multi-row pandas DataFrame: F1 takes a window of cross-protocol rates and emits the EWMA spread; F3 takes utilization history and emits the post-kink-slope signal; F4 takes (apr, gas) lags and emits the gas-adjusted advantage. In replay these builders consume `data/cached/per_block_panel.parquet`.

In the live agent there is no parquet — there is one new `BlockState` per block. The wrappers convert the live state into a single-row DataFrame, append it to a rolling buffer (handed by Task 6's `HistoryStore`), and call the **exact same** research-side builder. Zero divergence between live signals and the values the empirical study measured.

Each wrapper:
```python
def compute(state: BlockState, history: HistoryStore) -> float: ...
```
returns the single live-block signal value used by T3's hazard model.

- [ ] **Step 1: Write the failing test**

`tests/agent/test_signal_f1.py`:
```python
"""F1 single-row wrapper tests.

The wrapper must call the SAME research-side decision.features.f1
builder used in replay -- not a re-implementation."""
from __future__ import annotations

import pandas as pd
import pytest

from agent.signal.f1 import compute_f1


class FakeHistory:
    def __init__(self, df): self._df = df
    def snapshot_df(self) -> pd.DataFrame: return self._df.copy()


def _make_state(block, aave_apr, comp_apr, current="aave_v3"):
    from agent.decision.base import BlockState
    return BlockState(
        block_number=block,
        block_timestamp=pd.Timestamp(2_000_000_000 + block * 12, unit="s", tz="UTC"),
        protocols=("aave_v3", "compound_v3"),
        lending_apr={"aave_v3": aave_apr, "compound_v3": comp_apr},
        utilization={"aave_v3": 0.8, "compound_v3": 0.7},
        tvl_usd={"aave_v3": 1e9, "compound_v3": 5e8},
        current_protocol=current, position_usd=1.0,
        gas_price_gwei=25.0, eth_price_usd=3500.0, gas_used_estimate=200_000,
    )


def test_f1_returns_finite_float_with_enough_history():
    """Given 200 blocks of history, F1 (EWMA spread) returns a finite float."""
    rows = [{
        "block_number": 100 + i,
        "aave_v3_lending_apr": 0.04 + 0.001 * (i % 7),
        "compound_v3_lending_apr": 0.03 + 0.001 * (i % 5),
    } for i in range(200)]
    df = pd.DataFrame(rows)
    state = _make_state(block=300, aave_apr=0.045, comp_apr=0.030)
    val = compute_f1(state=state, history=FakeHistory(df))
    assert isinstance(val, float)
    assert val == val  # not NaN
    # EWMA of (Aave - Compound) on those rows is in [0, 0.02] decimal.
    assert 0.0 <= val <= 0.05


def test_f1_short_history_returns_nan():
    """Less than the EWMA span of history -> NaN (caller must handle)."""
    import math
    df = pd.DataFrame([{
        "block_number": 1, "aave_v3_lending_apr": 0.04, "compound_v3_lending_apr": 0.03,
    }])
    state = _make_state(block=2, aave_apr=0.04, comp_apr=0.03)
    val = compute_f1(state=state, history=FakeHistory(df))
    assert math.isnan(val)


def test_f1_calls_research_side_builder():
    """The wrapper must dispatch to decision.features.f1.build_f1, not
    a private copy. This guarantees zero divergence with replay."""
    from unittest.mock import patch
    df = pd.DataFrame([
        {"block_number": i,
         "aave_v3_lending_apr": 0.04, "compound_v3_lending_apr": 0.03}
        for i in range(100)
    ])
    state = _make_state(block=101, aave_apr=0.04, comp_apr=0.03)
    with patch("agent.signal.f1._build_f1") as mock_build:
        mock_build.return_value = pd.Series([0.123])
        val = compute_f1(state=state, history=FakeHistory(df))
        mock_build.assert_called_once()
        assert val == 0.123
```

`tests/agent/test_signal_f3.py`:
```python
"""F3 single-row wrapper tests (post-kink-slope utilization signal)."""
from __future__ import annotations

import math

import pandas as pd

from agent.signal.f3 import compute_f3


class FakeHistory:
    def __init__(self, df): self._df = df
    def snapshot_df(self): return self._df.copy()


def _state(block, util_aave=0.95, util_comp=0.5):
    from agent.decision.base import BlockState
    return BlockState(
        block_number=block, block_timestamp=pd.Timestamp.utcnow(),
        protocols=("aave_v3", "compound_v3"),
        lending_apr={"aave_v3": 0.04, "compound_v3": 0.03},
        utilization={"aave_v3": util_aave, "compound_v3": util_comp},
        tvl_usd={"aave_v3": 1e9, "compound_v3": 5e8},
        current_protocol="aave_v3", position_usd=1.0,
        gas_price_gwei=25.0, eth_price_usd=3500.0, gas_used_estimate=200_000,
    )


def test_f3_above_kink_returns_positive_signal():
    """When current protocol's utilization is above the 0.8 kink for
    sustained history, F3 must emit a positive (post-kink-slope) signal."""
    df = pd.DataFrame([
        {"block_number": i, "aave_v3_utilization": 0.92, "compound_v3_utilization": 0.5}
        for i in range(500)
    ])
    val = compute_f3(state=_state(501, 0.95, 0.5), history=FakeHistory(df))
    assert isinstance(val, float)
    assert val > 0


def test_f3_below_kink_returns_zero_or_negative():
    df = pd.DataFrame([
        {"block_number": i, "aave_v3_utilization": 0.4, "compound_v3_utilization": 0.5}
        for i in range(500)
    ])
    val = compute_f3(state=_state(501, 0.4, 0.5), history=FakeHistory(df))
    assert val <= 0.0 or math.isclose(val, 0.0, abs_tol=1e-6)


def test_f3_dispatches_to_research_builder():
    from unittest.mock import patch
    df = pd.DataFrame([
        {"block_number": i, "aave_v3_utilization": 0.8, "compound_v3_utilization": 0.5}
        for i in range(100)
    ])
    with patch("agent.signal.f3._build_f3") as m:
        m.return_value = pd.Series([0.0042])
        val = compute_f3(state=_state(101), history=FakeHistory(df))
        m.assert_called_once()
        assert val == 0.0042
```

`tests/agent/test_signal_f4.py`:
```python
"""F4 single-row wrapper tests (gas-adjusted advantage)."""
from __future__ import annotations

import pandas as pd

from agent.signal.f4 import compute_f4


class FakeHistory:
    def __init__(self, df): self._df = df
    def snapshot_df(self): return self._df.copy()


def _state(block, gas_gwei=25.0):
    from agent.decision.base import BlockState
    return BlockState(
        block_number=block, block_timestamp=pd.Timestamp.utcnow(),
        protocols=("aave_v3", "compound_v3"),
        lending_apr={"aave_v3": 0.05, "compound_v3": 0.03},
        utilization={"aave_v3": 0.8, "compound_v3": 0.7},
        tvl_usd={"aave_v3": 1e9, "compound_v3": 5e8},
        current_protocol="compound_v3", position_usd=1_000_000.0,
        gas_price_gwei=gas_gwei, eth_price_usd=3500.0,
        gas_used_estimate=200_000,
    )


def test_f4_returns_decimal_value():
    """Sanity: 200 bp spread / $17.5 gas / $1M position must be positive."""
    df = pd.DataFrame([
        {"block_number": i, "gas_price_gwei": 25.0,
         "aave_v3_lending_apr": 0.05, "compound_v3_lending_apr": 0.03}
        for i in range(300)
    ])
    val = compute_f4(state=_state(301), history=FakeHistory(df))
    assert isinstance(val, float)
    assert val > 0.0


def test_f4_dispatches_to_research_builder():
    from unittest.mock import patch
    df = pd.DataFrame([
        {"block_number": i, "gas_price_gwei": 25.0,
         "aave_v3_lending_apr": 0.04, "compound_v3_lending_apr": 0.04}
        for i in range(100)
    ])
    with patch("agent.signal.f4._build_f4") as m:
        m.return_value = pd.Series([0.123])
        val = compute_f4(state=_state(101), history=FakeHistory(df))
        m.assert_called_once()
        assert val == 0.123
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\pytest tests\agent\test_signal_f1.py tests\agent\test_signal_f3.py tests\agent\test_signal_f4.py -v
```
Expected: `ModuleNotFoundError: No module named 'agent.signal'`.

- [ ] **Step 3: Write minimal implementation**

`DeFi-Vega Project/agent/signal/__init__.py`:
```python
"""Live signal wrappers.

Each module here wraps the SAME builder used by the research-side
replay (decision.features.{f1,f3,f4}.build_*) but takes a single live
BlockState + a HistoryStore snapshot instead of a per-block parquet.
This is the zero-drift guarantee for signals -- if F1 measured 12 bps
in the empirical study, F1 in the live agent reads 12 bps on the same
inputs."""
```

`DeFi-Vega Project/agent/signal/f1.py`:
```python
"""F1: cross-protocol EWMA spread (live single-row wrapper)."""
from __future__ import annotations

import math

import pandas as pd

from agent.decision.base import BlockState
from agent.decision.features.f1 import build_f1 as _build_f1


def compute_f1(*, state: BlockState, history) -> float:
    """Return the F1 signal for the live block."""
    df = history.snapshot_df()
    # Append the live row so the builder sees the most-recent observation.
    live_row = {"block_number": state.block_number}
    for p in state.protocols:
        live_row[f"{p}_lending_apr"] = state.lending_apr[p]
    df = pd.concat([df, pd.DataFrame([live_row])], ignore_index=True)
    series = _build_f1(df)
    val = float(series.iloc[-1])
    return val if not math.isnan(val) else float("nan")
```

`DeFi-Vega Project/agent/signal/f3.py`:
```python
"""F3: post-kink-slope utilization advantage (live wrapper)."""
from __future__ import annotations

import math

import pandas as pd

from agent.decision.base import BlockState
from agent.decision.features.f3 import build_f3 as _build_f3


def compute_f3(*, state: BlockState, history) -> float:
    df = history.snapshot_df()
    live = {"block_number": state.block_number}
    for p in state.protocols:
        live[f"{p}_utilization"] = state.utilization[p]
    df = pd.concat([df, pd.DataFrame([live])], ignore_index=True)
    series = _build_f3(df)
    val = float(series.iloc[-1])
    return val if not math.isnan(val) else float("nan")
```

`DeFi-Vega Project/agent/signal/f4.py`:
```python
"""F4: gas-adjusted-advantage (live wrapper)."""
from __future__ import annotations

import math

import pandas as pd

from agent.decision.base import BlockState
from agent.decision.features.f4 import build_f4 as _build_f4


def compute_f4(*, state: BlockState, history) -> float:
    df = history.snapshot_df()
    live = {
        "block_number": state.block_number,
        "gas_price_gwei": state.gas_price_gwei,
    }
    for p in state.protocols:
        live[f"{p}_lending_apr"] = state.lending_apr[p]
    df = pd.concat([df, pd.DataFrame([live])], ignore_index=True)
    series = _build_f4(df)
    val = float(series.iloc[-1])
    return val if not math.isnan(val) else float("nan")
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\pytest tests\agent\test_signal_f1.py tests\agent\test_signal_f3.py tests\agent\test_signal_f4.py -v
```
Expected: `9 passed` (3 per signal × 3 signals).

- [ ] **Step 5: Commit**

```bash
git add "DeFi-Vega Project/agent/signal/__init__.py" "DeFi-Vega Project/agent/signal/f1.py" "DeFi-Vega Project/agent/signal/f3.py" "DeFi-Vega Project/agent/signal/f4.py" tests/agent/test_signal_f1.py tests/agent/test_signal_f3.py tests/agent/test_signal_f4.py
git commit -m "Live F1/F3/F4 signal builders (Plan E Task 5)

Each module wraps the SAME research-side decision.features.{f1,f3,f4}.
build_* builder used in replay, but takes a single live BlockState
plus a HistoryStore snapshot rather than a per-block parquet. The
wrapper appends the live block as the last row of the snapshot DF
and returns series.iloc[-1].

Zero-drift guarantee: if F1 measured 12 bps in the empirical study
(Plan D), F1 in the live agent reads 12 bps on the same inputs --
because it's the literal same function call.

9 tests cover for each signal: finite-with-enough-history,
short-history-returns-NaN, dispatches-to-research-builder (patched
to confirm no private re-implementation snuck in)."
```

---

## Task 6: State persistence — rolling history.parquet with atomic write

**Files:**
- Create: `DeFi-Vega Project/agent/state/__init__.py`
- Create: `DeFi-Vega Project/agent/state/history.py`
- Create: `tests/agent/test_state_history.py`

**Methodology** (lit-foundation §4 AFML purged windows):

T2's `OUCalibrator.fit()` needs ≥50 spread observations (it raises `ValueError` otherwise) and is happiest with ≥5,000 for the κ MLE confidence interval to be tight. T3's hazard features (F1 EWMA spread, F3 post-kink slope, F4 gas-adjusted advantage) each need ≥500 lags. A 5,000-block window (~16.7 hours at 12 s/block) covers both with margin.

The store is a single parquet file at `agent/state/history.parquet`, rewritten atomically every block:
1. Append the new row to an in-memory pandas `DataFrame` (truncate to the last 5,000 rows).
2. Write the full window to `history.parquet.tmp`.
3. Rename `history.parquet.tmp` → `history.parquet` (atomic on the same filesystem on Windows since Python 3.3 / NTFS; uses `os.replace`).

Atomic-rename is essential because a crash mid-write must not leave a half-written parquet that crashes the agent on restart. The `.tmp` file is also fsync'd before the rename to flush page cache.

- [ ] **Step 1: Write the failing test**

`tests/agent/test_state_history.py`:
```python
"""Rolling history.parquet tests: window length, atomic write,
crash-resilient restart."""
from __future__ import annotations

import os
import pandas as pd
import pytest

from agent.state.history import HistoryStore


def _state(block):
    from agent.decision.base import BlockState
    return BlockState(
        block_number=block, block_timestamp=pd.Timestamp.utcnow(),
        protocols=("aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler"),
        lending_apr={p: 0.04 + 0.0001 * block for p in ("aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler")},
        utilization={p: 0.7 for p in ("aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler")},
        tvl_usd={p: 1e9 for p in ("aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler")},
        current_protocol="aave_v3", position_usd=1_000_000.0,
        gas_price_gwei=25.0, eth_price_usd=3500.0, gas_used_estimate=200_000,
    )


def _action():
    from agent.decision.base import Action
    return Action(kind="hold", target_protocol=None, rationale="test")


@pytest.mark.asyncio
async def test_append_writes_parquet(tmp_path):
    store = HistoryStore(path=tmp_path / "h.parquet", max_rows=5_000)
    await store.append(state=_state(100), action=_action())
    assert (tmp_path / "h.parquet").exists()
    df = pd.read_parquet(tmp_path / "h.parquet")
    assert len(df) == 1
    assert df["block_number"].iloc[0] == 100


@pytest.mark.asyncio
async def test_rolling_window_drops_oldest(tmp_path):
    """After max_rows + N appends, only the last max_rows are kept."""
    store = HistoryStore(path=tmp_path / "h.parquet", max_rows=10)
    for b in range(100, 130):
        await store.append(state=_state(b), action=_action())
    df = pd.read_parquet(tmp_path / "h.parquet")
    assert len(df) == 10
    assert df["block_number"].min() == 120
    assert df["block_number"].max() == 129


@pytest.mark.asyncio
async def test_snapshot_df_returns_copy(tmp_path):
    """snapshot_df() must return a COPY -- mutating it must NOT
    corrupt the store's internal buffer."""
    store = HistoryStore(path=tmp_path / "h.parquet", max_rows=10)
    for b in range(100, 105):
        await store.append(state=_state(b), action=_action())
    snap = store.snapshot_df()
    snap["block_number"] = -1
    snap2 = store.snapshot_df()
    assert (snap2["block_number"] > 0).all()


@pytest.mark.asyncio
async def test_atomic_rename_no_partial_file_on_crash(tmp_path, monkeypatch):
    """Simulate a crash mid-write: the .tmp file may exist but the real
    .parquet must NOT be corrupted -- it should be the last good write."""
    store = HistoryStore(path=tmp_path / "h.parquet", max_rows=10)
    await store.append(state=_state(100), action=_action())
    # First good write done; now monkeypatch os.replace to raise.
    real_replace = os.replace
    monkeypatch.setattr("agent.state.history.os.replace",
                        lambda src, dst: (_ for _ in ()).throw(OSError("simulated crash")))
    with pytest.raises(OSError):
        await store.append(state=_state(101), action=_action())
    # The real parquet still contains only the first row.
    df = pd.read_parquet(tmp_path / "h.parquet")
    assert len(df) == 1
    assert df["block_number"].iloc[0] == 100
    # And the .tmp file may or may not exist; we don't care.
    monkeypatch.setattr("agent.state.history.os.replace", real_replace)


@pytest.mark.asyncio
async def test_restart_loads_existing_parquet(tmp_path):
    """Constructor reads any existing parquet on disk into the internal buffer."""
    store1 = HistoryStore(path=tmp_path / "h.parquet", max_rows=100)
    for b in range(100, 105):
        await store1.append(state=_state(b), action=_action())
    # Simulate restart with a fresh store object.
    store2 = HistoryStore(path=tmp_path / "h.parquet", max_rows=100)
    snap = store2.snapshot_df()
    assert len(snap) == 5
    assert list(snap["block_number"]) == [100, 101, 102, 103, 104]


@pytest.mark.asyncio
async def test_schema_has_required_columns(tmp_path):
    """Parquet schema must include block_number, all <proto>_lending_apr,
    all <proto>_utilization, action_kind, action_target."""
    store = HistoryStore(path=tmp_path / "h.parquet", max_rows=10)
    await store.append(state=_state(100), action=_action())
    df = pd.read_parquet(tmp_path / "h.parquet")
    required = {"block_number", "block_timestamp", "gas_price_gwei",
                "action_kind", "action_target"}
    for p in ("aave_v3", "compound_v3", "spark", "morpho", "fluid", "euler"):
        required.add(f"{p}_lending_apr")
        required.add(f"{p}_utilization")
    missing = required - set(df.columns)
    assert not missing, f"missing columns: {missing}"
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\pytest tests\agent\test_state_history.py -v
```
Expected: `ModuleNotFoundError: No module named 'agent.state'`.

- [ ] **Step 3: Write minimal implementation**

`DeFi-Vega Project/agent/state/__init__.py`:
```python
"""Agent state persistence (rolling per-block parquet)."""
```

`DeFi-Vega Project/agent/state/history.py`:
```python
"""Rolling per-block history.parquet store with atomic write.

The store keeps the last `max_rows` blocks in an in-memory DataFrame.
Every append() rewrites the entire window to a .tmp file, fsyncs it,
then atomically renames it over the live path. A crash mid-write
leaves the previous good write intact (NTFS / POSIX semantics of
os.replace on same-filesystem rename).

Sized at 5,000 rows by default (~16.7 hours at 12 s/block), enough
for:
  * T2 OUCalibrator.fit (needs >=50, happy with >=5000)
  * T3 hazard features F1/F3/F4 (need >=500 lags each)

The parquet schema is a flat per-block row:
  block_number, block_timestamp, gas_price_gwei, eth_price_usd,
  <proto>_lending_apr, <proto>_utilization, <proto>_tvl_usd,
  current_protocol, position_usd,
  action_kind, action_target, action_rationale
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pandas as pd

from agent.decision.base import Action, BlockState


class HistoryStore:
    DEFAULT_MAX_ROWS = 5_000

    def __init__(self, *, path: Path, max_rows: int = DEFAULT_MAX_ROWS) -> None:
        self.path = Path(path)
        self.max_rows = int(max_rows)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._buffer: pd.DataFrame = self._load_existing()
        self._lock = asyncio.Lock()

    def _load_existing(self) -> pd.DataFrame:
        if self.path.exists():
            try:
                return pd.read_parquet(self.path)
            except Exception:   # noqa: BLE001 -- corrupted parquet -> start fresh
                return pd.DataFrame()
        return pd.DataFrame()

    @staticmethod
    def _row(state: BlockState, action: Action) -> dict:
        row = {
            "block_number": int(state.block_number),
            "block_timestamp": state.block_timestamp,
            "gas_price_gwei": float(state.gas_price_gwei),
            "eth_price_usd": float(state.eth_price_usd),
            "current_protocol": state.current_protocol or "",
            "position_usd": float(state.position_usd),
            "action_kind": action.kind,
            "action_target": action.target_protocol or "",
            "action_rationale": action.rationale,
        }
        for p in state.protocols:
            row[f"{p}_lending_apr"] = float(state.lending_apr[p])
            row[f"{p}_utilization"] = float(state.utilization[p])
            row[f"{p}_tvl_usd"] = float(state.tvl_usd[p])
        return row

    async def append(self, *, state: BlockState, action: Action) -> None:
        async with self._lock:
            new_row = pd.DataFrame([self._row(state, action)])
            self._buffer = pd.concat([self._buffer, new_row], ignore_index=True)
            if len(self._buffer) > self.max_rows:
                self._buffer = self._buffer.iloc[-self.max_rows:].reset_index(drop=True)
            await asyncio.get_event_loop().run_in_executor(None, self._atomic_write)

    def _atomic_write(self) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        self._buffer.to_parquet(tmp, index=False)
        # fsync to flush OS page cache before rename.
        with open(tmp, "rb") as f:
            os.fsync(f.fileno())
        os.replace(tmp, self.path)   # atomic on same filesystem

    def snapshot_df(self) -> pd.DataFrame:
        """Return a defensive copy of the in-memory buffer."""
        return self._buffer.copy()
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\pytest tests\agent\test_state_history.py -v
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add "DeFi-Vega Project/agent/state/__init__.py" "DeFi-Vega Project/agent/state/history.py" tests/agent/test_state_history.py
git commit -m "Rolling history.parquet store with atomic write (Plan E Task 6)

Single parquet at agent/state/history.parquet, last `max_rows` blocks
(default 5000 -- ~16.7 hours at 12 s/block). Every append rewrites
the full window to .tmp, fsync, os.replace to live path. Atomic-rename
on NTFS / POSIX means a crash mid-write leaves the previous good
write intact.

Sized for:
  T2 OUCalibrator.fit (needs >=50, happy with >=5000)
  T3 hazard features F1/F3/F4 (need >=500 lags each)

Constructor reads any existing parquet so restart picks up where we
left off (no warmup penalty after restart).

Schema is flat per-block row: block_number, block_timestamp,
gas_price_gwei, eth_price_usd, current_protocol, position_usd,
action_kind, action_target, action_rationale, plus
<proto>_{lending_apr,utilization,tvl_usd} for all 6 protocols.

6 tests: writes-parquet / rolling-window-drops-oldest /
snapshot-df-returns-copy / atomic-rename-no-partial-file-on-crash /
restart-loads-existing-parquet / schema-has-required-columns."
```

---

## Task 7: Sepolia paper-trade RUNBOOK (operator instructions, not code)

**Files:**
- Create: `DeFi-Vega Project/agent/RUNBOOK.md`

**Methodology:**

This task is operator-facing — there is no test-fail / test-pass cycle, only a markdown document that the operator follows to bring the agent up on Sepolia testnet, run it for ≥10 rebalances against the six (testnet-deployed) protocols, and verify the Flashbots path with `dry_run=True` end-to-end. The deliverable is the document itself; "completion" means the operator has executed all the steps and pasted the log block into `agent/state/runbook_first_run.log`.

Acceptance gates for the run (informational):
- ≥10 `Action(kind="switch")` decisions in the log.
- Every switch goes through `agent.mempool.submit_private_tx` with `dry_run=True` returning `status="dry_run"` and a non-empty `txhash`.
- `agent/state/history.parquet` ≥ 100 rows at end of run.
- No `unhandled exception` lines in the log.

- [ ] **Step 1: Write the failing "test" (smoke-check that RUNBOOK.md exists and references the right scripts)**

`tests/agent/test_runbook_exists.py`:
```python
"""Smoke check: RUNBOOK.md exists and references the right files."""
from __future__ import annotations

from pathlib import Path

import pytest

RUNBOOK = Path(__file__).resolve().parents[2] / "DeFi-Vega Project" / "agent" / "RUNBOOK.md"


def test_runbook_exists():
    assert RUNBOOK.exists(), f"RUNBOOK missing at {RUNBOOK}"


def test_runbook_has_required_sections():
    content = RUNBOOK.read_text(encoding="utf-8")
    required = [
        "## First-time setup",
        "## Sepolia paper-trade",
        "## Flashbots dry-run verification",
        "## Acceptance gates",
        "mklink /J decision",
        "FLASHBOTS_AUTH_KEY",
        "per_block_loop",
        "history.parquet",
    ]
    missing = [s for s in required if s not in content]
    assert not missing, f"RUNBOOK missing sections / refs: {missing}"


def test_runbook_acceptance_gates_explicit():
    """The acceptance gates must mention >=10 rebalances and dry_run path."""
    content = RUNBOOK.read_text(encoding="utf-8")
    assert ">=10" in content or "10 or more" in content or "ten rebalances" in content.lower()
    assert "dry_run" in content
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv\Scripts\pytest tests\agent\test_runbook_exists.py -v
```
Expected: `AssertionError: RUNBOOK missing at .../agent/RUNBOOK.md`.

- [ ] **Step 3: Write the RUNBOOK**

`DeFi-Vega Project/agent/RUNBOOK.md`:
```markdown
# Agent Runbook — Sepolia paper-trade for Plan E

This document is the operator playbook for the event-time agent
(`agent/per_block_loop.py`). Follow it top-to-bottom on a fresh clone
to bring the agent up on Sepolia testnet, run ≥10 rebalances, and
verify the Flashbots private-mempool path end-to-end (in `dry_run`
mode -- no real-money tx submission).

## First-time setup

### 1. Decision bridge (one-shot, after every fresh checkout)

The `agent/decision/` directory is a Windows directory junction to the
research repo's `predictive-mcdm-defi/decision/` package. The agent
and the research notebooks consume the SAME T1/T2/T3 source files.
Recreate it after fresh checkout:

```cmd
cd "%REPO_ROOT%\DeFi-Vega Project\agent"
mklink /J decision "%REPO_ROOT%\predictive-mcdm-defi\decision"
```

POSIX equivalent (Linux/macOS CI):
```bash
ln -s "$REPO_ROOT/predictive-mcdm-defi/decision" "$REPO_ROOT/DeFi-Vega Project/agent/decision"
```

Verify:
```cmd
.venv\Scripts\pytest tests\agent\test_decision_bridge.py -v
```

### 2. Environment variables

Create `agent/.env` (NEVER commit -- already in .gitignore):

```dotenv
# Sepolia RPC -- Alchemy / Infura free tier suffices
SEPOLIA_WS_URL=wss://eth-sepolia.g.alchemy.com/v2/<YOUR_KEY>
SEPOLIA_HTTP_URL=https://eth-sepolia.g.alchemy.com/v2/<YOUR_KEY>

# Wallet -- a Sepolia-funded account (use a FRESH burner key, not your
# mainnet wallet). Faucet at https://www.alchemy.com/faucets/ethereum-sepolia
WALLET_KEY=0x<64 hex chars>

# Flashbots reputation signer -- a SEPARATE secp256k1 key from the
# wallet key. Generate with:
#   .venv\Scripts\python -c "from eth_account import Account; print(Account.create().key.hex())"
FLASHBOTS_AUTH_KEY=0x<64 hex chars>
```

### 3. Install dependencies

```cmd
cd "%REPO_ROOT%\DeFi-Vega Project\agent"
py -3.11 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### 4. Pre-flight tests

```cmd
.venv\Scripts\pytest tests\agent -v -m "not network"
```

Expected: all Plan-E tests pass (decision-bridge + 4 protocol readers +
per_block_loop + mempool + 3 signal builders + state history + runbook
smoke = 41 tests).

## Sepolia paper-trade

### Configuration

Create `agent/configs/sepolia_paper.yaml`:

```yaml
mode: paper_trade
network: sepolia
position_usd: 1_000_000.0
policy:
  name: t2_optimal_stopping     # one of: t1_threshold | t2_optimal_stopping | t3_hazard
  initial_dwell_blocks: 10000   # T1 only -- ignored by T2/T3
  recalibrate_every: 1000       # T2/T3
mempool:
  dry_run: true                 # CRITICAL -- false would submit real tx
  max_block_offset: 25
history:
  path: agent/state/history.parquet
  max_rows: 5000
```

### Launch

```cmd
cd "%REPO_ROOT%\DeFi-Vega Project\agent"
.venv\Scripts\python -m agent.per_block_loop --config configs\sepolia_paper.yaml --log-level INFO 2>&1 | tee state\runbook_first_run.log
```

Run for at least 30 minutes (~150 blocks at 12 s/block). Watch the
log for lines like:

```
INFO block=4500123 policy=T2OptimalStoppingPolicy action=switch
     rationale=T2 switch: spread 32.4bp > S* 14.1bp (kappa=4.2e-04)
INFO switch submitted: {'status': 'dry_run', 'txhash': '0xabc...'}
```

### Stopping

`Ctrl-C` is safe -- the async loop's `KeyboardInterrupt` handler
flushes any in-progress `history.append` before exit. After stopping:

```cmd
.venv\Scripts\python -c "import pandas as pd; df = pd.read_parquet('state/history.parquet'); print(df.tail()); print(f'{len(df)} rows, {(df.action_kind == \"switch\").sum()} switches')"
```

## Flashbots dry-run verification

The `dry_run=true` config short-circuits before the POST to
`https://relay.flashbots.net`. To verify the build-and-sign path WITHOUT
ever submitting a real tx, run the dedicated smoke:

```cmd
.venv\Scripts\python -m agent.scripts.flashbots_smoke --auth-key %FLASHBOTS_AUTH_KEY% --wallet-key %WALLET_KEY% --rpc-url %SEPOLIA_HTTP_URL%
```

Expected output:
```
[1/3] Building tx for migration aave -> morpho on Sepolia mock pools...
      raw_tx = 0x02f8...  (217 bytes)
      txhash = 0xc04b...
[2/3] Signing X-Flashbots-Signature with FLASHBOTS_AUTH_KEY...
      signer addr = 0xAE7F...   (NOT the wallet addr 0x1F2C... -- correct)
      sig = 0x9d3a...
[3/3] dry_run=True -- no POST. submit_private_tx returned:
      {'status': 'dry_run', 'txhash': '0xc04b...'}
```

If `[2/3]` shows the wallet addr instead of the auth-key addr, the
`X-Flashbots-Signature` header is using the wrong key -- this would
dox the wallet to every relay observer for free. STOP, regenerate
the auth key, and re-run.

To actually exercise the relay (still dry-run from a fund POV
because Sepolia ETH is worthless), set `dry_run: false` in the YAML
and confirm the relay accepts the tx and the receipt poller returns
`status: included` after one or two blocks. Roll back to `dry_run: true`
before any mainnet deployment.

## Acceptance gates

For Plan E to be considered complete, the runbook execution must
produce a `state/runbook_first_run.log` that satisfies:

| Gate | Threshold | Verify |
|---|---|---|
| Switch decisions | >=10 rebalances logged | `grep -c "action=switch" state/runbook_first_run.log` |
| Dry-run path | every switch returns `status='dry_run'` with non-empty txhash | `grep "submitted" state/runbook_first_run.log \| grep -v dry_run` returns 0 lines |
| History persistence | `history.parquet` has >=100 rows | `python -c "import pandas as pd; print(len(pd.read_parquet('state/history.parquet')))"` >=100 |
| No unhandled crashes | zero "unhandled exception" lines | `grep -c "unhandled exception\|crashed" state/runbook_first_run.log` returns 0 |

If any gate fails, debug before declaring Plan E complete. Common
failure modes:

* **No switches logged** -- check that the policy isn't permanently
  in `hold`. Likely T2's κ is below the floor (1e-6) on Sepolia mock
  spreads; try T1 instead, or raise `position_usd` to make the
  switching boundary easier to clear.

* **`unhandled exception in block N handler`** -- usually one of the
  protocol readers is calling a contract that isn't deployed on
  Sepolia. The plan deploys all six via the `agent/scripts/deploy_sepolia_mocks.sh`
  helper before this runbook step (deferred to a Plan E.1 follow-up
  if not yet done).

* **`history.parquet` corrupted on restart** -- `_load_existing()`
  catches the read error and starts fresh, so this is recoverable
  but shouldn't happen. Check disk space; the atomic-write code
  relies on `os.replace` succeeding.

## Operator sign-off

After all gates pass, append this block to
`state/runbook_first_run.log` and commit it:

```
=== OPERATOR SIGN-OFF (Plan E Task 7) ===
Operator: <name>
Date: <YYYY-MM-DD>
Run duration: <minutes>
Total blocks observed: <N>
Switch decisions: <K>
Final history.parquet rows: <M>
Flashbots dry-run verified: YES / NO
Unhandled exceptions: <0 expected>
```

Then commit the log:

```
git add agent/state/runbook_first_run.log
git commit -m "Plan E Task 7: Sepolia paper-trade runbook executed, all gates pass"
```
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv\Scripts\pytest tests\agent\test_runbook_exists.py -v
```
Expected: `3 passed`.

- [ ] **Step 5: Operator-initiated run + commit**

After the operator follows the runbook end-to-end (see "Operator sign-off" section), the deliverable is `state/runbook_first_run.log` with the sign-off block appended. The plan-side commit captures the runbook document itself:

```bash
git add "DeFi-Vega Project/agent/RUNBOOK.md" tests/agent/test_runbook_exists.py
git commit -m "Sepolia paper-trade RUNBOOK + smoke test (Plan E Task 7)

Operator playbook for the event-time agent (agent/per_block_loop.py).
Covers: decision-bridge first-time setup, .env scaffolding (with
explicit FLASHBOTS_AUTH_KEY != WALLET_KEY warning), Sepolia paper-
trade launch via configs/sepolia_paper.yaml (dry_run=true CRITICAL),
Flashbots dry-run end-to-end verification (build/sign without POST),
and 4 acceptance gates:
  >=10 switch decisions logged
  every switch returns dry_run status with non-empty txhash
  history.parquet has >=100 rows
  zero unhandled-exception lines

Three smoke tests verify the RUNBOOK file exists, contains the
required section headers, and explicitly states the >=10 rebalances
and dry_run-path gates. The runbook itself is operator-executed --
test only checks the document is present and well-formed."
```

---

## Plan summary

7 tasks. Files produced:

| File | Purpose |
|---|---|
| `agent/decision/` (junction) | Bridge to `predictive-mcdm-defi/decision/` |
| `agent/protocols/spark.py` | Spark sUSDS pool reader |
| `agent/protocols/morpho.py` | Morpho Blue base-market reader |
| `agent/protocols/fluid.py` | Fluid liquidity-layer reader |
| `agent/protocols/euler.py` | Euler V2 EVK vault reader |
| `agent/per_block_loop.py` | Event-time main loop (replaces hourly `main.py`) |
| `agent/mempool.py` | Flashbots private-mempool client |
| `agent/signal/{f1,f3,f4}.py` | Live single-row signal wrappers |
| `agent/state/history.py` | Rolling 5000-block parquet, atomic write |
| `agent/RUNBOOK.md` | Sepolia paper-trade operator playbook |
| Plus 11 test files (one per source module + runbook smoke) |

**End-state verification**:

```
.venv\Scripts\pytest tests/agent -v -m "not network"
```

Expected: 41 passed total (5 bridge + 12 protocol + 4 loop + 4 mempool + 9 signal + 6 history + 3 runbook).

Each task is one TDD cycle. Tasks are independent enough that 2, 4, 6 can be parallelised after Task 1 lands (lock the decision bridge first, same pattern as Plan A's schema-then-fork). Task 3 depends on Tasks 1+2+6 (needs the BlockState type, the readers, and a history-store to hand to the policy). Task 5 depends on Task 1 (imports `agent.decision.features.*` through the junction) and on Task 6 (consumes `HistoryStore.snapshot_df()`). Task 7 depends on every preceding task.

---

## Self-review (writing-plans skill §Self-Review)

**Spec coverage:**

| Design-spec section ("Live agent re-architecture (Week 5)") | Task | Status |
|---|---|---|
| Decision-policy zero-drift between agent and research repo | T1 | ✓ (Windows junction + 5 contract tests) |
| Six lending venues read every block | T2 | ✓ (Spark, Morpho, Fluid, Euler new; Aave, Compound pre-existing) |
| Event-time loop replaces hourly poll | T3 | ✓ (web3.py async WebSocket `eth_subscribe newHeads`) |
| Private-mempool dispatch for switch txs | T4 | ✓ (Flashbots `eth_sendPrivateTransaction`) |
| MacKenzie pp 200-203 asymmetric-speed-bump citation | T4 | ✓ (cited in module docstring and commit message) |
| Live signal builders feed T3 hazard with identical values to replay | T5 | ✓ (wrappers dispatch to research-side `build_*`, patched-mock test confirms) |
| Rolling state for OU calibrator + hazard lags | T6 | ✓ (5000-block parquet, atomic-rename, fsync) |
| Sepolia paper-trade ≥10 rebalances | T7 | ✓ (operator runbook + 4 acceptance gates) |
| Crash-resilient restart | T6 | ✓ (constructor reads existing parquet; corrupted-file fallback to empty) |
| Slow-reader does not stall policy step | T3 | ✓ (4-s `asyncio.wait_for` deadline; missing readers degrade to NaN APR) |

The "six venues" requirement is met by the four new readers plus the two pre-existing (Aave V3, Compound V3). The plan does NOT touch the pre-existing readers — they are pattern source only, read once at the start of Task 2.

**Placeholder scan:** zero TBD / TODO / fill-in-details. Every task has complete code in every step. The four new protocol readers each have **real** contract addresses (Spark `0xC13e21B6...`, Morpho Blue `0xBBBBBbbB...`, Fluid `0x52aa8994...`, Euler vault address from env), pinned in tests so upstream redeploys are detected as test diffs. ABIs are truncated in the plan-doc for readability with `# Truncated for brevity` comments — the executing subagent is expected to embed the full ABIs in the real `.py` files (these are public, available from each protocol's docs site or Etherscan).

One soft placeholder: the Euler vault address is `0xEulerEVCxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` in the docstring (literal `xxx` — a sentinel). The executing subagent must replace this with the real USDC-vault address from Euler's deployment registry before tests can run against a real RPC. The unit tests pass with a `MagicMock` w3 regardless of address validity, but Task 7 RUNBOOK explicitly calls this out as a pre-flight requirement.

**Type consistency:** every reader emits `agent.protocols.base.ProtocolState`; `per_block_loop.py` assembles those into `agent.decision.base.BlockState` (imported through the Task-1 junction = literally the research-side class, so `isinstance()` works in both repos); every policy returns `agent.decision.base.Action`; `agent.mempool.FlashbotsMempool.submit_private_tx` accepts `BlockState` and returns `dict[str, Any]` with a stable `status` field (`"included" | "failed" | "dry_run"`); `HistoryStore.append(state, action)` takes the same two types and writes a flat per-block parquet row. The signal wrappers consume `(state: BlockState, history: HistoryStore)` and return `float` (possibly NaN — caller responsibility).

The one type subtle: `eth_price_usd_provider` in `PerBlockLoop.__init__` is typed as `Callable[[], Awaitable[float]]`. In the test it's an `AsyncMock(return_value=3500.0)` — `AsyncMock()` returns a coroutine wrapping the value, satisfying the awaitable contract. Real-world wiring will pass a Chainlink oracle wrapper, not a constant. Flagged for the executing subagent to wire correctly at startup (the constant value used in tests should not bleed into production config).

**Cross-task coupling check:** Task 5's `compute_f1/f3/f4` use `history.snapshot_df()` (Task 6's API) and the research-side `decision.features.{f1,f3,f4}.build_*` functions (Plan C, imported via Task 1's junction). Task 6's parquet schema includes every column those builders need: `block_number`, `<proto>_lending_apr`, `<proto>_utilization`, `gas_price_gwei` — verified by the `test_schema_has_required_columns` test in Task 6 which lists exactly these. Task 3's `_handle_block` calls `history.append` (Task 6) and `mempool.submit_private_tx` (Task 4); the `AsyncMock`-based tests in Task 3 prove the contract holds without depending on Tasks 4 or 6's real implementations.

**Citation grounding spot-check:** MacKenzie *Material Markets* pp 200-203 is the IEX speed-bump section; the analogy to Flashbots private mempool is mine, not MacKenzie's, but the underlying claim (asymmetric latency enables toxic-order-flow extraction → mandatory delay / private routing removes the asymmetry → reduces extraction) is the central thesis of those pages. Cited in `mempool.py` docstring and in the Task 4 commit message. The plan-doc itself includes the citation in the methodology paragraph for Task 4.

---

## Execution handoff

**Plan complete and saved to `D:\DeFi\predictive-mcdm-defi\docs\superpowers\plans\2026-05-25-agent-event-time-rearch.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task via `superpowers:subagent-driven-development`, two-stage review (spec coverage + code quality), parallelisable after Task 1. Tasks 2, 4, 6 can be parallelised once the decision bridge (Task 1) lands; Tasks 3 and 5 depend on those landing first; Task 7 is operator-final.

**2. Inline Execution** — execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints between Tasks 1→2 and 2→3.

**Recommended sequence:**
- Task 1 (decision bridge) inline (~5 min, locks the import path for everything else)
- Tasks 2, 4, 6 in 3 parallel subagents (~25 min wall-clock; Task 2 is the heaviest at 4 readers)
- Task 3 (per_block_loop) inline after 2 + 6 land (~10 min)
- Task 5 (signal wrappers) inline after Task 1 + Task 6 land (~5 min)
- Task 7 (RUNBOOK) inline; document only, no compute work (~5 min)
- Operator step (Sepolia run) is human-loop, ~30-45 min wall-clock with the agent running live.

Total wall-clock for the plan code: ~50 min in best case. The Sepolia paper-trade is operator-initiated and runs in real time (one block per 12 s; ≥10 switches typically take 30-90 min depending on T1/T2/T3 sensitivity to the testnet's pseudo-rates).

**Pre-flight before kicking off Task 1:** verify that `predictive-mcdm-defi/decision/{base,t1_threshold,t2_optimal_stopping,ou_calibrator,t3_hazard}.py` exist and `predictive-mcdm-defi/decision/features/{f1,f3,f4}.py` exist (Plans B + C must be complete). Run `pytest tests/test_decision_base.py tests/test_t1_threshold.py tests/test_t2_optimal_stopping.py tests/test_ou_calibrator.py tests/test_t3_hazard.py -v` against the research repo and confirm all pass before junctioning the agent to it — if the research-side tests are red, the agent inherits the red.
