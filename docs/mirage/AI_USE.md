# AI use and contribution disclosure

Prepared on 9 September 2026 for MIRAGE's ETHOnline Continuity submission. This records observed work and identifies historical attribution that still needs owner confirmation.

The [ETHOnline rules, “Use of AI Tools”](https://ethglobal.com/events/ethonline2026/info/details) require disclosure of AI-assisted files, meaningful team participation, and the specifications/prompts/planning artifacts used in a specification-driven build. This document does not establish eligibility or certify that the historical archive is complete.

## People, tools and evidence

- **Human direction observed in the supplied instructions:** Sergey supplied the two existing repositories, the MIRAGE problem framing and hackathon constraints; directed priorities, reuse and the requirement to check demonstration numbers through individual mainnet calls; and requested that errors be challenged before implementation.
- **Human research reported by the owner:** the initial instructions describe personal mainnet checks. This disclosure does not independently establish who performed each historical check. Subsequent agent checks corrected several interpretations in the handoff; see [corrections](CORRECTIONS_2026-09-09.md).
- **OpenAI Codex agents, 9 September:** generated and revised nearly all of the new MIRAGE Python implementation, tests, web interface, deployment configuration and documentation — every file in the table below except the earlier Claude-authored subgraph scaffold and the standard MIT license text. The exact Codex model and version are not recorded in this repository. Agents also inspected the existing code, consulted primary documentation, ran RPC/browser/CLI verification and produced evidence reports. Passing an automated check is not a claim of human code review.
- **Claude Code, 13 September:** wrote the Chainlink addition — `contracts/src/MirageGate.sol`, `contracts/src/ExecutionGuard.sol`, their 21 Foundry tests, the deploy script, the key-free publisher `scripts/mirage_chainlink_publish.py` and the accompanying documentation — and rehearsed the deployment against a forked Sepolia. It signed nothing and never handled a private key.
- **Claude Code, earlier preparation:** the user-supplied history attributes the earlier handoff, initial README and creation-event subgraph preparation to Claude Code. This is reported provenance, not a reconstructed original session log. Exact historical model versions and the division of human/AI authorship of the older repositories remain unverified.

## Existing work is not new AI-generated MIRAGE work

The allocator baseline is [commit 520b676](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/commit/520b676). Its [decision policies](../../decision/), [replay engine](../../backtest/replay_per_block.py), research data and notebooks predate this extension. Their historical human/AI authorship is not determined here. The first hackathon commit is [e56cd7f](https://github.com/SergeySolovyev/icicpe-2026-event-time-mcdm-defi/commit/e56cd7f); it already existed when the current Codex continuation began.

The second baseline is [revert.pro at 324431a514c5ebebbdbe620cb789f83ea78a231a](https://github.com/SergeySolovyev/smart-contract-vuln-detection-from-bytecode/tree/324431a514c5ebebbdbe620cb789f83ea78a231a). The vendored [evm_extractor.py](../../mirage/vendor/revert_pro/evm_extractor.py) retains its exact original bytes and upstream MIT license; [provenance](../../mirage/vendor/revert_pro/PROVENANCE.md) records its hash. Copying that source does not establish new authorship. MIRAGE's adapter and operand diagnostics are new Codex-assisted code.

## Two pre-event files at the repository root

[`LLM_TRANSCRIPT.md`](../../LLM_TRANSCRIPT.md) and [`CLAUDE.md`](../../CLAUDE.md) are
artifacts of the pre-existing HSE coursework project that produced the allocator
baseline described above. `CLAUDE.md` arrived in this repository's first commit
`327cf6e` on 14 May 2026 and `LLM_TRANSCRIPT.md` in `3e3d189` the same day, so both
predate the baseline commit `520b676` of 5 September 2026 and the first hackathon
commit `e56cd7f` of 9 September 2026. `LLM_TRANSCRIPT.md` satisfies that course's own
"Requirement 15" reproducibility rule; its recorded session is dated 14 May 2026, and
neither file mentions MIRAGE or ETHOnline.

They are therefore Continuity-track evidence that the reused repository existed before
this event, not MIRAGE's AI-use disclosure. Do not read the May transcript as an
incomplete log of this submission's AI use: MIRAGE's own attribution is this document
plus [`planning/PROMPT_PROVENANCE.md`](planning/PROMPT_PROVENANCE.md), and the
completeness limits of that archive are stated there and below.

## Affected files and assets

Paths below are repository-relative. Directory patterns include their Python initialization files. Attribution concerns the MIRAGE changes, not every historical line in a reused file.

| Files / assets | AI use and limits |
| --- | --- |
| [`mirage/chain/`](../../mirage/chain/): `rpc.py`, `cache.py`, `codec.py`, `selectors.py`, `morpho.py`, `oracle.py`, `token.py`, `rates.py`, `uniswap.py` | Codex wrote/revised transport, decoding, collectors and replay validation, using the handoff's exploratory code as input and correcting its assumptions. |
| [`mirage/discovery/subgraph.py`](../../mirage/discovery/subgraph.py), [`mirage/detectors/`](../../mirage/detectors/), [`mirage/scan.py`](../../mirage/scan.py), [`mirage/verdict.py`](../../mirage/verdict.py) | Codex implemented discovery, accounting/oracle/reference/exit findings and report construction. Detector files are `phantom_volume.py`, `frozen_price.py`, `reference_price.py`, `exit_depth.py`. |
| [`mirage/bytecode.py`](../../mirage/bytecode.py), vendor initialization/provenance files | Codex integrated the unchanged upstream extractor and added bounded structural diagnostics. No new trained model is claimed. |
| [`mirage/gate.py`](../../mirage/gate.py), [`mirage/allocator.py`](../../mirage/allocator.py) | Codex wrote the entry veto and explicit scenario adapter around the existing T1 policy. |
| [`mirage/server.py`](../../mirage/server.py), [`mirage/__main__.py`](../../mirage/__main__.py), [`mirage/mcp_server.py`](../../mirage/mcp_server.py) | Codex generated the local HTTP/CLI and optional official-SDK MCP interfaces. |
| [`mirage/web/index.html`](../../mirage/web/index.html), [`style.css`](../../mirage/web/style.css), [`app.js`](../../mirage/web/app.js) | Codex generated the interface layout, styling, copy and behavior. No generated illustrative artwork or AI voiceover is part of these assets. |
| [`tests/`](../../tests/): `test_mirage_core.py`, `test_mirage_gate.py`, `test_mirage_oracle.py`, `test_mirage_uniswap.py`, `test_mirage_workbench.py`, `test_mirage_mcp.py`, `test_mirage_quote_reason.py`, `test_mirage_bytecode_metadata.py`, `test_mirage_universe.py`, `test_mirage_rederive.py` | Codex wrote the new tests, including synthetic edge cases, capture/resume behavior and replay of captured evidence across diagnostic versions. Existing `test_t1_threshold.py` is reused. |
| [`scripts/mirage_capture_demo.py`](../../scripts/mirage_capture_demo.py), [`mirage_verify_snapshot.py`](../../scripts/mirage_verify_snapshot.py), [`mirage_mcp_demo.py`](../../scripts/mirage_mcp_demo.py), [`mirage/snapshots/`](../../mirage/snapshots/), `tests/fixtures/mirage_oracle_mainnet-25937912.json` | Codex wrote capture/verification scripts, the official-SDK client example, and selected the demo manifest. RPC data were collected by tools; saved mainnet evidence is not invented model output. |
| [`scripts/mirage_capture_universe.py`](../../scripts/mirage_capture_universe.py), [`mirage_summarize_universe.py`](../../scripts/mirage_summarize_universe.py) | Codex prepared resumable capture and offline summary tools from the coordinator used for the 697-market accounting run. Checkpoints and coverage expose unfinished work; a complete collection does not imply every check passed. |
| [`scripts/mirage_rederive_snapshot.py`](../../scripts/mirage_rederive_snapshot.py) | Codex wrote the bounded offline diagnostic migration. It validates the original evidence, preserves recorded inputs and publishes a new artifact with the parent hash and exact derived-field changes. It does not collect new mainnet data. |
| [`scripts/mirage_mcp_server.py`](../../scripts/mirage_mcp_server.py) | Codex wrote the portable stdio entry point and a launch check from another working directory. It delegates to the existing MCP server and does not change its tools or evidence logic. |
| [`subgraph/subgraph.yaml`](../../subgraph/subgraph.yaml), [`schema.graphql`](../../subgraph/schema.graphql), [`src/morpho-blue.ts`](../../subgraph/src/morpho-blue.ts), [`abis/MorphoBlue.json`](../../subgraph/abis/MorphoBlue.json), package files and `.gitignore` | Earlier Claude Code assistance is reported in the supplied history. The package lock is package-manager output. Codex subsequently inspected and deployed this artifact. |
| [`subgraph/deploy.ps1`](../../subgraph/deploy.ps1), [`subgraph/README.md`](../../subgraph/README.md), [`subgraph/DEPLOYMENT.json`](../../subgraph/DEPLOYMENT.json) | Codex prepared deployment support and recorded tool-observed deployment verification. |
| [`Dockerfile.mirage`](../../Dockerfile.mirage), [`Dockerfile.mirage.dockerignore`](../../Dockerfile.mirage.dockerignore), [`render.yaml`](../../render.yaml), [`scripts/mirage_host.py`](../../scripts/mirage_host.py), [CI workflow](../../.github/workflows/mirage.yml), `requirements-mirage.txt`, `requirements-mirage-mcp.txt`, MIRAGE additions to `.gitignore` | Codex wrote product packaging, hosting configuration and focused Linux checks. Libraries remain attributed to their respective upstream projects. |
| [`README.md`](../../README.md), [`FEEDBACK.md`](../../FEEDBACK.md), [`docs/mirage/`](./), including this disclosure and [`planning/`](planning/) | Codex wrote/revised the current documentation and submission drafts. Verification JSON files summarize tool observations. The earlier README had reported Claude Code assistance and was subsequently corrected. |
| [`contracts/`](../../contracts/): [`src/MirageGate.sol`](../../contracts/src/MirageGate.sol), [`src/ExecutionGuard.sol`](../../contracts/src/ExecutionGuard.sol), [`test/MirageGate.t.sol`](../../contracts/test/MirageGate.t.sol), [`script/Deploy.s.sol`](../../contracts/script/Deploy.s.sol), `foundry.toml`; [`scripts/mirage_chainlink_publish.py`](../../scripts/mirage_chainlink_publish.py); [`CHAINLINK.md`](CHAINLINK.md) and [`CHAINLINK_FORK_REHEARSAL_2026-09-13.json`](CHAINLINK_FORK_REHEARSAL_2026-09-13.json) | Claude Code wrote the Chainlink addition on 13 September: both contracts, the 21 Foundry tests, the key-free publisher and this documentation. It also executed the deployment against a local Anvil fork of Sepolia and recorded the result; the addresses in that record are fork addresses. No private key was read, held or used, and no transaction was sent to a public network. |
| [`LICENSE`](../../LICENSE), [`mirage/vendor/revert_pro/LICENSE`](../../mirage/vendor/revert_pro/LICENSE) | Standard MIT license texts supplied with the project/upstream; not claimed as original AI-authored text. |

## Planning archive and confirmation still required

[BUILD_SPEC.md](planning/BUILD_SPEC.md) is the corrected current engineering specification. [PROMPT_PROVENANCE.md](planning/PROMPT_PROVENANCE.md) records selected exact directives, source identity and revisions. Both were prepared after implementation; neither is presented as an original pre-build artifact.

The private original handoff contains withdrawn financial claims and operational context. It is identified by hash rather than republished. These public documents are a selected, corrected disclosure, **not a complete archive of all original prompts or planning artifacts**. Historical archive completeness must be resolved with the owner and, if necessary, the organizers before asserting that the specification-disclosure requirement is satisfied.

**Owner confirmation pending:** confirm or correct the historical Claude Code attribution, the human/AI division of work in both baselines, and the concrete personal research/design/validation contributions. No manual line-by-line review, human authorship of the baselines, or independent security audit is asserted here. Eligibility remains the organizers' decision.
