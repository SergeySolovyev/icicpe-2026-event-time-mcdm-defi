# MIRAGE tools for an agent

The optional stdio server exposes the existing evidence pipeline through the official MCP Python SDK. Starting it registers tools without making network calls. It has no wallet, signing or transaction submission API.

From the repository root, using Python 3.12 (the validated product environment):

```powershell
python -m pip install -r requirements-mirage.txt -r requirements-mirage-mcp.txt
python -m mirage.mcp_server
```

An MCP client should launch `python` with arguments `["-m", "mirage.mcp_server"]` and set its working directory to this repository. Use the full interpreter path when the client does not inherit your virtual environment. Add `--snapshot` and an absolute snapshot path to select another saved artifact. The default follows `mirage/snapshots/demo.json`. Do not type ordinary text into its stdin: this transport expects MCP JSON-RPC messages.

## Run the client demonstration

After installing the two requirements files above, run this single command from the repository root:

```powershell
python scripts/mirage_mcp_demo.py
```

The script launches the actual stdio server with the same Python interpreter and the repository as its working directory. Through the [official SDK client](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/client.md), it initializes the session, discovers tools, calls `get_saved_report`, then calls `preview_saved_allocation` for PAXG at 10000 USDC and WETH at 10000 and 20000 USDC. Each line prints values returned by the server: saved mode, block, original/gated actions, admission and whether the sale size matches recorded evidence. The report's full block hash is printed once. There are no hard-coded expected decisions.

This demonstrates working MCP discovery, saved evidence replay and access to the existing allocator/gate, including the size-mismatch case. It uses no network and does not run an LLM or submit a transaction. The default snapshot follows `mirage/snapshots/demo.json`; its results can change if that artifact changes. SDK context managers shut down the local stdio child on completion or failure. The example prints safe tool error codes/stages, suppresses raw exception text and child logs, and returns a nonzero exit code on failure. It intentionally has no live option; use an explicitly invoked `inspect_market` call in a configured client for live evidence.

The historical Windows demonstration completed with exit code 0 on 9 September 2026 using the pinned SDK and the parent `mainnet-full-25938082-routes-v2.json.gz` snapshot (SHA-256 `91aa45a2134eb8757ff4dcd9a4e651447067fa55ba20c40f700ac4840c2385fa`). The real stdio server negotiated protocol `2025-11-25`, listed all three tools and returned four markets at saved block `25938082`, hash `0x7647a0738f03a46dd0c957cca4664d73f9bcc7c981405a8ccb00e3bd08ede2cb`. Its observed previews were:

| Saved preview | Original T1 | MIRAGE-gated T1 | Exact sale size | Admission |
| --- | --- | --- | --- | --- |
| PAXG, 10000 USDC | `switch` | `hold` | `true` | `block` |
| WETH, 10000 USDC | `switch` | `switch` | `true` | `pass` |
| WETH, 20000 USDC | `switch` | `hold` | `false` | `insufficient` |

The last result included `exit_scenario_not_checked`; the saved 10000-USDC sale quote did not authorize the 20000-USDC scenario. The client printed its completion message only after leaving both SDK session/transport contexts.

The current default is the [diagnostics-v2 snapshot](../../mirage/snapshots/mainnet-full-25938082-diagnostics-v2.json.gz), which preserves those recorded inputs and their block. Separately, the clean Ubuntu/Python 3.12 [CI run 34340178487](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/actions/runs/34340178487) passed all **218 focused offline product tests** and the official SDK stdio client example on 9 September 2026. These Linux results are distinct from the Windows size measurements below.

## Available tools

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

Measured on 9 September 2026 for the current four-market `mainnet-full-25938082-diagnostics-v2.json.gz` snapshot, SHA-256 `3df5fa7330740453cf64464ff992e541b2095b01c952f34cd8c262afe888ed7b`, at block `25938082`. The successful measurement used the **official SDK in-memory connected client/server**, the actual `create_server(snapshot_path=...)`, and unchanged saved-report tool calls, with no mocks or replacement report data. The environment was Windows CPython 3.12.8, MCP SDK 1.30.0, Pydantic 2.13.5 and AnyIO 4.10.0.

| Serialized UTF-8 size | Full evidence | Compact default |
| --- | ---: | ---: |
| JSON payload, one copy | 253,357 bytes | 17,437 bytes |
| MCP `CallToolResult`, including text and structured copies | 512,558 bytes | 35,535 bytes |

The exact serialization definitions are:

```python
payload_bytes = len(result.content[0].text.encode("utf-8"))
result_bytes = len(result.model_dump_json(by_alias=True, exclude_none=True).encode("utf-8"))
```

The payload text is produced by the server's `json.dumps(payload, allow_nan=False, ensure_ascii=True)`. The result size includes both text content and `structuredContent`; it excludes the JSON-RPC envelope, transport framing and compression. Reduction is `100 * (full_bytes - compact_bytes) / full_bytes`: **93.1%** rounded to one decimal place for both rows. These are serialized byte counts, not token estimates, a latency benchmark or a fixed upper bound for other markets.

