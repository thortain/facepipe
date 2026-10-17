"""Opt-in private LAN service discovery over a small UDP request/response."""
from __future__ import annotations

import ipaddress
import json
import socket
import threading
from typing import List, Optional

from .network import is_private_ipv4, require_private_bind

DISCOVERY_PORT = 49982
QUERY = b"FACEPIPE_DISCOVER_V1"


class DiscoveryServer:
    def __init__(self, bind_host: str, *, port: int = DISCOVERY_PORT,
                 udp_port: int = 49983, tcp_port: Optional[int] = 49984,
                 capture_port: Optional[int] = None, secure_capture: bool = False) -> None:
        self.bind_host = require_private_bind(bind_host)
        self.port = port
        self._payload = json.dumps({
            "service": "FacePipe", "version": 1, "host": bind_host,
            "fmv3_udp": udp_port, "fmv3_tcp": tcp_port,
            "capture_port": capture_port, "capture_https": secure_capture,
        }, separators=(",", ":")).encode("utf-8")
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((bind_host, port))
        self._socket.settimeout(0.2)
        self._running = threading.Event()
        self._thread = None

    def start(self) -> None:
        self._running.set()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while self._running.is_set():
            try:
                data, peer = self._socket.recvfrom(128)
            except socket.timeout:
                continue
            except OSError:
                break
            if data == QUERY and is_private_ipv4(peer[0]):
                try:
                    self._socket.sendto(self._payload, peer)
                except OSError:
                    break

    def close(self) -> None:
        self._running.clear()
        self._socket.close()
        if self._thread:
            self._thread.join(timeout=1)


def discover(*, host: Optional[str] = "127.0.0.1", subnet: Optional[str] = None,
             port: int = DISCOVERY_PORT, timeout: float = 1.0) -> List[dict]:
    """Probe a private host or CIDR and return the services that answered."""
    if subnet:
        network = ipaddress.ip_network(subnet, strict=False)
        if network.version != 4 or network.num_addresses > 1024 or not all(
                is_private_ipv4(str(address)) for address in (network.network_address,
                                                               network.broadcast_address)):
            raise ValueError("subnet must be a private IPv4 network of at most 1024 addresses")
        targets = [str(address) for address in network.hosts()]
    else:
        if host is None or not is_private_ipv4(host):
            raise ValueError("discovery host must be a private IPv4 address")
        targets = [host]
    found = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        for target in targets:
            sock.sendto(QUERY, (target, port))
        import time
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            sock.settimeout(max(0.01, until - time.monotonic()))
            try:
                data, peer = sock.recvfrom(1024)
            except socket.timeout:
                break
            if not is_private_ipv4(peer[0]):
                continue
            try:
                item = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                continue
            if item.get("service") == "FacePipe" and item.get("host") == peer[0]:
                found[(peer[0], peer[1])] = item
    return list(found.values())
