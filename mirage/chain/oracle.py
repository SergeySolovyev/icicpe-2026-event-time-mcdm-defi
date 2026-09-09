"""Fixed-block oracle observations, preserving single-call evidence.

Supported template: official mainnet MorphoChainlinkOracleV2 factory members.
Getter compatibility alone does not prove a custom contract implements that code.
Reference implementation (not vendored):
https://github.com/morpho-org/morpho-blue-oracles/blob/main/src/morpho-chainlink/MorphoChainlinkOracleV2.sol
"""
from dataclasses import asdict
import hashlib

from .codec import enc_addr, hex_bytes, word_addr, words
from .rpc import BlockAnchor, RpcClient
from .selectors import FACTORY, GETTERS, PRICE
from mirage.bytecode import inspect_bytecode
from mirage.verdict import Evidence

ZERO_ADDRESS = "0x" + "00" * 20
FACTORY_MEMBERSHIP = "0x4cf4a264"
ROUND_DATA = "0xfeaf968c"
DECIMALS = "0x313ce567"
ORACLE_GETTERS = {**GETTERS, "BASE_VAULT_CONVERSION_SAMPLE": "0x054f7ac0",
                  "QUOTE_VAULT_CONVERSION_SAMPLE": "0x461739d2"}
ADDRESS_GETTERS = tuple(key for key in GETTERS if key != "SCALE_FACTOR")


def collect_oracle(client: RpcClient, address: str, anchor: BlockAnchor,
                   lookback: int = 1_000_000) -> dict:
    """Collect current/historical prices, all nine getters and feed timestamps.

Only successful RPC returns become Evidence. Failures remain explicit errors.
Code is published by byte length and SHA-256 reference to an eth_getCode call,
not as thousands of bytes embedded in every market's public finding.
"""
    enc_addr(address)
    if type(lookback) is not int or lookback <= 0:
        raise ValueError("lookback must be a positive block count")
    address = address.lower()
    result = {
        "address": address, "chain_id": anchor.chain_id, "block_number": anchor.number,
        "block_hash": anchor.hash, "timestamp": anchor.timestamp,
        "code_length": None, "code_sha256": None, "current_price": None,
        "previous_price": None, "previous_block": None, "previous_block_hash": None,
        "previous_timestamp": None, "lookback_blocks": lookback,
        "runtime_code": None, "previous_runtime_code": None,
        "anchor_verified": False, "previous_anchor_verified": None,
        "previous_code_length": None, "getters": {}, "factory": FACTORY.lower(),
        "factory_verified": None, "template": "unsupported", "bytecode": None,
        "feed_rounds": [], "evidence": [], "code_references": [], "errors": [],
    }

    def call(target, data, stamp, label):
        try:
            raw = client.call(target, data, stamp.number)
            result["evidence"].append(asdict(Evidence(target, data, stamp.number, raw, stamp.hash)))
            return raw
        except (RuntimeError, ValueError) as error:
            result["errors"].append({"check": label, "error": type(error).__name__})
            return None

    def uint(target, data, stamp, label):
        raw = call(target, data, stamp, label)
        if raw is None:
            return None
        try:
            return words(raw, 1)[0]
        except ValueError:
            result["errors"].append({"check": label, "error": "invalid_uint256_return"})
            return None

    def code(stamp):
        try:
            raw = client.code(address, stamp.number)
            data = hex_bytes(raw)
            digest = hashlib.sha256(data).hexdigest()
            result["code_references"].append({"to": address, "method": "eth_getCode", "block": stamp.number,
                                                "block_hash": stamp.hash, "length": len(data), "sha256": digest})
            return raw, len(data), digest
        except (RuntimeError, ValueError) as error:
            result["errors"].append({"check": "runtime_code", "error": type(error).__name__})
            return None, None, None

    raw_code, result["code_length"], result["code_sha256"] = code(anchor)
    result["runtime_code"] = raw_code
    if not result["code_length"]:
        return result
    current = uint(address, PRICE, anchor, "current_price")
    result["current_price"] = str(current) if current is not None else None
    member = uint(FACTORY, FACTORY_MEMBERSHIP + enc_addr(address), anchor, "factory_membership")
    if member in (0, 1):
        result["factory_verified"] = bool(member)
    elif member is not None:
        result["errors"].append({"check": "factory_membership", "error": "invalid_bool_return"})
    for name, selector in ORACLE_GETTERS.items():
        value = uint(address, selector, anchor, name)
        if value is not None:
            try:
                result["getters"][name] = word_addr(value) if name in ADDRESS_GETTERS else str(value)
            except ValueError:
                result["errors"].append({"check": name, "error": "invalid_address_padding"})

    if result["factory_verified"] is True and len(result["getters"]) == len(ORACLE_GETTERS):
        result["template"] = "morpho-chainlink-oracle-v2"
    else:
        result["bytecode"] = inspect_bytecode(raw_code)

    if anchor.number >= lookback:
        try:
            previous = client.anchor(anchor.number - lookback)
            result.update(previous_block=previous.number, previous_block_hash=previous.hash,
                          previous_timestamp=previous.timestamp)
            result["previous_runtime_code"], result["previous_code_length"], _ = code(previous)
            if result["previous_code_length"]:
                value = uint(address, PRICE, previous, "previous_price")
                result["previous_price"] = str(value) if value is not None else None
        except (RuntimeError, ValueError) as error:
            result["errors"].append({"check": "previous_anchor", "error": type(error).__name__})
    else:
        result["errors"].append({"check": "previous_anchor", "error": "lookback_precedes_genesis"})

    # Chainlink-compliant feeds may be adapters, not Chainlink-operated feeds.
    # The observation describes their reported timestamps without certifying them.
    feeds = {value for name, value in result["getters"].items()
             if "FEED" in name and value != ZERO_ADDRESS}
    for feed in sorted(feeds):
        raw = call(feed, ROUND_DATA, anchor, "feed_round")
        if raw is None:
            continue
        try:
            round_id, answer, started, updated, answered_in_round = words(raw, 5)
            if round_id >= 2**80 or answered_in_round >= 2**80:
                raise ValueError("round id exceeds uint80")
            if answer >= 2**255:
                answer -= 2**256
            result["feed_rounds"].append({"address": feed, "round_id": str(round_id),
                                          "answer": str(answer), "started_at": started,
                                          "updated_at": updated, "answered_in_round": str(answered_in_round),
                                          "age_seconds": anchor.timestamp - updated})
        except ValueError:
            result["errors"].append({"check": "feed_round", "error": "invalid_round_data"})
    # Numeric anchors fix state. Rechecking hashes detects a reorg/provider mismatch.
    try:
        final_anchor = client.anchor(anchor.number)
    except (RuntimeError, ValueError) as error:
        result["errors"].append({"check": "anchor_recheck", "error": type(error).__name__})
    else:
        if final_anchor.hash != anchor.hash:
            raise ValueError("Oracle observation block hash changed")
        result["anchor_verified"] = True
    if result["previous_block"] is not None:
        try:
            final_previous = client.anchor(result["previous_block"])
        except (RuntimeError, ValueError) as error:
            result["previous_anchor_verified"] = False
            result["errors"].append({"check": "previous_anchor_recheck", "error": type(error).__name__})
        else:
            if final_previous.hash != result["previous_block_hash"]:
                raise ValueError("Oracle historical observation block hash changed")
            result["previous_anchor_verified"] = True
    return result


