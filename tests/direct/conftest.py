"""Shared helpers for direct mode tests."""


import eth_utils


def to_hex(addr_bytes):
    """Convert address bytes to checksummed hex matching contract output."""
    if hasattr(addr_bytes, "as_hex"):
        return addr_bytes.as_hex
    return eth_utils.to_checksum_address(addr_bytes)
