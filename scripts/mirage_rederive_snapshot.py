"""Re-derive versioned diagnostics from saved evidence only; never contact RPC."""
import argparse
import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from mirage.bytecode import inspect_bytecode
from mirage.chain.oracle import validate_oracle
from mirage.chain.uniswap import replay_reference
from mirage.scan import report_from_snapshot, save_snapshot


BYTECODE_FIELDS = {"diagnostics_version", "status", "interpretation",
                   "truncated_push_offset", "linear_walk_note"}
ALLOWED_PATH = re.compile(r"/rows/\d+/(?:reference/(?:quote_reason_version|quote/reason)"
                          r"|oracle/bytecode/(?:" + "|".join(sorted(BYTECODE_FIELDS)) + r"))\Z")


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def changes(before, after, path=""):
    """List exact JSON changes; absent keys are distinct from null values."""
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            pointer = path + "/" + key.replace("~", "~0").replace("/", "~1")
            if key in before and key in after:
                result.extend(changes(before[key], after[key], pointer))
            else:
                item = {"path": pointer, "before_present": key in before, "after_present": key in after}
                if key in before:
                    item["before"] = before[key]
                if key in after:
                    item["after"] = after[key]
                result.append(item)
        return result
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        return [item for index, (left, right) in enumerate(zip(before, after))
                for item in changes(left, right, path + "/" + str(index))]
    if type(before) is type(after) and before == after:
        return []
    return [{"path": path, "before_present": True, "after_present": True,
             "before": before, "after": after}]


def protected_content(snapshot):
    """All content except the explicitly permitted diagnostic explanation fields."""
    result = copy.deepcopy(snapshot)
    result.pop("derivation", None)
    for row in result["rows"]:
        reference = row.get("reference")
        if reference is not None:
            reference.pop("quote_reason_version", None)
            reference.get("quote", {}).pop("reason", None)
        bytecode = row.get("oracle", {}).get("bytecode")
        if isinstance(bytecode, dict):
            for key in BYTECODE_FIELDS:
                bytecode.pop(key, None)
    return result


def evidence_counts(snapshot):
    records, unique, runtimes, unique_codes = [], {}, [], {}
    for row in snapshot["rows"]:
        records.extend(row["evidence"])
        for component in ("reference", "oracle", "rate"):
            records.extend((row.get(component) or {}).get("evidence", []))
        runtimes.extend(row.get("oracle", {}).get("code_references", []))
    for item in records:
        key = (item["method"], item["to"].lower(), item["data"].lower(), item["block"], item["block_hash"])
        value = item["result"].lower()
        if key in unique and unique[key] != value:
            raise ValueError("Conflicting recorded results for the same anchored call")
        unique[key] = value
    for item in runtimes:
        key = (item["method"], item["to"].lower(), item["block"], item["block_hash"])
        value = (item["length"], item["sha256"])
        if key in unique_codes and unique_codes[key] != value:
            raise ValueError("Conflicting recorded bytecode for the same anchored code read")
        unique_codes[key] = value
    return {"eth_call_records": len(records), "unique_eth_call_results": len(unique),
            "runtime_code_records": len(runtimes), "unique_runtime_code_results": len(unique_codes),
            "unique_saved_rpc_results": len(unique) + len(unique_codes),
            "count_scope": "Stored eth_call and eth_getCode records across accounting/reference/oracle/rate; unique results count distinct anchored method/target/calldata identities, with conflicting duplicates rejected; block-header requests are excluded"}


def rederive_snapshot(source_path: Path, output_path: Path):
    source_path, output_path = Path(source_path).resolve(), Path(output_path).resolve()
    if output_path.exists() or source_path == output_path:
        raise FileExistsError("Output must be a new immutable snapshot path")
    original_bytes = source_path.read_bytes()
    source = json.loads(gzip.decompress(original_bytes) if source_path.suffix == ".gz" else original_bytes)
    report_from_snapshot(source)  # Validate the source before any re-derivation.
    if "derivation" in source:
        raise ValueError("This bounded migration requires an original capture, not a previous derivation")
    result = copy.deepcopy(source)
    for row in result["rows"]:
        if "reference" in row:
            row["reference"]["quote_reason_version"] = 1
            row["reference"] = replay_reference(row["reference"])
        oracle = row.get("oracle")
        if oracle is not None:
            if oracle.get("template") == "unsupported" and oracle.get("code_length"):
                oracle["bytecode"] = inspect_bytecode(oracle["runtime_code"], diagnostics_version=2)
            validate_oracle(oracle)  # Strict comparisons still cover runtime and all derivations.

    modified = changes(source, result)
    for item in modified:
        if not ALLOWED_PATH.fullmatch(item["path"]):
            raise ValueError("Unexpected changed field: " + item["path"])
    protected = encoded(protected_content(source))
    if protected != encoded(protected_content(result)):
        raise ValueError("Raw inputs or other protected content changed")
    if not modified:
        raise ValueError("No diagnostic fields require re-derivation")
    report_from_snapshot(result)
    parent_hash = hashlib.sha256(original_bytes).hexdigest()
    result["derivation"] = {
        "schema": "mirage-snapshot-derivation/1", "method": "offline-versioned-diagnostics",
        "parent_filename": source_path.name, "parent_sha256": parent_hash,
        "quote_reason_version": 1, "bytecode_diagnostics_version": 2,
        "changed_derived_fields": modified,
        "unchanged_content_sha256": hashlib.sha256(protected).hexdigest(),
        "unchanged_content_scope": "Entire snapshot except the listed diagnostic explanation fields and this provenance object",
        "recorded_evidence": evidence_counts(source), "new_network_calls": 0,
        "scope": "New derivation of the same saved returns at the same block; not a new chain capture",
    }
    if source_path.read_bytes() != original_bytes:
        raise ValueError("Source changed during re-derivation")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pending = output_path.with_name("." + output_path.name + "." + uuid.uuid4().hex + ".pending" + output_path.suffix)
    try:
        save_snapshot(pending, result)
        os.link(pending, output_path)  # Atomic publication; fails if any target already exists.
    finally:
        if pending.exists():
            pending.unlink()
    return {"output": str(output_path), "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "parent_sha256": parent_hash, "block": source["anchor"]["number"],
            "changed_derived_field_count": len(modified), "recorded_evidence": result["derivation"]["recorded_evidence"],
            "new_network_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(rederive_snapshot(args.source, args.output), indent=2))
    except Exception as error:
        print("Offline re-derivation failed (" + type(error).__name__ +
              "). Validate the source and use a new output path; existing snapshots are never overwritten.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
