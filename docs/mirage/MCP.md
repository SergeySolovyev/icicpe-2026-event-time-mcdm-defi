# MIRAGE tools for an agent

The optional stdio server exposes the existing evidence pipeline through the official MCP Python SDK. Starting it registers tools without making network calls. It has no wallet, signing or transaction submission API.

From the repository root, using Python 3.11 or newer:

```powershell
python -m pip install -r requirements-mirage.txt -r requirements-mirage-mcp.txt
python -m mirage.mcp_server
```

An MCP client should launch `python` with arguments `["-m", "mirage.mcp_server"]` and set its working directory to this repository. Use the full interpreter path when the client does not inherit your virtual environment. Add `--snapshot` and an absolute snapshot path to select another saved artifact. The default follows `mirage/snapshots/demo.json`. Do not type ordinary text into its stdin: this transport expects MCP JSON-RPC messages.

| Tool | Inputs | Result and network use |
| --- | --- | --- |
| `get_saved_report` | `include_evidence` (default `false`) | Replays the configured local evidence; compact `mirage-agent-summary/1` by default or full `mirage-feed/1` when requested. `mode: saved`, exact block/hash. No network. |
| `inspect_market` | `market_id`, `amount_usdc` (default `"10000"`), `include_evidence` (default `false`) | Captures one market after live Graph discovery at the RPC finalized block **and hash**. Compact summary by default or full feed when requested. `mode: live_capture`, timestamp and scenario. May take minutes. |
| `preview_saved_allocation` | `amount_usdc` (default `"10000"`), optional `market_id` | Runs existing T1 and MIRAGE gate on saved evidence. Returns original/gated decisions and `evidence_mode: saved`. No network. Requires the allocator's existing pandas dependency. |

The market ID must contain `0x` plus exactly 64 hexadecimal digits. Amounts are decimal strings from `0.000001` to `1000000000` USDC, with at most six decimal places. Invalid inputs are rejected before creating an RPC client. An arbitrary market must appear in The Graph's live USDC market set before any full capture. The Graph provider is a required discovery step; failures do not fall back to cached IDs or API monetary fields.

`MIRAGE_SUBGRAPH_URL` optionally selects the deployed Graph endpoint; otherwise the server uses the same deployed endpoint as the workbench. `MIRAGE_RPC_URLS` configures RPC endpoints through the existing client. Keep credential-bearing values outside version control. Live tool results are returned to the caller; they do not overwrite or silently promote the saved snapshot. Saved Graph-origin evidence remains saved.

Successful results include identical JSON in MCP `structuredContent` and text content for client compatibility. The default summary avoids duplicating a large evidence feed into an agent's context. Operational failures use `isError: true` and `mirage-tool-error/1` with a code, stage and safe message. Provider exception strings are suppressed because they can contain endpoint credentials. At most one live inspection runs per server process, and blocking capture work runs in a worker thread so saved tools remain responsive.

## Compact and full responses

`mirage-agent-summary/1` preserves capture mode, chain/block/hash/time, scenario, scalar source fields, market identifiers/display labels and aggregate severities. Every finding retains its original code, severity and summary. Up to 16 scalar metrics per finding are included without rounding or truncating their values; the selector prioritizes decision facts such as available liquidity, price deviation and the exact quote amount. Strings longer than 192 characters, opaque hex payloads and complex values are omitted.

Each finding exposes its original `metric_count`, `evidence_count` and an explicit `omitted_metrics` list. Omissions name the field, the reason and the item count for a list/object. Top-level `evidence_count_scope` explicitly states that the count sums finding-attached records, includes duplicates and excludes omitted market-rate evidence. It is not a count of unique RPC calls. Market-level rate observations are listed under `omitted_market_fields`; the authentic rate-based T1 comparison remains available through `preview_saved_allocation`. Raw calldata, return data, bytecode, feature objects and nested route details are absent from the summary. Source and display omissions, if any, are also explicit.

