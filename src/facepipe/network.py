"""Network boundary checks shared by FacePipe listeners."""
from __future__ import annotations

import ipaddress


_PRIVATE_RANGES = tuple(ipaddress.ip_network(value) for value in (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
    "100.64.0.0/10",
))


def is_private_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return bool(address.version == 4 and
                any(address in network for network in _PRIVATE_RANGES))


def require_private_bind(value: str) -> str:
    if not is_private_ipv4(value):
        raise ValueError("bind address must be a loopback, private LAN, or private VPN IPv4 address")
    return value
