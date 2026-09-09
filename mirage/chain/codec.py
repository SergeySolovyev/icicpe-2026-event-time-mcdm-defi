"""Strict ABI subset used by Morpho and Multicall3."""
import re


def hex_bytes(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"0x(?:[0-9a-fA-F]{2})*", value):
        raise ValueError("Expected even-length, 0x-prefixed hex")
    return bytes.fromhex(value[2:])


def enc_b32(value: str) -> str:
    raw = hex_bytes(value)
    if len(raw) != 32:
        raise ValueError("Market id must be exactly 32 bytes")
    return raw.hex()


def enc_addr(value: str) -> str:
    raw = hex_bytes(value)
    if len(raw) != 20:
        raise ValueError("Address must be exactly 20 bytes")
    return raw.hex().rjust(64, "0")


def words(value: str, count: int) -> tuple[int, ...]:
    raw = hex_bytes(value)
    if len(raw) != count * 32:
        raise ValueError(f"Expected {count} ABI words, received {len(raw)} bytes")
    return tuple(int.from_bytes(raw[i:i + 32], "big") for i in range(0, len(raw), 32))


def word_addr(value: int) -> str:
    if not 0 <= value < 2**160:
        raise ValueError("Nonzero ABI address padding")
    return "0x" + value.to_bytes(20, "big").hex()


def uint_word(value: int) -> bytes:
    return value.to_bytes(32, "big")


def encode_aggregate3(calls: list[tuple[str, str]]) -> str:
    from .selectors import AGGREGATE3
    bodies, offsets, cursor = [], [], len(calls) * 32
    for target, data in calls:
        raw = hex_bytes(data)
        body = (bytes.fromhex(enc_addr(target)) + uint_word(1) + uint_word(96)
                + uint_word(len(raw)) + raw + bytes((-len(raw)) % 32))
        offsets.append(uint_word(cursor))
        bodies.append(body)
        cursor += len(body)
    return AGGREGATE3 + (uint_word(32) + uint_word(len(calls))
                         + b"".join(offsets) + b"".join(bodies)).hex()


def decode_aggregate3(value: str, expected: int) -> list[tuple[bool, str]]:
    raw = hex_bytes(value)

    def read(offset: int) -> int:
        if offset < 0 or offset % 32 or offset + 32 > len(raw):
            raise ValueError("Truncated/misaligned Multicall3 response")
        return int.from_bytes(raw[offset:offset + 32], "big")

    if len(raw) % 32 or read(0) != 32 or read(32) != expected:
        raise ValueError("Multicall3 response count/encoding mismatch")
    cursor, result = 64 + 32 * expected, []
    for index in range(expected):
        start = 64 + read(64 + index * 32)
        # aggregate3 produces canonical non-overlapping tuple tails.
        if start != cursor or read(start + 32) != 64:
            raise ValueError("Invalid Multicall3 tuple offset")
        ok, length = read(start), read(start + 64)
        if ok not in (0, 1):
            raise ValueError("Invalid ABI bool")
        end = start + 96 + length
        cursor = end + (-length) % 32
        if cursor > len(raw) or any(raw[end:cursor]):
            raise ValueError("Truncated Multicall3 bytes/padding")
        result.append((bool(ok), "0x" + raw[start + 96:end].hex()))
    if cursor != len(raw):
        raise ValueError("Unexpected Multicall3 trailing bytes")
    return result
