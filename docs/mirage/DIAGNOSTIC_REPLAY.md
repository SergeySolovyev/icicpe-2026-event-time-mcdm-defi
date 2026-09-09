# Versioned diagnostic replay

Two explanations in the original collection needed correction. Neither changes
market accounting, quote math, route selection or the admission rules.

- A missing usable Uniswap reference route was described as a missing liquidation
  size even when a 10,000 USDC notional had been supplied. Quote-reason version 1
  distinguishes these cases. The result remains `INSUFFICIENT` when no route is usable.
- A linear instruction walk could enter compiler metadata and label runtime
  bytecode `malformed` because an apparent PUSH operand extended past the end.
  Bytecode diagnostic version 2 reports completion of structural collection,
  retains the incomplete-walk diagnostic and explicitly disclaims EVM semantic
  validation. The entire original runtime still goes to the unchanged revert.pro
  extractor; its 70 features and digest do not change.

Unversioned saved observations retain their old interpretation when replayed.
This keeps historical artifacts reproducible and preserves strict validation of
the bytecode diagnostics against the recorded runtime.

## Re-derive explanations without collecting new data

The [offline migration](../../scripts/mirage_rederive_snapshot.py) validates the
original snapshot, recomputes the versioned explanations and writes a new file.
It refuses an existing output path. The previous file remains unchanged.

```console
python scripts/mirage_rederive_snapshot.py --source mirage/snapshots/mainnet-full-25938082-routes-v2.json.gz --output data/cached/mirage/diagnostics-replay.json.gz
python -m mirage demo --offline --snapshot data/cached/mirage/diagnostics-replay.json.gz
```

The new file records its parent's filename and SHA-256, every changed JSON field
with its before/after value, and a digest of the preserved content. A fixed
allowlist permits only the diagnostic version/explanation fields. Changes to a
raw call or result, runtime, anchor, rate input, route, quote amount or other
protected field abort publication.

This is an offline derivation of already captured returns. It is neither a new
mainnet capture nor a new independent provider verification. The original
[provider verification record](VERIFICATION_2026-09-09.json) continues to name
the original compressed artifact; its hash must not be replaced with the hash
of a derived file. Hashes establish file identity, not Ethereum authenticity.

## Committed default

The [demo manifest](../../mirage/snapshots/demo.json) selects
`mainnet-full-25938082-diagnostics-v2.json.gz`, SHA-256
`3df5fa7330740453cf64464ff992e541b2095b01c952f34cd8c262afe888ed7b`.
Its parent is `mainnet-full-25938082-routes-v2.json.gz`, SHA-256
`91aa45a2134eb8757ff4dcd9a4e651447067fa55ba20c40f700ac4840c2385fa`.

The derivation records 12 changed diagnostic fields. The unchanged inputs include
263 stored call records representing 185 distinct contract calls, and eight
distinct runtime-code reads: 193 unique saved RPC results. No new network calls
were made. Block 25938082, routes, quote amounts, feature digests and market
admission severities remain the same.

The deUSD exit explanation now identifies the unavailable reference route. PAXG's
linear-walk diagnostic no longer calls its runtime malformed; the walk offset
remains visible. Neither change supplies the missing oracle/reference evidence
or turns an insufficient finding into a pass.
