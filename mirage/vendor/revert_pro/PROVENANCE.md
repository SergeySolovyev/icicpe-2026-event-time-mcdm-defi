# revert.pro source reused by MIRAGE

- Repository: https://github.com/SergeySolovyev/smart-contract-vuln-detection-from-bytecode
  (formerly `icicpe-2026-defi-vuln-detection`; the old path still resolves
  through GitHub's rename redirect, but cite the canonical name above)
- Commit: `324431a514c5ebebbdbe620cb789f83ea78a231a`
- Source: `features/evm_extractor.py`
- SHA-256 of the exact vendored bytes: `d12773dda40ba781441b49ea7bda9542b037237c4b7216fce175c188e365f0bd`
- Copied on 2026-09-09 from the clean source file at that commit. The file is
  unmodified, including line endings. The upstream MIT license is alongside it.

`mirage.bytecode.inspect_bytecode` directly calls
`EVMBytecodeFeatureExtractor(n_workers=1)._extract_features_single(runtime)`.
No model weights, model inference, vulnerability labels, or security scores are
used. MIRAGE exposes a small structural subset of the 70 extracted features and
a digest of the full feature output. The upstream heuristic columns whose names
contain "risk" or "vulnerability" are not security conclusions and are not
published in MIRAGE findings.

MIRAGE's instruction-boundary walk and PUSH operand candidate extraction are new
code. PUSH operands can be constants, masks, metadata, or unreachable data; an
address-shaped operand does not establish a called dependency. Exact EIP-1167
runtime recognition identifies the proxy implementation embedded in that
standard runtime, but does not establish the implementation's behavior.

The stock pyevmasm 0.2.3 decoder predates newer EVM opcodes. MIRAGE exposes its
version and invalid-opcode count, and does not use its output to certify oracle
correctness. Empty/malformed input and missing dependencies are explicit states,
never a zero-feature "safe" result.
