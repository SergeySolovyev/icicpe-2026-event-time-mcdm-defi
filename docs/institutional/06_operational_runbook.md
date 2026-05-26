# Operational Runbook (mainnet extension)

Extends `DeFi-Vega Project/agent/RUNBOOK.md` (Plan E Task 7,
Sepolia-focused) with mainnet-grade operations.

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

## Post-incident review template

Each incident: 5-section markdown — (1) what happened, (2) detection
time, (3) response time, (4) root cause, (5) remediation. Reviewed
weekly.