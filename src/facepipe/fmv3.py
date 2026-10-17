"""Face Motion v3 (FMV3) - the binary protocol used by iFacialMocap 1.5.3+,
iFacialMocapTr 1.2.6+ and Facemotion3d 1.4.6+.

Contract revision 6. Little-endian, no padding.

Every message is a 40-byte header followed by a payload.

    magic          4s  b"FMV3"
    message_type   B   1 HELLO, 2 SCHEMA, 3 SCHEMA_ACK, 4 FRAME, 5 GET_SCHEMA,
                       6 PING, 7 PONG, 8 STOP, 9 ERROR
    flags          B   FRAME only: bit0 = tracking, bit1 = playback
    header_size    H   40
    session_id     Q
    schema_id      I
    sequence       I
    source_token   I   FRAME only
    total_payload  I   full payload length before fragmentation
    part_index     H
    part_count     H
    chunk_length   I

Ports: iOS listens on UDP 49983 / TCP 49984. The receiver (PC) listens on the
same numbers for a "manual start" where the phone connects to the PC.

Reference specification:
https://github.com/emoto-yasushi/iFacialMocap_Facemotion3d_udp-tcp_v3
"""
from __future__ import annotations

import math
import queue
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .blendshapes import IDENTIFIERS
from .frame import Frame
from .network import require_private_bind

MAGIC = b"FMV3"
HEADER_FORMAT = "<4sBBHQIIIIHHI"
HEADER_SIZE = 40
CONTRACT_REVISION = 6

HELLO, SCHEMA, SCHEMA_ACK, FRAME, GET_SCHEMA, PING, PONG, STOP, ERROR = range(1, 10)

MODE_VARIABLE = 0
MODE_FIXED52 = 1
ENC_I16 = 1
ENC_I32 = 2

MIN_UDP_SIZE = 576
MAX_UDP_SIZE = 1200
SCHEMA_UDP_SIZE = 576
SCHEMA_CAPACITY = SCHEMA_UDP_SIZE - HEADER_SIZE          # 536
LEASE_MS = 10_000

IOS_UDP_PORT = 49983
IOS_TCP_PORT = 49984

START_INFO = struct.Struct("<QHHII")
DESCRIPTOR = struct.Struct("<HBBH")
HELLO_BODY = struct.Struct("<HHIH")
POSE = struct.Struct("<12f")


# --------------------------------------------------------------------------- #
# header
# --------------------------------------------------------------------------- #
@dataclass
class Header:
    message_type: int
    flags: int = 0
    session_id: int = 0
    schema_id: int = 0
    sequence: int = 0
    source_token: int = 0
    total_payload_length: int = 0
    part_index: int = 0
    part_count: int = 1
    chunk_length: int = 0

    def pack(self) -> bytes:
        return struct.pack(
            HEADER_FORMAT, MAGIC, self.message_type, self.flags, HEADER_SIZE,
            self.session_id & 0xFFFFFFFFFFFFFFFF, self.schema_id & 0xFFFFFFFF,
            self.sequence & 0xFFFFFFFF, self.source_token & 0xFFFFFFFF,
            self.total_payload_length & 0xFFFFFFFF, self.part_index & 0xFFFF,
            self.part_count & 0xFFFF, self.chunk_length & 0xFFFFFFFF,
        )

    @classmethod
    def unpack(cls, data: bytes) -> Header:
        magic, mtype, flags, hsize, session, schema, seq, token, total, pidx, pcount, chunk = \
            struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
        if magic != MAGIC or hsize != HEADER_SIZE:
            raise ValueError("not an FMV3 message")
        return Header(mtype, flags, session, schema, seq, token, total, pidx, pcount, chunk)


def build_message(message_type: int, payload: bytes, *, session_id: int,
                  schema_id: int = 0, sequence: int = 0, flags: int = 0,
                  source_token: int = 0, part_index: int = 0, part_count: int = 1,
                  total_payload_length: Optional[int] = None) -> bytes:
    total = len(payload) if total_payload_length is None else total_payload_length
    header = Header(message_type, flags, session_id, schema_id, sequence,
                    source_token, total, part_index, part_count, len(payload))
    return header.pack() + payload


