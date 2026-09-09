"""Raw Morpho Blue readers. Stored asset totals may have unaccrued interest."""
from dataclasses import dataclass

from .codec import enc_b32, words, word_addr
from .selectors import MARKET, MARKET_PARAMS, MORPHO
from .rpc import BlockAnchor, RpcClient
from mirage.verdict import Evidence


@dataclass(frozen=True)
class MarketState:
    total_supply_assets: int
    total_supply_shares: int
    total_borrow_assets: int
    total_borrow_shares: int
    last_update: int
    fee: int

    @classmethod
    def decode(cls, result: str):
        values = words(result, 6)
        if any(value >= 2**128 for value in values):
            raise ValueError("market() value exceeds uint128")
        return cls(*values)


@dataclass(frozen=True)
class MarketParams:
    loan_token: str
    collateral_token: str
    oracle: str
    irm: str
    lltv: int

    @classmethod
    def decode(cls, result: str):
        values = words(result, 5)
        return cls(*(word_addr(value) for value in values[:4]), values[4])


def read_market(client: RpcClient, market_id: str, anchor: BlockAnchor):
    """Two SINGLE calls: independently reproducible evidence for demo numbers."""
    suffix = enc_b32(market_id)
    params_raw = client.call(MORPHO, MARKET_PARAMS + suffix, anchor.number)
    state_raw = client.call(MORPHO, MARKET + suffix, anchor.number)
    evidence = tuple(Evidence(MORPHO, selector + suffix, anchor.number, raw, anchor.hash)
                     for selector, raw in ((MARKET_PARAMS, params_raw), (MARKET, state_raw)))
    return MarketParams.decode(params_raw), MarketState.decode(state_raw), evidence