Every report first runs the complete original evidence replay and JSON validation. Compaction is only a projection of the validated output: it cannot convert insufficient evidence or a block into a pass. Use `get_saved_report({"include_evidence": true})` or add `"include_evidence": true` to `inspect_market` for the unchanged full `mirage-feed/1`, including raw evidence and all metrics. A second **live** inspection captures a new finalized block; compare its block/hash before assuming it describes the first call. Saved evidence is unchanged across compact/full calls.

Measured on the actual four-market snapshot at block `25938082`:

| Serialized UTF-8 size | Full evidence | Compact default |
| --- | ---: | ---: |
| JSON payload, one copy | 253,010 bytes | 17,442 bytes |
| MCP `CallToolResult`, including text and structured copies | 511,862 bytes | 35,545 bytes |

The MCP result is **93.1% smaller**. These are exact serialized sizes for this snapshot, not token estimates or a fixed upper bound for every market. The full-evidence option intentionally remains large.

Allocation is an evidence-block cold-start replay. A quote for another amount does not qualify as exact-size evidence. A blocking finding or insufficient evidence can veto entry; these are not predictions of loss, an investment recommendation, or a completed transaction. The same detector limitations documented in the main README apply to every tool.

## Validation and SDK choice

```powershell
python -m pytest tests/test_mirage_mcp.py -q
```

The tests use the SDK's in-memory client/server transport: real tool discovery and calls, saved snapshot replay, compact/full schema and known-fact equality, explicit omissions, validation without network, live discovery/capture sequencing, explicit failures and response during a blocked worker. A separate fresh-process stdio test checks both compact and full saved reports and clean shutdown. Live network smoke testing is separate and must be recorded with its actual block.

The stdio entry loads installed optional extractor dependencies on the main thread before starting the event loop. This avoids a native NumPy import stall observed when the full snapshot was first replayed in a Windows worker thread. It defaults `OPENBLAS_NUM_THREADS` and `OMP_NUM_THREADS` to `1` inside the server process, preserving explicit caller values. It does not modify the vendored extractor, load a snapshot or contact a provider. An environment without those optional dependencies retains the core's explicit unavailable diagnostics.

The optional requirement pins official `mcp==1.30.0`. The SDK's current main line is v2; FastMCP is provided by the maintained v1 line, so an unbounded SDK dependency would be incompatible. Primary references: [official v1 SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x), [server tools and errors](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/server.md), [in-memory testing](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/testing.md).

## Verified run, 9 September 2026

The final compact/full revision passed all **21 tests in 51.49 seconds** on the Windows Python 3.12 development host with the pinned SDK. This run used one native numerical thread and disabled unrelated globally installed pytest plugins, explicitly loading `anyio.pytest_plugin`. The fresh-process official SDK stdio test returned both schemas at the same block, produced the exact byte counts above and shut down cleanly.

The earlier full-response release also completed a separate official SDK stdio call to each of the three tools:

| Operation | Observed result | Elapsed time |
| --- | --- | --- |
| Start and initialize | Optional numerical imports prepared; no chain calls | 9.80 s |
| `get_saved_report` | Four markets, saved block `25938082` | 0.14 s |
| `preview_saved_allocation` | PAXG, 10000 USDC: original T1 `switch`, gated `hold`; exact scenario matched | 0.23 s |
| `inspect_market` | PAXG, 10000 USDC: 697 Graph-discovered markets, one fully inspected | 54.36 s |

The live run used only the public Tenderly and dRPC endpoints. Its finalized block was `25938274`, hash `0xac0a5d7c6140eeb998c3c474859a627fa21dffd5dc6cb13ab92cbdf4f2ca5c6a`, and capture timestamp `1788939258` (Unix seconds). The Graph reported the same query block/hash and deployment `QmYkbwLirDouGqfRapedCcQ8YCbM8dzKA13agskDwGzJ6K`.

The aggregate live verdict was **block**: `no_free_liquidity` and `oracle_reference_divergence` blocked entry; `oracle_template_unsupported` remained insufficient; `exit_size_quoted` passed its specific quote check. This is one dated smoke test, not continuous monitoring or a guarantee that future calls complete in this time. The live result did not overwrite the saved snapshot, and no transaction was submitted.
