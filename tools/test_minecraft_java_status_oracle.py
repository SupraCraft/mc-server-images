#!/usr/bin/env python3
"""Offline loopback-only protocol falsification for the Java status oracle."""
import importlib.util
import json
import pathlib
import socket
import threading
import unittest

P = pathlib.Path(__file__).with_name("minecraft_java_status_oracle.py")
spec = importlib.util.spec_from_file_location("minecraft_java_status_oracle", P)
oracle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(oracle)


class FakeServer:
    def __init__(self, payload):
        self.payload = payload
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.error = None

    def __enter__(self):
        def serve():
            try:
                conn, _ = self.sock.accept()
                with conn:
                    conn.settimeout(3)
                    first_length = oracle.decode_varint(conn)
                    handshake = oracle.recv_exact(conn, first_length)
                    if handshake[0] != 0:
                        raise ValueError("missing handshake")
                    request_length = oracle.decode_varint(conn)
                    if oracle.recv_exact(conn, request_length) != b"\x00":
                        raise ValueError("missing status request")
                    conn.sendall(self.payload)
            except Exception as exc:
                self.error = exc
            finally:
                self.sock.close()
        self.thread = threading.Thread(target=serve, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.thread.join(timeout=4)
        if self.error is not None:
            raise self.error


def status_frame(version="1.21.11", protocol=774, *, online=0, maximum=10):
    body = json.dumps({
        "version": {"name": version, "protocol": protocol},
        "players": {"online": online, "max": maximum},
        "description": {"text": "public synthetic test only"},
    }).encode()
    payload = b"\x00" + oracle.encode_varint(len(body)) + body
    return oracle.framed(payload)


class TestStatusOracle(unittest.TestCase):
    def test_varint_boundary(self):
        for n in (0, 1, 127, 128, 255, 32767, 0x7FFFFFFF):
            encoded = oracle.encode_varint(n)
            self.assertEqual(oracle.decode_varint(_Reader(encoded)), n)

    def test_varint_rejects_negative_and_overflow(self):
        for n in (-1, 0x80000000, True):
            with self.assertRaises(oracle.OracleFailure):
                oracle.encode_varint(n)
        for blob in (b"\x80", b"\x80\x80\x80\x80\x80\x00"):
            with self.assertRaises(oracle.OracleFailure):
                oracle.decode_varint(_Reader(blob))

    def test_real_status_negotiation(self):
        with FakeServer(status_frame()) as server:
            result = oracle.query_java_status(server.port, "1.21.11")
        self.assertTrue(result["oracleSatisfied"])
        self.assertEqual(result["server_protocol"], 774)
        self.assertNotIn("description", result)
        self.assertNotIn("players", result)

    def test_wrong_version_refused(self):
        with FakeServer(status_frame(version="1.21.10")) as server:
            with self.assertRaisesRegex(oracle.OracleFailure, "version mismatch"):
                oracle.query_java_status(server.port, "1.21.11")

    def test_invalid_player_counts_refused(self):
        with FakeServer(status_frame(online=11, maximum=10)) as server:
            with self.assertRaisesRegex(oracle.OracleFailure, "counter bounds"):
                oracle.query_java_status(server.port, "1.21.11")

    def test_malformed_packet_refused(self):
        with FakeServer(oracle.framed(b"\x01\x01{}")) as server:
            with self.assertRaises(oracle.OracleFailure):
                oracle.query_java_status(server.port, "1.21.11")

    def test_truncated_packet_refused(self):
        with FakeServer(b"\x0b\x00") as server:
            with self.assertRaises(oracle.OracleFailure):
                oracle.query_java_status(server.port, "1.21.11")

    def test_oversized_frame_refused(self):
        with FakeServer(oracle.encode_varint(oracle.MAX_PACKET + 1)) as server:
            with self.assertRaisesRegex(oracle.OracleFailure, "frame length"):
                oracle.query_java_status(server.port, "1.21.11")

    def test_bounds_refused_before_io(self):
        for port, version, timeout in ((0, "1.21.11", 2), (25565, "", 2), (25565, "x", 999)):
            with self.assertRaises(oracle.OracleFailure):
                oracle.query_java_status(port, version, timeout=timeout)


class _Reader:
    def __init__(self, content):
        self._content = content
    def recv(self, n):
        data, self._content = self._content[:n], self._content[n:]
        return data


if __name__ == "__main__":
    unittest.main()