def is_valid_header(header: Header) -> bool:
    return 1 <= header.message_type <= 9 and header.session_id != 0


# --------------------------------------------------------------------------- #
# schema
# --------------------------------------------------------------------------- #
@dataclass
class Schema:
    client_nonce: int = 0
    actual_fps: int = 60
    max_udp_size: int = MAX_UDP_SIZE
    lease_ms: int = LEASE_MS
    contract_revision: int = CONTRACT_REVISION
    mode: int = MODE_VARIABLE
    blend_encoding: int = ENC_I16
    schema_format_version: int = 1
    blend_count: int = 0
    app: str = "FacePipe"
    profile: str = "facepipe"
    blend_names: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_fixed52(self) -> bool:
        return self.mode == MODE_FIXED52

    def index_by_name(self) -> dict:
        return {name: i for i, name in enumerate(self.blend_names)}

    def body(self) -> bytes:
        start = START_INFO.pack(self.client_nonce, self.actual_fps, self.max_udp_size,
                                self.lease_ms, self.contract_revision)
        desc = DESCRIPTOR.pack(self.mode, self.blend_encoding,
                               self.schema_format_version, self.blend_count)
        if self.mode == MODE_VARIABLE:
            names = b"".join(len(n.encode("utf-8")).to_bytes(1, "little") + n.encode("utf-8")
                             for n in self.blend_names)
            strings = (len(self.app.encode("utf-8")).to_bytes(2, "little") + self.app.encode("utf-8")
                       + len(self.profile.encode("utf-8")).to_bytes(2, "little")
                       + self.profile.encode("utf-8") + names)
        else:
            strings = b""
        return start + desc + strings

    @classmethod
    def from_body(cls, body: bytes) -> Schema:
        if len(body) < 26:
            raise ValueError("SCHEMA body too short")
        nonce, fps, udp, lease, revision = START_INFO.unpack(body[:20])
        mode, encoding, version, count = DESCRIPTOR.unpack(body[20:26])
        if version != 1:
            raise ValueError(f"unsupported schema_format_version {version}")
        schema = cls(client_nonce=nonce, actual_fps=fps, max_udp_size=udp, lease_ms=lease,
                    contract_revision=revision, mode=mode, blend_encoding=encoding,
                    schema_format_version=version, blend_count=count)
        if mode == MODE_VARIABLE:
            pos = 26
            app_len = int.from_bytes(body[pos:pos + 2], "little"); pos += 2
            schema.app = body[pos:pos + app_len].decode("utf-8"); pos += app_len
            prof_len = int.from_bytes(body[pos:pos + 2], "little"); pos += 2
            schema.profile = body[pos:pos + prof_len].decode("utf-8"); pos += prof_len
            names: List[str] = []
            for _ in range(count):
                nlen = body[pos]; pos += 1
                names.append(body[pos:pos + nlen].decode("utf-8")); pos += nlen
            if pos != len(body):
                raise ValueError("trailing bytes in SCHEMA body")
            schema.blend_names = tuple(names)
        elif len(body) != 26:
            raise ValueError("fixed52 SCHEMA body must be exactly 26 bytes")
        else:
            schema.blend_names = IDENTIFIERS
        return schema


def fragment(payload: bytes, capacity: int) -> List[bytes]:
    """Split a payload into fragments of at most `capacity` bytes."""
    capacity = max(1, capacity)
    count = max(1, math.ceil(len(payload) / capacity))
    return [payload[i * capacity:(i + 1) * capacity] for i in range(count)]


