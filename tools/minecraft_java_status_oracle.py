#!/usr/bin/env python3
"""Dependency-free Minecraft Java status oracle for disposable RDTE.

Queries the status protocol over an explicitly loopback-only QEMU host forward.
A RUNNING container or open TCP socket is not evidence of Minecraft readiness.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import socket
import sys

MAX_PACKET = 32768
MAX_TEXT = 255


class OracleFailure(RuntimeError):
    pass


class StatusVersionMismatch(OracleFailure):
    """Public-safe diagnostic for a genuine status protocol version mismatch."""

    def __init__(self, shape: str, protocol_valid: bool):
        super().__init__("server version mismatch")
        self.shape = shape
        self.protocol_valid = protocol_valid


def version_name_shape(name: object, expected: str) -> str:
    """Never return the observed string, only an enumerated relation to pinned expected."""
    if name is None:
        return "missing"
    if not isinstance(name, str):
        return "non_string"
    if name.strip() == expected:
        return "whitespace_only"
    if name.lower() == expected.lower():
        return "case_only"
    if len(name) <= 128 and expected in name:
        return "decorated_expected"
    return "other"


def encode_varint(value: int) -> bytes:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0x7FFFFFFF:
        raise OracleFailure("invalid unsigned VarInt")
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        out.append(b | (0x80 if value else 0))
        if not value:
            return bytes(out)


def decode_varint(sock: socket.socket) -> int:
    value = 0
    read_byte = getattr(sock, "recv", None) or sock.read
    for shift in range(0, 35, 7):
        raw = read_byte(1)
        if len(raw) != 1:
            raise OracleFailure("truncated VarInt")
        value |= (raw[0] & 0x7F) << shift
        if not (raw[0] & 0x80):
            if value > 0x7FFFFFFF:
                raise OracleFailure("VarInt overflow")
            return value
    raise OracleFailure("VarInt too long")


def recv_exact(sock: socket.socket, length: int) -> bytes:
    if not 0 <= length <= MAX_PACKET:
        raise OracleFailure("packet exceeds bound")
    chunks = bytearray()
    while len(chunks) < length:
        piece = sock.recv(length - len(chunks))
        if not piece:
            raise OracleFailure("truncated packet")
        chunks.extend(piece)
    return bytes(chunks)


def framed(payload: bytes) -> bytes:
    if len(payload) > MAX_PACKET:
        raise OracleFailure("outbound packet exceeds bound")
    return encode_varint(len(payload)) + payload


def query_java_status(port: int, expected_version: str, *, timeout: float = 8.0) -> dict:
    """Status is a protocol oracle, not authentication or gameplay acceptance."""
    if not 1 <= port <= 65535 or not expected_version or len(expected_version) > MAX_TEXT:
        raise OracleFailure("invalid oracle input")
    if not 0.2 <= timeout <= 20.0:
        raise OracleFailure("invalid timeout")
    host = "127.0.0.1"
    with socket.create_connection((host, port), timeout=timeout) as conn:
        conn.settimeout(timeout)
        address = host.encode("utf-8")
        # Protocol 0 is valid for status-state negotiation; server reports its
        # exact actual protocol in the response, without assuming a value here.
        handshake = (encode_varint(0) + encode_varint(0)
                     + encode_varint(len(address)) + address
                     + port.to_bytes(2, "big") + encode_varint(1))
        conn.sendall(framed(handshake) + framed(encode_varint(0)))
        size = decode_varint(conn)
        if size < 3 or size > MAX_PACKET:
            raise OracleFailure("status frame length invalid")
        payload = recv_exact(conn, size)
    from io import BytesIO
    reader = BytesIO(payload)
    if decode_varint(reader) != 0:
        raise OracleFailure("wrong status packet id")
    json_len = decode_varint(reader)
    if json_len <= 0 or json_len > MAX_PACKET or json_len != size - reader.tell():
        raise OracleFailure("status JSON length mismatch")
    try:
        response = json.loads(reader.read(json_len).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OracleFailure("malformed status JSON") from exc
    if not isinstance(response, dict):
        raise OracleFailure("status payload not an object")
    version = response.get("version")
    if not isinstance(version, dict) or version.get("name") != expected_version:
        name = version.get("name") if isinstance(version, dict) else None
        protocol_candidate = version.get("protocol") if isinstance(version, dict) else None
        raise StatusVersionMismatch(
            version_name_shape(name, expected_version),
            isinstance(protocol_candidate, int) and not isinstance(protocol_candidate, bool)
            and protocol_candidate > 0,
        )
    protocol = version.get("protocol")
    if not isinstance(protocol, int) or isinstance(protocol, bool) or protocol <= 0:
        raise OracleFailure("server protocol is absent or invalid")
    players = response.get("players")
    if not isinstance(players, dict):
        raise OracleFailure("players status absent")
    online, maximum = players.get("online"), players.get("max")
    if any(not isinstance(v, int) or isinstance(v, bool) for v in (online, maximum)):
        raise OracleFailure("players counters invalid")
    if not 0 <= online <= maximum:
        raise OracleFailure("player counter bounds invalid")
    # Avoid copying arbitrary MOTD, player identities, IPs, or server extension
    # fields to public workflow artifacts.
    return {
        "schema": "minecraft-java-status-oracle/v1",
        "classification": "SUPPORTED",
        "oracleSatisfied": True,
        "java_version": expected_version,
        "server_protocol": protocol,
        "status_packet_valid": True,
        "players_counter_valid": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True, help="loopback-forwarded disposable server port")
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = query_java_status(args.port, args.expected_version, timeout=args.timeout)
        exit_code = 0
    except (OSError, OracleFailure) as exc:
        result = {
            "schema": "minecraft-java-status-oracle/v1",
            "classification": "ORACLE_FAILURE",
            "oracleSatisfied": False,
            "failure_type": type(exc).__name__,
            "failure_reason": str(exc) if isinstance(exc, OracleFailure) else "transport failure",
            **({"version_name_shape": exc.shape,
                "version_protocol_field_valid": exc.protocol_valid}
               if isinstance(exc, StatusVersionMismatch) else {}),
        }
        exit_code = 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
