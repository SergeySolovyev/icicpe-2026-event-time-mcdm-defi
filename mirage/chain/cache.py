"""Request-local memoization of immutable numeric-block reads, never latest state."""
from .rpc import RpcClient


class CachingRpcClient(RpcClient):
    """Reuse successful reads at fixed blocks; bound failures to one market.

    Each instance belongs to one worker. Begin each market before collecting it
    so a transient failure does not suppress a later market's read retry.
    Pinning and final block-hash verification remain the caller's responsibility.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._read_cache = {}
        self._failed_reads = set()

    def begin_market(self):
        """Allow failed reads to retry for a new market; retain successful reads."""
        self._failed_reads.clear()

    def _read(self, kind, to, data, block):
        if type(block) is not int or block < 0:
            raise ValueError("Cache requires numeric blocks")
        key = kind, to.lower(), data.lower(), block
        if key in self._failed_reads:
            raise RuntimeError("Read unavailable earlier in this market capture")
        if key not in self._read_cache:
            try:
                self._read_cache[key] = (super().call(to, data, block) if kind == "call"
                                         else super().code(to, block))
            except (RuntimeError, ValueError):
                self._failed_reads.add(key)
                raise
        return self._read_cache[key]

    def call(self, to, data, block):
        return self._read("call", to, data, block)

    def code(self, to, block):
        return self._read("code", to, "0x", block)
