"""Optional display metadata, never a token identity or risk decision."""
from .codec import hex_bytes


def symbol(client, address, block):
    try:
        raw = hex_bytes(client.call(address, "0x95d89b41", block))
        if len(raw) == 32:
            value = raw.rstrip(b"\x00")
        elif len(raw) >= 96 and int.from_bytes(raw[:32], "big") == 32:
            length = int.from_bytes(raw[32:64], "big")
            if not 0 < length <= 64 or len(raw) < 64 + length:
                raise ValueError("Invalid symbol")
            value = raw[64:64 + length]
        else:
            raise ValueError("Unsupported symbol encoding")
        decoded = value.decode("utf-8")
        if not decoded or any(ord(char) < 32 for char in decoded):
            raise ValueError("Invalid symbol characters")
        return decoded[:64]
    except (RuntimeError, ValueError, UnicodeError):
        return address[:8] + "…"