class FragmentAssembler:
    """Reassemble fragmented payloads keyed by (session_id, schema_id, message_type)."""

    def __init__(self, timeout: float = 3.0) -> None:
        self.parts = {}
        self.timeout = timeout

    def feed(self, header: Header, payload: bytes) -> Optional[Tuple[Header, bytes]]:
        key = (header.session_id, header.schema_id, header.message_type)
        now = time.time()
        if header.part_count == 1:
            self.parts.pop(key, None)
            return header, payload
        entry = self.parts.setdefault(key, {"parts": {}, "total": header.total_payload_length,
                                           "count": header.part_count, "seen": 0, "time": now})
        if entry["total"] != header.total_payload_length or entry["count"] != header.part_count:
            del self.parts[key]
            return None
        if header.part_index in entry["parts"]:
            if entry["parts"][header.part_index] != payload:
                del self.parts[key]
                return None
        else:
            entry["parts"][header.part_index] = payload
            entry["seen"] += 1
        if entry["seen"] == entry["count"]:
            body = b"".join(entry["parts"][i] for i in range(entry["count"]))
            del self.parts[key]
            return header, body
        if now - entry["time"] > self.timeout:
            del self.parts[key]
        return None


# --------------------------------------------------------------------------- #
# frame
# --------------------------------------------------------------------------- #
def encode_frame_body(frame: Frame, schema: Schema) -> bytes:
    values = []
    for name in schema.blend_names:
        percent = int(round(frame.blendshapes.get(name, 0.0) * 100))
        values.append(percent)
    if schema.blend_encoding == ENC_I16:
        body = b"".join(struct.pack("<h", max(-32768, min(32767, v))) for v in values)
    else:
        body = b"".join(struct.pack("<i", v) for v in values)
    head = frame.head + (0.0, 0.0, 0.0)
    body += POSE.pack(*head[:6], *frame.right_eye, *frame.left_eye)
    return body


def decode_frame_body(body: bytes, schema: Schema) -> Frame:
    fmt = "h" if schema.blend_encoding == ENC_I16 else "i"
    size = 2 if schema.blend_encoding == ENC_I16 else 4
    expected = size * schema.blend_count + 48
    if len(body) != expected:
        raise ValueError(f"FRAME body {len(body)} bytes, expected {expected}")
    values = struct.unpack(f"<{schema.blend_count}{fmt}", body[:size * schema.blend_count])
    pose = POSE.unpack(body[size * schema.blend_count:])
    blend = {name: v / 100.0 for name, v in zip(schema.blend_names, values)}
    return Frame(blendshapes=blend, head=pose[:6], right_eye=pose[6:9], left_eye=pose[9:12])


