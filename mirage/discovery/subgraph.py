"""Block-pinned, paginated live Graph discovery; no API monetary fields."""
import os
from dataclasses import dataclass

from mirage.chain.codec import enc_b32, hex_bytes
from mirage.chain.rpc import post_json
from mirage.chain.selectors import USDC


@dataclass(frozen=True)
class Discovery:
    market_ids: tuple[str, ...]
    source: dict


def discover_markets(block: int, *, block_hash: str | None = None,
                     url: str | None = None, page_size: int = 500) -> Discovery:
    endpoint = url or os.environ.get("MIRAGE_SUBGRAPH_URL")
    if not endpoint:
        raise ValueError("Set MIRAGE_SUBGRAPH_URL to the deployed Graph query URL")
    if type(page_size) is not int or not 1 <= page_size <= 1000:
        raise ValueError("page_size must be between 1 and 1000")
    if type(block) is not int or block < 0:
        raise ValueError("Discovery requires a numeric block")
    if block_hash is not None and len(hex_bytes(block_hash)) != 32:
        raise ValueError("Invalid discovery block hash")

    def query(text: str, variables: dict):
        try:
            response = post_json(endpoint, {"query": text, "variables": variables})
        except Exception as error:
            raise RuntimeError(f"Graph request failed ({type(error).__name__}); no fallback used") from None
        if response.get("errors") or not isinstance(response.get("data"), dict):
            raise RuntimeError("Graph query failed; no fallback used")
        return response["data"]

    def checked_meta(value):
        if (not isinstance(value, dict) or value.get("hasIndexingErrors") is not False
                or not isinstance(value.get("deployment"), str) or not value["deployment"]
                or not isinstance(value.get("block"), dict)):
            raise RuntimeError("Invalid subgraph metadata or indexing errors")
        chain_block = value["block"]
        if (type(chain_block.get("number")) is not int or chain_block["number"] < 0
                or len(hex_bytes(chain_block.get("hash"))) != 32):
            raise RuntimeError("Invalid subgraph block metadata")
        return value

    meta = checked_meta(query("{ _meta { deployment hasIndexingErrors block { number hash } } }", {}).get("_meta"))
    if meta["block"]["number"] < block:
        raise RuntimeError("Subgraph not ready at requested block or has indexing errors")
    cursor, ids, query_hash = "0x" + "00" * 32, [], None
    document = """query Markets($block: Int!, $first: Int!, $cursor: Bytes!, $loan: Bytes!) {
      _meta(block: {number: $block}) { deployment hasIndexingErrors block { number hash } }
      markets(block: {number: $block}, first: $first, orderBy: id, orderDirection: asc,
              where: {id_gt: $cursor, loanToken: $loan}) { id }
    }"""
    # Graph Node may legitimately return hash:null for historical number queries.
    # Query by the RPC-resolved finalized hash to bind both pagination and _meta.
    if block_hash is not None:
        document = document.replace("$block: Int!", "$block: Bytes!").replace("number: $block", "hash: $block")
    while True:
        data = query(document, {"block": block_hash or block, "first": page_size, "cursor": cursor, "loan": USDC})
        current = checked_meta(data.get("_meta"))
        if (current["deployment"] != meta["deployment"]
                or current["block"]["number"] != block):
            raise RuntimeError("Subgraph deployment/block changed during discovery")
        current_hash = current["block"]["hash"].lower()
        if block_hash is not None and current_hash != block_hash.lower():
            raise RuntimeError("Subgraph returned a different block hash")
        if query_hash is not None and current_hash != query_hash:
            raise RuntimeError("Subgraph block hash changed during discovery")
        query_hash = current_hash
        items = ["0x" + enc_b32(item["id"]) for item in data["markets"]]
        if items != sorted(set(items)) or any(item <= cursor for item in items):
            raise ValueError("Invalid Graph pagination order/duplicate id")
        if len(items) > page_size:
            raise ValueError("Graph page exceeds request")
        ids.extend(items)
        if len(items) < page_size:
            break
        cursor = items[-1]
    if not ids:
        raise RuntimeError("Subgraph returned no USDC markets; check deployment/topic0")
    return Discovery(tuple(ids), {"kind": "the-graph", "deployment": meta["deployment"],
                                 "indexed_block": meta["block"]["number"], "query_block": block,
                                 "query_block_hash": query_hash, "market_count": len(ids)})