def validate_oracle(observation: dict) -> dict:
    """Replay recorded RPC returns without network and reject changed derivations.

    Raw runtime is kept once in the snapshot observation, and omitted from the
    public Finding by the detector. This proves internal consistency with saved
    RPC evidence; it does not authenticate an arbitrary file as Ethereum truth.
    """
    obs = observation
    current = BlockAnchor(obs["chain_id"], obs["block_number"], obs["block_hash"], obs["timestamp"])
    anchors = {current.number: current}
    codes = {current.number: obs.get("runtime_code")}
    previous_number = obs.get("previous_block")
    if previous_number is not None:
        previous = BlockAnchor(current.chain_id, previous_number, obs["previous_block_hash"], obs["previous_timestamp"])
        if previous.number >= current.number or previous.timestamp >= current.timestamp:
            raise ValueError("Invalid historical oracle anchor ordering")
        anchors[previous.number] = previous
        codes[previous.number] = obs.get("previous_runtime_code")
    calls = {}
    for item in obs.get("evidence", []):
        proof = item if isinstance(item, Evidence) else Evidence(**item)
        enc_addr(proof.to)
        hex_bytes(proof.data)
        hex_bytes(proof.result)
        if proof.method != "eth_call" or proof.block not in anchors or proof.block_hash != anchors[proof.block].hash:
            raise ValueError("Oracle evidence does not match its recorded block anchor")
        key = (proof.to.lower(), proof.data.lower(), proof.block)
        if key in calls:
            raise ValueError("Duplicate oracle evidence call")
        calls[key] = proof.result

    class RecordedRpc:
        def __init__(self):
            self.used = set()
            self.anchor_calls = {}

        def anchor(self, number):
            self.anchor_calls[number] = self.anchor_calls.get(number, 0) + 1
            if number == current.number and obs.get("anchor_verified") is False:
                raise RuntimeError("Recorded current anchor recheck unavailable")
            if number == previous_number and self.anchor_calls[number] > 1 and obs.get("previous_anchor_verified") is False:
                raise RuntimeError("Recorded historical anchor recheck unavailable")
            if number not in anchors:
                raise RuntimeError("No recorded block header")
            return anchors[number]

        def code(self, address, number):
            if address.lower() != obs["address"].lower() or codes.get(number) is None:
                raise RuntimeError("No recorded runtime")
            return codes[number]

        def call(self, address, data, number):
            key = (address.lower(), data.lower(), number)
            if key not in calls:
                raise RuntimeError("No recorded RPC return")
            self.used.add(key)
            return calls[key]

    recorded = RecordedRpc()
    replay = collect_oracle(recorded, obs["address"], current, obs["lookback_blocks"])
    if recorded.used != calls.keys():
        raise ValueError("Oracle observation contains unused RPC evidence")
    # Error descriptions are transport diagnostics, not data. All economic and
    # classification derivations, including runtime fingerprints, are compared.
    for key in replay:
        if key not in ("errors", "evidence") and replay[key] != obs.get(key):
            raise ValueError("Oracle observation differs from its evidence: " + key)
    for key in ("loan_decimals", "collateral_decimals"):
        if key in obs:
            value = obs[key]
            if type(value) is not int or not 0 <= value <= 255:
                raise ValueError("Invalid oracle token decimals")
            replay[key] = value
    return replay