# --------------------------------------------------------------------------- #
# sender  (behaves like the iOS app: a PC receiver connects to us)
# --------------------------------------------------------------------------- #
class FMV3Sender:
    """Serve FMV3 frames over UDP (and optionally TCP) as if we were the iPhone."""

    def __init__(self, *, udp_port: int = IOS_UDP_PORT, tcp_port: Optional[int] = IOS_TCP_PORT,
                 fps: int = 60, mode: int = MODE_FIXED52, blend_names: Sequence[str] = IDENTIFIERS,
                 app: str = "FacePipe", profile: str = "facepipe", source_token: int = 0,
                 bind_host: str = "127.0.0.1", max_clients: int = 32) -> None:
        self.bind_host = require_private_bind(bind_host)
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.max_clients = max_clients
        self.fps = max(1, min(60, fps))
        self.mode = mode
        self.blend_names = tuple(blend_names)
        self.app = app
        self.profile = profile
        self.source_token = source_token
        self.session_id = 0
        self.schema_id = 1
        self.sequence = 0
        self.running = threading.Event()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((bind_host, udp_port))
        self._sock.settimeout(0.2)
        self._peers = {}          # (ip, port) -> session state
        self._lock = threading.Lock()
        self._tcp_server = None
        if tcp_port:
            self._tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._tcp_server.bind((bind_host, tcp_port))
            self._tcp_server.listen(5)
            self._tcp_server.settimeout(0.2)

    def _schema_body(self, client_nonce: int, actual_fps: int, max_udp_size: int) -> bytes:
        schema = Schema(client_nonce=client_nonce, actual_fps=actual_fps,
                        max_udp_size=max_udp_size, lease_ms=LEASE_MS,
                        contract_revision=CONTRACT_REVISION, mode=self.mode,
                        blend_encoding=ENC_I32 if self.mode == MODE_FIXED52 else ENC_I16,
                        blend_count=len(self.blend_names), app=self.app,
                        profile=self.profile, blend_names=self.blend_names)
        return schema.body()

    def _send_schema(self, peer, session_id: int, body: bytes) -> None:
        parts = fragment(body, SCHEMA_CAPACITY)
        for i, part in enumerate(parts):
            self._send(peer, SCHEMA, session_id, part, schema_id=self.schema_id,
                       part_index=i, part_count=len(parts),
                       total_payload_length=len(body))

    def _send(self, peer, message_type: int, session_id: int, payload: bytes = b"",
              schema_id: int = 0, sequence: int = 0, flags: int = 0,
              source_token: int = 0, part_index: int = 0, part_count: int = 1,
              total_payload_length: Optional[int] = None, send_lock=None) -> None:
        msg = build_message(message_type, payload, session_id=session_id, schema_id=schema_id,
                            sequence=sequence, flags=flags, source_token=source_token,
                            part_index=part_index, part_count=part_count,
                            total_payload_length=total_payload_length)
        if isinstance(peer, socket.socket):
            if send_lock is None:
                peer.sendall(msg)
            else:
                with send_lock:
                    peer.sendall(msg)
        else:
            self._sock.sendto(msg, peer)

    def _drop_peer(self, peer, expected=None) -> None:
        with self._lock:
            state = self._peers.get(peer)
            if state is None or (expected is not None and state is not expected):
                return
            del self._peers[peer]
        state["stop"].set()
        if isinstance(peer, socket.socket):
            try:
                peer.close()
            except OSError:
                pass

    def _add_peer(self, peer, state: dict) -> bool:
        state["queue"] = queue.Queue(maxsize=2)
        state["stop"] = threading.Event()
        state["send_lock"] = threading.Lock()
        state["last_seen"] = time.monotonic()
        with self._lock:
            if peer not in self._peers and len(self._peers) >= self.max_clients:
                return False
            previous = self._peers.get(peer)
            self._peers[peer] = state
        if previous:
            previous["stop"].set()
        threading.Thread(target=self._peer_worker, args=(peer, state), daemon=True).start()
        return True

    def _prune_peers(self) -> None:
        now = time.monotonic()
        with self._lock:
            stale = [(peer, state) for peer, state in self._peers.items()
                     if now - state["last_seen"] > LEASE_MS / 1000]
        for peer, state in stale:
            self._drop_peer(peer, state)

    def _peer_worker(self, peer, state: dict) -> None:
        interval = 1.0 / state["schema"].actual_fps
        next_send = time.monotonic()
        while self.running.is_set() and not state["stop"].is_set():
            try:
                frame, sequence = state["queue"].get(timeout=0.2)
            except queue.Empty:
                continue
            delay = next_send - time.monotonic()
            if delay > 0 and state["stop"].wait(delay):
                break
            # A slow peer receives the freshest frame, without delaying other peers.
            try:
                while True:
                    frame, sequence = state["queue"].get_nowait()
            except queue.Empty:
                pass
            if time.monotonic() - state["last_seen"] > LEASE_MS / 1000:
                self._drop_peer(peer, state)
                break
            try:
                body = encode_frame_body(frame, state["schema"])
                parts = (fragment(body, state["max_udp_size"] - HEADER_SIZE)
                         if isinstance(peer, tuple) else [body])
                for index, part in enumerate(parts):
                    self._send(peer, FRAME, state["session_id"], part,
                               schema_id=self.schema_id, sequence=sequence,
                               flags=1 if frame.tracking else 0,
                               source_token=self.source_token,
                               part_index=index, part_count=len(parts),
                               total_payload_length=len(body),
                               send_lock=state["send_lock"])
            except (OSError, ValueError, struct.error):
                self._drop_peer(peer, state)
                break
            next_send = max(next_send + interval, time.monotonic())

    def push(self, frame: Frame) -> int:
        """Queue the latest frame independently for every acknowledged peer."""
        self._prune_peers()
        with self._lock:
            peers = list(self._peers.items())
        served = 0
        for peer, state in peers:
            if not state.get("acknowledged") or state["stop"].is_set():
                continue
            item = (frame, self.sequence)
            try:
                state["queue"].put_nowait(item)
            except queue.Full:
                try:
                    state["queue"].get_nowait()
                except queue.Empty:
                    pass
                try:
                    state["queue"].put_nowait(item)
                except queue.Full:
                    pass
            served += 1
        self.sequence += 1
        return served

    def run(self, frame_source, *, duration: Optional[float] = None) -> None:
        """Serve frames from `frame_source` (an iterator of Frame) until stopped."""
        self.running.set()
        start = time.time()
        interval = 1.0 / self.fps
        next_tick = time.time()
        for frame in frame_source:
            if not self.running.is_set():
                break
            self.push(frame)
            next_tick += interval
            delay = next_tick - time.time()
            if delay > 0:
                time.sleep(delay)
            if duration and time.time() - start > duration:
                break

    def stop(self) -> None:
        self.running.clear()
        with self._lock:
            peers = list(self._peers.items())
        for peer, state in peers:
            self._drop_peer(peer, state)
        self._sock.close()
        if self._tcp_server:
            self._tcp_server.close()

    def _handle_udp(self) -> None:
        while self.running.is_set():
            try:
                data, peer = self._sock.recvfrom(2048)
            except socket.timeout:
                self._prune_peers()
                continue
            except OSError:
                break
            if len(data) < HEADER_SIZE:
                continue
            try:
                header = Header.unpack(data)
            except ValueError:
                continue
            if not is_valid_header(header):
                continue
            payload = data[HEADER_SIZE:]
            if header.chunk_length != len(payload) or header.part_count != 1:
                continue
            if header.message_type == HELLO:
                if len(payload) != 10:
                    continue
                fps, udp_size, revision, mode = HELLO_BODY.unpack(payload)
                if revision != CONTRACT_REVISION:
                    self._send(peer, ERROR, header.session_id,
                               f"UNSUPPORTED_CONTRACT: requires {CONTRACT_REVISION}".encode())
                    continue
                if mode not in (MODE_VARIABLE, MODE_FIXED52):
                    self._send(peer, ERROR, header.session_id, b"UNSUPPORTED_MODE")
                    continue
                with self._lock:
                    existing = self._peers.get(peer)
                    if existing and existing["session_id"] == header.session_id:
                        # same HELLO repeated: resend the schema, keep the session alive
                        existing["last_seen"] = time.monotonic()
                        self._send_schema(peer, header.session_id, existing["schema"].body())
                        continue
                actual_fps = max(1, min(self.fps, fps or self.fps))
                max_udp = max(MIN_UDP_SIZE, min(MAX_UDP_SIZE, udp_size or MAX_UDP_SIZE))
                schema = Schema(client_nonce=header.session_id, actual_fps=actual_fps,
                                max_udp_size=max_udp, lease_ms=LEASE_MS,
                                contract_revision=CONTRACT_REVISION, mode=mode,
                                blend_encoding=ENC_I32 if mode == MODE_FIXED52 else ENC_I16,
                                blend_count=len(self.blend_names), app=self.app,
                                profile=self.profile, blend_names=self.blend_names)
                if not self._add_peer(peer, {"session_id": header.session_id,
                                             "schema": schema, "max_udp_size": max_udp,
                                             "acknowledged": False}):
                    self._send(peer, ERROR, header.session_id, b"BUSY")
                    continue
                self._send_schema(peer, header.session_id, schema.body())
            elif header.message_type == SCHEMA_ACK:
                with self._lock:
                    state = self._peers.get(peer)
                    if state and header.session_id == state["session_id"] \
                            and header.schema_id == self.schema_id:
                        state["acknowledged"] = True
                        state["last_seen"] = time.monotonic()
            elif header.message_type == PING:
                with self._lock:
                    state = self._peers.get(peer)
                    if state and header.session_id == state["session_id"]:
                        state["last_seen"] = time.monotonic()
                    else:
                        state = None
                if state:
                    self._send(peer, PONG, header.session_id, sequence=header.sequence)
            elif header.message_type == STOP:
                with self._lock:
                    state = self._peers.get(peer)
                if state and state["session_id"] == header.session_id:
                    self._drop_peer(peer, state)
            elif header.message_type == GET_SCHEMA:
                with self._lock:
                    state = self._peers.get(peer)
                if state and state["session_id"] == header.session_id:
                    self._send_schema(peer, state["session_id"], state["schema"].body())

    def _handle_tcp(self) -> None:
        while self.running.is_set():
            try:
                conn, _ = self._tcp_server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._tcp_connection, args=(conn,), daemon=True).start()

    def _tcp_connection(self, conn: socket.socket) -> None:
        buffer = b""
        state = None
        conn.settimeout(0.5)
        try:
            while self.running.is_set():
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer += chunk
                while len(buffer) >= HEADER_SIZE:
                    try:
                        header = Header.unpack(buffer[:HEADER_SIZE])
                    except ValueError:
                        return
                    if not is_valid_header(header) or header.chunk_length > 65536:
                        return
                    need = HEADER_SIZE + header.chunk_length
                    if len(buffer) < need:
                        break
                    payload = buffer[HEADER_SIZE:need]
                    buffer = buffer[need:]
                    if header.message_type == HELLO:
                        if state is not None or len(payload) != HELLO_BODY.size:
                            return
                        fps, udp_size, revision, mode = HELLO_BODY.unpack(payload)
                        if revision != CONTRACT_REVISION or mode not in (MODE_VARIABLE, MODE_FIXED52):
                            self._send(conn, ERROR, header.session_id, b"UNSUPPORTED_CONTRACT_OR_MODE")
                            return
                        schema = Schema(client_nonce=header.session_id,
                                        actual_fps=max(1, min(self.fps, fps or self.fps)),
                                        max_udp_size=max_udp_size(udp_size), lease_ms=LEASE_MS,
                                        mode=mode, blend_encoding=ENC_I32 if mode == MODE_FIXED52 else ENC_I16,
                                        blend_count=len(self.blend_names), app=self.app,
                                        profile=self.profile, blend_names=self.blend_names)
                        state = {"session_id": header.session_id, "schema": schema,
                                 "max_udp_size": max_udp_size(udp_size),
                                 "acknowledged": False}
                        if not self._add_peer(conn, state):
                            self._send(conn, ERROR, header.session_id, b"BUSY")
                            return
                        self._send(conn, SCHEMA, state["session_id"], schema.body(),
                                   schema_id=self.schema_id, send_lock=state["send_lock"])
                        state["acknowledged"] = True
                    elif header.message_type == PING:
                        if state and header.session_id == state["session_id"]:
                            state["last_seen"] = time.monotonic()
                            self._send(conn, PONG, state["session_id"],
                                       sequence=header.sequence, send_lock=state["send_lock"])
                    elif header.message_type == STOP:
                        return
        except OSError:
            pass
        finally:
            self._drop_peer(conn, state)
            try:
                conn.close()
            except OSError:
                pass

    def start(self) -> None:
        self.running.set()
        threading.Thread(target=self._handle_udp, daemon=True).start()
        if self._tcp_server:
            threading.Thread(target=self._handle_tcp, daemon=True).start()


