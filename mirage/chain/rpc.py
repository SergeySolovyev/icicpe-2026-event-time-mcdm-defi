"""Adapted from ETHOnline_2026/work/rpc.py: rotation, retry and aggregate3.

No JSON-RPC batching. Fixed numeric blocks, strict ABI bounds, and bounded retries.
Endpoint credentials are never included in raised errors or evidence.
"""
import json
import os
import time
import urllib.request
from dataclasses import dataclass

from .codec import decode_aggregate3, encode_aggregate3, enc_addr, hex_bytes
from .selectors import MULTICALL3

RPCS = (
    "https://eth.drpc.org", "https://gateway.tenderly.co/public/mainnet",
    "https://ethereum-rpc.publicnode.com", "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth", "https://eth.merkle.io",
)


def post_json(url: str, body: dict, *, timeout: float = 20) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "MIRAGE/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("Expected one JSON object; batches are not accepted")
    return value


@dataclass(frozen=True)
class BlockAnchor:
    chain_id: int
    number: int
    hash: str
    timestamp: int

    def __post_init__(self):
        if type(self.chain_id) is not int or self.chain_id != 1:
            raise ValueError("MIRAGE currently supports Ethereum mainnet only")
        if any(type(value) is not int or value < 0 for value in (self.number, self.timestamp)):
            raise ValueError("Block number and timestamp must be nonnegative integers")
        if len(hex_bytes(self.hash)) != 32:
            raise ValueError("Invalid block hash")


class RpcClient:
    def __init__(self, endpoints=None, *, tries: int = 6, timeout: float = 15):
        configured = os.environ.get("MIRAGE_RPC_URLS", "")
        self.endpoints = tuple(endpoints or ([s.strip() for s in configured.split(",") if s.strip()] or RPCS))
        self.tries, self.timeout, self._cursor, self._request_id = tries, timeout, 0, 0
        if not self.endpoints or tries < 1:
            raise ValueError("At least one endpoint and attempt required")

    def rpc(self, method: str, params: list):
        last = "unavailable"
        for attempt in range(self.tries):
            endpoint = self.endpoints[self._cursor % len(self.endpoints)]
            self._cursor += 1
            self._request_id += 1
            try:
                response = post_json(endpoint, {"jsonrpc": "2.0", "id": self._request_id,
                                                "method": method, "params": params}, timeout=self.timeout)
                if response.get("id") != self._request_id or response.get("jsonrpc") != "2.0":
                    raise ValueError("RPC envelope mismatch")
                if "error" in response or "result" not in response or response["result"] is None:
                    raise ValueError("RPC error/missing result")
                return response["result"]
            except Exception as error:
                last = type(error).__name__
                if attempt + 1 < self.tries:
                    time.sleep(min(0.25 * (attempt + 1), 1))
        raise RuntimeError(f"{method} failed after {self.tries} attempts ({last})")

    def anchor(self, block: int | str = "latest") -> BlockAnchor:
        chain = int(self.rpc("eth_chainId", []), 16)
        if chain != 1:
            raise ValueError("MIRAGE currently supports Ethereum mainnet only")
        tag = hex(block) if isinstance(block, int) else block
        value = self.rpc("eth_getBlockByNumber", [tag, False])
        if len(hex_bytes(value["hash"])) != 32:
            raise ValueError("Invalid block hash")
        number = int(value["number"], 16)
        if isinstance(block, int) and number != block:
            raise ValueError("Wrong RPC block")
        return BlockAnchor(chain, number, value["hash"].lower(), int(value["timestamp"], 16))

    def call(self, to: str, data: str, block: int) -> str:
        if type(block) is not int or block < 0:
            raise ValueError("eth_call requires a resolved numeric block")
        enc_addr(to)
        hex_bytes(data)
        result = self.rpc("eth_call", [{"to": to, "data": data}, hex(block)])
        hex_bytes(result)
        return result

    def code(self, to: str, block: int) -> str:
        if type(block) is not int or block < 0:
            raise ValueError("eth_getCode requires a numeric block")
        enc_addr(to)
        result = self.rpc("eth_getCode", [to, hex(block)])
        hex_bytes(result)
        return result

    def multicall(self, calls: list[tuple[str, str]], block: int, *, chunk: int = 100):
        if chunk < 1:
            raise ValueError("chunk must be positive")
        result = []
        for start in range(0, len(calls), chunk):
            part = calls[start:start + chunk]
            try:
                raw = self.call(MULTICALL3, encode_aggregate3(part), block)
                result.extend(decode_aggregate3(raw, len(part)))
            except (RuntimeError, ValueError):
                # Recover a truncated aggregate by actual single calls, never zero-fill it.
                result.extend((True, self.call(target, data, block)) for target, data in part)
        return result
