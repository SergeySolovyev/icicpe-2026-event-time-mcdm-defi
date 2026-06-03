# O1 — Yield-Drag Analyst (agent-operation)

The first **agent-run operation** of the treasury product (Layer A, op O1 in
[`docs/founder/09_agentic_operating_system.md`](../../docs/founder/09_agentic_operating_system.md)).
It turns one expensive, repeatable analyst workflow — *"how much yield is this
treasury's idle USDC leaving on the table?"* — into a contracted, reproducible,
human-gated deliverable. It is the **AI-native-service wedge**: priced on the
outcome (validated net-of-cost basis points), not on dashboard access
([`docs/founder/08_vertical_ai_repositioning.md`](../../docs/founder/08_vertical_ai_repositioning.md)).

## The Agent-Operation Contract

| Field | This operation |
|---|---|
| **Role** | Yield-Drag Analyst — one job, named |
| **Inputs** | `position_usd: float`, `current_protocol: str` (one of the 6 venues), `start`/`end` UTC dates (default = Jan–Apr 2026 held-out test window) |
| **Output artifact** | a 1-page markdown report + a JSON audit sidecar |
| **Forbidden actions** | never sends/publishes; never moves funds; never signs or submits a tx; never enters credentials. **This module GENERATES; a human sends.** |
| **SOP** | slice the real-gas panel → replay passive buy-and-hold of `current_protocol` AND the T1 gas-aware allocator over the same blocks → reconcile → render |
| **Quality / evals** | 5 numeric gates (below). The report is **withheld** (RuntimeError → escalate) if any fails. |
| **Logging / audit** | every run writes `<report>.audit.json`: inputs, panel-slice SHA-256, all outputs |
| **Escalation** | a failed gate raises instead of emitting an untrusted report |
| **Human approval gate** | a printed `NOT SENT` notice; delivery to a client is the human's call |

### The 5 quality gates (the eval set)
1. `passive_apy_sane` — passive net APY in [0, 30] %
2. `active_apy_sane` — allocator net APY in [0, 30] %
3. `active_beats_passive` — the allocator does not *lose* to passive (the whole claim)
4. `time_share_sums_100` — the per-protocol time-share reconciles to 100 %
5. `no_phantom_yield` — both final positions are strictly positive

These gates exist because the underlying engine couples the **decision** (the T1
switch threshold scales with position size) and the **accounting** (absolute gas
deducted per switch). A wrong notional silently freezes the allocator into
buy-and-hold; gate #3 catches exactly that class of error.

## Run it

```bash
# canonical demo: $5M idle in Aave V3, held-out test window
python -m product.yield_drag.yield_drag_report \
    --position-usd 5000000 --protocol aave_v3 \
    --start 2026-01-01 --end 2026-05-01

# any client persona
python -m product.yield_drag.yield_drag_report \
    --position-usd 25000000 --protocol compound_v3
```

Outputs land in `product/yield_drag/samples/` (`.md` report + `.audit.json`).
A full-test-window run replays ~864k blocks twice (passive + active) in pure
Python — this is a **batch analyst deliverable (minutes), not a real-time
dashboard**, and we say so.

## What the report says — honest by design

The report leads with the real, leakage-free result (net-of-**real**-gas edge,
6/6 walk-forward windows, p<0.001) AND its caveats, every time:

- **Net of gas, gross of MEV/slippage** — at institutional size slippage/MEV is
  the binding cost; production execution uses a Flashbots private mempool.
- **No ML magic** — the Cox-hazard ML tier does *not* beat the 50-line T1 rule
  out-of-sample (−5.97 bp, 0/5 windows). We report that openly; the edge is
  event-time resolution + gas-aware execution, not a black box.
- **Non-custodial** — the production agent can propose/execute with the client's
  keys but can **never move their funds**.

Trust is the moat (a16z *Context is King*); the report manufactures it cheaply.

## Why this and not a model

The honest research proved the model is not the moat — the *vertical workflow*
is. O1 productizes the first slice of that workflow. The ladder (O2 Rebalance
Proposer → O3 Guarded Keeper → O4 Risk Sentinel) is specced in the plan doc and
gated on the first 10 treasurer conversations — the founder action, not more
code.

## Files
- `yield_drag_report.py` — the operation (contract in its module docstring)
- `samples/` — generated reports + audit sidecars
- `__init__.py` — package marker
