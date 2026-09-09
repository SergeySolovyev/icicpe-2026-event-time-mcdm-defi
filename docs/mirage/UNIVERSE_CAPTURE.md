# Reproduce a resumable USDC universe capture

These scripts collect real Ethereum mainnet observations and replay them through MIRAGE. They extend the single-run CLI with per-market checkpoints. They do not send transactions or require a wallet, API key, or paid RPC plan.

The universe is whatever the pinned Graph deployment discovers for USDC at the finalized Ethereum block chosen when a new run starts. A previous capture discovered 697 markets; this is a historical observation, not a hardcoded count or a promise about a new run.

## Run from the repository root

Use Python 3.12 and the product requirements. Full collection can load the vendored bytecode feature extractor, so install the same dependencies used by the product:

```sh
python -m pip install -r requirements-mirage.txt
python scripts/mirage_capture_universe.py --run-dir data/cached/mirage/universe-run --phase accounting --log-progress
python scripts/mirage_capture_universe.py --run-dir data/cached/mirage/universe-run --phase full --log-progress
```

Start with a new directory. The accounting phase creates the manifest and records the two raw Morpho reads for each market. The full phase adds oracle history, Uniswap execution observations, display metadata and rate observations for the fixed 10,000 USDC scenario. The scenario is an input to the quote checks, not a deposit or liquidation instruction.

The full phase requires an existing accounting manifest; accounting may be partial. Full capture reads each market's accounting state again at the same block. A merged snapshot uses its full row when available and otherwise retains its accounting row.

Run the same command again after a partial result or Ctrl+C. Completed checkpoints are validated and skipped; missing or previously failed markets are retried. A completed run can be replayed again without recollecting its markets. To collect a newer block, choose a **new directory**.

Exit codes: `0` means every market has a valid checkpoint for the requested phase; `2` means that phase has remaining failed markets; `1` means a fatal error; `130` means Ctrl+C. Completed collection can contain BLOCK, WARN and INSUFFICIENT findings. It does not mean every market passed or that every external observation was available.

## Fixed source and provenance

The collector uses the public [MIRAGE Subgraph Studio query endpoint](https://api.studio.thegraph.com/query/1759002/mirage-morpho-markets/v0.0.1), deployment `QmYkbwLirDouGqfRapedCcQ8YCbM8dzKA13agskDwGzJ6K`, and the public Tenderly/dRPC mainnet endpoints listed in the script. These explicit endpoints do not inherit an RPC URL from the environment. No network request occurs merely by importing a script.

Discovery is queried at the finalized block's hash. The manifest fixes the source, deployment, sorted market IDs, chain ID, block number/hash/timestamp and scenario. Resume validates that manifest and all accounting/full checkpoints before collecting anything. Checkpoints must have the exact source and anchor, one matching market ID, the expected phase's observations and replayable raw evidence. The full row's reference scenario must itself specify 10,000 USDC; matching only the snapshot header is insufficient.

The collector verifies the anchor on entry, after a failed market and before completing the run. The underlying capture also verifies its anchor after collection. A changed current or historical block hash is fatal. An unavailable anchor verification is fatal too. Saved observations are supplied RPC evidence, not a cryptographic state proof; offline replay does not independently authenticate a provider response or establish freshness.

Free public services can throttle or fail, and historical calls can become unavailable. The Graph deployment must still be available and index the requested block. There is no promised runtime, and retries cannot repair an unavailable historical archive. Errors leave already published checkpoints intact.

## Files and interruption

| File | Meaning |
| --- | --- |
| `manifest.json` | Immutable discovery source, anchor, scenario and complete market ID list. |
| `accounting/<market_id>.json.gz` | Immutable, validated raw accounting checkpoint. |
| `full/<market_id>.json.gz` | Immutable, validated checkpoint with all detector observations recorded. |
| `failures.jsonl` | Append-only failed-attempt history. A later successful checkpoint supersedes its old failure for current coverage. |
| `status.json` | Latest atomic progress update, phase, counts and final artifact paths. |
| `progress.jsonl` | Optional append-only progress stream when `--log-progress` is present. |
| `<phase>-merged-<unique_id>.json.gz` | New immutable merged snapshot, with explicit discovery/included/full/accounting-only/missing counts. |
| `<phase>-merged-<unique_id>.feed.json` | MIRAGE feed produced by replaying that merged snapshot. |
| `.running.lock` | Exclusive lock for one writer in this run directory. |

Snapshots and manifests are first written to a sibling `.pending` directory, then published with a hard link that fails if the destination exists. This requires a filesystem supporting hard links, such as NTFS or ext4. Existing checkpoints and merged artifacts are never overwritten. A killed process can leave an ignored pending file; it is not treated as a checkpoint. Mutable status uses atomic replacement. Atomic visibility is not a guarantee against storage failure or power-loss durability.

Ctrl+C releases the lock and preserves finished checkpoints. A force kill can leave `.running.lock`; confirm its recorded process is no longer running before manually removing only that lock. The script never removes another writer's lock automatically. A nonempty directory without a manifest is rejected; if discovery failed before publishing the manifest, choose another empty run directory.

Successful fixed-block reads are cached within one invocation. Failed reads are memoized only within one market and retried for the next market. This in-memory cache is not reused between invocations; the durable resume mechanism is the validated per-market checkpoint.

## Offline summary

Copy the actual `snapshot` path from the finished `status.json`. Each completion writes a unique artifact; the scripts do not guess which historical file is newest.

```sh
python scripts/mirage_summarize_universe.py --snapshot "PATH_FROM_STATUS.json.gz" --output data/cached/mirage/universe-summary.json
```

Use `--stdout` instead of `--output` to print JSON. An output path must be new. The summary makes no network calls and replays every supplied raw observation with the product validators before counting findings or summing balances. It includes the source snapshot's SHA-256, anchor, coverage, exact USDC base-unit totals, finding counts, and example rankings.

Coverage distinguishes discovered markets, included markets, accounting-only rows, and rows with all three checks recorded. A missing row is not automatically a failed attempt. An unknown discovery count remains unknown. Conflicting discovery counts are rejected; source counts are metadata from the snapshot, not independently re-queried by the summary.

Accounting totals are decoded stored `market()` fields at the pinned block. No additional interest accrual is simulated. Supply/borrow amounts are not recovered deposit principal or a dollar TVL valuation. Supply minus borrow is a stored free-liquidity balance, not a guarantee that a withdrawal will succeed. Share exchange-rate multiples describe the share conversion rate relative to its initial scale; they do not prove accumulated interest or losses. Rankings describe accounting size, not investment suitability.

## Offline lifecycle checks

```sh
python -m pip install pytest
python -m pytest --noconftest -q tests/test_mirage_universe.py
```

The focused invocation skips the research repository's root `conftest.py` and its unrelated imports. Tests replace discovery and collection with deterministic transport fakes while retaining committed WETH/deUSD raw evidence and the real snapshot validators. They cover interruption, partial accounting/full coverage, resumption, source and block mismatches, corrupt checkpoints, immutable publication, locks, cache retry scope and offline summary validation. They do not run a fresh network capture.

This reproduces the collection procedure at a newly chosen finalized block. It cannot promise byte-identical observations to a past capture, future RPC availability, a PASS finding, or complete risk coverage.
