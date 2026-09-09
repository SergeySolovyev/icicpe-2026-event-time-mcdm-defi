# Full recorded observations for 697 Morpho USDC markets

MIRAGE recorded and replayed all three check groups for every one of the **697
USDC market IDs** in its Graph discovery manifest at Ethereum block **25938815**.
The scenario is a hypothetical **10000 USDC** collateral-sale notional. Complete
recording includes unavailable observations; it does not mean that every check
passed, that every oracle is understood, or that every market supports the sale.

The evidence block hash is
`0x6151b63f20f0f5fa115ccd736cf42d08759914eb60748c9b102d38a7ad9ffe00`.
Discovery used the deployed Graph subgraph at this same block/hash. The
[manifest](evidence/full-25938815/manifest.json) fixes the IDs and source; offline
verification did not query Graph again. The four-market demonstration at block
25938082 remains the default and is a separate artifact.

## Recorded coverage and outcomes

The [summary](evidence/full-25938815/summary.json) contains 697 unique markets,
all three check groups for each, and 697 replayed rate observations, with zero missing
rows and zero accounting-only rows. Unavailable results remain explicit.

| Aggregate detector verdict | Markets |
|---|---:|
| PASS | 32 |
| WARN | 3 |
| BLOCK | 95 |
| INSUFFICIENT | 567 |
| Total | 697 |

**625 markets have at least one INSUFFICIENT finding.** This differs from the 567
aggregate INSUFFICIENT verdicts because BLOCK takes precedence: 58 blocked markets
also contain an insufficient finding. Only 72 markets have no insufficient finding;
that count still includes warnings and blocks.

PASS applies to the configured checks, evidence block and declared size. The table
is not a count of T1 proposals, agent admissions, transactions or safe investments.
For example, an exit quote may pass while an unsupported oracle prevents admission.

The separate exit check yields **79 PASS, 34 BLOCK and 584 INSUFFICIENT**. The
summary also records 145 unsupported oracle-template findings and 569 unavailable
reference findings. These categories overlap and must not be summed as distinct
markets. Unavailable reference/quote evidence is not proof of zero liquidity across
all venues. The route search covers the implemented Uniswap v3 candidates, not every
fee combination, split route or liquidation venue.

## Completion and resume

The first full pass left one market uncollected. The missing-only resume reused
**696 immutable full checkpoints** and made **one new attempt**. Its terminal
[capture status](evidence/full-25938815/capture-final-status.json) records 697
completed, zero failed, and completion at **2026-09-09 13:18:36 UTC**.
The resume and merged-artifact work took **180.66 seconds**, about three minutes;
this is not the duration of the entire universe collection.

For every market, the raw parameter/state calls in its full checkpoint match its
accounting checkpoint exactly. This compares two stored collection stages at the
same anchor; it is **not a second-provider reread**. The final verifier also matched
all 697 full-checkpoint rows to the original merged snapshot.

## Stored accounting quantities

All quantities below are sums of decoded stored `market()` fields across 697
markets. No extra interest accrual is simulated.

| Stored quantity | Exact raw base units | USDC token units |
|---|---:|---:|
| Supply assets | 11750194544266864 | 11750194544.266864 |
| Borrow assets | 11650901635717876 | 11650901635.717876 |
| Supply minus borrow | 99292908548988 | 99292908.548988 |

Supply and borrow are stored accounting assets and debt. These sums are **not
recovered principal or a dollar TVL valuation**. Supply minus borrow is stored
free liquidity, not a guarantee of an account's withdrawal rights. No market had
a negative stored difference. The normalized share exchange rate can warrant
investigation; it does not independently prove phantom debt or insolvency.

The independent accounting audit decoded all six `uint128` words per market,
recomputed market IDs with Keccak, and rechecked all 1394 checkpoint hashes after
comparison. **691 checkpoints contain their own USDC `decimals()` response equal
to six. Six lack their own response** and are recorded as
`missing_own_response / insufficient`: five have unavailable token-decimal
metadata and one has a zero token address. Another checkpoint's response is not
attributed to any missing case. The USDC-unit column uses the canonical loan-token
identity and six-decimal denomination; the missing per-market metadata remains
disclosed. See [accounting proof](evidence/full-25938815/accounting-independent.json)
and [paired input inventory](evidence/full-25938815/accounting-inventory.json).