def max_udp_size(value) -> int:
    try:
        return max(MIN_UDP_SIZE, min(MAX_UDP_SIZE, int(value)))
    except (TypeError, ValueError):
        return MAX_UDP_SIZE


# --------------------------------------------------------------------------- #
# receiver  (behaves like the PC side: we connect to an iPhone)
# --------------------------------------------------------------------------- #
class FMV3Receiver:
    """Connect to an iFacialMocap / Facemotion3d app and decode its frames."""

    def __init__(self, host: str, *, port: int = IOS_UDP_PORT, pc_port: Optional[int] = None,
                 transport: str = "udp", mode: int = MODE_FIXED52, fps: int = 60,
                 bind_host: str = "127.0.0.1") -> None:
        self.host = host
        self.port = port
        self.pc_port = pc_port if pc_port is not None else port
        self.bind_host = require_private_bind(bind_host)
        self.transport = transport
        self.mode = mode
        self.fps = fps
        self.client_nonce = int.from_bytes(b"\x00" * 8, "big")  # set by new_nonce()
        self.running = threading.Event()
        self.schema: Optional[Schema] = None
        self.last_sequence = 0
        self.frames_received = 0

    def new_nonce(self) -> int:
        import secrets
        self.client_nonce = secrets.randbelow(2**64 - 1) + 1
        return self.client_nonce

    def hello(self) -> bytes:
        body = HELLO_BODY.pack(self.fps, MAX_UDP_SIZE, CONTRACT_REVISION, self.mode)
        return build_message(HELLO, body, session_id=self.client_nonce)

    def run(self, on_frame, *, duration: Optional[float] = None) -> int:
        self.running.set()
        start = time.time()
        if self.transport == "udp":
            return self._run_udp(on_frame, start, duration)
        return self._run_tcp(on_frame, start, duration)

    def _run_udp(self, on_frame, start: float, duration: Optional[float]) -> int:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.bind_host, self.pc_port))
        sock.settimeout(0.2)
        assembler = FragmentAssembler()
        last_ping = time.time()
        last_hello = 0.0
        hello_sent = False
        self.new_nonce()
        try:
            while self.running.is_set() and (duration is None or time.time() - start < duration):
                now = time.time()
                if not hello_sent or (self.schema is None and now - last_hello > 1.0):
                    sock.sendto(self.hello(), (self.host, self.port))
                    hello_sent = True
                    last_hello = now
                try:
                    data, peer = sock.recvfrom(2048)
                except socket.timeout:
                    pass
                else:
                    if len(data) >= HEADER_SIZE:
                        header = Header.unpack(data)
                        if is_valid_header(header):
                            result = assembler.feed(header, data[HEADER_SIZE:])
                            if result is not None:
                                header, body = result
                                if header.message_type == SCHEMA:
                                    self.schema = Schema.from_body(body)
                                    sock.sendto(build_message(SCHEMA_ACK, b"",
                                                             session_id=header.session_id,
                                                             schema_id=header.schema_id), peer)
                                elif header.message_type == FRAME and self.schema:
                                    frame = decode_frame_body(body, self.schema)
                                    frame.tracking = bool(header.flags & 1)
                                    self.frames_received += 1
                                    on_frame(frame)
                                elif header.message_type == ERROR:
                                    print(f"FMV3 error from device: "
                                          f"{body.decode('utf-8', 'replace')}")
                if time.time() - last_ping > 3.0:
                    sock.sendto(build_message(PING, b"", session_id=self.client_nonce),
                                (self.host, self.port))
                    last_ping = time.time()
        finally:
            sock.sendto(build_message(STOP, b"", session_id=self.client_nonce), (self.host, self.port))
            sock.close()
        return self.frames_received

    def _run_tcp(self, on_frame, start: float, duration: Optional[float]) -> int:
        conn = socket.create_connection((self.host, self.port), timeout=5)
        self.new_nonce()
        conn.sendall(self.hello())
        buffer = b""
        last_ping = time.time()
        try:
            while self.running.is_set() and (duration is None or time.time() - start < duration):
                try:
                    buffer += conn.recv(4096)
                except socket.timeout:
                    continue
                while len(buffer) >= HEADER_SIZE:
                    header = Header.unpack(buffer[:HEADER_SIZE])
                    need = HEADER_SIZE + header.chunk_length
                    if len(buffer) < need:
                        break
                    body = buffer[HEADER_SIZE:need]
                    buffer = buffer[need:]
                    if header.message_type == SCHEMA:
                        self.schema = Schema.from_body(body)
                    elif header.message_type == FRAME and self.schema:
                        frame = decode_frame_body(body, self.schema)
                        frame.tracking = bool(header.flags & 1)
                        self.frames_received += 1
                        on_frame(frame)
                if time.time() - last_ping > 3.0:
                    conn.sendall(build_message(PING, b"", session_id=self.client_nonce))
                    last_ping = time.time()
        finally:
            conn.sendall(build_message(STOP, b"", session_id=self.client_nonce))
            conn.close()
        return self.frames_received

    def stop(self) -> None:
        self.running.clear()
