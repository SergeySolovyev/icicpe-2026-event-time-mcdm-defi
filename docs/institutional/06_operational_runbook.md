# Operational Runbook (mainnet extension)

Extends `DeFi-Vega Project/agent/RUNBOOK.md` (Plan E Task 7,
Sepolia-focused) with mainnet-grade operations.

## SLA targets (commit to LPs)

| Metric | Target | Tolerance | Action if breached |
|---|---|---|---|
| Agent uptime | 99.5%/month | ≥ 99.0% | RCA + post-mortem; LPs notified |
| Block-lag P95 | < 30 blocks | 100 blocks | RPC failover; manual review |
| Rebalance latency | < 5 s after signal | 60 s | Investigate Flashbots inclusion path |
| Auto-withdraw on depeg | within 1 block of trigger | 5 blocks | Manual override; LPs notified within 1 h |
| Position reporting | T+0 (real-time UI) | T+1 (daily) | Manual upload; investigate timestamp drift |

## Deployment topology

- **Off-chain agent**: cloud VM (AWS us-east-1 preferred for low
  latency to mainnet RPC; Hetzner / DigitalOcean as fallback).
- **RPC providers**: 2× primary (Alchemy + Infura), 1× failover
  (QuickNode or own node).
- **Database**: Postgres for audit trail; history.parquet snapshots
  backed up hourly.
- **Key management**: HSM (CloudHSM / YubiHSM) for production wallet
  key; multisig (Safe / Gnosis) treasury layer above $1M.

## Monitoring & alerting (PagerDuty / Opsgenie)

| Alert | Trigger | Severity | Response |
|---|---|---|---|
| Block-lag | Agent missed > 100 blocks | High | Failover RPC, restart agent |
| Gas spike | gas > 200 gwei sustained > 10 blocks | Medium | Built-in pause; manual review |
| Depeg | USDC \| USDT > 50 bp deviation | High | Auto-withdraw to ETH |
| Policy stall | No rebalance in 24h on switching policy | Low | Verify panel data freshness |
| TVL collapse | In-position protocol TVL drop > 20% / 1h | High | Auto-withdraw; manual investigation |

## Kill-switch protocol

- **Manual**: operator sends `STOP` signal via signed message to
  multisig → agent withdraws all positions to USDC custody.
- **Auto**: triggered on (a) USDC depeg ≥1%, (b) in-position protocol
  exploit detected on Forta, (c) chain reorganization > 12 blocks
  detected.

## Fee + cost budget (annualized, $1M position)

| Cost item | Annualized | Source |
|---|---:|---|
| Gas (35–45 rebalances/yr × $17.5) | $612–788 | Test-window measurement |
| Slippage (sub-$5M position, IRM curve) | < 10 bp | Capacity §03 |
| MEV (Flashbots private mempool) | ~0 bp | Asymmetric speed-bump |
| RPC + infra (Alchemy + Infura + own node) | $200–400/mo = $2.4–4.8k/yr | Provider pricing |
| Monitoring (PagerDuty / Sentry / Datadog) | $100–300/mo = $1.2–3.6k/yr | Service tiers |
| Custody/HSM ($1M tier) | $200–500/mo = $2.4–6k/yr | CloudHSM pricing |
| **Total operational** | **$6–15k/yr** | < 0.15% AUM |

Operational costs amortize to a 7–15 bp drag at $1M AUM, dropping to
1–2 bp at $10M+ where infrastructure costs are mostly fixed. The
gas-cost crossover inequality `E[gain] > C^(b)` (§III) already
encodes the gas budget; slippage and MEV are bounded by the
capacity analysis and the Flashbots integration.

## Disaster recovery scenarios

| Scenario | Detection | Recovery RTO | Recovery RPO |
|---|---|---|---|
| Cloud VM crash | Block-lag alert | < 5 min (auto-restart) | 0 (state in Postgres) |
| RPC provider outage | Failover triggered | < 1 min | 0 (multi-provider) |
| Wallet key compromise (suspected) | Multisig signature anomaly | < 30 min (revoke + rotate) | dependent on extraction |
| In-position protocol exploit | Forta agent | < 1 block (auto-withdraw) | dependent on slippage |
| Chain reorganization > 12 blocks | Block monitor | Manual pause + reconcile | 0 (history.parquet) |
| USDC depeg ≥ 1% | Oracle freshness check | < 1 block | 0 (auto-route to ETH) |

## LP communications

- **Daily**: automated equity snapshot to LP dashboard (Dune-compatible
  on-chain proof + off-chain UI).
- **Weekly**: rebalance summary email (n_switches, gas spent, current
  protocol weights, alerts triggered).
- **Monthly**: performance attribution memo (per-protocol $ P&L,
  policy contribution analysis, capacity utilization).
- **Quarterly**: drawdown debrief + risk-register update if any new
  events emerged.
- **Ad-hoc**: any kill-switch trigger or safety event notified
  within 1 hour.

## Post-incident review template

Each incident: 5-section markdown — (1) what happened, (2) detection
time, (3) response time, (4) root cause, (5) remediation. Reviewed
weekly. Catalogued in `docs/institutional/incidents/` with sequential
INCIDENT-YYYY-NNN identifier; high-severity incidents trigger LP
notification within 1 hour.