For the historical parent `mainnet-full-25938082-routes-v2.json.gz` (SHA-256 `91aa45a2134eb8757ff4dcd9a4e651447067fa55ba20c40f700ac4840c2385fa`), a successful **official SDK STDIO** measurement with the same current product code produced **253,010 / 17,442 bytes** for full/compact payloads and **511,862 / 35,545 bytes** for full/compact `CallToolResult` objects. These parent-snapshot numbers use the same serialization definitions; they are not the current default's sizes.

Two new Windows STDIO attempts for diagnostics-v2 failed before session initialization completed, so they yielded no saved-report response sizes. The in-memory fallback above then succeeded and closed its SDK session. No live tools, RPC calls or Graph calls were used, and both snapshot files remained unchanged. The underlying cause of the Windows startup failures was not established. This size measurement is not a startup-speed benchmark or a successful diagnostics-v2 STDIO verification; the separate successful Linux STDIO check is linked above.

Allocation is an evidence-block cold-start replay. A quote for another amount does not qualify as exact-size evidence. A blocking finding or insufficient evidence can veto entry; these are not predictions of loss, an investment recommendation, or a completed transaction. The same detector limitations documented in the main README apply to every tool.

## Validation and SDK choice

```powershell
python -m pip install -r requirements-mirage.txt -r requirements-mirage-mcp.txt "pytest==8.3.5" "anyio==4.10.0"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"
python -m pytest --noconftest -p anyio.pytest_plugin -m "not network" -q tests/test_mirage_mcp.py
```

`--noconftest` skips the repository's unrelated Windows research-DLL preload. Disabling plugin autoload and explicitly loading `anyio.pytest_plugin` keeps this invocation focused on the product dependencies. The tests use the SDK's in-memory client/server transport: real tool discovery and calls, saved snapshot replay, compact/full schema and known-fact equality, explicit omissions, validation without network, live discovery/capture sequencing, explicit failures and response during a blocked worker. A separate fresh-process stdio test checks both compact and full saved reports and clean shutdown. Live network smoke testing is separate and must be recorded with its actual block.

The stdio entry loads installed optional extractor dependencies on the main thread before starting the event loop. This was introduced after a native NumPy import stall was observed when the full snapshot was first replayed in a Windows worker thread. It defaults `OPENBLAS_NUM_THREADS` and `OMP_NUM_THREADS` to `1` inside the server process, preserving explicit caller values. It does not modify the vendored extractor, load a snapshot or contact a provider. An environment without those optional dependencies retains the core's explicit unavailable diagnostics.

The optional requirement pins official `mcp==1.30.0`; this integration uses the v1 FastMCP API and should not be installed with an unbounded SDK dependency. Primary references: [official v1 SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x), [server tools and errors](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/server.md), [in-memory testing](https://github.com/modelcontextprotocol/python-sdk/blob/v1.x/docs/testing.md).

## Historical Windows runs, 9 September 2026

The earlier compact/full revision passed all **21 MCP tests in 51.49 seconds** on the Windows Python 3.12 development host with the pinned SDK and the parent routes-v2 snapshot. This historical run used one native numerical thread and disabled unrelated globally installed pytest plugins, explicitly loading `anyio.pytest_plugin`. Its fresh-process official SDK stdio test returned both schemas at the same block, produced the parent-snapshot byte counts recorded above and shut down cleanly. This timing does not describe the new diagnostics-v2 measurement or the later 218-test Linux CI run.

The earlier full-response release also completed a separate official SDK stdio call to each of the three tools:

| Operation | Observed result | Elapsed time |
| --- | --- | --- |
| Start and initialize | Optional numerical imports prepared; no chain calls | 9.80 s |
| `get_saved_report` | Four markets, saved block `25938082` | 0.14 s |
| `preview_saved_allocation` | PAXG, 10000 USDC: original T1 `switch`, gated `hold`; exact scenario matched | 0.23 s |
| `inspect_market` | PAXG, 10000 USDC: 697 Graph-discovered markets, one fully inspected | 54.36 s |

The live run used only the public Tenderly and dRPC endpoints. Its finalized block was `25938274`, hash `0xac0a5d7c6140eeb998c3c474859a627fa21dffd5dc6cb13ab92cbdf4f2ca5c6a`, and capture timestamp `1788939258` (Unix seconds). The Graph reported the same query block/hash and deployment `QmYkbwLirDouGqfRapedCcQ8YCbM8dzKA13agskDwGzJ6K`.

The aggregate live verdict was **block**: `no_free_liquidity` and `oracle_reference_divergence` blocked entry; `oracle_template_unsupported` remained insufficient; `exit_size_quoted` passed its specific quote check. This is one dated smoke test, not continuous monitoring or a guarantee that future calls complete in this time. The live result did not overwrite the saved snapshot, and no transaction was submitted.
