# MIRAGE analyst interface

Implemented as static HTML, CSS and JavaScript in `mirage/web/`, with no build
step, package installation, external font request, or client-side framework.

## Design direction

The audience is an allocator deciding whether a proposed Morpho destination
has enough evidence to admit capital. The interface should make uncertainty
legible, keep accounting claims separate from free liquidity, and expose the
exact contract calls behind the result.

Tokens: paper `#F3F2EB`, white `#FFFFFF`, ink `#172F35`, muted `#64767A`, aqua
`#6EE2CA`, danger `#A94034`. Windows Bahnschrift is the primary interface face,
with Segoe UI/system fallbacks; Georgia gives the editorial heading a distinct
voice. Tabular numerals are used for quantities. Monospace is reserved for
contract IDs and raw evidence.

The memorable element is the dark allocation workbench alongside a light,
dense market ledger. The initial concept of a large headline number was
rejected: a large aggregate would obscure the distinction between stored
claims and withdrawable liquidity. Only observed market counts and explicit
block/source metadata are promoted to the top strip.

```text
brand                         methodology / repository
headline                      source + scan action
observed markets | admission | block | evidence source
market ledger (search/filter)  allocation workbench
                              original -> gated action
click market -> evidence drawer with three checks and raw calls
```

All content is left aligned except numeric columns. The amount input is a
user-editable scenario, not historical evidence. Mobile stacks the allocation
workbench after the ledger. The drawer stays within the viewport and restores
focus on close. Reduced motion and visible keyboard focus are supported.

## Data and safety

- `GET /api/report`: existing report, or `{report: ...}` envelope.
- `GET /api/status`: accepts `state`, `status`, `running`, or `busy`; optional
  `message`, `progress`, `error`, `updated_at` and `mode`.
- `POST /api/scan`: starts a scan with `{amount_usdc, market_id}`. A selected
  destination is inspected against the live discovered universe. The UI polls status while work is running and
  reloads the report after completion. Starting a scan is always user-driven.
- The ledger's Check another market form accepts an exact 32-byte market ID
  and calls the same endpoint. It never inserts a synthetic market row or
  destination; the Graph-backed server must validate and capture it first.
- `GET /api/allocator?amount=...&market=...`: accepts original/gated Action
  objects, or original_action/gated_action. Unknown response shapes remain
  available in a details disclosure instead of fabricating a decision.

Market amounts are formatted from raw USDC integers with BigInt division;
large raw amounts are never first converted through JavaScript Number.
Ratios are presentation-only strings. Unavailable fields display an em dash
or an explicit missing-evidence message, never zero or PASS. The report's
severity is authoritative. No successful admission is inferred from an
accounting-only pass.

`report.source.kind == 'the-graph'` identifies Graph as the discovery origin.
The report is labelled Live evidence only when `/api/status.mode == 'live'`
also confirms the current run; otherwise it is Saved evidence. The recorded
block is always visible. `source.discovery_market_count` describes the discovered
universe separately from the number of inspected markets shown in the table.
The displayed live state is a completed capture, not a continuous stream;
the block's UTC timestamp is included when the server supplies it. Optional
rate observations are labelled annualized accrual-rate indications, with the
IRM's temporal semantics and no promise of realized yield. Their raw evidence
is included in the drawer alongside detector evidence.
The standalone sample has no synthesized values. If the API is unavailable,
the user sees a connection error and a retry action.

Dynamic strings are inserted with `textContent` or DOM attribute APIs. They
are not interpolated into HTML. Raw evidence is copied exactly as JSON and
uses `to`, `data`, `block`, `block_hash`, `method`, `result` where supplied.
External links use constant trusted URLs and `rel="noopener noreferrer"`.

Three detector sections remain visible even when unfinished. Missing oracle
or exit-depth checks are labelled Pending, not passed. An implementation-level
pending finding is preserved in the market result. The interface does not
construct a simulated allocation action if the backend fails.

## Verification boundary

On 9 September 2026, `node --check mirage/web/app.js` passed. Browser inspection
against the actual local server at `http://127.0.0.1:8765/` verified:

- Both saved markets render at block 25,937,912 with 0 and 0.01 USDC available.
- Searching deUSD leaves one row; clearing search and filtering Blocked leaves
  PAXG. Search and verdict filters compose rather than replacing each other.
- Market drawers show three check groups, preserve Pending/Insufficient, expose
  original call results, and close with focus restored.
- The real allocator endpoint returns hold/hold for the old snapshot without
  APR observations; the interface displays the missing-rate rationale.
- A zero allocation is rejected locally with a specific validation message.
- The later Graph-backed saved report at block 25,938,082 renders 697 discovered
  markets separately from three inspected markets. The source remains Saved
  after server restart. Rate observations in the drawer are labelled accrual-rate
  indications. The new market-ID form rejects `0x1234` without creating a row.
- Large bytecode/getter measurement objects are behind an explicit measurements
  disclosure, so all three detector summaries remain easy to inspect.
- The 390-pixel responsive override rendered with an effective content width
  of 375 pixels, no horizontal body overflow, readable market rows, and a
  viewport-contained evidence drawer. The override was reset after inspection.

Only browser-extension-origin errors were observed in the inspected console
sample. Live scan polling is connected to the actual API contract but a live
scan was not launched during this UI review. This document does not claim an
admission transaction, historical backtest, or deployment.