## Original evidence and corrected diagnostics

| Artifact | SHA-256 |
|---|---|
| [Original merged snapshot](../../mirage/snapshots/full-merged-85f88148bb9c4dad99a6aa1efec34d3e.json.gz) | `a0655aaebd29c669321fbabbf5f2bc08b90becf3a62fe3c44c51c135ffd4e6be` |
| [Derived full-universe snapshot](../../mirage/snapshots/mainnet-full-25938815-diagnostics-v2.json.gz) | `270bae6cb656a0ed1d87ede25ea04c296acc7c1101d81356365d17a6343c2585` |

The derived artifact uses quote-reason version 2 and bytecode-diagnostic version 2.
It corrects explanations such as an unavailable reference being described as an
unspecified sale despite a supplied notional. The migration changes 1739 explicitly
listed diagnostic fields, including 569 quote reasons. It preserves raw calls,
runtime bytes, anchors, scenarios, numerical inputs and rate observations.
For all 697 markets, finding codes, severities and rates are unchanged.
No network calls were made during this derivation.

The [final offline verification](evidence/full-25938815/offline-verification.json)
replayed both artifacts, checked the narrow change allowlist and protected-content
hash, and reconciled the manifest, checkpoints and original merged report.
It records **13575 distinct anchored `eth_call` results** and **1182 distinct
runtime-code results**. These are unique saved-result identities, not a claim about
total transport requests, retries or block-header reads.

The [independent Uniswap audit](evidence/full-25938815/uniswap-independent.json)
uses separate ABI and numerical calculations over the
[frozen checkpoint inventory](evidence/full-25938815/uniswap-inventory.json).
Its expected exit outcomes matched production results for every market in the
[per-ID comparison](evidence/full-25938815/exit-comparison.json), with zero mismatches.
This does not independently validate every oracle mechanism or make product replay
an independent detector implementation. None of these offline checks authenticates
a fabricated raw dataset as Ethereum truth or replaces another RPC provider.

The [asset manifest](evidence/full-25938815/asset-manifest.json) lists the published
files and hashes. The `*.py.txt` files beside it archive the exact local audit and
capture logic, including its original paths; they are historical sources, not
portable launch commands. Individual checkpoint files and the large original
rendered feed are not included. Their raw rows are preserved in the merged snapshot,
with checkpoint equality and inventories recorded in the proofs above.

## Reproduce without network

Use Python 3.12 and install `requirements-mirage.txt` from the repository root.
The public summary command validates the raw snapshot through offline replay and
writes a summary to a new absolute path; it does not print the full evidence feed:

```powershell
python -m pip install -r requirements-mirage.txt
$universeSnapshot = (Resolve-Path 'mirage/snapshots/mainnet-full-25938815-diagnostics-v2.json.gz').Path
$universeSummary = Join-Path $env:TEMP ('mirage-summary-' + [guid]::NewGuid().ToString('N') + '.json')
python scripts/mirage_summarize_universe.py --snapshot $universeSnapshot --output $universeSummary
```

Use `--stdout` instead of `--output` if a printed summary is preferred. To reproduce
the diagnostic child from the original capture with the product dependencies:

```powershell
$universeParent = (Resolve-Path 'mirage/snapshots/full-merged-85f88148bb9c4dad99a6aa1efec34d3e.json.gz').Path
$universeDerived = Join-Path $env:TEMP ('mirage-derived-' + [guid]::NewGuid().ToString('N') + '.json.gz')
python scripts/mirage_rederive_snapshot.py --source $universeParent --output $universeDerived
Get-FileHash -LiteralPath $universeDerived -Algorithm SHA256
```

The expected child SHA-256 is the derived-artifact hash above. Both commands refuse
existing output paths. Re-derivation starts from the original capture, not from an
already derived file. These commands make no RPC calls, submit no transactions and
do not change the default four-market demonstration or assert a new browser check.
