"""Versioned, JSON-safe reports. Monetary raw integers are strings in the feed."""
from dataclasses import asdict, dataclass
from enum import Enum


class Severity(str, Enum):
    PASS = "pass"
    WARN = "warn"
    INSUFFICIENT = "insufficient"
    BLOCK = "block"


@dataclass(frozen=True)
class Evidence:
    to: str
    data: str
    block: int
    result: str
    block_hash: str
    method: str = "eth_call"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    summary: str
    metrics: dict
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class MarketVerdict:
    market_id: str
    block_number: int
    findings: tuple[Finding, ...]

    @property
    def severity(self) -> Severity:
        order = {Severity.PASS: 0, Severity.WARN: 1, Severity.INSUFFICIENT: 2, Severity.BLOCK: 3}
        return max((f.severity for f in self.findings), key=order.get, default=Severity.INSUFFICIENT)


@dataclass(frozen=True)
class MarketReport:
    chain_id: int
    block_number: int
    block_hash: str
    source: dict
    markets: tuple[MarketVerdict, ...]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["schema"] = "mirage-feed/1"
        result["scope"] = "accounting-checks-only; oracle and exit-depth checks pending"
        for value, verdict in zip(result["markets"], self.markets):
            value["severity"] = verdict.severity.value
        return result
