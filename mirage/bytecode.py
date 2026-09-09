"""Structural bytecode diagnostics, not vulnerability inference.

The original revert.pro extractor is invoked directly. PUSH candidates below
are new MIRAGE code and never treated as proven immutables or dependencies.
"""
from functools import lru_cache
import hashlib
import importlib.metadata
import json
import re


UPSTREAM_COMMIT = "324431a514c5ebebbdbe620cb789f83ea78a231a"
UPSTREAM_SHA256 = "d12773dda40ba781441b49ea7bda9542b037237c4b7216fce175c188e365f0bd"
STRUCTURAL_FEATURES = (
    "total_instructions", "unique_instructions", "external_call_count",
    "has_external_calls", "control_flow_ops", "jumpi_count", "opcode_entropy",
    "total_calldata_ops", "arithmetic_ops_count",
)


@lru_cache(maxsize=1)
def _extractor():
    from .vendor.revert_pro.evm_extractor import EVMBytecodeFeatureExtractor
    return EVMBytecodeFeatureExtractor(n_workers=1)


def _normalize(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    if not isinstance(value, str):
        raise ValueError("Bytecode must be a hex string or bytes")
    value = value.strip()
    value = value[2:] if value.startswith("0x") else value
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2})*", value):
        raise ValueError("Malformed bytecode hex")
    return bytes.fromhex(value)


def inspect_bytecode(value: str | bytes, *, max_candidates: int = 64,
                     diagnostics_version: int = 2) -> dict:
    """Return bounded JSON-safe diagnostics and provenance for one runtime."""
    if type(max_candidates) is not int or max_candidates < 0:
        raise ValueError("max_candidates must be a nonnegative integer")
    if type(diagnostics_version) is not int or diagnostics_version not in (1, 2):
        raise ValueError("Unsupported bytecode diagnostics version")
    result = {
        "status": "unavailable", "upstream_commit": UPSTREAM_COMMIT,
        "upstream_file_sha256": UPSTREAM_SHA256, "features_extracted": False,
        "push_candidates": [], "candidate_count": 0,
        "interpretation": "Structural diagnostics only; operands are candidates, not dependencies or security findings.",
    }
    if diagnostics_version == 2:
        result["diagnostics_version"] = 2
        result["interpretation"] += " Status describes diagnostic collection, not EVM semantic validity."
    try:
        raw = _normalize(value)
    except ValueError:
        result.update(status="malformed", error="invalid_hex")
        return result
    result.update(code_length=len(raw), code_sha256=hashlib.sha256(raw).hexdigest())
    if not raw:
        result.update(status="empty", error="no_runtime_code")
        return result

    # Advance by the full operand width so bytes within PUSH data cannot become
    # opcodes. Metadata and unreachable code remain possible false candidates.
    pc, candidates, truncated = 0, [], False
    while pc < len(raw):
        opcode = raw[pc]
        size = opcode - 0x5f if 0x60 <= opcode <= 0x7f else 0
        if pc + 1 + size > len(raw):
            truncated = True
            break
        if size in (20, 32):
            operand = raw[pc + 1:pc + 1 + size]
            candidate = {"pc": pc, "opcode": f"PUSH{size}", "value_hex": "0x" + operand.hex()}
            if size == 20 or (size == 32 and not any(operand[:12])):
                candidate["address_candidate"] = "0x" + operand[-20:].hex()
            candidates.append(candidate)
        pc += 1 + size
    result.update(push_candidates=candidates[:max_candidates], candidate_count=len(candidates),
                  candidates_truncated=len(candidates) > max_candidates, truncated_push=truncated)
    if diagnostics_version == 2 and truncated:
        result.update(truncated_push_offset=pc, linear_walk_note=
                      "A linear PUSH scan can reach metadata or unreachable data; an incomplete operand does not establish malformed runtime.")
    prefix, suffix = bytes.fromhex("363d3d373d3d3d363d73"), bytes.fromhex("5af43d82803e903d91602b57fd5bf3")
    if len(raw) == 45 and raw.startswith(prefix) and raw.endswith(suffix):
        result["eip1167_implementation"] = "0x" + raw[10:30].hex()

    try:
        # Real reuse of the exact original implementation; do not call transform
        # because that creates a joblib worker pool for a single runtime.
        extracted = _extractor()._extract_features_single(raw)
        features = {key: float(value) for key, value in extracted.items()}
        result.update(
            status="malformed" if truncated and diagnostics_version == 1 else "ok", features_extracted=True,
            feature_count=len(features),
            features_sha256=hashlib.sha256(json.dumps(features, sort_keys=True, allow_nan=False).encode()).hexdigest(),
            structural_features={key: features[key] for key in STRUCTURAL_FEATURES},
            decoder_version=importlib.metadata.version("pyevmasm"),
        )
        from pyevmasm import disassemble_all
        result["decoder_invalid_opcode_count"] = sum(i.mnemonic == "INVALID" for i in disassemble_all(raw))
    except ImportError:
        result.update(error="install_requirements_mirage", status="unavailable")
    except Exception as error:
        result.update(error="extractor_failed_" + type(error).__name__, status="unavailable")
    return result
